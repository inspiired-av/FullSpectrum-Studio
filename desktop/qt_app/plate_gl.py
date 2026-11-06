"""OpenGL-only, separately owned build-plate renderer. No model shader changes.

Shader compiles lazily inside the viewport's current GL 3.3 context. Vendor bed
STLs are supplied by PlateMesh; vendor logos/textures are read from installed
slicer resources and are not packaged or re-exported.
"""
from __future__ import annotations

from array import array
import ctypes
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

VERTEX_SHADER = '''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec3 normal;
layout(location=2) in vec2 uv;
uniform mat4 projectionView;
uniform vec3 plateOffset;
out vec3 vNormal;
out vec2 vUV;
void main() {
    gl_Position = projectionView * vec4(position + plateOffset, 1.0);
    vNormal = normal;
    vUV = uv;
}
'''
FRAGMENT_SHADER = '''#version 330 core
in vec3 vNormal;
in vec2 vUV;
uniform sampler2D surfaceArt;
uniform int hasArt;
out vec4 fragColor;
void main() {
    float shade = 0.68 + 0.24 * abs(dot(normalize(vNormal), normalize(vec3(.33, -.4, .85))));
    vec3 base = vec3(.19, .20, .23);
    if (hasArt != 0) {
        vec4 art = texture(surfaceArt, vUV);
        base = mix(base, art.rgb, art.a * .90);
    }
    fragColor = vec4(base * shade, 1.0);
}
'''


def _raster_texture(path):
    """Raster installed SVG or bitmap to a bounded RGBA image (Qt-owned data)."""
    if path is None:
        return None
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 16_000_000:
        return None
    image = None
    if path.suffix.casefold() == '.svg':
        try:
            from PySide6.QtSvg import QSvgRenderer
            renderer = QSvgRenderer(str(path))
            if not renderer.isValid():
                return None
            natural = renderer.defaultSize()
            width = natural.width() if natural.width() > 0 else 1024
            height = natural.height() if natural.height() > 0 else 1024
            ratio = min(1., 2048./max(width, height))
            width, height = max(1, int(width*ratio)), max(1, int(height*ratio))
            image = QImage(width, height, QImage.Format.Format_RGBA8888)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
        except (ImportError, RuntimeError):
            return None
    else:
        reader = QImageReader(str(path))
        reader.setAutoTransform(False)
        initial = reader.size()
        if initial.isValid() and max(initial.width(), initial.height()) > 2048:
            factor = 2048/max(initial.width(), initial.height())
            from PySide6.QtCore import QSize
            reader.setScaledSize(QSize(max(1, int(initial.width()*factor)),
                                       max(1, int(initial.height()*factor))))
        image = reader.read()
    if image is None or image.isNull() or image.width() > 2048 or image.height() > 2048:
        return None
    return image.convertToFormat(QImage.Format.Format_RGBA8888)


class PlateGpuRenderer:
    def __init__(self):
        self.mesh = None
        self.texture_path = None
        self.program = self.vao = self.vbo = self.texture = 0
        self.dirty = True
        self._bound_context = None

    def set_plate(self, mesh, texture=None):
        self.mesh = mesh
        self.texture_path = Path(texture) if texture else None
        self.dirty = True

    def _create_shader(self, gl, stage, source):
        shader = gl.glCreateShader(stage)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
            raise RuntimeError('Build plate shader: ' + str(gl.glGetShaderInfoLog(shader)))
        return shader

    def _initialize(self, gl):
        vertex = self._create_shader(gl, gl.GL_VERTEX_SHADER, VERTEX_SHADER)
        fragment = self._create_shader(gl, gl.GL_FRAGMENT_SHADER, FRAGMENT_SHADER)
        try:
            self.program = gl.glCreateProgram()
            gl.glAttachShader(self.program, vertex)
            gl.glAttachShader(self.program, fragment)
            gl.glLinkProgram(self.program)
            if not gl.glGetProgramiv(self.program, gl.GL_LINK_STATUS):
                raise RuntimeError('Build plate program: ' + str(gl.glGetProgramInfoLog(self.program)))
        finally:
            gl.glDeleteShader(vertex)
            gl.glDeleteShader(fragment)
        self.vao = gl.glGenVertexArrays(1)
        self.vbo = gl.glGenBuffers(1)

    def _upload(self, gl):
        if self.mesh is None:
            return
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        data = self.mesh.vertices.tobytes()
        gl.glBufferData(gl.GL_ARRAY_BUFFER, len(data), data, gl.GL_STATIC_DRAW)
        stride = 32
        for index, length, offset in ((0, 3, 0), (1, 3, 12), (2, 2, 24)):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(index, length, gl.GL_FLOAT, gl.GL_FALSE,
                                     stride, ctypes.c_void_p(offset))
        gl.glBindVertexArray(0)
        if self.texture:
            gl.glDeleteTextures([self.texture]); self.texture = 0
        image = _raster_texture(self.texture_path)
        if image is not None:
            self.texture = gl.glGenTextures(1)
            gl.glActiveTexture(gl.GL_TEXTURE1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            # QImage lives until upload finishes. This is neither a QPixmap nor a GL context in a thread.
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA8,
                            image.width(), image.height(), 0, gl.GL_RGBA,
                            gl.GL_UNSIGNED_BYTE, bytes(image.constBits()))
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        self.dirty = False

    def draw(self, gl, mvp, offset):
        if self.mesh is None:
            return
        if not self.program:
            self._initialize(gl)
        if self.dirty:
            self._upload(gl)
        gl.glUseProgram(self.program)
        gl.glUniformMatrix4fv(gl.glGetUniformLocation(self.program, 'projectionView'),
                              1, gl.GL_TRUE, array('f', mvp.copyDataTo()).tobytes())
        gl.glUniform3f(gl.glGetUniformLocation(self.program, 'plateOffset'), *offset)
        gl.glUniform1i(gl.glGetUniformLocation(self.program, 'hasArt'), int(bool(self.texture)))
        if self.texture:
            gl.glActiveTexture(gl.GL_TEXTURE1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, 'surfaceArt'), 1)
        gl.glBindVertexArray(self.vao)
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, self.mesh.faces * 3)
        gl.glBindVertexArray(0)
        gl.glUseProgram(0)
        # Keep GL texture state predictable for forecast influence sampling.
        if self.texture:
            gl.glActiveTexture(gl.GL_TEXTURE1)
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
            gl.glActiveTexture(gl.GL_TEXTURE0)

    def release(self, gl):
        if self.texture:
            gl.glDeleteTextures([self.texture]); self.texture = 0
        if self.vbo:
            gl.glDeleteBuffers(1, [self.vbo]); self.vbo = 0
        if self.vao:
            gl.glDeleteVertexArrays(1, [self.vao]); self.vao = 0
        if self.program:
            gl.glDeleteProgram(self.program); self.program = 0
        self.dirty = True
