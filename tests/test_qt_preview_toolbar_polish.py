"""Contracts for preview-toolbar polish; safe without OpenGL/PySide6."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT/'desktop/qt_app'


class PreviewPolishTests(unittest.TestCase):
    def test_layout_breakpoints_are_stable(self):
        path = PKG/'preview_toolbar_breakpoint.py'
        spec = importlib.util.spec_from_file_location('preview_toolbar_breakpoint',path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        compact = mod.compact_preview_rows
        self.assertFalse(compact(850, 650))
        self.assertTrue(compact(410, 650))
        self.assertTrue(compact(650, 650, was_compact=True))
        self.assertFalse(compact(690, 650, was_compact=True))
        self.assertFalse(compact(650, 650, was_compact=False))

    def test_toolbar_uses_stable_wide_requirement_and_shrinkable_minimum(self):
        code=(PKG/'preview_toolbar.py').read_text(encoding='utf-8')
        self.assertIn('def minimumSizeHint(self)',code)
        self.assertIn('return QSize(0,',code)
        self.assertIn('self._wide_minimum',code)
        self.assertIn('compact_preview_rows(',code)
        self.assertIn('self.refresh(event.size().width())',code)
        self.assertNotIn('showFullScreen(',code)
        ast.parse(code)

    def test_modern_popup_is_non_native_and_preserves_disabled_options(self):
        code=(PKG/'preview_mode_combo.py').read_text(encoding='utf-8')
        self.assertIn('class ModernPreviewComboBox(WheelSafeComboBox)',code)
        self.assertIn('view = QListView(self)',code)
        self.assertIn('QStyledItemDelegate',code)
        self.assertIn('Qt.ItemFlag.ItemIsEnabled',code)
        self.assertIn('def showPopup(self)',code)
        self.assertNotIn('showFullScreen()',code)
        ast.parse(code)

    def test_new_icons_use_arrows_not_box_and_reset_arc(self):
        icons=(PKG/'preview_toolbar_icons.py').read_text(encoding='utf-8')
        self.assertIn("name == 'expand'",icons)
        self.assertIn("name == 'reset'",icons)
        self.assertIn('curve.cubicTo(',icons)
        self.assertNotIn('painter.drawArc(',icons)
        ast.parse(icons)

    def test_main_uses_modern_mode_only_at_preview_toolbar(self):
        code=(PKG/'main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.preview_mode = ModernPreviewComboBox()',code)
        self.assertIn('from desktop.qt_app.preview_mode_combo import ModernPreviewComboBox',code)
        self.assertIn('self.preview_mode.setMaxVisibleItems(self.preview_mode.count())',code)
        ast.parse(code)


if __name__ == '__main__':
    unittest.main()
