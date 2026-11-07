"""Depth-tested OpenGL 3.3 text rulers for the perspective grid only.

Text is generated into a small QImage atlas (Qt GUI/OpenGL thread) and drawn
as camera-facing pixel-size quads anchored in world-space grid coordinates.
The model's actual depth buffer, not a projected bounding rectangle, handles
occlusion. No model/plate geometry or export data is altered.
"""
from __future__ import annotations

from array import array
import ctypes
import math

from desktop.qt_app.preview_grid_measurements import format_millimeters, grid_ruler_ticks

VERTEX_SHADER = '''#version 330 core
layout(location=0) in vec3 anchorPosition;
layout(location=1) in vec2 pixelOffset;
layout(location=2) in vec2 texcoord;
uniform mat4 projectionView;
uniform vec2 viewportPixels;
out vec2 vUV;
void main() {
    vec4 clip = projectionView * vec4(anchorPosition, 1.0);
    // Make text camera-facing, at a fixed physical-pixel size, without
    // changing its world-space depth. Depth testing then hides it behind
    // actual rendered model triangles instead of a guessed bounding box.
    clip.xy += 2.0 * pixelOffset / viewportPixels * clip.w;
    gl_Position = clip;
    vUV = texcoord;
}
'''
FRAGMENT_SHADER = '''#version 330 core
in vec2 vUV;
uniform sampler2D textAtlas;
out vec4 fragColor;
void main() {
    vec4 texel = texture(textAtlas, vUV);
    if (texel.a < 0.02) discard;
    fragColor = texel;
}
'''


def ruler_anchors(step, limits, floor_z, *, max_per_axis=16):
    """Shared-origin X/Y distance rulers on the perspective grid only.

    The first visible *major* X and Y grid lines intersect at one grid-relative
    origin. There is exactly one neutral ``0`` label at that intersection.
    Positive X and Y distances are measured from the same position, never
    from the model/world origin or two independently chosen viewport edges.

    Axis identifiers: O is the shared origin, X/Y are numeric distances, and
    MX/MY are a single small colored direction marker near each positive end.
    All anchors live in world coordinates and remain fixed during camera orbit.
    """
    try:
        s = float(step)
        x0, x1, y0, y1 = (float(v) for v in limits)
        z = float(floor_z)
        if not all(map(math.isfinite, (s, x0, x1, y0, y1, z))):
            return ()
        if s <= 0 or x1 < x0 or y1 < y0:
            return ()
        limit = max(1, min(24, int(max_per_axis)))
        xticks = grid_ruler_ticks(x0, x1, s, limit=limit)
        yticks = grid_ruler_ticks(y0, y1, s, limit=limit)
        if not xticks or not yticks:
            return ()

        # A small lift avoids coplanar Z-fighting with the grid lines while
        # retaining the model-depth occlusion of the text quads.
        z += max(0.0001, 0.002 * s)
        ox, oy = float(xticks[0][0]), float(yticks[0][0])
        labels = [('O', '0', (ox, oy, z))]
        labels.extend(('X', format_millimeters(distance), (float(world), oy, z))
                      for world, distance in xticks[1:])
        labels.extend(('Y', format_millimeters(distance), (ox, float(world), z))
                      for world, distance in yticks[1:])

        # Show X and Y close to the *shared* 0 at the first major interval.
        # Keep true numeric 50/100/... mm ticks in their fixed world positions;
        # only the direction letters move. 40% leaves room for the 0 and the
        # first numeric label even when the camera foreshortens the grid.
        if len(xticks) > 1:
            first, next_ = float(xticks[0][0]), float(xticks[1][0])
            labels.append(('MX', 'X', (first + (next_ - first) * 0.4, oy, z)))
        if len(yticks) > 1:
            first, next_ = float(yticks[0][0]), float(yticks[1][0])
            labels.append(('MY', 'Y', (ox, first + (next_ - first) * 0.4, z)))
        return tuple(labels)
    except (TypeError, ValueError, OverflowError):
        return ()


def _next_power_of_two(value):
    return 1 << (max(1, int(value)) - 1).bit_length()


