"""Stage 5 compact Export layout and unified diagnostic interactions."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
QT = ROOT / 'desktop' / 'qt_app'


class CompactExportContracts(unittest.TestCase):
    @staticmethod
    def method(module, name):
        source = (QT / module).read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name in ('MainWindow', 'ResultsTab'))
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(source, node)

    def test_two_column_settings_and_visible_slicer_choices(self):
        method = self.method('main_window.py', '_build_export_settings')
        self.assertIn('QGridLayout()', method)
        self.assertIn('grid.addWidget(template_box, 0, 0)', method)
        self.assertIn('grid.addWidget(directory_box, 0, 1)', method)
        self.assertIn("('OrcaSlicer', 'OrcaSlicer')", method)
        self.assertIn("('Bambu Studio', 'Bambu Studio')", method)
        self.assertIn('self.output_application.currentIndexChanged.connect', method)

    def test_all_preexisting_output_bindings_preserved(self):
        code = (QT/'main_window.py').read_text(encoding='utf-8-sig')
        for key in ('nativeTemplatePath', 'exportOutputDirectory', 'exportSaveSettings',
                    'exportRevertSettings', 'slicerExecutableBrowse', 'slicerExecutableAuto',
                    'export3mfButton', 'cancelExportButton'):
            self.assertIn(key, code)
        self.assertIn('make_export_request(', code)
        self.assertIn('self.output_application.currentData()', code)

    def test_cancel_is_contextual(self):
        method = self.method('main_window.py', '_refresh_export_availability')
        self.assertIn('self.export_cancel_button.setVisible(busy)', method)
        action = self.method('main_window.py', '_build_export_actions')
        self.assertIn('self.export_cancel_button.setVisible(False)', action)

    def test_shared_diagnostics_and_inline_actions(self):
        method = self.method('results_tab.py', '_build')
        self.assertIn('QStackedWidget()', method)
        self.assertIn('self.diagnostics_stack.addWidget(self.activity_log)', method)
        self.assertIn('self.diagnostics_stack.addWidget(self.report_view)', method)
        self.assertIn("self.activity_toggle.setText('Activity')", method)
        self.assertIn("self.report_toggle.setText('Report')", method)
        self.assertIn('self.copy_activity_button', method)
        self.assertIn('self.clear_report_button', method)
        self.assertNotIn("layout.addWidget(_text('CURRENT ACTIVITY'", method)
        self.assertNotIn("layout.addWidget(_text('EXISTING / GENERATED REPORT'", method)

    def test_success_displays_result_actions_without_old_sections(self):
        m = self.method('results_tab.py', 'set_export_result')
        self.assertIn('self.validated_output_panel.show()', m)
        self.assertIn('self.export_summary.show()', m)
        self.assertIn("self.phase_label.setText('Validated native 3MF')", m)

    def test_report_load_selects_shared_report_view(self):
        m = self.method('results_tab.py', 'load_report')
        self.assertIn("self._select_diagnostics('report')", m)

    def test_template_warning_stays_discoverable(self):
        method = self.method('main_window.py', '_update_export_template_attention')
        self.assertIn('self.template_compatibility.text()', method)
        self.assertIn('self.template_attention.setToolTip(detail)', method)
        self.assertIn('self.template_attention.setVisible(bool(short))', method)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class CompactExportQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_diagnostics_switch_has_one_visible_view(self):
        from desktop.qt_app.results_tab import ResultsTab
        tab = ResultsTab()
        self.addCleanup(tab.close)
        tab.show()
        self.app.processEvents()
        self.assertIs(tab.diagnostics_stack.currentWidget(), tab.activity_log)
        self.assertTrue(tab.copy_activity_button.isVisibleTo(tab))
        self.assertFalse(tab.copy_report_button.isVisibleTo(tab))
        tab.report_toggle.click()
        self.app.processEvents()
        self.assertIs(tab.diagnostics_stack.currentWidget(), tab.report_view)
        self.assertTrue(tab.open_report_button.isVisibleTo(tab))
        self.assertFalse(tab.clear_activity_button.isVisibleTo(tab))
        tab.diagnostics_collapse.click()
        self.assertFalse(tab.diagnostics_stack.isVisibleTo(tab))
        tab.diagnostics_collapse.click()
        self.assertTrue(tab.diagnostics_stack.isVisibleTo(tab))

    def test_report_load_is_visible_and_validated_output_is_contextual(self):
        from desktop.qt_app.results_tab import ResultsTab
        tab = ResultsTab()
        self.addCleanup(tab.close)
        tab.show()
        self.app.processEvents()
        self.assertFalse(tab.validated_output_panel.isVisibleTo(tab))
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'report.txt'
            report.write_text('Validated test report', encoding='utf-8')
            self.assertTrue(tab.load_report(report))
        self.assertIs(tab.diagnostics_stack.currentWidget(), tab.report_view)
        self.assertIn('Validated test report', tab.report_view.toPlainText())
        tab.set_export_result({'output':str(Path(tempfile.gettempdir())/'validated.3mf'), 'slicer':'OrcaSlicer'})
        self.app.processEvents()
        self.assertTrue(tab.validated_output_panel.isVisibleTo(tab))
        self.assertTrue(tab.export_summary.isVisibleTo(tab))

    def test_slicer_segment_updates_preference_combo_and_revert(self):
        from desktop.qt_app.main_window import MainWindow
        with tempfile.TemporaryDirectory() as tmp:
            window = MainWindow(settings_path=Path(tmp)/'settings.json')
            self.addCleanup(window.close)
            window.show()
            self.app.processEvents()
            window.slicer_choice_buttons['OrcaSlicer'].click()
            self.assertEqual(window.output_application.currentData(), 'OrcaSlicer')
            self.assertTrue(window.slicer_choice_buttons['OrcaSlicer'].isChecked())
            window._set_combo_value(window.output_application, 'Bambu Studio')
            self.assertTrue(window.slicer_choice_buttons['Bambu Studio'].isChecked())
            self.assertFalse(window.export_cancel_button.isVisibleTo(window))
            window.tabs.setCurrentWidget(window.results_panel)
            self.app.processEvents()
            self.assertFalse(window.export_advanced_panel.isVisibleTo(window))
            window.export_advanced_toggle.click()
            self.app.processEvents()
            self.assertTrue(window.export_advanced_panel.isVisibleTo(window))


if __name__ == '__main__':
    unittest.main()
