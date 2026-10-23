"""Stage 3B OpenGL 3D viewport: original source colors and smoothed geometry.

Uses a 3.3 Core shader; source data is handed in by the UI-thread completion
handler only. OpenGL is optional until a model is actually displayed.
"""
from __future__ import annotations

from array import array
from desktop.qt_app.preview_shading import flatten_faces as _flatten_faces
from desktop.qt_app.preview_stage6a import classify_model_drop
import ctypes
import math

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
        self._gl=None;self._program=0;self._vao=0;self._vbo=0;self._error=''
        self._influence_data=None;self._influence_texture=0;self._influence_dirty=False
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

    @property
    def mesh(self):return self._mesh

    def set_mesh(self,mesh,*,preserve_camera=False):
        self._mesh=mesh
        # Prefer geometry prepared by ModelLoadWorker so the UI remains responsive.
        self._data=(getattr(mesh, 'render_buffer', None) or _flatten_faces(mesh)) if mesh else None
        self._verts=len(self._data)//12 if self._data is not None else 0
        self._dirty=True
        if preserve_camera:
            self.update()
        else:
            self.reset_camera()

    def clear_mesh(self):
        self.set_mesh(None)
        self.set_highlights(None, ())

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
            self._radius=max(math.dist((x0,y0,z0),(x1,y1,z1))/2,0.01)
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
        data=self._data.tobytes() if self._data is not None else b''
        gl.glBufferData(gl.GL_ARRAY_BUFFER,len(data),data,gl.GL_STATIC_DRAW)
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
        if self._error or not self._mesh or not self._verts:return
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
                if self._influence_texture:
                    self._gl.glDeleteTextures([self._influence_texture]);self._influence_texture=0
                if self._vbo:self._gl.glDeleteBuffers(1,[self._vbo]);self._vbo=0
                if self._vao:self._gl.glDeleteVertexArrays(1,[self._vao]);self._vao=0
                if self._program:self._gl.glDeleteProgram(self._program);self._program=0
            finally:self.doneCurrent()
        super().closeEvent(event)