def quad_vertices(anchors, rectangles, viewport_dpr=1.0):
    """Create GPU vertex data; atlas rectangles are (u0,v0,u1,v1,w,h).

    Positions are pixel offsets from fixed world anchors, not free-floating
    Qt text labels. The atlas itself is rasterized once per geometry change.
    """
    if len(anchors) != len(rectangles):
        raise ValueError('Label/atlas rectangle mismatch')
    dpr = max(0.5, min(4.0, float(viewport_dpr)))
    data = array('f')
    for (axis, _label, anchor), (u0, v0, u1, v1, w, h) in zip(anchors, rectangles):
        # All rulers share the same world-space origin. The single 0 marker
        # sits just outside that corner; X labels sit below the positive-X
        # edge, and Y labels to the left of the positive-Y edge. The markers
        # MX/MY use their respective axis placement without repeating prefixes.
        if axis == 'O':
            cx, cy = -(w * 0.5 + 7.0 * dpr), -(h * 0.5 + 7.0 * dpr)
        elif axis in ('X', 'MX'):
            cx, cy = 0.0, -(h * 0.5 + 10.0 * dpr)
        elif axis in ('Y', 'MY'):
            cx, cy = -(w * 0.5 + 8.0 * dpr), 0.0
        else:
            raise ValueError('Unknown ruler label role: ' + str(axis))
        x0, x1 = cx - w * 0.5, cx + w * 0.5
        y0, y1 = cy - h * 0.5, cy + h * 0.5
        # QImage first row (top of text) uploads to GL v=0. Use v0 on the
        # screen-top vertices to keep lettering upright without flipping bytes.
        corners = ((x0,y1,u0,v0), (x0,y0,u0,v1), (x1,y0,u1,v1),
                   (x0,y1,u0,v0), (x1,y0,u1,v1), (x1,y1,u1,v0))
        for px, py, u, v in corners:
            data.extend((*anchor, px, py, u, v))
    return data


