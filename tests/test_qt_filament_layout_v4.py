"""Stage 2B scroll-layout regression and safe installer tests."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
TARGET = PACKAGE / 'desktop/qt_app/filaments_tab.py'


class SourceTests(unittest.TestCase):
    def test_source_compiles_without_running_qt(self):
        ast.parse(TARGET.read_text(encoding='utf-8'))

    def test_scroll_area_wraps_tab_content(self):
        code = TARGET.read_text(encoding='utf-8')
        self.assertIn('self.content_scroll = QScrollArea(self)', code)
        self.assertIn('self.content_scroll.setWidgetResizable(True)', code)
        self.assertIn('lay.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)', code)
        self.assertIn('self.content_scroll.setWidget(self.content)', code)

    def test_tables_scroll_independently(self):
        code = TARGET.read_text(encoding='utf-8')
        self.assertIn('self.filaments.setMinimumHeight(230)', code)
        self.assertIn('self.solid_table.setMinimumHeight(178)', code)
        self.assertIn('lay.addWidget(self.filaments, 3)', code)
        self.assertIn('lay.addWidget(self.solid_table, 2)', code)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QtGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        plan = PlanPreferences(Path(self.tmp.name) / 'settings.json')
        self.tab = FilamentsTab(plan, settings_path=plan.path)
        self.tab.resize(470, 510)
        self.tab.show()
        self.app.processEvents()
        self.addCleanup(self.tab.close)

    def test_short_window_scrollbar_and_no_overlap(self):
        from PySide6.QtCore import QPoint
        self.assertGreater(self.tab.content_scroll.verticalScrollBar().maximum(), 0)
        table_end = self.tab.filaments.mapTo(self.tab.content, QPoint(0, self.tab.filaments.height())).y()
        bulk_start = self.tab.bulk_use_button.mapTo(self.tab.content, QPoint(0, 0)).y()
        self.assertGreaterEqual(bulk_start, table_end)
        solid_end = self.tab.solid_table.mapTo(self.tab.content, QPoint(0, self.tab.solid_table.height())).y()
        assign_start = self.tab.target.mapTo(self.tab.content, QPoint(0, 0)).y()
        self.assertGreaterEqual(assign_start, solid_end)

    def test_taller_window_expands_both_tables(self):
        self.tab.resize(470, 1350)
        self.app.processEvents()
        self.assertGreater(self.tab.filaments.height(), 230)
        self.assertGreater(self.tab.solid_table.height(), 178)

    def test_many_colors_scroll_inside_table(self):
        self.tab.options = [dict(key=f'key-{i}',name=f'Filament {i}',series='PLA',
                                 color=f'#{i%256:02X}22FF') for i in range(62)]
        self.tab._populate_options()
        self.app.processEvents()
        self.assertGreater(self.tab.filaments.verticalScrollBar().maximum(), 0)
        self.assertGreater(self.tab.content_scroll.verticalScrollBar().maximum(), 0)


if __name__ == '__main__':
    unittest.main()
