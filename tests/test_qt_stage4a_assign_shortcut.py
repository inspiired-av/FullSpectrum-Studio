"""Stage 4A Assign Filament shortcut: lazy scanning and selection handoff."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from qt_test_cleanup import dispose_test_widget
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
QT_AVAILABLE = importlib.util.find_spec('PySide6') is not None


class SourceContractTests(unittest.TestCase):
    def test_main_shortcut_is_an_assignment_workflow(self):
        code = (ROOT / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        tree = ast.parse(code)
        main = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
        method = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == '_show_protection_controls')
        text = ast.get_source_segment(code, method)
        self.assertIn('open_assignment_dialog(self._source_palette_selected_colors)', text)
        self.assertIn('self._source_palette_selected_colors', text)
        self.assertIn("QPushButton('Assign Filament…')", code)

    def test_scan_completes_pending_selection(self):
        code = (ROOT / 'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        tree = ast.parse(code)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FilamentsTab')
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'prepare_source_assignments', '_apply_pending_assignment_selection',
                         '_colors_loaded', 'set_model'} <= set(methods))
        loaded = ast.get_source_segment(code, methods['_colors_loaded'])
        self.assertIn('self._apply_pending_assignment_selection()', loaded)
        self.assertIn('self._pending_assignment_colors = ()', ast.get_source_segment(code, methods['set_model']))


@unittest.skipUnless(QT_AVAILABLE, 'PySide6 Qt GUI is not installed')
class QtAssignmentShortcutTests(unittest.TestCase):
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
        self.source = Path(self.tmp.name) / 'sample.3mf'
        self.source.write_bytes(b'fixture')  # scanning is mocked: no actual archive is read
        self.preferences = PlanPreferences(Path(self.tmp.name) / 'settings.json')
        self.panel = FilamentsTab(self.preferences, settings_path=Path(self.tmp.name) / 'settings.json')
        self.addCleanup(dispose_test_widget, self.panel)
        self.panel.set_model(str(self.source))

    def test_unscanned_source_starts_scan_and_applies_selection_on_completion(self):
        selection = ('#0080FF', '#FF8000')
        with patch.object(self.panel, 'scan_colors') as scanner:
            self.panel.prepare_source_assignments(selection)
            scanner.assert_called_once_with()
        self.assertEqual(self.panel._pending_assignment_colors, selection)
        self.panel._colors_loaded(self.panel._scan_serial, self.panel.model_path,
                                  {'#0080FF': 15, '#FF8000': 7, '#000000': 3}, None)
        self.assertEqual(set(self.panel._selected_colors()), set(selection))
        self.assertEqual(self.panel._pending_assignment_colors, ())

    def test_already_scanned_source_does_not_rescan(self):
        self.panel.source_colors = {'#000000': 4, '#FFFFFF': 5}
        self.panel._populate_solid_colors()
        with patch.object(self.panel, 'scan_colors') as scanner:
            self.panel.prepare_source_assignments(('#FFFFFF',))
            scanner.assert_not_called()
        self.assertEqual(self.panel._selected_colors(), ('#FFFFFF',))

    def test_while_scanning_do_not_request_duplicate_scan(self):
        self.panel._source_scan_busy = True
        with patch.object(self.panel, 'scan_colors') as scanner:
            self.panel.prepare_source_assignments(('#FFFFFF',))
            self.panel.prepare_source_assignments(('#0080FF',))
            scanner.assert_not_called()
        self.assertEqual(self.panel._pending_assignment_colors, ('#0080FF',))

    def test_model_switch_invalidates_old_pending_selection(self):
        self.panel._pending_assignment_colors = ('#FFFFFF',)
        self.panel._source_scan_busy = True
        before = self.panel._scan_serial
        second = Path(self.tmp.name) / 'other.3mf'
        second.write_bytes(b'fixture')
        self.panel.set_model(str(second))
        self.assertEqual(self.panel._pending_assignment_colors, ())
        self.assertFalse(self.panel._source_scan_busy)
        self.assertEqual(self.panel._scan_serial, before + 1)


if __name__ == '__main__':
    unittest.main()