class WorldGridRulerRenderer:
    """Tiny GL-owned text layer, only active for perspective measurements."""

    def __init__(self):
        self.program = self.vao = self.vbo = self.texture = 0
        self._key = None
        self._count = 0
        self._atlas_size = (0, 0)

    @staticmethod
    def _shader(gl, kind, source):
        shader = gl.glCreateShader(kind)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
            report = gl.glGetShaderInfoLog(shader)
            gl.glDeleteShader(shader)
            raise RuntimeError('Grid ruler shader: ' + str(report))
        return shader

    def _initialize(self, gl):
        vert = self._shader(gl, gl.GL_VERTEX_SHADER, VERTEX_SHADER)
        try:
            frag = self._shader(gl, gl.GL_FRAGMENT_SHADER, FRAGMENT_SHADER)
        except Exception:
            gl.glDeleteShader(vert)
            raise
        try:
            program = gl.glCreateProgram()
            gl.glAttachShader(program, vert)
            gl.glAttachShader(program, frag)
            gl.glLinkProgram(program)
            if not gl.glGetProgramiv(program, gl.GL_LINK_STATUS):
                report = gl.glGetProgramInfoLog(program)
                gl.glDeleteProgram(program)
                raise RuntimeError('Grid ruler link: ' + str(report))
            self.program = program
            self.vao = gl.glGenVertexArrays(1)
            self.vbo = gl.glGenBuffers(1)
        finally:
            gl.glDeleteShader(vert)
            gl.glDeleteShader(frag)

    @staticmethod
    def _raster_atlas(anchors, dpr):
        """Create only local QImage/QPainter data, never a QPixmap or font file."""
        from PySide6.QtCore import Qt, QRect
        from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
        font = QFont('Consolas')
        font.setPixelSize(max(11, int(round(14 * dpr))))
        metrics = QFontMetrics(font)
        padding = max(3, int(round(4 * dpr)))
        col_width = max(metrics.horizontalAdvance(label) for _, label, _ in anchors) + 2 * padding
        row_height = metrics.height() + 2 * padding
        columns = min(4, len(anchors))
        rows = math.ceil(len(anchors) / columns)
        tw = _next_power_of_two(col_width * columns)
        th = _next_power_of_two(row_height * rows)
        if tw > 2048 or th > 2048:
            raise ValueError('Grid ruler atlas exceeds 2048px limit')
        img = QImage(tw, th, QImage.Format.Format_RGBA8888)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.setFont(font)
            rectangles = []
            for i, (axis, label, _xyz) in enumerate(anchors):
                x = (i % columns) * col_width
                y = (i // columns) * row_height
                # The origin is neutral; both numeric rulers and the short
                # endpoint markers inherit the axis's red/green tint.
                tint = ('#d9e8ee' if axis == 'O' else
                        '#ef999d' if axis in ('X', 'MX') else '#8cdcad')
                p.setPen(QColor(tint))
                p.drawText(QRect(x, y, col_width, row_height),
                           Qt.AlignmentFlag.AlignCenter, label)
                rectangles.append((x/tw, y/th, (x+col_width)/tw,
                                   (y+row_height)/th, col_width, row_height))
        finally:
            p.end()
        return img, tuple(rectangles)

    def _upload(self, gl, step, limits, floor_z, dpr):
        anchors = ruler_anchors(step, limits, floor_z)
        if not anchors:
            self._count = 0
            return
        image, rectangles = self._raster_atlas(anchors, dpr)
        data = quad_vertices(anchors, rectangles, dpr)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.vbo)
        gl.glBufferData(gl.GL_ARRAY_BUFFER, len(data)*4, data.tobytes(), gl.GL_STATIC_DRAW)
        for index, size, offset in ((0, 3, 0), (1, 2, 12), (2, 2, 20)):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(index, size, gl.GL_FLOAT, gl.GL_FALSE,
                                     28, ctypes.c_void_p(offset))
        gl.glBindVertexArray(0)
        if self.texture:
            gl.glDeleteTextures([self.texture])
            self.texture = 0
        self.texture = gl.glGenTextures(1)
        gl.glActiveTexture(gl.GL_TEXTURE2)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA8,
                        image.width(), image.height(), 0, gl.GL_RGBA,
                        gl.GL_UNSIGNED_BYTE, bytes(image.constBits()))
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        self._count = len(data) // 7
        self._atlas_size = (image.width(), image.height())

    def draw(self, gl, mvp, step, limits, floor_z, *, viewport_pixels, dpr=1.0):
        """Call AFTER model + world grid, with their depth buffer intact."""
        if step is None or limits is None:
            return
        if len(viewport_pixels) != 2 or min(viewport_pixels) <= 0:
            return
        dpr = max(0.5, min(4.0, float(dpr)))
        key = (float(step), tuple(float(v) for v in limits), float(floor_z), dpr)
        if not self.program:
            self._initialize(gl)
        if key != self._key:
            self._upload(gl, *key[:3], dpr)
            self._key = key
        if not self._count:
            return
        blend = bool(gl.glIsEnabled(gl.GL_BLEND))
        depth = bool(gl.glIsEnabled(gl.GL_DEPTH_TEST))
        depth_write = bool(gl.glGetBooleanv(gl.GL_DEPTH_WRITEMASK))
        try:
            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glDepthMask(gl.GL_FALSE)
            gl.glUseProgram(self.program)
            gl.glUniformMatrix4fv(gl.glGetUniformLocation(self.program, 'projectionView'),
                                  1, gl.GL_TRUE, array('f', mvp.copyDataTo()).tobytes())
            gl.glUniform2f(gl.glGetUniformLocation(self.program, 'viewportPixels'),
                           float(viewport_pixels[0]), float(viewport_pixels[1]))
            gl.glActiveTexture(gl.GL_TEXTURE2)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
            gl.glUniform1i(gl.glGetUniformLocation(self.program, 'textAtlas'), 2)
            gl.glBindVertexArray(self.vao)
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, self._count)
        finally:
            gl.glBindVertexArray(0)
            gl.glActiveTexture(gl.GL_TEXTURE2)
            gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
            gl.glActiveTexture(gl.GL_TEXTURE0)
            gl.glUseProgram(0)
            gl.glDepthMask(gl.GL_TRUE if depth_write else gl.GL_FALSE)
            if not depth:
                gl.glDisable(gl.GL_DEPTH_TEST)
            if not blend:
                gl.glDisable(gl.GL_BLEND)

    def release(self, gl):
        if self.texture:
            gl.glDeleteTextures([self.texture]); self.texture = 0
        if self.vbo:
            gl.glDeleteBuffers(1, [self.vbo]); self.vbo = 0
        if self.vao:
            gl.glDeleteVertexArrays(1, [self.vao]); self.vao = 0
        if self.program:
            gl.glDeleteProgram(self.program); self.program = 0
        self._key = None
        self._count = 0
        self._atlas_size = (0, 0)
