"""Stage 5 v3: toggle isolation, diagnostic layout and readable sizing."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
QT = ROOT/'desktop'/'qt_app'

def read(path):
    return (QT/path).read_text(encoding='utf-8-sig')

class Stage5V3Contracts(unittest.TestCase):
    def test_all_sources_compile(self):
        for path in ('main_window.py','results_tab.py','export_ui_icons.py'):
            ast.parse(read(path))

    def test_warning_is_separate_from_advanced(self):
        main=read('main_window.py')
        self.assertIn('exportTemplateWarningPanel',main)
        self.assertIn('self.template_attention.toggled.connect(self._toggle_template_warning)',main)
        self.assertIn('self.template_warning_panel.setVisible(bool(checked))',main)
        self.assertNotIn('self.template_attention.clicked.connect(lambda: self.export_advanced_toggle',main)
        self.assertIn('self.export_advanced_toggle.toggled.connect(self.export_advanced_panel.setVisible)',main)
        self.assertNotIn('self.template_compatibility = _label',main[main.index('        # Only slicer-launch configuration belongs under Advanced.'):main.index('    def _toggle_template_warning')])

    def test_warning_note_is_under_output_paths(self):
        src=read('main_window.py')
        self.assertIn('grid.addWidget(self.template_attention, 1, 0, 1, 2',src)
        self.assertIn('grid.addWidget(self.template_warning_panel, 2, 0, 1, 2)',src)
        self.assertNotIn('template_title.addWidget(self.template_attention)',src)
        self.assertIn('template_help.setSizePolicy(QSizePolicy.Policy.Maximum',src)

    def test_controls_are_font_safe_and_consistent(self):
        src=read('main_window.py')
        self.assertIn('self.template_path.setMinimumHeight(34)',src)
        self.assertIn('self.export_directory.setMinimumHeight(34)',src)
        self.assertIn("compact_icon_button(self.template_browse, 'folder', 'Browse native project template', side=34)",src)
        self.assertIn("compact_icon_button(self.export_directory_browse, 'folder', 'Browse output directory', side=34)",src)
        self.assertNotIn('self.template_path.setFixedHeight(28)',src)
        self.assertNotIn('self.export_cancel_button.setFixedHeight(28)',src)

    def test_advanced_is_only_about_slicer_launch(self):
        src=read('main_window.py')
        self.assertIn("_label('SLICER LAUNCH', 'sectionTitle')",src)
        self.assertIn("QRadioButton('Automatic detection')",src)
        self.assertIn("QRadioButton('Custom executable')",src)
        self.assertIn('col.addWidget(self.export_preferences_row)',src)
        self.assertIn("self.export_advanced_toggle.setIcon(export_icon('settings'))",src)
        icons=read('export_ui_icons.py')
        self.assertIn("elif name == 'settings':",icons)

    def test_filename_file_icon_and_centered_diagnostics(self):
        src=read('results_tab.py')
        self.assertIn('exportFileIcon',src)
        self.assertIn("export_icon('file', '#89d9c3')",src)
        self.assertIn('self.export_summary_row.show()',src)
        # The selector is a normal second header row, not a floating overlay.
        self.assertIn('self.diagnostics_mode_group = QWidget(self.diagnostics_header)',src)
        self.assertIn('diagnostics_head.addWidget(',src)
        self.assertIn('self.diagnostics_mode_group, 0, Qt.AlignmentFlag.AlignHCenter',src)
        self.assertNotIn('def _center_diagnostics_switch(self):',src)

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 unavailable')
class Stage5V3QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def open_window(self):
        from desktop.qt_app.main_window import MainWindow
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        w=MainWindow(settings_path=Path(self.tmp.name)/'settings.json')
        self.addCleanup(w.close)
        w.show()
        w.tabs.setCurrentWidget(w.results_panel)
        self.app.processEvents()
        return w

    def test_warning_and_advanced_are_independent(self):
        w=self.open_window()
        self.assertTrue(w.template_attention.isVisibleTo(w))
        self.assertFalse(w.template_warning_panel.isVisibleTo(w))
        self.assertFalse(w.export_advanced_panel.isVisibleTo(w))
        w.template_attention.click();self.app.processEvents()
        self.assertTrue(w.template_warning_panel.isVisibleTo(w))
        self.assertFalse(w.export_advanced_panel.isVisibleTo(w))
        w.export_advanced_toggle.click();self.app.processEvents()
        self.assertTrue(w.template_warning_panel.isVisibleTo(w))
        self.assertTrue(w.export_advanced_panel.isVisibleTo(w))
        w.template_attention.click();self.app.processEvents()
        self.assertFalse(w.template_warning_panel.isVisibleTo(w))
        self.assertTrue(w.export_advanced_panel.isVisibleTo(w))

    def test_wider_control_heights_and_file_icon(self):
        w=self.open_window()
        self.assertEqual(w.template_path.height(),w.export_directory.height())
        self.assertGreaterEqual(w.template_path.height(),34)
        self.assertEqual(w.template_browse.height(),34)
        self.assertEqual(w.export_directory_browse.height(),34)
        self.assertFalse(w.export_advanced_toggle.icon().isNull())
        w.results_panel.set_export_result({'output':str(Path(self.tmp.name)/'demo.3mf'), 'slicer':'OrcaSlicer'})
        self.app.processEvents()
        self.assertTrue(w.results_panel.export_summary_row.isVisibleTo(w))
        self.assertFalse(w.results_panel.export_file_icon.pixmap().isNull())

    def test_activity_report_mode_center(self):
        w=self.open_window()
        tab=w.results_panel
        center=tab.diagnostics_mode_group.mapTo(tab,tab.diagnostics_mode_group.rect().center()).x()
        midpoint=tab.width()/2
        self.assertLess(abs(center-midpoint),55)
        self.assertTrue(tab.activity_toggle.isChecked())
        tab.report_toggle.click();self.app.processEvents()
        self.assertTrue(tab.report_toggle.isChecked())
        self.assertTrue(tab.open_report_button.isVisibleTo(tab))

if __name__=='__main__':unittest.main()
