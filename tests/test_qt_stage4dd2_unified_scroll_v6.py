"""Stage 4D-D2 v6: one wheel-scrollable section for swatches + assignments."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
PANEL = ROOT / 'desktop/qt_app/source_assignments_panel.py'


class ScrollSourceContracts(unittest.TestCase):
    def test_both_swatches_and_assignments_are_in_one_scroll_widget(self):
        source = MAIN.read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn("self.source_palette_scroll.setWidget(self.source_palette_body)", source)
        self.assertIn('palette_outer.addWidget(self.source_palette_scroll)', source)
        self.assertLess(source.index('palette_layout.addWidget(self.source_palette_content)'),
                        source.index('palette_layout.addWidget(self.assignment_panel)'))
        self.assertLess(source.index('palette_layout.addWidget(self.assignment_panel)'),
                        source.index('self.source_palette_scroll.setWidget(self.source_palette_body)'))
        self.assertNotIn('palette_layout.addWidget(self.source_palette_scroll, stretch=1)', source)
        self.assertNotIn('self.source_palette_scroll.setVisible(False)', source)
        self.assertIn('self.source_palette_content.setVisible(bool(palette))', source)

    def test_parent_scroll_handles_inspector_rows(self):
        source = PANEL.read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn('def _resize_tree_to_contents(', source)
        self.assertIn('self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)', source)
        self.assertIn('self.tree.itemExpanded.connect(self._resize_tree_to_contents)', source)
        self.assertIn('self._resize_tree_to_contents()', source)
        self.assertNotIn('self.tree.setMaximumHeight(210)', source)

    def test_earlier_ui_contracts_are_updated(self):
        for name in ('test_qt_stage4dd2_layout_help_v4.py',
                     'test_qt_stage4dd2_inspector_v5.py'):
            text = (ROOT/'tests'/name).read_text(encoding='utf-8')
            ast.parse(text)
            self.assertIn('palette_layout.addWidget(self.source_palette_content)', text)
            self.assertNotIn('palette_layout.addWidget(self.source_palette_scroll, stretch=1)', text)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class UnifiedScrollQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_expansion_has_one_vertical_scrollbar_and_can_reach_last_assignment(self):
        from desktop.qt_app.main_window import MainWindow
        from PySide6.QtCore import Qt
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(settings_path=Path(tmp)/'settings.json')
            try:
                w.resize(1040, 650)
                w.show()
                self.app.processEvents()
                colors = [f'#{i:06X}' for i in range(1, 32)]
                w._populate_source_palette(SimpleNamespace(
                    palette_counts=tuple((color, 2) for color in colors),
                    color_status='Standard colors'))
                mapping = {color:'white' for color in colors}
                w.assignment_panel.set_assignments(
                    mapping,
                    [{'key':'white', 'name':'Example Very Long White PLA', 'color':'#FFFFFF'}],
                    dict.fromkeys(colors, 2))
                w.assignment_panel.toggle.setChecked(True)
                self.app.processEvents()
                scroll = w.source_palette_scroll
                self.assertIs(scroll.widget(), w.source_palette_body)
                self.assertTrue(w.source_palette_body.isAncestorOf(w.source_palette_content))
                self.assertTrue(w.source_palette_body.isAncestorOf(w.assignment_panel))
                self.assertEqual(w.assignment_panel.tree.verticalScrollBarPolicy(),
                                 Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                self.app.processEvents()
                self.assertEqual(scroll.verticalScrollBar().value(),
                                 scroll.verticalScrollBar().maximum())
                w.assignment_panel.toggle.setChecked(False)
                self.app.processEvents()
                self.assertFalse(w.assignment_panel.details.isVisible())
            finally:
                w.close()


if __name__ == '__main__':
    unittest.main()
