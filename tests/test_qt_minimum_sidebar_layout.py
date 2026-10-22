"""Small regression set for narrow Qt sidebar / Export control visibility."""
from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'desktop/qt_app/main_window.py'
RESULTS=ROOT/'desktop/qt_app/results_tab.py'


class NarrowSidebarSourceContracts(unittest.TestCase):
    def test_sidebar_minimum_and_splitter_guards(self):
        code=MAIN.read_text(encoding='utf-8-sig')
        ast.parse(code)
        # Minimum widths are restored; Export rearranges its own widgets.
        self.assertIn('sidebar.setMinimumWidth(340)',code)
        self.assertIn('self.setMinimumSize(920, 630)',code)
        self.assertIn('self._arrange_export_grid(True)',code)
        self.assertIn('export_viewport_resized.connect(self._update_export_layout)',code)
        self.assertIn('self.slicer_segment.setMaximumWidth(268)',code)

    def test_results_overflow_and_live_layout_event_checks(self):
        code=RESULTS.read_text(encoding='utf-8-sig')
        ast.parse(code)
        self.assertIn('setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)',code)
        self.assertIn('diagnostics_head.addWidget(',code)
        self.assertIn('self.diagnostics_mode_group, 0, Qt.AlignmentFlag.AlignHCenter',code)
        self.assertNotIn('def _queue_diagnostics_recenter(self):',code)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not installed')
class NarrowSidebarQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def make_window(self):
        from desktop.qt_app.main_window import MainWindow
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        w=MainWindow(settings_path=Path(temp.name)/'settings.json')
        self.addCleanup(w.close)
        w.show()
        w.tabs.setCurrentWidget(w.results_panel)
        self.app.processEvents()
        return w

    def test_drag_to_minimum_does_not_cut_export_controls(self):
        from PySide6.QtCore import QPoint
        w=self.make_window()
        for width in (1050,1280,1680):
            w.resize(width,850)
            self.app.processEvents()
            # Simulate the extreme user drag that used to clip the sidebar.
            w.splitter.setSizes([3000,1])
            self.app.processEvents()
            self.assertGreaterEqual(w.splitter.widget(1).width(),340)
            self.assertTrue(w._export_grid_compact)
            viewport=w.results_panel.content_scroll.viewport()
            for control in (w.template_path,w.export_directory,w.slicer_segment,
                            w.auto_open,w.export_advanced_toggle):
                right=control.mapTo(viewport,QPoint(control.width(),0)).x()
                self.assertLessEqual(right,viewport.width()+2,
                                     (width,control.objectName(),right,viewport.width()))
                left=control.mapTo(viewport,QPoint(0,0)).x()
                self.assertGreaterEqual(left,-2,(width,control.objectName(),left))

    def test_repeated_resize_and_warning_layout_keeps_horizontal_access(self):
        w=self.make_window()
        for width in (1050,1440,1100):
            w.resize(width,740)
            w.splitter.setSizes([3000,1])
            w.template_attention.setChecked(True)
            self.app.processEvents()
            self.assertGreaterEqual(w.splitter.widget(1).width(),340)
            self.assertTrue(w._export_grid_compact)
            self.assertEqual(w.results_panel.content_scroll.horizontalScrollBarPolicy().name,
                             'ScrollBarAsNeeded')
            w.template_attention.setChecked(False)
            self.app.processEvents()


if __name__=='__main__':
    unittest.main()
