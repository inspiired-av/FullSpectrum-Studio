"""Installed Stage 3B regression checks.

Installer-safety tests run with the *downloaded patch*, not as part of the
repository suite. A repository clone must not require download-only scripts.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Stage3BRepositoryTests(unittest.TestCase):
    def test_preview_modules_exist_and_compile(self):
        for name in ('mesh_loader.py', 'preview_shading.py', 'gl_viewport.py',
                     'preview_worker.py', 'main_window.py'):
            path = ROOT / 'desktop' / 'qt_app' / name
            self.assertTrue(path.is_file(), name)
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_renderer_keeps_source_colors_and_camera_controls(self):
        renderer = (ROOT / 'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        self.assertIn('def set_wireframe(self,enabled):', renderer)
        self.assertIn('def reset_camera(self):', renderer)
        self.assertIn('layout(location=2) in vec3 color;', renderer)


if __name__ == '__main__':
    unittest.main()
