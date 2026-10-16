"""Stage 4A: protection rows populate automatically after source preview."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
QT_AVAILABLE = importlib.util.find_spec('PySide6') is not None


def method_source(path, classname, method):
    code = (ROOT / path).read_text(encoding='utf-8')
    module = ast.parse(code)
    cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == classname)
    function = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method)
    return ast.get_source_segment(code, function)


class AutomaticSourceColorContracts(unittest.TestCase):
    def test_model_preview_starts_automatic_validation(self):
        code = method_source('desktop/qt_app/main_window.py', 'MainWindow', '_preview_loaded')
        self.assertIn('self._populate_source_palette(mesh)', code)
        self.assertIn('self.filaments_panel.auto_load_source_colors()', code)
        self.assertLess(code.index('self._populate_source_palette(mesh)'), code.index('self.filaments_panel.auto_load_source_colors()'))

    def test_no_manual_source_scan_button(self):
        source = (ROOT / 'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertNotIn("QPushButton('Scan Source Colors')", source)
        self.assertNotIn('self.scan_button', source)
        self.assertIn("setObjectName('sourceColorLoadStatus')", source)

    def test_authoritative_scanner_kept_separate_from_preview(self):
        automatic = method_source('desktop/qt_app/filaments_tab.py', 'FilamentsTab', 'auto_load_source_colors')
        self.assertIn('self.scan_colors()', automatic)
        scan = method_source('desktop/qt_app/filaments_tab.py', 'FilamentsTab', 'scan_colors')
        self.assertIn('self._start(scan_source_colors', scan)
        self.assertIn('self._source_scan_attempted = True', scan)

    def test_scan_failure_is_inline_and_nonmodal(self):
        method = method_source('desktop/qt_app/filaments_tab.py', 'FilamentsTab', '_colors_loaded')
        self.assertNotIn('QMessageBox.warning', method)
        self.assertIn('Protection unavailable for this model:', method)

    def test_changed_model_invalidates_completed_and_inflight_scans(self):
        method = method_source('desktop/qt_app/filaments_tab.py', 'FilamentsTab', 'set_model')
        self.assertIn('self._scan_serial += 1', method)
        self.assertIn('self._source_scan_attempted = False', method)
        self.assertIn('self.source_colors={}', method)


@unittest.skipUnless(QT_AVAILABLE, 'PySide6 GUI is unavailable')
class QtAutoScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.plan_preferences import PlanPreferences
        from desktop.qt_app.filaments_tab import FilamentsTab
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        settings_path = Path(self.tmp.name) / 'settings.json'
        self.panel = FilamentsTab(PlanPreferences(settings_path), settings_path=settings_path)
        self.addCleanup(self.panel.close)
        self.model = Path(self.tmp.name) / 'sample.3mf'
        self.model.write_bytes(b'dummy: async loader is mocked')
        self.panel.set_model(str(self.model))

    def test_scans_once_then_reuses_existing_table(self):
        with patch.object(self.panel, '_start') as start:
            self.panel.auto_load_source_colors()
            self.panel.auto_load_source_colors()
            self.assertEqual(start.call_count, 1)
            self.assertTrue(self.panel._source_scan_attempted)
        self.panel._colors_loaded(self.panel._scan_serial, self.panel.model_path,
                                  {'#FF0000': 3, '#000000': 2}, None)
        self.assertEqual(self.panel.solid_table.rowCount(), 2)
        with patch.object(self.panel, 'scan_colors') as scan:
            self.panel.auto_load_source_colors()
            scan.assert_not_called()

    def test_selection_before_scan_restored(self):
        with patch.object(self.panel, '_start'):
            self.panel.auto_load_source_colors()
        self.panel.select_source_colors(('#FF0000', '#000000'))
        self.assertEqual(set(self.panel._pending_assignment_colors), {'#FF0000', '#000000'})
        self.panel._colors_loaded(self.panel._scan_serial, self.panel.model_path,
                                  {'#FF0000': 3, '#000000': 2, '#FFFFFF': 5}, None)
        self.assertEqual(set(self.panel._selected_colors()), {'#FF0000', '#000000'})

    def test_scan_failure_inline_without_dialog(self):
        with patch.object(self.panel, '_start'):
            self.panel.auto_load_source_colors()
        with patch('desktop.qt_app.filaments_tab.QMessageBox.warning') as modal:
            self.panel._colors_loaded(self.panel._scan_serial, self.panel.model_path,
                                      None, 'unsupported native paint encoding')
            modal.assert_not_called()
        self.assertIn('unsupported native paint encoding', self.panel.protected_count.text())
        self.assertEqual(self.panel.solid_table.rowCount(), 0)

    def test_new_model_discards_obsolete_result(self):
        with patch.object(self.panel, '_start'):
            self.panel.auto_load_source_colors()
        old_serial = self.panel._scan_serial
        old_path = self.panel.model_path
        second = Path(self.tmp.name) / 'other.3mf'
        second.write_bytes(b'dummy')
        self.panel.set_model(str(second))
        self.panel._colors_loaded(old_serial, old_path, {'#FF0000': 3}, None)
        self.assertEqual(self.panel.source_colors, {})
        self.assertEqual(self.panel.solid_table.rowCount(), 0)


if __name__ == '__main__':
    unittest.main()
