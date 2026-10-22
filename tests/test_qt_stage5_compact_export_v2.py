"""Stage 5 v2 spacing, icon and compatibility layout regression checks."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
QT=ROOT/'desktop'/'qt_app'

def source(path):
    return (QT/path).read_text(encoding='utf-8-sig')

class Stage5VisualContracts(unittest.TestCase):
    def test_icons_have_no_runtime_font_or_extra_asset_dependency(self):
        s=source('export_ui_icons.py')
        ast.parse(s)
        self.assertIn('QPainter',s)
        self.assertIn('QPixmap',s)
        self.assertNotIn('QSvgRenderer',s)
        self.assertNotIn('from PIL',s)

    def test_compact_buttons_are_uniform_and_accessible(self):
        s=source('main_window.py')
        self.assertIn("compact_icon_button(self.template_browse, 'folder'",s)
        self.assertIn("compact_icon_button(self.template_clear, 'x'",s)
        self.assertIn("compact_icon_button(self.export_directory_browse, 'folder'",s)
        self.assertIn('button.setMinimumHeight(34)',s)
        self.assertIn('self.export_directory.setMinimumHeight(34)',s)
        self.assertIn('self.template_path.setMinimumHeight(34)',s)
        self.assertIn('self.compose_button.setIcon(export_icon(',s)

    def test_compatibility_attaches_to_template_not_full_width(self):
        s=source('main_window.py')
        start=s.index('    def _build_export_settings(')
        end=s.index('    def _sync_slicer_choice_buttons(',start)
        method=s[start:end]
        self.assertIn('grid.addWidget(self.template_attention, 1, 0, 1, 2',method)
        self.assertNotIn("col.addWidget(self.template_attention)",method)
        self.assertIn('options_row.addWidget(self.export_advanced_toggle)',method)
        self.assertNotIn('col.addLayout(controls)',method)
        self.assertIn('col.addWidget(self.export_advanced_panel)',method)

    def test_diagnostics_icons_are_uniform_and_contextual(self):
        s=source('results_tab.py')
        for icon in ('folder','copy','trash','down','info'):
            self.assertIn("'"+icon+"'",s)
        self.assertIn('self.diagnostics_collapse.setIcon(export_icon(',s)
        self.assertIn("self._select_diagnostics('report')",s)

    def test_older_export_tests_follow_stage5_structure(self):
        for path in ('tests/test_qt_stage4b_help_polish.py',
                     'tests/test_qt_stage4b_section_help.py',
                     'tests/test_qt_stage4dc_export_workspace.py'):
            ast.parse((ROOT/path).read_text(encoding='utf-8'))
        s=source('results_tab.py')
        self.assertIn("self.diagnostics_stack.setObjectName('exportDiagnosticsStack')",s)

@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class Stage5VisualQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_button_icons_render_and_sizes_match(self):
        from desktop.qt_app.main_window import MainWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=MainWindow(settings_path=Path(tmp)/'settings.json')
            self.addCleanup(w.close)
            w.show()
            w.tabs.setCurrentWidget(w.results_panel)
            self.app.processEvents()
            for b in (w.template_browse,w.template_clear,w.export_directory_browse):
                self.assertEqual((b.width(),b.height()),(34,34))
                self.assertFalse(b.icon().isNull())
                self.assertTrue(b.toolTip())
            self.assertGreaterEqual(w.template_path.height(),34)
            self.assertEqual(w.template_path.height(),w.export_directory.height())
            self.assertFalse(w.export_advanced_panel.isVisibleTo(w))
            w.export_advanced_toggle.click()
            self.app.processEvents()
            self.assertTrue(w.export_advanced_panel.isVisibleTo(w))

    def test_compatibility_no_extra_row_and_header_icons(self):
        from desktop.qt_app.main_window import MainWindow
        with tempfile.TemporaryDirectory() as tmp:
            w=MainWindow(settings_path=Path(tmp)/'settings.json')
            self.addCleanup(w.close)
            w.show();w.tabs.setCurrentWidget(w.results_panel)
            self.app.processEvents()
            self.assertFalse(w.template_attention.icon().isNull())
            self.assertFalse(w.results_panel.session_toggle.icon().isNull())
            self.assertFalse(w.results_panel.copy_activity_button.icon().isNull())
            self.assertFalse(w.results_panel.diagnostics_collapse.icon().isNull())
            self.assertTrue(w.template_attention.isVisibleTo(w))
            w.template_attention.click();self.app.processEvents()
            self.assertTrue(w.template_warning_panel.isVisibleTo(w))
            self.assertFalse(w.export_advanced_panel.isVisibleTo(w))
            w.template_attention.click();self.app.processEvents()
            self.assertFalse(w.template_warning_panel.isVisibleTo(w))

if __name__=='__main__':unittest.main()
