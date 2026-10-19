"""Stage 4D-D2 v8: expanding the unified palette must not spread its contents."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'


class SpacingSourceContracts(unittest.TestCase):
    def test_spacer_is_after_swatches_and_assignments(self):
        source = MAIN.read_text(encoding='utf-8')
        ast.parse(source)
        self.assertLess(source.index('palette_layout.addWidget(self.source_palette_content)'),
                        source.index('palette_layout.addWidget(self.assignment_panel)'))
        self.assertLess(source.index('palette_layout.addWidget(self.assignment_panel)'),
                        source.index('palette_layout.addStretch(1)'))
        self.assertLess(source.index('palette_layout.addStretch(1)'),
                        source.index('self.source_palette_scroll.setWidget(self.source_palette_body)'))

    def test_unified_scroll_kept_without_nested_scrollbars(self):
        source = MAIN.read_text(encoding='utf-8')
        self.assertIn('self.source_palette_scroll.setWidget(self.source_palette_body)', source)
        self.assertIn('self.source_palette_content.setVisible(bool(palette))', source)
        panel = (ROOT / 'desktop/qt_app/source_assignments_panel.py').read_text(encoding='utf-8')
        self.assertIn('self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)', panel)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class SpacingQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_expanded_palette_widgets_stay_compact_even_when_pane_is_tall(self):
        from desktop.qt_app.main_window import MainWindow
        from PySide6.QtCore import QPoint
        with tempfile.TemporaryDirectory() as tmp:
            window=MainWindow(settings_path=Path(tmp)/'settings.json')
            try:
                window.resize(1440,900)
                window.show()
                self.app.processEvents()
                colors=[f'#{i:06X}' for i in range(1,19)]
                window._populate_source_palette(SimpleNamespace(
                    palette_counts=tuple((color,2) for color in colors),
                    color_status='Standard colors'))
                window.assignment_panel.set_assignments(
                    {'#000001':'white'},
                    [{'key':'white','name':'Sample White PLA','color':'#FFFFFF'}],
                    {'#000001':2})
                window.assignment_panel.toggle.setChecked(True)
                self.app.processEvents()
                # A manually enlarged Source Palette must not create extra
                # gaps between its message, swatches and assignment table.
                splitter=window.preview_splitter
                total=sum(splitter.sizes())
                if total>630:
                    splitter.setSizes([max(195,total-490),490])
                for _ in range(3):
                    self.app.processEvents()
                body=window.source_palette_body
                def top(widget):
                    return widget.mapTo(body,QPoint(0,0)).y()
                def bottom(widget):
                    return top(widget)+widget.height()
                self.assertLessEqual(top(window.source_palette_detail)-bottom(window.source_palette_message),24)
                self.assertLessEqual(top(window.source_palette_content)-bottom(window.source_palette_detail),24)
                self.assertLessEqual(top(window.assignment_panel)-bottom(window.source_palette_content),24)
                self.assertTrue(body.isAncestorOf(window.assignment_panel))
                self.assertTrue(body.isAncestorOf(window.source_palette_content))
                window.assignment_panel.toggle.setChecked(False)
                self.app.processEvents()
                self.assertFalse(window.assignment_panel.details.isVisible())
            finally:
                window.close()

if __name__=='__main__':
    unittest.main()
