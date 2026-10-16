"""Stage 3B palette hover / adaptive sizing regressions."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PALETTE = ROOT / 'desktop/qt_app/source_palette.py'
MAIN = ROOT / 'desktop/qt_app/main_window.py'


class PaletteLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette_text = PALETTE.read_text(encoding='utf-8')
        tree = ast.parse(cls.palette_text)
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'responsive_columns')
        module = ast.Module(body=[fn], type_ignores=[])
        scope = {}
        exec(compile(ast.fix_missing_locations(module), '<palette>', 'exec'), scope)
        cls.cols = staticmethod(scope['responsive_columns'])

    def test_full_width_changes_column_count(self):
        self.assertGreater(self.cols(900, 59), self.cols(300, 59))
        self.assertGreater(self.cols(600, 59), self.cols(300, 59))
        self.assertEqual(self.cols(900, 8), 8)
        self.assertEqual(self.cols(0, 8), 1)

    def test_color_details_are_explicit_not_just_tooltips(self):
        main = MAIN.read_text(encoding='utf-8')
        for value in ('source_palette_detail', '_on_palette_hover',
                      '_select_palette_color', 'self.preview_splitter',
                      'responsive_columns(viewport_width, len(cells))'):
            self.assertIn(value, main)
        for method in ('enterEvent', 'mouseMoveEvent', 'leaveEvent', 'mousePressEvent', 'keyPressEvent'):
            self.assertIn('def ' + method, self.palette_text)

    def test_no_forced_palette_height(self):
        main = MAIN.read_text(encoding='utf-8')
        self.assertNotIn('self.source_palette_scroll.setFixedHeight(', main)
        self.assertIn("self.preview_splitter.setChildrenCollapsible(False)", main)
        self.assertIn('event.size().width()', main)

if __name__ == '__main__':
    unittest.main()
