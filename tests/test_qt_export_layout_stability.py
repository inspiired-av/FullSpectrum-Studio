"""Regression tests for compact slicer sizing and Diagnostics header alignment.

Older Stage 5 snapshots can remain as historical contracts; these checks focus
on the behavior users see after visibility changes and font scaling.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENT = ROOT / 'desktop/qt_app/export_slicer_segment.py'
MAIN = ROOT / 'desktop/qt_app/main_window.py'
RESULTS = ROOT / 'desktop/qt_app/results_tab.py'


class ExportLayoutContracts(unittest.TestCase):
    def test_sources_compile_and_no_contradictory_slicer_minimum(self):
        s = SEGMENT.read_text(encoding='utf-8-sig')
        main = MAIN.read_text(encoding='utf-8-sig')
        ast.parse(s)
        ast.parse(main)
        self.assertNotIn('self.setMinimumWidth(2 * half)', s)
        self.assertIn('self.slicer_segment.setMaximumWidth(268)', main)
        self.assertIn('self.slicer_segment.setMinimumWidth(240)', main)
        self.assertIn('QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding', main)
        self.assertIn('metrics.elidedText(', s)

    def test_diagnostics_reacts_to_relayout_and_header_movement(self):
        text = RESULTS.read_text(encoding='utf-8-sig')
        ast.parse(text)
        self.assertIn('self.diagnostics_mode_group = QWidget(self.diagnostics_header)', text)
        self.assertIn('diagnostics_head.addWidget(', text)
        self.assertIn('self.export_viewport_resized.emit(', text)
        self.assertNotIn('group.move(x, y)', text)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 unavailable')
class ExportLayoutQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def create_window(self):
        from desktop.qt_app.main_window import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        w = MainWindow(settings_path=Path(tmp.name) / 'settings.json')
        self.addCleanup(w.close)
        w.resize(1340, 860)
        w.show()
        w.tabs.setCurrentWidget(w.results_panel)
        self.pump()
        return w

    def pump(self):
        # Qt may schedule several nested LayoutRequests in the same interaction.
        for _ in range(4):
            self.app.processEvents()

    def assert_centered_on_header(self, w):
        tab = w.results_panel
        group = tab.diagnostics_mode_group
        header = tab.diagnostics_header
        self.pump()
        self.assertTrue(group.isVisibleTo(w))
        yc = group.mapTo(tab, group.rect().center()).y()
        yh = header.mapTo(tab, header.rect().center()).y()
        self.assertGreater(yc, yh, (yc, yh))
        self.assertIs(group.parent(), header)
        xc = group.mapTo(tab, group.rect().center()).x()
        hx = header.mapTo(tab, header.rect().center()).x()
        self.assertLessEqual(abs(xc - hx), 4, (xc, hx))

    def test_slicer_width_and_equal_hit_targets_at_multiple_sizes(self):
        w = self.create_window()
        for width in (1120, 1340, 1640):
            w.resize(width, 820)
            self.pump()
            pill = w.slicer_segment
            self.assertGreaterEqual(pill.width(), 240)
            self.assertLessEqual(pill.width(), 268)
            a, b = w.slicer_choice_buttons.values()
            self.assertLessEqual(abs(a.width() - b.width()), 1)
            self.assertLessEqual(abs(a.width() + b.width() - pill.width()), 1)
            for name in ('OrcaSlicer', 'Bambu Studio'):
                w.slicer_choice_buttons[name].click()
                self.pump()
                self.assertEqual(w.output_application.currentData(), name)

    def test_diagnostics_switch_tracks_visibility_and_dynamic_row_height(self):
        w = self.create_window()
        self.assert_centered_on_header(w)
        # Compatibility disclosure moves the diagnostics header without
        # changing its own size; that is the regression being covered.
        w.template_warning_panel.setVisible(True)
        self.assert_centered_on_header(w)
        w.template_warning_panel.setVisible(False)
        self.assert_centered_on_header(w)
        # Advanced options and unsaved settings also modify the rows above.
        w.export_advanced_toggle.click()
        self.assert_centered_on_header(w)
        w.export_advanced_toggle.click()
        self.assert_centered_on_header(w)
        w.export_preferences_row.setVisible(True)
        self.assert_centered_on_header(w)
        w.export_preferences_row.setVisible(False)
        self.assert_centered_on_header(w)
        for mode in ('report', 'activity'):
            w.results_panel._select_diagnostics(mode)
            self.assert_centered_on_header(w)


if __name__ == '__main__':
    unittest.main()
