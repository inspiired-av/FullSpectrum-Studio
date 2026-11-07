"""Stage 3B OpenGL 3D viewport: original source colors and smoothed geometry.

Uses a 3.3 Core shader; source data is handed in by the UI-thread completion
handler only. OpenGL is optional until a model is actually displayed.
"""
from __future__ import annotations

from array import array
from desktop.qt_app.preview_shading import flatten_faces as _flatten_faces
from desktop.qt_app.preview_stage6a import classify_model_drop
from desktop.qt_app.plate_gl import PlateGpuRenderer
from desktop.qt_app.preview_grid_gl import WorldGridRenderer
from desktop.qt_app.preview_grid_camera import (
    world_grid_footprint, expand_clip_for_grid, scene_grid_bounds, fit_grid_zoom,
)
from desktop.qt_app.preview_grid_ruler_gl import WorldGridRulerRenderer
from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
from desktop.qt_app.preview_axis_indicator import ViewAxisIndicator
from desktop.qt_app.preview_grid_policy import choose_grid_layers
from desktop.qt_app.preview_performance import (
    require_upload_budget, preview_performance_snapshot)
from time import perf_counter
from desktop.qt_app.plate_mesh import combined_scene_bounds
from desktop.qt_app.plate_mesh import plate_offset, scene_clip_planes
import ctypes
import math
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMatrix4x4, QVector3D, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget


VERTEX_SHADER = '''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec3 color;
layout(location=3) in vec3 exactFaceTag;
uniform mat4 projectionView;
out vec3 worldNormal;
out vec3 faceColor;
flat out vec3 sourceTag;
void main() {
    gl_Position = projectionView * vec4(position, 1.0);
    worldNormal = normal;
    faceColor = color;
    sourceTag = exactFaceTag;
}
'''
FRAGMENT_SHADER = '''#version 330 core
in vec3 worldNormal;
in vec3 faceColor;
flat in vec3 sourceTag;
uniform vec3 selectedSourceColor;
uniform int selectedExtraCount;
uniform vec3 selectedExtraColors[64];
uniform int protectedCount;
uniform int showProtectedOverlay;
uniform vec3 protectedSourceColors[128];
// Optional Stage 4D-A lookup. For this mode sourceTag.x is the SOURCE slot,
// not a display RGB tag. Source slot 0 is reserved for missing metadata.
uniform int influenceMode;  // 0=normal, 1=physical, 2=categorical, 3=contribution
uniform int influenceSelectedSlot;
uniform int influenceAnchorCount;
uniform sampler2D influenceWeights;
uniform vec3 influencePhysicalColors[8];
uniform vec3 influenceCategoricalColors[8];
out vec4 fragColor;
void main() {
    vec3 n = normalize(worldNormal);
    // Soft studio light with a fill contribution. No harsh per-triangle dark banding.
    vec3 keyLight = normalize(vec3(0.44, -0.32, 0.83));
    vec3 fillLight = normalize(vec3(-0.64, 0.57, 0.48));
    float key = abs(dot(n, keyLight));
    float fill = abs(dot(n, fillLight));
    float shade = 0.54 + 0.34 * key + 0.12 * fill;
    vec3 surface = faceColor * shade;
    if (influenceMode != 0) {
        int sourceSlot = int(sourceTag.r + 0.5);
        if (sourceSlot > 0) {
            int dominant = int(texelFetch(influenceWeights, ivec2(0, sourceSlot), 0).g + 0.5);
            if (influenceSelectedSlot > 0 && influenceSelectedSlot <= influenceAnchorCount) {
                float share = clamp(texelFetch(influenceWeights,
                    ivec2(influenceSelectedSlot - 1, sourceSlot), 0).r, 0.0, 1.0);
                // Dark means not present; brighter cyan means a larger recipe share.
                surface = mix(vec3(0.11, 0.16, 0.22), vec3(0.19, 0.87, 0.96), share) * shade;
            } else if (dominant >= 1 && dominant <= influenceAnchorCount) {
                vec3 display = (influenceMode == 2)
                    ? influenceCategoricalColors[dominant - 1]
                    : influencePhysicalColors[dominant - 1];
                surface = display * shade;
            }
        }
        fragColor = vec4(surface, 1.0);
        return;
    }
    bool isSelected = selectedSourceColor.r >= 0.0 && distance(sourceTag, selectedSourceColor) < 0.0025;
    if (!isSelected) {
        for (int i = 0; i < selectedExtraCount; ++i) {
            if (distance(sourceTag, selectedExtraColors[i]) < 0.0025) {
                isSelected = true;
                break;
            }
        }
    }
    if (isSelected) {
        surface = mix(surface, vec3(1.0, 0.76, 0.20), 0.67);
    } else if (showProtectedOverlay != 0) {
        for (int i = 0; i < protectedCount; ++i) {
            if (distance(sourceTag, protectedSourceColors[i]) < 0.0025) {
                surface = mix(surface, vec3(0.20, 0.95, 0.80), 0.55);
                break;
            }
        }
    }
    fragColor = vec4(surface, 1.0);
}
'''




