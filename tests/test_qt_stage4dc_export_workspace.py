"""Stage 4D-C export workspace: UI-only refactor, legacy engine unchanged."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'desktop' / 'qt_app'


class ExportWorkspaceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = (UI/'main_window.py').read_text(encoding='utf-8')
        cls.results = (UI/'results_tab.py').read_text(encoding='utf-8')

    def method(self, name):
        tree = ast.parse(self.window)
        main = next(item for item in tree.body
                    if isinstance(item, ast.ClassDef) and item.name == 'MainWindow')
        method = next(item for item in main.body
                      if isinstance(item, ast.FunctionDef) and item.name == name)
        return ast.get_source_segment(self.window, method)

    def test_export_workflow_is_one_tab_without_duplicate_buttons(self):
        sidebar=self.method('_sidebar')
        self.assertIn('"Export"', sidebar)
        self.assertNotIn('"Results"', sidebar)
        self.assertIn('attach_export_panels(', sidebar)
        self.assertIn('self.results_panel.open_export_button', sidebar)
        plan=self.method('_plan_tab')
        self.assertIn('Review && Export →', plan)
        self.assertNotIn('Export Native 3MF…', plan)
        self.assertNotIn('self.template_path = QLineEdit()', plan)
        self.assertNotIn('self.auto_open = QCheckBox', plan)
        self.assertNotIn('self.output_application = self._choice(', plan)

    def test_all_export_choices_live_together(self):
        config=self.method('_build_export_settings')
        for token in ('nativeTemplatePath', 'native_project_template',
                      'output_application', 'auto_open', 'slicerExecutableBrowse',
                      'exportOutputDirectory', 'exportDirectoryBrowse',
                      'exportSaveSettings', 'exportRevertSettings'):
            self.assertIn(token, config)
        self.assertIn("self._refresh_export_directory()", self.method('_choose_export_directory'))
        self.assertIn("self.export_directory.text().strip()", self.method('_begin_export'))
        self.assertNotIn('QFileDialog.getExistingDirectory', self.method('_begin_export'))
        self.assertIn('self.export_directory_browse.setEnabled(False)', self.method('_begin_export'))
        self.assertIn('self.export_directory_browse.setEnabled(True)', self.method('_release_export'))

    def test_background_export_contract_and_live_forecast_stay_separate(self):
        actions=self.method('_build_export_actions')
        for token in ('self.compose_button', 'self.export_progress',
                      'self.export_cancel_button', 'self._begin_export'):
            self.assertIn(token, actions)
        self.assertNotIn("self.open_export_button = QPushButton",actions)
        self.assertIn("ForecastWorker('forecast', request, self)", self.window)
        self.assertIn('ExportWorker(request, self)',self.window)
        svc=(UI/'export_service.py').read_text(encoding='utf-8')
        self.assertIn('plan_only=False',svc)
        self.assertIn('_exclusive_publish(paths, destination)',svc)
        self.assertIn("result.get('validation') != 'OK'",svc)

    def test_results_present_export_and_keep_logs_optional(self):
        for token in ('EXPORT SETTINGS', 'NATIVE 3MF EXPORT', 'VALIDATED OUTPUT',
                      'EXISTING / GENERATED REPORT', 'CURRENT ACTIVITY',
                      'def attach_export_panels', 'exportActivityToggle',
                      'exportReportToggle', 'self.report_toggle.setChecked(True)'):
            self.assertIn(token,self.results)
        self.assertLess(self.results.index("_text('VALIDATED OUTPUT'"),
                        self.results.index("_text('CURRENT ACTIVITY'"))
        self.assertNotIn('self.compose_button =', self.results)
        self.assertNotIn('help_heading(', self.results)


try:
    from PySide6.QtWidgets import QApplication, QLineEdit
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication=None


@unittest.skipUnless(QApplication is not None, 'PySide6 is not installed')
class QtExportWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_widgets_are_mounted_in_export_not_plan(self):
        with TemporaryDirectory() as folder:
            window=MainWindow(settings_path=Path(folder)/'settings.json')
            try:
                self.assertEqual([window.tabs.tabText(i) for i in range(3)],
                                 ['Plan','Filaments','Export'])
                self.assertIsNone(window.tabs.widget(0).findChild(QLineEdit,'nativeTemplatePath'))
                self.assertIsNotNone(window.tabs.widget(2).findChild(QLineEdit,'nativeTemplatePath'))
                self.assertIsNone(window.tabs.widget(0).findChild(QLineEdit,'exportOutputDirectory'))
                self.assertFalse(window.compose_button.isEnabled())
                self.assertIs(window.open_export_button,window.results_panel.open_export_button)
                window.review_export_button.click()
                self.assertIs(window.tabs.currentWidget(),window.results_panel)
            finally:
                window.close()

    def test_export_settings_still_use_plan_preferences(self):
        with TemporaryDirectory() as folder:
            window=MainWindow(settings_path=Path(folder)/'settings.json')
            try:
                window.auto_open.setChecked(False)
                self.assertFalse(window.plan_preferences.get('auto_open'))
                window._export_directory_override=folder
                window._refresh_export_directory()
                self.assertEqual(window.export_directory.text(),folder)
                self.assertTrue(window.export_directory.isReadOnly())
            finally:
                window.close()


if __name__ == '__main__':
    unittest.main()
