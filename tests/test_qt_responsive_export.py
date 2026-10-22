"""Responsive Qt Export form: compact sidebar, accessible controls, no width clamp."""
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


class ResponsiveExportContracts(unittest.TestCase):
    def test_breakpoint_reflows_existing_widgets_not_preferences(self):
        main = MAIN.read_text(encoding='utf-8-sig')
        results = RESULTS.read_text(encoding='utf-8-sig')
        ast.parse(main)
        ast.parse(results)
        self.assertIn('self.setMinimumSize(920, 630)', main)
        self.assertIn('sidebar.setMinimumWidth(340)', main)
        self.assertNotIn('self._ensure_sidebar_visible', main)
        self.assertIn('self._arrange_export_grid(True)', main)
        self.assertIn('def _arrange_export_grid(self, compact):', main)
        self.assertIn('def _update_export_layout(self, viewport_width=None):', main)
        self.assertIn('limit = 690 if self._export_grid_compact else 650', main)
        self.assertIn('if compact != self._export_grid_compact:', main)
        self.assertIn('grid.removeWidget(widget)', main)
        self.assertIn('export_viewport_resized.connect(self._update_export_layout)', main)
        self.assertIn('export_viewport_resized = Signal(int)', results)
        self.assertIn('self.export_viewport_resized.emit(', results)
        self.assertIn("self.export_preferences_caption.setVisible(not compact)", main)
        self.assertIn('launch_modes = QGridLayout()', main)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 unavailable')
class ResponsiveExportQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        from desktop.qt_app.main_window import MainWindow
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        w = MainWindow(settings_path=Path(temp.name) / 'settings.json')
        self.addCleanup(w.close)
        w.show()
        w.tabs.setCurrentWidget(w.results_panel)
        self.pump()
        return w

    def pump(self):
        for _ in range(8):
            self.app.processEvents()

    def assert_visible_controls_inside_viewport(self, w, names):
        from PySide6.QtCore import QPoint
        viewport = w.results_panel.content_scroll.viewport()
        for name in names:
            c = getattr(w, name)
            self.assertTrue(c.isVisibleTo(w), name)
            left = c.mapTo(viewport, QPoint(0, 0)).x()
            right = c.mapTo(viewport, QPoint(c.width(), 0)).x()
            self.assertGreaterEqual(left, -2, (name, left, viewport.width()))
            self.assertLessEqual(right, viewport.width() + 2,
                                 (name, right, viewport.width()))

    def test_narrow_layout_restores_model_preview_space_and_keeps_controls(self):
        w = self.make_window()
        for width in (920, 1050, 1280):
            w.resize(width, 790)
            self.pump()
            w.splitter.setSizes([3000, 1])
            self.pump()
            self.assertGreaterEqual(w.splitter.widget(1).width(), 340)
            self.assertLess(w.splitter.widget(1).width(), 450)
            self.assertTrue(w._export_grid_compact)
            self.assert_visible_controls_inside_viewport(w,
                ('template_path', 'template_browse', 'template_clear',
                 'export_directory', 'export_directory_browse',
                 'slicer_segment', 'auto_open', 'export_advanced_toggle'))
            # Updating the layout must never change the chosen slicer.
            w.slicer_choice_buttons['Bambu Studio'].click()
            self.pump()
            self.assertEqual(w.output_application.currentData(), 'Bambu Studio')
            w.slicer_choice_buttons['OrcaSlicer'].click()
            self.pump()
            self.assertEqual(w.output_application.currentData(), 'OrcaSlicer')

    def test_advanced_settings_and_save_controls_fit_when_narrow(self):
        w = self.make_window()
        w.resize(1050, 760)
        w.splitter.setSizes([3000, 1])
        self.pump()
        w.export_advanced_toggle.setChecked(True)
        w.export_preferences_row.setVisible(True)
        self.pump()
        self.assertTrue(w._export_grid_compact)
        self.assert_visible_controls_inside_viewport(w,
            ('slicer_executable_auto', 'slicer_executable_custom',
             'export_save_settings_button', 'export_revert_settings_button'))
        self.assertFalse(w.export_preferences_caption.isVisibleTo(w))
        self.assertEqual(w._export_launch_modes.itemAtPosition(1, 0).widget(),
                         w.slicer_executable_custom)

    def test_expanded_sidebar_restores_two_columns_and_diagnostics_centers(self):
        w = self.make_window()
        w.resize(1680, 880)
        w.splitter.setSizes([700, 800])
        self.pump()
        self.assertFalse(w._export_grid_compact)
        grid = w._export_settings_grid
        self.assertIs(grid.itemAtPosition(0, 1).widget(),
                      w._export_grid_sections[1])
        self.assertIs(grid.itemAtPosition(3, 1).widget(),
                      w._export_grid_sections[5])
        w.template_warning_panel.setVisible(True)
        self.pump()
        tab = w.results_panel
        y_header = tab.diagnostics_header.mapTo(tab,tab.diagnostics_header.rect().center()).y()
        y_switch = tab.diagnostics_mode_group.mapTo(tab,tab.diagnostics_mode_group.rect().center()).y()
        self.assertGreater(y_switch, y_header)
        self.assertEqual(tab.diagnostics_mode_group.parent(), tab.diagnostics_header)
        w.splitter.setSizes([3000, 1])
        self.pump()
        self.assertTrue(w._export_grid_compact)


if __name__ == '__main__':
    unittest.main()
