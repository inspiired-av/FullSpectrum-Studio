"""Focused, primarily headless checks for the pre-6B toolbar + custom palette UI.

No full MainWindow/OpenGL context required. Run from repository root:
  python -m unittest discover -s tests -p 'test_qt_pre6b_ui_cleanup.py' -v
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'desktop/qt_app'


def method_source(source: str, name: str):
    module = ast.parse(source)
    window = next(node for node in module.body
                  if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    method = next(node for node in window.body
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, method)


class ToolbarAndPaletteStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (SOURCE / 'main_window.py').read_text(encoding='utf-8-sig')
        cls.icons = (SOURCE / 'preview_toolbar_icons.py').read_text(encoding='utf-8-sig')
        ast.parse(cls.main)
        ast.parse(cls.icons)

    def test_grid_toggles_with_icon_and_opens_menu_from_separate_chevron(self):
        pane = method_source(self.main, '_preview_pane')
        self.assertIn('self.preview_grid_button.setCheckable(True)', pane)
        self.assertIn('self.preview_grid_button.toggled.connect(self._toggle_preview_grid)', pane)
        self.assertIn("setObjectName('previewGridMenuButton')", pane)
        self.assertIn("preview_toolbar_icon('chevron-down')", pane)
        self.assertIn('self.preview_grid_menu_button.setMenu(self.preview_grid_menu)', pane)
        self.assertIn('ToolButtonPopupMode.InstantPopup', pane)
        self.assertNotIn('ToolButtonPopupMode.MenuButtonPopup', pane)

    def test_grid_is_in_plate_group_not_camera_group(self):
        pane = method_source(self.main, '_preview_pane')
        group = pane.split('self.preview_plate_group = make_preview_group(',1)[1].split('name=\'build_plate\')',1)[0]
        camera = pane.split('self.preview_camera_group = make_preview_group(',1)[1].split('name=\'camera\')',1)[0]
        self.assertIn('self.plate_button', group)
        self.assertIn('self.plate_visibility_button', group)
        self.assertIn('self.preview_grid_button', group)
        self.assertIn('self.preview_grid_menu_button', group)
        self.assertNotIn('self.preview_grid_button', camera)
        self.assertNotIn('self.preview_grid_menu_button', camera)
        self.assertIn('self.expand_preview_toggle', camera)
        self.assertIn('self.reset_camera_button', camera)

    def test_custom_palette_label_and_presets_are_distinct(self):
        method = method_source(self.main, '_set_palette_limit_choice')
        self.assertIn("f'(Custom) {value} colors'", method)
        pane = method_source(self.main, '_plan_tab')
        self.assertIn('("32 colors", "32")', pane)
        self.assertIn('self.palette_limit_custom', pane)

    def test_existing_grid_settings_menu_and_binding_intact(self):
        pane = method_source(self.main, '_preview_pane')
        self.assertIn("self.preview_grid_menu = QMenu('Grid and Axes', self)", pane)
        self.assertIn("'automatic': 'Automatic (recommended)'", pane)
        self.assertIn("'perspective': 'Perspective Grid'", pane)
        self.assertIn('self.preview_grid_menu_button.setMenu(self.preview_grid_menu)', pane)
        self.assertIn('self.preview_axes_action', pane)

    def test_chevron_icon_is_vector_not_text_or_unicode_glyph(self):
        self.assertIn("'chevron-down'", self.icons)
        self.assertIn("name == 'chevron-down'", self.icons)
        self.assertIn('painter.drawLine(QPointF(6, 9), QPointF(12, 15))', self.icons)


class PaletteBehaviorTests(unittest.TestCase):
    """Execute the actual method AST using minimal combo-box test doubles."""

    @staticmethod
    def harness():
        source = (SOURCE / 'main_window.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        window = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
        method = next(node for node in window.body
                      if isinstance(node, ast.FunctionDef) and node.name == '_set_palette_limit_choice')
        namespace = {}
        exec(compile(ast.Module(body=[method],type_ignores=[]), '<palette method>', 'exec'), namespace)

        class FakeCombo:
            def __init__(self):
                self.items = [('Auto','auto'),('8 colors','8'),('16 colors','16'),
                              ('24 colors','24'),('32 colors','32')]
                self.selected = None
            def findData(self, val):
                return next((i for i,(_,d) in enumerate(self.items) if val == d), -1)
            def addItem(self,label,data): self.items.append((label,data))
            def removeItem(self,index): self.items.pop(index)
            def setCurrentIndex(self,index): self.selected = index
            def currentData(self): return self.items[self.selected][1]

        class Harness:
            def __init__(self): self.palette_limit = FakeCombo()
            def _set_combo_value(self, combo, value):
                i = combo.findData(value)
                if i >= 0: combo.setCurrentIndex(i)

        Harness._set_palette_limit_choice = namespace['_set_palette_limit_choice']
        return Harness()

    def test_selecting_and_replacing_custom_value_uses_custom_label(self):
        h=self.harness()
        h._set_palette_limit_choice('30')
        self.assertEqual(h.palette_limit.items[h.palette_limit.selected], ('(Custom) 30 colors','30'))
        h._set_palette_limit_choice('7')
        self.assertNotIn(('(Custom) 30 colors','30'), h.palette_limit.items)
        self.assertEqual(h.palette_limit.items[h.palette_limit.selected], ('(Custom) 7 colors','7'))

    def test_preset_and_auto_do_not_gain_custom_label(self):
        h=self.harness()
        h._set_palette_limit_choice('30')
        h._set_palette_limit_choice('24')
        self.assertEqual(h.palette_limit.items[h.palette_limit.selected], ('24 colors','24'))
        h._set_palette_limit_choice('auto')
        self.assertEqual(h.palette_limit.items[h.palette_limit.selected], ('Auto','auto'))


if __name__=='__main__':
    unittest.main()
