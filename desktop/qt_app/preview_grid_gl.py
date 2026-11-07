"""OpenGL 3.3 Core renderer for an optional world-space perspective grid.

Independent VAO/VBO/program: never touches model/plate buffers or exports.
"""
from __future__ import annotations

from array import array
import ctypes

from desktop.qt_app.preview_grid_geometry import world_grid_vertices
from desktop.qt_app.preview_grid_measurements import grid_xy_limits

_VERTEX = '''#version 330 core
layout(location=0) in vec3 position;
layout(location=1) in vec4 tint;
uniform mat4 projectionView;
out vec4 vTint;
void main() {
    gl_Position = projectionView * vec4(position, 1.0);
    vTint = tint;
}
'''
_FRAGMENT = '''#version 330 core
in vec4 vTint;
out vec4 fragColor;
void main() { fragColor = vTint; }
'''


class WorldGridRenderer:
    """Small, bounded GL_LINES draw; only constructs buffers on the GL thread."""

    def __init__(self):
        self.program = self.vao = self.vbo = 0
        self._key = None
        self._count = 0
        self.grid_step = None
        self.xy_limits = None

    @staticmethod
    def _shader(gl, kind, source):
        shader = gl.glCreateShader(kind)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
            report = gl.glGetShaderInfoLog(shader)
            gl.glDeleteShader(shader)
            raise RuntimeError('World grid shader: ' + str(report))
        return shader

    def _initialize(self, gl):
        vertex = self._shader(gl, gl.GL_VERTEX_SHADER, _VERTEX)
        try:
            fragment = self._shader(gl, gl.GL_FRAGMENT_SHADER, _FRAGMENT)
        except Exception:
            gl.glDeleteShader(vertex)
            raise
        try:
            program = gl.glCreateProgram()
            gl.glAttachShader(program, vertex)
            gl.glAttachShader(program, fragment)
            gl.glLinkProgram(program)
            if not gl.glGetProgramiv(program, gl.GL_LINK_STATUS):
                report = gl.glGetProgramInfoLog(program)
                gl.glDeleteProgram(program)
                raise RuntimeError('World grid link: ' + str(report))
            self.program = program
            self.vao = gl.glGenVertexArrays(1)
            self.vbo = gl.glGenBuffers(1)
        finally:
            gl.glDeleteShader(vertex)
            gl.glDeleteShader(fragment)

    def draw(self, gl, matrix, bounds, floor_z):
        if not self.program:
            self._initialize(gl)
        # Key only changes when visible bounds/plate placement changes. A camera
        # orbit reuses GPU geometry and updates only the projection matrix.
        key = (tuple(bounds), float(floor_z))
        if key != self._key:
            data, step = world_grid_vertices(bounds, floor_z)
            # Metadata comes from the identical vertices and spacing uploaded
            # to the GPU, never from an independent approximation.
            self.grid_step = float(step)
            self.xy_limits = grid_xy_limits(data)
            self._count = len(data) // 7
            gl.glBindVertexArray(self.vao)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, len(data) * 4, data.tobytes(), gl.GL_STATIC_DRAW)
            for index, width, offset in ((0, 3, 0), (1, 4, 12)):
                gl.glEnableVertexAttribArray(index)
                gl.glVertexAttribPointer(index, width, gl.GL_FLOAT, gl.GL_FALSE, 28,
                                         ctypes.c_void_p(offset))
            gl.glBindVertexArray(0)
            self._key = key
        blend_was_enabled = bool(gl.glIsEnabled(gl.GL_BLEND))
        depth_was_writable = bool(gl.glGetBooleanv(gl.GL_DEPTH_WRITEMASK))
        try:
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glDepthMask(gl.GL_FALSE)
            gl.glUseProgram(self.program)
            gl.glUniformMatrix4fv(gl.glGetUniformLocation(self.program, 'projectionView'),
                                  1, gl.GL_TRUE, array('f', matrix.copyDataTo()).tobytes())
            gl.glBindVertexArray(self.vao)
            gl.glDrawArrays(gl.GL_LINES, 0, self._count)
        finally:
            gl.glBindVertexArray(0)
            gl.glUseProgram(0)
            gl.glDepthMask(gl.GL_TRUE if depth_was_writable else gl.GL_FALSE)
            if not blend_was_enabled:
                gl.glDisable(gl.GL_BLEND)

    def release(self, gl):
        if self.vbo:
            gl.glDeleteBuffers(1, [self.vbo]); self.vbo = 0
        if self.vao:
            gl.glDeleteVertexArrays(1, [self.vao]); self.vao = 0
        if self.program:
            gl.glDeleteProgram(self.program); self.program = 0
        self._key = None
        self._count = 0
        self.grid_step = None
        self.xy_limits = None
