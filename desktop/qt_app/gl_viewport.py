"""Stage 3B OpenGL 3D viewport: original source colors and smoothed geometry.

Uses a 3.3 Core shader; source data is handed in by the UI-thread completion
handler only. OpenGL is optional until a model is actually displayed.
"""
from __future__ import annotations

from array import array
from desktop.qt_app.preview_shading import flatten_faces as _flatten_faces
import ctypes
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMatrix4x4, QVector3D, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget


VERTEX_SHADER = '''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec3 color;
uniform mat4 projectionView;
out vec3 worldNormal;
out vec3 faceColor;
void main() {
    gl_Position = projectionView * vec4(position, 1.0);
    worldNormal = normal;
    faceColor = color;
}
'''
FRAGMENT_SHADER = '''#version 330 core
in vec3 worldNormal;
in vec3 faceColor;
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


class ModelViewport(QOpenGLWidget):
    render_error = Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        fmt=QSurfaceFormat()
        fmt.setVersion(3,3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.setObjectName('modelViewport')
        self.setMinimumHeight(270)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._mesh=None;self._data=None;self._dirty=False;self._verts=0
        self._gl=None;self._program=0;self._vao=0;self._vbo=0;self._error=''
        self._last=None;self._drag_button=None
        self.wireframe=False
        self.yaw=-1.47;self.pitch=0.30;self.zoom=1.
        self.pan_x=0.;self.pan_y=0.
        self._center=(0.,0.,0.);self._radius=1.
        self.setToolTip('Left drag: orbit · Right drag or Shift+drag: pan · Wheel: zoom · R: reset view')

    @property
    def mesh(self):return self._mesh

    def set_mesh(self,mesh):
        self._mesh=mesh
        # Prefer geometry prepared by ModelLoadWorker so the UI remains responsive.
        self._data=(getattr(mesh, 'render_buffer', None) or _flatten_faces(mesh)) if mesh else None
        self._verts=len(self._data)//9 if self._data is not None else 0
        self._dirty=True
        self.reset_camera()

    def clear_mesh(self):
        self.set_mesh(None)

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
        gl.glVertexAttribPointer(0,3,gl.GL_FLOAT,gl.GL_FALSE,36,ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1,3,gl.GL_FLOAT,gl.GL_FALSE,36,ctypes.c_void_p(12))
        gl.glEnableVertexAttribArray(2)
        gl.glVertexAttribPointer(2,3,gl.GL_FLOAT,gl.GL_FALSE,36,ctypes.c_void_p(24))
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
            projection.perspective(45.,max(0.01,self.width()/max(1,self.height())),
                                   max(0.001,eye_distance-radius*2.1),eye_distance+radius*3.0)
            mvp=projection*view
            gl.glUseProgram(self._program)
            location=gl.glGetUniformLocation(self._program,'projectionView')
            # Qt copyDataTo() is row-major; helper requests GL transpose.
            _upload_projection_view(gl, location, mvp)
            gl.glBindVertexArray(self._vao)
            if self.wireframe:gl.glPolygonMode(gl.GL_FRONT_AND_BACK,gl.GL_LINE)
            gl.glDrawArrays(gl.GL_TRIANGLES,0,self._verts)
            if self.wireframe:gl.glPolygonMode(gl.GL_FRONT_AND_BACK,gl.GL_FILL)
            gl.glBindVertexArray(0);gl.glUseProgram(0)
        except Exception as exc:
            self._error='Unable to render model: '+str(exc)
            self.render_error.emit(self._error)

    def mousePressEvent(self,event):
        self._last=event.position();self._drag_button=event.button()
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
                if self._vbo:self._gl.glDeleteBuffers(1,[self._vbo]);self._vbo=0
                if self._vao:self._gl.glDeleteVertexArrays(1,[self._vao]);self._vao=0
                if self._program:self._gl.glDeleteProgram(self._program);self._program=0
            finally:self.doneCurrent()
        super().closeEvent(event)
