"""Stage 5 v7 regressions: one compatibility warning, row alignment and centered UI."""
from __future__ import annotations
import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
RESULTS = ROOT / 'desktop/qt_app/results_tab.py'

class V7Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding='utf-8-sig')
        cls.results = RESULTS.read_text(encoding='utf-8-sig')

    def test_syntax(self):
        ast.parse(self.main)
        ast.parse(self.results)

    def test_compatibility_warning_precedence(self):
        self.assertIn("template_app = details.get('slicer')",self.main)
        self.assertIn("template_app != selected_app:",self.main)
        self.assertIn('warning = orca_h2c_warning(details, selected_app)',self.main)
        self.assertNotIn("warning = (warning + '\\n' if warning else '') + mismatch",self.main)

    def test_matching_column_header_and_control_heights(self):
        for label in ('slicer_heading','options_heading'):
            self.assertIn(f'{label}.setFixedHeight(20)',self.main)
        self.assertIn('self.slicer_segment.setMinimumHeight(36)',self.main)
        self.assertIn('self.auto_open.setMinimumHeight(36)',self.main)
        self.assertIn('self.export_advanced_toggle.setMinimumHeight(36)',self.main)
        self.assertIn('grid.addWidget(options_box, 3, 1, Qt.AlignmentFlag.AlignTop)',self.main)

    def test_no_redundant_output_setup_heading(self):
        self.assertNotIn("_text('OUTPUT SETUP', 'sectionTitle')",self.results)
        self.assertIn("_label('OUTPUT SLICER', 'sectionTitle')",self.main)
        self.assertIn("_label('OUTPUT DIRECTORY', 'sectionTitle')",self.main)

    def test_diagnostics_centered_in_tab_coordinates(self):
        self.assertIn('self.diagnostics_mode_group = QWidget(self.diagnostics_header)',self.results)
        self.assertIn('diagnostics_head.addWidget(',self.results)
        self.assertIn('self.diagnostics_mode_group, 0, Qt.AlignmentFlag.AlignHCenter',self.results)
        self.assertNotIn('group.move(x, y)',self.results)

@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 not installed')
class V7QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        from desktop.qt_app.main_window import MainWindow
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        window=MainWindow(settings_path=Path(temporary.name)/'prefs.json')
        self.addCleanup(window.close)
        window.show()
        window.tabs.setCurrentWidget(window.results_panel)
        self.app.processEvents()
        return window

    def test_compatibility_mismatch_replaces_orca_warning(self):
        w=self.make_window()
        info={'path':'test.3mf','slicer':'OrcaSlicer','slicerVersion':'2.5.0-alpha',
              'printerPreset':'Bambu Lab H2C','nozzle':'0.4','processPreset':'0.08mm'}
        w.template_path.setText('test.3mf')
        with patch('native_project_template.inspect_template',return_value=info),\
             patch('orca_profile_warning.orca_h2c_warning',return_value='Orca H2C 2.5 build required') as o_warning:
            w._set_combo_value(w.output_application,'Bambu Studio')
            w._refresh_template_status()
            self.assertIn('Template was saved by OrcaSlicer',w.template_compatibility.text())
            self.assertNotIn('2.5 build',w.template_compatibility.text())
            # Mismatch takes precedence; Orca-only warning is not queried.
            o_warning.assert_not_called()
            w._set_combo_value(w.output_application,'OrcaSlicer')
            w._refresh_template_status()
            self.assertEqual(w.template_compatibility.text(),'Orca H2C 2.5 build required')

    def test_slicer_and_after_exporting_align(self):
        w=self.make_window()
        # Compare actual widget coordinates, not Qt style-dependent text metrics.
        slicer=w.slicer_segment
        auto=w.auto_open
        self.app.processEvents()
        slicer_top=slicer.mapTo(w.results_panel,slicer.rect().topLeft()).y()
        auto_top=auto.mapTo(w.results_panel,auto.rect().topLeft()).y()
        if w._export_grid_compact:
            self.assertGreater(auto_top,slicer_top)
        else:
            self.assertLessEqual(abs(slicer_top-auto_top),4,(slicer_top,auto_top))

    def test_diagnostics_switch_center_at_various_sizes(self):
        w=self.make_window()
        tab=w.results_panel
        for width,height in ((1220,760),(1440,880),(1640,1040)):
            w.resize(width,height)
            self.app.processEvents()
            for mode in ('activity','report'):
                tab._select_diagnostics(mode)
                self.app.processEvents()
                group=tab.diagnostics_mode_group
                center=group.mapTo(tab,group.rect().center()).x()
                header=tab.diagnostics_header
                header_center=header.mapTo(tab,header.rect().center()).x()
                self.assertLess(abs(center-header_center),5,(width,mode,center,header_center))
                self.assertTrue(group.isVisibleTo(w))

if __name__ == '__main__':
    unittest.main()
