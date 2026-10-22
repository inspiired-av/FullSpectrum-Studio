"""Stage 3A projection matrix upload regression (runs without PySide6/OpenGL)."""
from __future__ import annotations

from array import array
import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'desktop/qt_app/gl_viewport.py'


def upload_function():
    """Extract pure-GL upload helper without importing GUI-only dependencies."""
    parsed = ast.parse(SOURCE.read_text(encoding='utf-8'))
    helper = next(node for node in parsed.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_upload_projection_view')
    namespace = {'array': array}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['_upload_projection_view']


class FakeMatrix:
    def __init__(self, elements):
        self.elements = elements

    def copyDataTo(self):
        # Qt's documented row-major representation.
        return self.elements


class FakeGL:
    GL_FALSE = 0
    GL_TRUE = 1

    def __init__(self):
        self.received = None

    def glUniformMatrix4fv(self, location, count, transpose, data):
        self.received = location, count, transpose, tuple(array('f', data))


class MatrixUploadTests(unittest.TestCase):
    def test_uploaded_matrix_is_transposed_for_opengl(self):
        gl = FakeGL()
        row_major = [1, 0, 0, 12,
                     0, 1, 0, -7,
                     0, 0, 1, 4,
                     0, 0, 0, 1]
        upload_function()(gl, 3, FakeMatrix(row_major))
        location, count, transpose, values = gl.received
        self.assertEqual((location, count), (3, 1))
        self.assertEqual(transpose, gl.GL_TRUE)
        self.assertEqual(values, tuple(row_major))
        # With GL_TRUE Qt's row-major translation ends up at OpenGL's
        # column-major slots 12-14 instead of corrupting the w-coordinate.
        stored = [values[row * 4 + col] for col in range(4) for row in range(4)]
        self.assertEqual(stored[12:15], [12, -7, 4])
        self.assertEqual(stored[3:12:4], [0, 0, 0])

    def test_render_path_uses_checked_matrix_helper(self):
        parsed = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls = next(node for node in parsed.body if isinstance(node, ast.ClassDef)
                   and node.name == 'ModelViewport')
        paint = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'paintGL')
        calls = [node for node in ast.walk(paint) if isinstance(node, ast.Call)]
        self.assertTrue(any(isinstance(c.func, ast.Name) and
                            c.func.id == '_upload_projection_view' for c in calls))
        self.assertFalse(any(isinstance(c.func, ast.Attribute) and
                             c.func.attr == 'glUniformMatrix4fv' for c in calls),
                         'Call the checked matrix uploader rather than duplicating it')

    def test_projection_shader_uses_matrix_on_position(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn('gl_Position = projectionView * vec4(position, 1.0);', source)


if __name__ == '__main__':
    unittest.main()