def _upload_projection_view(gl, location, matrix):
    """Upload QMatrix4x4 correctly to OpenGL.

    QMatrix4x4.copyDataTo() returns ROW-major floats. OpenGL defaults to
    COLUMN-major input, so GL_TRUE is required to transpose on upload.
    GL_FALSE here destroys the perspective transform (thin wedge/clipping).
    Desktop OpenGL 3.3 Core supports this transpose flag.
    """
    gl.glUniformMatrix4fv(location, 1, gl.GL_TRUE,
                          array('f', matrix.copyDataTo()).tobytes())


def _camera_clip_planes(radius, distance):
    """Maintain depth-buffer precision while allowing a close-up orbit.

    Do not let near collapse to 0.001 as the camera approaches the mesh: a
    huge far/near ratio amplifies z-fighting on tightly spaced colored faces.
    This is purely a display-camera change, never a geometry modification.
    """
    r = max(float(radius), 0.001)
    d = max(float(distance), r * 0.00001)
    near = max(0.002 * r, 0.05 * d)
    far = max(near * 2.0, d + 1.5 * r)
    return near, far


class ModelViewport(QOpenGLWidget):
    render_error = Signal(str)
    background_clicked = Signal()
    model_file_dropped = Signal(str)
    drop_feedback = Signal(str)
    plate_render_error = Signal(str)
    grid_render_error = Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        fmt=QSurfaceFormat()
        fmt.setVersion(3,3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.setObjectName('modelViewport')
        self.setAcceptDrops(True)
        self._drop_enabled = True
        self.setMinimumHeight(270)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mesh=None;self._data=None;self._dirty=False;self._verts=0
        self._preview_upload_ms=None;self._preview_upload_bytes=0
        self._preview_upload_detail=None
        self._preview_upload_mode=os.environ.get(
            'FULLSPECTRUM_PREVIEW_UPLOAD', 'direct').strip().lower()
        if self._preview_upload_mode not in (
                'direct', 'split', 'raw-direct', 'raw-split'):
            self._preview_upload_mode='direct'
        self._preview_fallback_prepare_ms=None
        self._gl=None;self._program=0;self._vao=0;self._vbo=0;self._error=''
        self._influence_data=None;self._influence_texture=0;self._influence_dirty=False
        self._plate_renderer = PlateGpuRenderer()  # Own GL objects; never part of model buffers.
        self._world_grid = WorldGridRenderer()  # Independent resources; draw only when requested.
        self._world_ruler = WorldGridRulerRenderer()  # Depth-tested, perspective-only numeric labels.
        self._grid_ruler_failed = False
        self._grid_mode = 'automatic'
        self._grid_show_axes = True
        self._grid_show_measurements = True
        self._grid_failed = False
        self._influence_display='physical';self._influence_selected=0
        self._last=None;self._drag_button=None
        self._press_position=None
        self.wireframe=False
        self.selected_source_color=None
        self.selected_source_colors=()
        self.protected_source_colors=()
        self.show_protected_overlay=False
        self.yaw=-1.47;self.pitch=0.30;self.zoom=1.
        self.pan_x=0.;self.pan_y=0.
        self._center=(0.,0.,0.);self._radius=1.
        self.setToolTip('Left drag: orbit · Right drag or Shift+drag: pan · Wheel: zoom · R: reset view')
        self._axis_indicator = ViewAxisIndicator(self)
        self._grid_measurements = PerspectiveGridMeasurementOverlay(self)

    @property
    def mesh(self):return self._mesh

    def preview_performance_snapshot(self):
        """Return preview-only timings and memory estimates for UI diagnostics."""
        return preview_performance_snapshot(
            self._mesh, upload_submit_ms=self._preview_upload_ms,
            upload_bytes=self._preview_upload_bytes,
            fallback_prepare_ms=self._preview_fallback_prepare_ms,
            upload_detail=self._preview_upload_detail)

    def set_mesh(self,mesh,*,preserve_camera=False):
        self._mesh=mesh
        self._preview_upload_ms=None
        self._preview_upload_bytes=0
        self._preview_upload_detail=None
        self._preview_fallback_prepare_ms=None
        # Prefer geometry prepared by ModelLoadWorker so the UI remains responsive.
        prepare_start = perf_counter()
        self._data=(getattr(mesh, 'render_buffer', None) or _flatten_faces(mesh)) if mesh else None
        if mesh is not None and getattr(mesh, 'render_buffer', None) is None:
            self._preview_fallback_prepare_ms=(perf_counter()-prepare_start)*1000.0
        self._verts=len(self._data)//12 if self._data is not None else 0
        self._dirty=True
        self._axis_indicator.setVisible(mesh is not None and self._grid_show_axes)
        self._axis_indicator.refresh_obstacles()
        self._axis_indicator.update()
        if mesh is None:
            self._grid_measurements.clear_scene()
        if preserve_camera:
            self.update()
        else:
            self.reset_camera()

    def clear_mesh(self):
        self.set_mesh(None)
        self.set_highlights(None, ())

    def set_plate(self, plate_mesh, texture_path=None):
        """Swap visual plate assets without touching the model mesh, camera or exports."""
        self._plate_renderer.set_plate(plate_mesh, texture_path)
        _plate, show_world = choose_grid_layers(
            self._grid_mode, plate_visible=plate_mesh is not None,
            plate_has_art=bool(texture_path))
        if not show_world:
            self._grid_measurements.clear_scene()
        self.update()

    def set_grid_preferences(self, mode='automatic', show_axes=True,
                             show_measurements=True):
        """Display-only: grid and XYZ overlay never enter export/forecast data."""
        if mode not in ('automatic', 'plate', 'perspective', 'off'):
            raise ValueError('Unknown grid mode: ' + str(mode))
        self._grid_mode = mode
        self._grid_show_axes = bool(show_axes)
        self._grid_show_measurements = bool(show_measurements)
        self._grid_measurements.set_enabled(self._grid_show_measurements)
        _plate, show_world = choose_grid_layers(
            mode, plate_visible=self._plate_renderer.mesh is not None,
            plate_has_art=bool(self._plate_renderer.texture_path))
        if not show_world or not self._grid_show_measurements:
            self._grid_measurements.clear_scene()
        self._axis_indicator.setVisible(self._mesh is not None and self._grid_show_axes)
        self._axis_indicator.refresh_obstacles()
        self._axis_indicator.update()
        self.update()

    def fit_perspective_grid(self):
        """Explicitly frame the whole reference grid without changing the view angle.

        Unlike Reset Camera, this deliberately prioritizes the full grid extent.
        Zooming back in may crop the grid at screen edges, as expected.
        """
        plate = self._plate_renderer.mesh
        _plate_grid, world_grid = choose_grid_layers(
            self._grid_mode, plate_visible=plate is not None,
            plate_has_art=bool(self._plate_renderer.texture_path))
        if self._mesh is None or not world_grid:
            return False
        floor_z = self._mesh.bounds[2] - 0.75
        if plate is not None:
            floor_z = combined_scene_bounds(self._mesh.bounds, plate.bounds)[2] - 0.75
        x0, y0, z0, x1, y1, z1 = scene_grid_bounds(self._mesh.bounds, floor_z)
        self._center = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        self._radius = max(math.dist((x0,y0,z0), (x1,y1,z1)) / 2, 0.01)
        self.zoom = fit_grid_zoom(self.width(), self.height())
        self.pan_x = self.pan_y = 0.0
        self.update()
        return True

    def set_highlights(self, selected=None, protected=()):
        # Shader uniforms avoid rebuilding the entire mesh when colors change.
        if isinstance(selected, (tuple, list, set)):
            selected_colors = tuple(dict.fromkeys(str(v).upper() for v in selected if v))
        else:
            selected_colors = (str(selected).upper(),) if selected else ()
        self.selected_source_colors = selected_colors[:65]
        # Retain single-color property expected by existing Stage 3C UI tests.
        self.selected_source_color = self.selected_source_colors[-1] if selected_colors else None
        self.protected_source_colors=tuple(sorted({str(v).upper() for v in protected if v}))[:128]
        self.update()

    def set_protected_overlay(self, enabled):
        """Optional inspection tint; original material colors remain intact by default."""
        self.show_protected_overlay=bool(enabled)
        self.update()

    def set_influence_analysis(self, data, *, display='physical', selected=0):
        """Change analysis colors by shader uniforms; do not rebuild geometry."""
        if data is not self._influence_data:
            self._influence_data=data
            self._influence_dirty=True
        self._influence_display=display if display in ('physical','categorical') else 'physical'
        self._influence_selected=max(0,int(selected or 0))
        self.update()

    def _upload_influence_texture(self):
        gl=self._gl
        if self._influence_texture:
            gl.glDeleteTextures([self._influence_texture]);self._influence_texture=0
        self._influence_dirty=False
        if not self._influence_data:return
        data=self._influence_data
        count=int(data['sourceCount'])+1
        if count>int(gl.glGetIntegerv(gl.GL_MAX_TEXTURE_SIZE)):
            raise ValueError('Source color count exceeds the graphics driver texture limit')
        self._influence_texture=gl.glGenTextures(1)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D,self._influence_texture)
        gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_MIN_FILTER,gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_MAG_FILTER,gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_WRAP_S,gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D,gl.GL_TEXTURE_WRAP_T,gl.GL_CLAMP_TO_EDGE)
        gl.glTexImage2D(gl.GL_TEXTURE_2D,0,gl.GL_RGBA32F,8,count,0,
                        gl.GL_RGBA,gl.GL_FLOAT,data['weights'].tobytes())

    def reset_camera(self):
        self.yaw=-1.47;self.pitch=0.30;self.zoom=1.
        self.pan_x=0.;self.pan_y=0.
        if self._mesh:
            x0,y0,z0,x1,y1,z1=self._mesh.bounds
            self._center=((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)
            # Reset/Fit explicitly frames the *visual* plate too, if displayed.
            plate = self._plate_renderer.mesh
            if plate is not None:
                a,b,c,d,e,f = plate.bounds
                ox,oy,oz = plate_offset(self._mesh.bounds, plate.bounds)
                combined = (min(x0,a+ox),min(y0,b+oy),min(z0,c+oz),
                            max(x1,d+ox),max(y1,e+oy),max(z1,f+oz))
                x0,y0,z0,x1,y1,z1 = combined
                self._center=((x0+x1)/2,(y0+y1)/2,(z0+z1)/2)
            self._radius=max(math.dist((x0,y0,z0),(x1,y1,z1))/2,0.01)
        self._axis_indicator.update()
        self.update()

    def set_wireframe(self,enabled):
        self.wireframe=bool(enabled)
        self.update()

    def initializeGL(self):
        try:
            from OpenGL import GL as gl
            self._gl=gl
            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glEnable(gl.GL_MULTISAMPLE)  # Use the MSAA requested from Qt when supported.
            gl.glDepthFunc(gl.GL_LEQUAL)
            gl.glDisable(gl.GL_CULL_FACE)  # double-sided: source meshes may have varied winding
            vs=gl.glCreateShader(gl.GL_VERTEX_SHADER)
            gl.glShaderSource(vs,VERTEX_SHADER)
            gl.glCompileShader(vs)
            if not gl.glGetShaderiv(vs,gl.GL_COMPILE_STATUS):
                raise RuntimeError('Vertex shader: '+str(gl.glGetShaderInfoLog(vs)))
            fs=gl.glCreateShader(gl.GL_FRAGMENT_SHADER)
            gl.glShaderSource(fs,FRAGMENT_SHADER)
            gl.glCompileShader(fs)
            if not gl.glGetShaderiv(fs,gl.GL_COMPILE_STATUS):
                raise RuntimeError('Fragment shader: '+str(gl.glGetShaderInfoLog(fs)))
            program=gl.glCreateProgram()
            gl.glAttachShader(program,vs);gl.glAttachShader(program,fs)
            gl.glLinkProgram(program)
            gl.glDeleteShader(vs);gl.glDeleteShader(fs)
            if not gl.glGetProgramiv(program,gl.GL_LINK_STATUS):
                raise RuntimeError('Shader linking: '+str(gl.glGetProgramInfoLog(program)))
            self._program=program
            self._vao=gl.glGenVertexArrays(1)
            self._vbo=gl.glGenBuffers(1)
        except Exception as exc:
            self._error=f'OpenGL 3.3 renderer unavailable: {exc}'
            self.render_error.emit(self._error)

    def _upload(self):
        if not self._gl or not self._vao or not self._vbo:return
        gl=self._gl
        gl.glBindVertexArray(self._vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER,self._vbo)
        # Borrow the writable float32 array directly. The old tobytes()
        # path duplicated the entire expanded mesh in Python heap memory.
        count=len(self._data) if self._data is not None else 0
        size=count*self._data.itemsize if count else 0
        require_upload_budget(size)
        if count and self._data.itemsize != ctypes.sizeof(ctypes.c_float):
            raise ValueError("Preview render buffer must contain float32 values")
        # Pointer binding is timed separately from driver calls. No CPU
        # float32 copy is made here, and the array remains alive in self._data.
        pointer_start=perf_counter()
        pointer=(ctypes.c_float*count).from_buffer(self._data) if count else None
        pointer_ms=(perf_counter()-pointer_start)*1000.0
        mode=getattr(self, '_preview_upload_mode', 'direct')
        if mode not in ('direct', 'split', 'raw-direct', 'raw-split'):
            mode='direct'
        # Diagnostic only. The raw GL entrypoints skip PyOpenGL's
        # array FormatHandler/wrapper; they do not change byte layout.
        if mode.startswith('raw-'):
            from OpenGL.raw.GL.VERSION.GL_1_5 import (
                glBufferData as upload_data,
                glBufferSubData as upload_subdata)
            upload_pointer=(ctypes.cast(pointer, ctypes.c_void_p)
                            if pointer is not None else None)
        else:
            upload_data=gl.glBufferData
            # Direct uploads only require glBufferData. Defer looking up
            # glBufferSubData until a split transfer is actually selected.
            upload_subdata=gl.glBufferSubData if mode == 'split' else None
            upload_pointer=pointer
        upload_start=perf_counter()
        direct_ms=None
        allocation_ms=None
        transfer_ms=None
        if mode in ('split', 'raw-split'):
            # Opt-in diagnostic: allocate orphaned storage, then fill it.
            # Do not force glFinish/glGet* synchronization here.
            allocation_start=perf_counter()
            upload_data(gl.GL_ARRAY_BUFFER,size,None,gl.GL_STATIC_DRAW)
            allocation_ms=(perf_counter()-allocation_start)*1000.0
            if size:
                transfer_start=perf_counter()
                upload_subdata(gl.GL_ARRAY_BUFFER,0,size,upload_pointer)
                transfer_ms=(perf_counter()-transfer_start)*1000.0
        else:
            # Default uses the same one-call glBufferData wrapper.
            # The raw variant differs only in entrypoint/argument conversion.
            direct_start=perf_counter()
            upload_data(gl.GL_ARRAY_BUFFER,size,upload_pointer,gl.GL_STATIC_DRAW)
            direct_ms=(perf_counter()-direct_start)*1000.0
        self._preview_upload_ms=(perf_counter()-upload_start)*1000.0
        if mode.startswith('raw-'):
            # Raw entrypoints skip PyOpenGL's normal error wrapper.
            error=gl.glGetError()
            if error!=gl.GL_NO_ERROR:
                raise RuntimeError(f'Raw preview GPU upload GL error: 0x{error:04X}')
        self._preview_upload_bytes=size
        self._preview_upload_detail={
            'mode':mode, 'pointer_ms':pointer_ms, 'direct_ms':direct_ms,
            'allocation_ms':allocation_ms, 'transfer_ms':transfer_ms}
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0,3,gl.GL_FLOAT,gl.GL_FALSE,48,ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1,3,gl.GL_FLOAT,gl.GL_FALSE,48,ctypes.c_void_p(12))
        gl.glEnableVertexAttribArray(2)
        gl.glVertexAttribPointer(2,3,gl.GL_FLOAT,gl.GL_FALSE,48,ctypes.c_void_p(24))
        gl.glEnableVertexAttribArray(3)
        gl.glVertexAttribPointer(3,3,gl.GL_FLOAT,gl.GL_FALSE,48,ctypes.c_void_p(36))
        gl.glBindVertexArray(0)
        self._dirty=False

    def paintGL(self):
        if not self._gl:return
        gl=self._gl
        gl.glViewport(0,0,max(1,int(self.width()*self.devicePixelRatioF())),
                      max(1,int(self.height()*self.devicePixelRatioF())))
        gl.glClearColor(.059,.071,.086,1.)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT|gl.GL_DEPTH_BUFFER_BIT)
        # Hide releases old plate GPU objects on the next draw, not through a
        # synchronous makeCurrent() call that could flicker on HDR displays.
        if self._plate_renderer.mesh is None and self._plate_renderer.program:
            self._plate_renderer.release(gl)
        if self._error or not self._mesh or not self._verts:
            self._grid_measurements.clear_scene()
            return
        try:
            if self._dirty:self._upload()
            radius=self._radius
            eye_distance=radius*3.2/self.zoom
            center=QVector3D(*(self._center))
            cp,sp=math.cos(self.pitch),math.sin(self.pitch)
            co,so=math.cos(self.yaw),math.sin(self.yaw)
            direction=QVector3D(cp*co,cp*so,sp)
            right=QVector3D(-so,co,0.)
            up=QVector3D(-sp*co,-sp*so,cp)
            target=center+right*(self.pan_x*radius)+up*(self.pan_y*radius)
            eye=target+direction*eye_distance
            view=QMatrix4x4();view.lookAt(eye,target,QVector3D(0,0,1))
            projection=QMatrix4x4()
            near,far=_camera_clip_planes(radius,eye_distance)
            plate_mesh = self._plate_renderer.mesh
            if plate_mesh is not None and self._mesh is not None:
                near,far=scene_clip_planes(
                    (eye.x(),eye.y(),eye.z()), self._mesh.bounds,
                    plate_mesh.bounds, (near,far),
                    (target.x(),target.y(),target.z()))
            # The model/plate clip planes can truncate the *larger* world grid
            # even when its lines are inside the visible viewport. Include the
            # same four XY corners the grid renderer uses before projection.
            # Screen-edge clipping on an intentionally zoomed-in view remains normal.
            _grid_plate, _grid_world = choose_grid_layers(
                self._grid_mode, plate_visible=plate_mesh is not None,
                plate_has_art=bool(self._plate_renderer.texture_path))
            if _grid_world and not self._grid_failed:
                grid_floor = self._mesh.bounds[2] - 0.75
                if plate_mesh is not None:
                    grid_floor = combined_scene_bounds(
                        self._mesh.bounds, plate_mesh.bounds)[2] - 0.75
                grid_limits = world_grid_footprint(tuple(self._mesh.bounds))
                near, far = expand_clip_for_grid(
                    (eye.x(), eye.y(), eye.z()),
                    (target.x(), target.y(), target.z()),
                    (near, far), grid_limits, grid_floor)
            projection.perspective(45.,max(0.01,self.width()/max(1,self.height())), near,far)
            mvp=projection*view
            gl.glUseProgram(self._program)
            if self._influence_dirty:self._upload_influence_texture()
            analysis=self._influence_data
            enabled=bool(analysis and self._influence_texture and not self.wireframe)
            mode=(3 if self._influence_selected else
                  2 if self._influence_display=='categorical' else 1) if enabled else 0
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'influenceMode'),mode)
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'influenceSelectedSlot'),
                           self._influence_selected if enabled else 0)
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'influenceAnchorCount'),
                           len(analysis['anchors']) if enabled else 0)
            if enabled:
                gl.glActiveTexture(gl.GL_TEXTURE0)
                gl.glBindTexture(gl.GL_TEXTURE_2D,self._influence_texture)
                gl.glUniform1i(gl.glGetUniformLocation(self._program,'influenceWeights'),0)
                for idx,(physical,categorical) in enumerate(analysis['anchors']):
                    for uniform,color in (('influencePhysicalColors',physical),
                                          ('influenceCategoricalColors',categorical)):
                        gl.glUniform3f(gl.glGetUniformLocation(self._program,f'{uniform}[{idx}]'),
                                       *(int(color[j:j+2],16)/255.0 for j in (1,3,5)))
            location=gl.glGetUniformLocation(self._program,'projectionView')
            # Qt copyDataTo() is row-major; helper requests GL transpose.
            _upload_projection_view(gl, location, mvp)
            def to_rgb(value):
                return tuple(int(value[j:j+2],16)/255. for j in (1,3,5))
            location=gl.glGetUniformLocation(self._program,'selectedSourceColor')
            selected=self.selected_source_color
            gl.glUniform3f(location,*(to_rgb(selected) if selected and len(selected)==7 else (-1.,-1.,-1.)))
            other_selected=self.selected_source_colors[:-1]
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'selectedExtraCount'),len(other_selected))
            for i,color in enumerate(other_selected):
                gl.glUniform3f(gl.glGetUniformLocation(self._program,f'selectedExtraColors[{i}]'),*to_rgb(color))
            protected=self.protected_source_colors
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'protectedCount'),len(protected))
            gl.glUniform1i(gl.glGetUniformLocation(self._program,'showProtectedOverlay'),int(self.show_protected_overlay))
            for i,color in enumerate(protected):
                gl.glUniform3f(gl.glGetUniformLocation(self._program,f'protectedSourceColors[{i}]'),*to_rgb(color))
            gl.glBindVertexArray(self._vao)
            if self.wireframe:gl.glPolygonMode(gl.GL_FRONT_AND_BACK,gl.GL_LINE)
            gl.glDrawArrays(gl.GL_TRIANGLES,0,self._verts)
            if self.wireframe:gl.glPolygonMode(gl.GL_FRONT_AND_BACK,gl.GL_FILL)
            gl.glBindVertexArray(0);gl.glUseProgram(0)
            plate = self._plate_renderer.mesh
            show_plate_grid, show_world_grid = choose_grid_layers(
                self._grid_mode, plate_visible=plate is not None,
                plate_has_art=bool(self._plate_renderer.texture_path))
            self._plate_renderer.grid_enabled = show_plate_grid
            if plate is not None:
                try:
                    self._plate_renderer.draw(gl, mvp,
                        plate_offset(self._mesh.bounds, plate.bounds))
                except Exception as plate_exc:
                    # A bad vendor texture/GL resource must not poison model rendering.
                    self._plate_renderer.set_plate(None)
                    self.plate_render_error.emit(str(plate_exc))
            if show_world_grid and not self._grid_failed:
                try:
                    floor_z = self._mesh.bounds[2] - 0.75
                    if plate is not None:
                        floor_z = combined_scene_bounds(
                            self._mesh.bounds, plate.bounds)[2] - 0.75
                    self._world_grid.draw(gl, mvp, self._mesh.bounds, floor_z)
                    if self._grid_show_measurements:
                        self._grid_measurements.set_scene(
                            mvp, self._world_grid.grid_step,
                            self._world_grid.xy_limits, floor_z)
                        # Draw labels in the SAME depth-tested OpenGL scene as
                        # the model and reference grid; never via QWidget text.
                        # A broken glyph atlas must not disable the grid itself.
                        if not self._grid_ruler_failed:
                            try:
                                pixel_ratio = self.devicePixelRatioF()
                                self._world_ruler.draw(
                                    gl, mvp, self._world_grid.grid_step,
                                    self._world_grid.xy_limits, floor_z,
                                    viewport_pixels=(
                                        max(1, round(self.width() * pixel_ratio)),
                                        max(1, round(self.height() * pixel_ratio))),
                                    dpr=pixel_ratio)
                            except Exception as ruler_exc:
                                self._grid_ruler_failed = True
                                self.grid_render_error.emit(
                                    'Perspective ruler unavailable: ' + str(ruler_exc))
                    else:
                        self._grid_measurements.clear_scene()
                except Exception as grid_exc:
                    self._grid_measurements.clear_scene()
                    # A grid shader failure must not disable the model renderer.
                    self._grid_failed = True
                    self.grid_render_error.emit(str(grid_exc))
            else:
                self._grid_measurements.clear_scene()
        except Exception as exc:
            self._error='Unable to render model: '+str(exc)
            self.render_error.emit(self._error)

    def set_drop_enabled(self, enabled):
        """Prevent model replacement while a native export is in flight."""
        self._drop_enabled = bool(enabled)
        if not enabled:
            self.drop_feedback.emit('')

    def _classify_drag(self, event):
        mime = event.mimeData()
        if not mime.hasUrls():
            return None, 'Drop a local .3mf, .obj or .glb model.'
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None, 'Drop exactly one local model file.'
        return classify_model_drop((urls[0].toLocalFile(),))

    def dragEnterEvent(self, event):
        path, reason = self._classify_drag(event)
        if not self._drop_enabled:
            self.drop_feedback.emit('Export in progress — model changes are blocked.')
            event.ignore()
        elif path:
            self.drop_feedback.emit('Drop model to open')
            event.acceptProposedAction()
        else:
            self.drop_feedback.emit(reason)
            event.ignore()

    def dragMoveEvent(self, event):
        path, _ = self._classify_drag(event)
        if path and self._drop_enabled:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_feedback.emit('')
        event.accept()

    def dropEvent(self, event):
        path, reason = self._classify_drag(event)
        self.drop_feedback.emit('')
        if path and self._drop_enabled:
            event.acceptProposedAction()
            self.model_file_dropped.emit(path)
        else:
            if not self._drop_enabled:
                reason = 'Export in progress — model changes are blocked.'
            self.drop_feedback.emit(reason)
            event.ignore()

    def mousePressEvent(self,event):
        self._last=event.position();self._drag_button=event.button()
        self._press_position=event.position() if event.button()==Qt.MouseButton.LeftButton else None
        event.accept()

    def mouseMoveEvent(self,event):
        if self._last is None or self._mesh is None:return
        delta=event.position()-self._last;self._last=event.position()
        if self._drag_button==Qt.MouseButton.RightButton or event.modifiers()&Qt.KeyboardModifier.ShiftModifier:
            factor=2.4/max(1,self.zoom*min(self.width(),self.height()))
            self.pan_x-=delta.x()*factor
            self.pan_y+=delta.y()*factor
        else:
            self.yaw-=delta.x()*.008
            self.pitch=max(-1.50,min(1.50,self.pitch+delta.y()*.008))
        self._axis_indicator.update()
        self.update();event.accept()

    def mouseReleaseEvent(self,event):
        if (self._press_position is not None and
            event.button()==Qt.MouseButton.LeftButton and
            (event.position()-self._press_position).manhattanLength()<5):
            # A click away clears a swatch selection; an orbit drag does not.
            self.background_clicked.emit()
        self._press_position=None
        self._last=None;self._drag_button=None
        event.accept()

    def wheelEvent(self,event):
        if self._mesh is not None:
            step=event.angleDelta().y()/120
            self.zoom=max(.2,min(20.,self.zoom*math.pow(1.16,step)))
            self.update()
        event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_R:
            self.reset_camera();event.accept()
        else:super().keyPressEvent(event)

    def closeEvent(self,event):
        if self._gl and self.context() and self.context().isValid():
            self.makeCurrent()
            try:
                self._plate_renderer.release(self._gl)
                self._world_grid.release(self._gl)
                self._world_ruler.release(self._gl)
                if self._influence_texture:
                    self._gl.glDeleteTextures([self._influence_texture]);self._influence_texture=0
                if self._vbo:self._gl.glDeleteBuffers(1,[self._vbo]);self._vbo=0
                if self._vao:self._gl.glDeleteVertexArrays(1,[self._vao]);self._vao=0
                if self._program:self._gl.glDeleteProgram(self._program);self._program=0
            finally:self.doneCurrent()
        super().closeEvent(event)
