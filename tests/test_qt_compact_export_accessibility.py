"""Qt Export compact form and stable Diagnostics layout regression tests.

Behavioral checks cover the smallest supported window width and user-visible
header positioning; keep full engine tests in the separate suite.
"""
from __future__ import annotations
import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
RESULTS = ROOT / 'desktop/qt_app/results_tab.py'


class CompactExportSourceContracts(unittest.TestCase):
    def test_compile_and_single_diagnostics_owner(self):
        main=MAIN.read_text(encoding='utf-8-sig')
        results=RESULTS.read_text(encoding='utf-8-sig')
        ast.parse(main);ast.parse(results)
        self.assertIn('self.diagnostics_mode_group = QWidget(self.diagnostics_header)',results)
        self.assertIn('diagnostics_head.addWidget(',results)
        self.assertNotIn('group.move(x, y)',results)
        self.assertNotIn('def _center_diagnostics_switch(self)',results)
        self.assertIn('self.content_scroll.viewport().installEventFilter(self)',results)
        self.assertIn('export_viewport_resized.emit(',results)

    def test_export_compacts_without_widening_sidebar(self):
        main=MAIN.read_text(encoding='utf-8-sig')
        self.assertIn('sidebar.setMinimumWidth(340)',main)
        self.assertIn('self.setMinimumSize(920, 630)',main)
        self.assertIn('self._arrange_export_grid(True)',main)
        self.assertIn('self.export_preferences_row.setMinimumWidth(0)',main)
        self.assertIn('preference_actions.addWidget(self.export_revert_settings_button)',main)
        self.assertIn('grid.setHorizontalSpacing(0 if compact else 12)',main)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not available')
class CompactExportQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.main_window import MainWindow
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window=MainWindow(settings_path=Path(self.temp.name)/'prefs.json')
        self.addCleanup(self.window.close)
        self.window.show()
        self.window.tabs.setCurrentWidget(self.window.results_panel)
        self.pump()

    def pump(self):
        for _ in range(10):self.app.processEvents()

    def assert_inside_horizontal_viewport(self, controls):
        from PySide6.QtCore import QPoint
        w=self.window
        viewport=w.results_panel.content_scroll.viewport()
        for control in controls:
            self.assertTrue(control.isVisibleTo(w),control.objectName())
            left=control.mapTo(viewport,QPoint(0,0)).x()
            right=control.mapTo(viewport,QPoint(control.width(),0)).x()
            self.assertGreaterEqual(left,-2,(control.objectName(),left,viewport.width()))
            self.assertLessEqual(right,viewport.width()+2,(control.objectName(),right,viewport.width()))

    def test_compact_sidebar_fields_buttons_and_saved_actions_fit(self):
        w=self.window
        for width in (920,1050,1280):
            w.resize(width,790)
            w.splitter.setSizes([3000,1])
            self.pump()
            self.assertTrue(w._export_grid_compact)
            self.assertGreaterEqual(w.splitter.widget(1).width(),340)
            w.export_preferences_row.setVisible(True)
            self.pump()
            self.assert_inside_horizontal_viewport((
                w.template_path,w.template_browse,w.template_clear,
                w.export_directory,w.export_directory_browse,
                w.slicer_segment,w.auto_open,w.export_advanced_toggle,
                w.export_save_settings_button,w.export_revert_settings_button))

    def test_diagnostics_never_overlaps_controls_when_layout_moves(self):
        w=self.window
        from PySide6.QtCore import QPoint
        for width in (920,1440,1680):
            w.resize(width,840)
            w.splitter.setSizes([3000,1] if width!=1680 else [700,800])
            for expanded in (False,True):
                w.template_warning_panel.setVisible(expanded)
                w.export_advanced_toggle.setChecked(expanded)
                w.export_preferences_row.setVisible(expanded)
                for mode in ('activity','report'):
                    w.results_panel._select_diagnostics(mode)
                    self.pump()
                    tab=w.results_panel
                    header=tab.diagnostics_header
                    group=tab.diagnostics_mode_group
                    self.assertIs(group.parent(),header)
                    self.assertTrue(group.isVisibleTo(w))
                    self.assertGreaterEqual(group.y(),tab.diagnostics_tools.height())
                    top=group.mapTo(tab,QPoint(0,0)).y()
                    # Header is in normal flow after Export controls, so its
                    # second-row selector cannot paint over the export action.
                    action_bottom=w.export_action_panel.mapTo(tab,QPoint(0,w.export_action_panel.height())).y()
                    self.assertGreaterEqual(top,action_bottom,(width,expanded,mode,top,action_bottom))
                    header_mid=header.mapTo(tab,header.rect().center()).x()
                    group_mid=group.mapTo(tab,group.rect().center()).x()
                    self.assertLessEqual(abs(group_mid-header_mid),5)


if __name__=='__main__':unittest.main()
