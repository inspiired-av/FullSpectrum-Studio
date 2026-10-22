"""Stage 5 v5: explicit slicer modes, single-footprint progress and responsive diagnostics."""
from __future__ import annotations
import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT/'desktop/qt_app/main_window.py'
RESULTS = ROOT/'desktop/qt_app/results_tab.py'

class V5Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding='utf-8-sig')
        cls.results = RESULTS.read_text(encoding='utf-8-sig')

    def test_source_syntax(self):
        ast.parse(self.main)
        ast.parse(self.results)

    def test_advanced_does_not_contain_preferences(self):
        self.assertIn("QRadioButton('Automatic detection')", self.main)
        self.assertIn("QRadioButton('Custom executable')", self.main)
        self.assertIn('self.slicer_custom_controls.setVisible(bool(path))', self.main)
        self.assertIn('self.export_preferences_row.setVisible(dirty)', self.main)
        self.assertIn('self.export_preferences_row.hide()', self.main)
        self.assertIn('self.slicer_executable_auto.toggled.connect(self._automatic_slicer_mode_selected)', self.main)

    def test_existing_executable_path_survives_restore(self):
        self.assertIn('with QSignalBlocker(self.slicer_executable_auto)', self.main)
        self.assertIn("self.slicer_executable_status.setText('Custom executable · ' + path)", self.main)
        self.assertIn("self.slicer_executable_status.setToolTip(tooltip)", self.main)
        self.assertIn('self._clear_slicer_executable()', self.main)

    def test_export_progress_replaces_main_button_not_second_row(self):
        text = self.main.split('    def _build_export_actions(self):',1)[1].split('\n    def ',1)[0]
        self.assertIn('self.export_action_stack = QStackedWidget()', text)
        self.assertIn('self.export_action_stack.addWidget(self.compose_button)', text)
        self.assertIn('self.export_action_stack.addWidget(self.export_progress)', text)
        self.assertIn('export_row.addWidget(self.export_cancel_button)', text)
        self.assertNotIn('col.addWidget(self.export_progress)', text)
        self.assertNotIn('col.addWidget(self.export_cancel_button)', text)
        self.assertIn('self.export_action_stack.setCurrentIndex(1 if busy else 0)', self.main)

    def test_cancel_does_not_repeat_status_under_button(self):
        text = self.main.split('    def _export_finished(self,',1)[1].split('\n    def ',1)[0]
        self.assertIn('self.export_status.setVisible(not cancelled)', text)
        self.assertIn("'warning' if cancelled else 'error'", text)
        self.assertIn('self.export_status.hide()', text)

    def test_diagnostics_are_centered_and_responsive(self):
        self.assertIn('self.diagnostics_header = QWidget()', self.results)
        self.assertIn('self.diagnostics_mode_group = QWidget(self.diagnostics_header)', self.results)
        self.assertIn('diagnostics_head.addWidget(', self.results)
        self.assertIn('self.content_scroll.viewport().installEventFilter(self)', self.results)
        # The movement-aware filter caches event.type() in `kind` so
        # Resize and LayoutRequest can both trigger a queued recenter.
        self.assertIn('and event.type() == QEvent.Type.Resize', self.results)
        # The compact-header implementation removed the overlay recenter API.
        # No responsive layout callback may invoke that deleted method.
        self.assertNotIn('_queue_diagnostics_recenter', self.main)
        self.assertIn('QEvent.Type.Resize', self.results)
        self.assertIn('min(440, int(viewport_height * 0.48))', self.results)
        self.assertNotIn('setMaximumHeight(200)', self.results)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 unavailable')
class V5QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def open_window(self):
        from desktop.qt_app.main_window import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        window = MainWindow(settings_path=Path(tmp.name)/'prefs.json')
        self.addCleanup(window.close)
        window.show()
        window.tabs.setCurrentWidget(window.results_panel)
        self.app.processEvents()
        return window, Path(tmp.name)

    def test_executable_mode_and_independent_preference(self):
        w,tmp = self.open_window()
        w.export_advanced_toggle.setChecked(True)
        self.app.processEvents()
        self.assertTrue(w.slicer_executable_auto.isChecked())
        self.assertFalse(w.slicer_custom_controls.isVisibleTo(w))
        w.slicer_executable_custom.click()
        self.app.processEvents()
        self.assertTrue(w.slicer_custom_controls.isVisibleTo(w))
        self.assertEqual(w.plan_preferences.get(w._selected_slicer_executable_key()), '')
        file = tmp/'OrcaSlicer.exe'
        file.write_bytes(b'MZ')
        w._set_combo_value(w.output_application, 'OrcaSlicer')
        with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName', return_value=(str(file), '')):
            w.slicer_executable_browse.click()
        self.assertIn(str(file), w.slicer_executable_status.text())
        w._set_combo_value(w.output_application, 'Bambu Studio')
        self.assertTrue(w.slicer_executable_auto.isChecked())
        w._set_combo_value(w.output_application, 'OrcaSlicer')
        self.assertTrue(w.slicer_executable_custom.isChecked())
        w.slicer_executable_auto.click()
        self.assertEqual(w.plan_preferences.get('orcaslicer_executable'), '')

    def test_stacked_action_and_cancel_during_export(self):
        w,_ = self.open_window()
        self.assertIs(w.export_action_stack.currentWidget(), w.compose_button)
        self.assertFalse(w.export_cancel_button.isVisibleTo(w))
        # No worker is started: simulate the visual busy state only.
        w.export_action_stack.setCurrentWidget(w.export_progress)
        w.export_cancel_button.show()
        self.app.processEvents()
        self.assertTrue(w.export_cancel_button.isVisibleTo(w))
        self.assertTrue(w.export_progress.isVisibleTo(w))
        self.assertFalse(w.compose_button.isVisibleTo(w))

    def test_diagnostics_height_and_center_across_window_sizes(self):
        w,_ = self.open_window()
        tab = w.results_panel
        for width,height in ((1220,760),(1640,1040)):
            w.resize(width,height)
            self.app.processEvents()
            viewport = tab.content_scroll.viewport().height()
            expected = max(190,min(440,int(viewport*.48)))
            self.assertAlmostEqual(tab.diagnostics_stack.height(),expected,delta=3)
            center = tab.diagnostics_mode_group.mapTo(tab,tab.diagnostics_mode_group.rect().center()).x()
            mid = tab.width()/2
            self.assertLess(abs(center-mid),55)

if __name__=='__main__':
    unittest.main()
