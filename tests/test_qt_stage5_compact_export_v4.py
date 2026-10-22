"""Stage 5 v4: visible warning, blue slicer segment and compact executable controls."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'


class Stage5V4Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding='utf-8-sig')

    def test_source_compiles(self):
        ast.parse(self.main)

    def test_compact_warning_is_visible_and_stateful(self):
        s = self.main
        self.assertIn("grid.addWidget(self.template_attention, 1, 0, 1, 2", s)
        self.assertIn("grid.addWidget(self.template_warning_panel, 2, 0, 1, 2)", s)
        self.assertIn("self.template_attention.setChecked(bool(error or message))", s)
        self.assertIn("getattr(self, '_export_template_warning_key', None)", s)
        self.assertIn("self.template_warning_panel.setVisible(bool(checked))", s)
        self.assertNotIn("template_title.addWidget(self.template_attention)", s)
        self.assertNotIn("template_attention.clicked.connect(lambda: self.export_advanced_toggle", s)

    def test_segment_matches_reference_and_keeps_preference_combo(self):
        s = self.main
        self.assertIn("self.slicer_segment.setObjectName('exportSlicerSegment')", s)
        self.assertIn('self.slicer_segment.watch_button(button)', s)
        self.assertIn("button.setAutoExclusive(True)", s)
        self.assertIn("self.output_application.currentIndexChanged.connect(self._sync_slicer_choice_buttons)", s)

    def test_advanced_is_inline_with_switch(self):
        s = self.main
        self.assertIn("options_row.addWidget(self.auto_open, 1)", s)
        self.assertIn("options_row.addWidget(self.export_advanced_toggle)", s)
        self.assertIn("grid.addWidget(slicer_box, 3, 0, Qt.AlignmentFlag.AlignTop)", s)
        self.assertIn("grid.addWidget(options_box, 3, 1, Qt.AlignmentFlag.AlignTop)", s)
        self.assertNotIn("options_head.addWidget(self.export_advanced_toggle)", s)

    def test_executable_modes_reuse_existing_preference(self):
        s = self.main
        self.assertIn("QRadioButton('Automatic detection')", s)
        self.assertIn("QRadioButton('Custom executable')", s)
        self.assertIn('self.slicer_executable_custom.toggled.connect(', s)
        self.assertIn('self.slicer_executable_browse.clicked.connect(self._browse_slicer_executable)', s)
        self.assertIn('self.slicer_executable_auto.toggled.connect(self._automatic_slicer_mode_selected)', s)
        self.assertIn("self.slicer_executable_status.setToolTip(tooltip)", s)
        self.assertIn('self.export_preferences_row.setVisible(dirty)', s)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 unavailable')
class Stage5V4QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def open_window(self):
        from desktop.qt_app.main_window import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        w = MainWindow(settings_path=Path(self.tmp.name) / 'settings.json')
        self.addCleanup(w.close)
        w.show()
        w.tabs.setCurrentWidget(w.results_panel)
        self.app.processEvents()
        return w

    def test_actual_compatibility_warning_opens_by_default_and_stays_closed(self):
        w = self.open_window()
        info = {'path': 'C:/demo.3mf', 'slicer': 'OrcaSlicer',
                'slicerVersion': '2.5.0-alpha', 'printerPreset': 'H2C',
                'nozzle': '0.4', 'processPreset': 'High Quality'}
        w.template_path.setText('C:/demo.3mf')
        with (patch('native_project_template.inspect_template', return_value=info),
              patch('orca_profile_warning.orca_h2c_warning',
                    return_value='H2C requires a compatible slicer build.')):
            w._refresh_dependent_plan_widgets()
            self.app.processEvents()
            self.assertTrue(w.template_warning_panel.isVisibleTo(w))
            self.assertTrue(w.template_attention.isChecked())
            w.template_attention.click()
            self.app.processEvents()
            self.assertFalse(w.template_warning_panel.isVisibleTo(w))
            w._refresh_dependent_plan_widgets()
            self.app.processEvents()
            self.assertFalse(w.template_warning_panel.isVisibleTo(w))
            w._set_combo_value(w.output_application, 'OrcaSlicer')
            self.app.processEvents()
            # The warning changed (template/slicer mismatch disappeared).
            self.assertTrue(w.template_warning_panel.isVisibleTo(w))
        self.assertFalse(w.export_advanced_panel.isVisibleTo(w))

    def test_switch_and_advanced_share_baseline(self):
        w = self.open_window()
        seg = w.slicer_segment
        adv = w.export_advanced_toggle
        first = seg.mapTo(w, seg.rect().center()).y()
        second = adv.mapTo(w, adv.rect().center()).y()
        # Wide Export keeps the controls on one row; narrow stacks them.
        if w._export_grid_compact:
            self.assertGreater(abs(first-second), 10)
        else:
            self.assertLess(abs(first-second), 10)
        self.assertEqual(w.slicer_segment.selected_color.name(), '#2183f5')
        w.slicer_choice_buttons['OrcaSlicer'].click()
        self.assertEqual(w.output_application.currentData(), 'OrcaSlicer')
        self.assertTrue(w.slicer_choice_buttons['OrcaSlicer'].isChecked())

    def test_executable_auto_and_custom_mode(self):
        w = self.open_window()
        w.export_advanced_toggle.click()
        self.app.processEvents()
        self.assertTrue(w.export_advanced_panel.isVisibleTo(w))
        self.assertTrue(w.slicer_executable_auto.isChecked())
        self.assertFalse(w.slicer_custom_controls.isVisibleTo(w))
        fake = Path(self.tmp.name) / 'OrcaSlicer.exe'
        fake.write_bytes(b'mock')
        w.slicer_choice_buttons['OrcaSlicer'].click()
        w._update_plan_value('orcaslicer_executable', str(fake))
        self.app.processEvents()
        self.assertTrue(w.slicer_executable_custom.isChecked())
        self.assertTrue(w.slicer_custom_controls.isVisibleTo(w))
        self.assertIn(str(fake), w.slicer_executable_status.text())
        w.slicer_executable_auto.click()
        self.app.processEvents()
        self.assertTrue(w.slicer_executable_auto.isChecked())
        self.assertFalse(w.slicer_custom_controls.isVisibleTo(w))
        self.assertEqual(w.plan_preferences.get('orcaslicer_executable'), '')


if __name__ == '__main__':
    unittest.main()
