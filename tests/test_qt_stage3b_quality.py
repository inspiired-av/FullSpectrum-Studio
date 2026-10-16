"""Regression checks for large source meshes and the responsive Stage 3B UI."""
from array import array
import ast
from pathlib import Path
import importlib.util
import os
import unittest

from desktop.qt_app.mesh_loader import _build_mesh, MAX_DRAW_TRIANGLES


class LargeMeshSafetyTests(unittest.TestCase):
    def test_450992_faces_keep_complete_geometry_without_holes(self):
        # Originally Stage 3B drew 225,496/450,992 triangles: every other
        # surface facet was absent. No private model is needed to catch it.
        self.assertGreaterEqual(MAX_DRAW_TRIANGLES, 450_992)
        faces = [(0, 1, 2)] * 450_992
        mesh = _build_mesh([(0.,0.,0.), (1.,0.,0.), (0.,1.,0.)],
                           faces, 'large-test', ['#AABBCC'] * len(faces))
        self.assertEqual(mesh.source_triangles, 450_992)
        self.assertEqual(len(mesh.triangles), 450_992)
        self.assertFalse(mesh.sampled)
        self.assertEqual(mesh.palette_counts, (('#AABBCC', 450_992),))

    def test_precomputed_render_buffer_is_optional_and_preserved(self):
        base = _build_mesh([(0,0,0), (1,0,0), (0,1,0)],
                           [(0,1,2)], 'triangle')
        self.assertIsNone(base.render_buffer)
        from dataclasses import replace
        gpu = array('f', [0.] * 27)
        cached = replace(base, render_buffer=gpu)
        self.assertIs(cached.render_buffer, gpu)
        self.assertEqual(cached.vertices, base.vertices)

    def test_oversize_mesh_rejected_not_punctured(self):
        from unittest.mock import patch
        with patch('desktop.qt_app.mesh_loader.MAX_DRAW_TRIANGLES', 3):
            with self.assertRaisesRegex(ValueError, 'Triangle skipping has been disabled'):
                _build_mesh([(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)]*4, 'oversize')

    def test_worker_prepares_gpu_off_gui_thread(self):
        root = Path(__file__).resolve().parents[1]
        worker = (root / 'desktop/qt_app/preview_worker.py').read_text(encoding='utf-8')
        self.assertIn('render_buffer=flatten_faces(result)', worker)
        window = (root / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        # The palette panel now accepts an optional viewport width. Assert the
        # method exists instead of freezing its positional argument signature.
        tree = ast.parse(window)
        main_window = next(node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
        reflow = next(node for node in main_window.body
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and node.name == '_reflow_source_palette')
        self.assertIn('responsive_columns', ast.unparse(reflow))
        self.assertIn('self._source_palette_columns', ast.unparse(reflow))
        # The swatch's styling and interactivity live in their own module.
        palette = (root / 'desktop/qt_app/source_palette.py').read_text(encoding='utf-8')
        self.assertIn("self.setObjectName('sourcePaletteSwatch')", palette)
        filament = (root / 'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('self.filaments.setMinimumHeight(230)', filament)
        self.assertIn('self.solid_table.setMinimumHeight(178)', filament)
        self.assertNotIn('self.solid_table.setFixedHeight', filament)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, 'Qt GUI unavailable')
class PaletteUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_palette_swatch_reflow_after_width_change(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            win = MainWindow(settings_path=Path(temp) / 'settings.json')
            try:
                mesh = _build_mesh([(0,0,0),(1,0,0),(0,1,0)],
                                   [(0,1,2)]*59, 'palette',
                                   [f'#{i:06X}' for i in range(59)])
                win._populate_source_palette(mesh)
                self.assertEqual(len(win._source_palette_cells), 59)
                win._reflow_source_palette(750)
                wide_cols = win._source_palette_columns
                win._reflow_source_palette(300)
                self.assertLess(win._source_palette_columns, wide_cols)
                self.assertIn('59 source colors', win.source_palette_message.text())
                self.assertTrue(all(cell.toolTip() for cell in win._source_palette_cells))
                self.assertTrue(all(cell.sizePolicy().horizontalPolicy().name == 'Expanding'
                                    for cell in win._source_palette_cells))
                first_color = mesh.palette_counts[0][0]
                win._on_palette_hover(first_color)
                self.assertIn(first_color, win.source_palette_detail.text())
                self.assertIn('faces', win.source_palette_detail.text())
                win._select_palette_color(first_color)
                self.assertEqual(win._source_palette_selected, first_color)
                self.assertTrue(win._source_palette_cells[0]._selected)
                self.assertIsNotNone(win.preview_splitter)
                self.assertEqual(win.preview_splitter.orientation().name, 'Vertical')
            finally:
                win.close()

if __name__ == '__main__':
    unittest.main()
