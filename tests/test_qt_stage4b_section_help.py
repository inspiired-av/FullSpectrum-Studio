"""Stage 4B contextual-help coverage; static checks run without PySide6."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'desktop' / 'qt_app'
REQUIRED = (
    # Stage 4C view modes merit a context-specific help button.
    'preview_modes', 'source_palette_assignments',
    'live_forecast', 'expected_palette',
    'color_optimization', 'native_project_template',
    'advanced_settings', 'filament_source', 'filament_colors',
    'protect_solid_colors',
)


def source(name):
    return (UI / name).read_text(encoding='utf-8')


class ContextualHelpContractTests(unittest.TestCase):
    def test_all_topics_have_distinct_summaries_and_long_explanations(self):
        tree = ast.parse(source('section_help.py'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'TOPICS' for t in n.targets))
        topics = {}
        for key, value in zip(assignment.value.keys, assignment.value.values):
            name = ast.literal_eval(key)
            self.assertEqual(len(value.args),3)
            topics[name] = value.args
            self.assertTrue(ast.literal_eval(value.args[0]).strip())
        self.assertEqual(set(topics), set(REQUIRED))
        self.assertIn('Remove every model',source('section_help.py'))
        self.assertIn('Save Filaments',source('section_help.py'))
        self.assertIn('software estimates',source('section_help.py'))

    def test_sections_are_wired_and_template_button_removed(self):
        main = source('main_window.py')
        tab = source('filaments_tab.py')
        results = source('results_tab.py')
        for name in ('model_preview', 'source_palette'):
            self.assertNotIn(f'SectionHelpButton("{name}")', main)
        self.assertIn("SectionHelpButton('advanced_settings')", main)
        self.assertIn("SectionHelpButton('preview_modes')", main)
        for name in ('live_forecast','expected_palette','color_optimization','native_project_template'):
            self.assertIn(f'help_heading("{name}"', main)
        for name in ('filament_source', 'filament_colors', 'protect_solid_colors'):
            self.assertIn(f"help_heading('{name}'", tab)
        self.assertNotIn('help_heading(', results)
        self.assertNotIn("SectionHelpButton('optimization_details')",main)
        self.assertNotIn('About Templates', main)
        self.assertNotIn('def _about_templates(', main)
        self.assertNotIn('self.template_about', main)

    def test_accessible_tooltips_and_modal_content(self):
        content = source('section_help.py')
        for fragment in ("self.setToolTip(topic.summary)",
                         "self.setAccessibleName(f'Help: {topic.title}')",
                         "browser.setMarkdown(topic.details)",
                         "dialog.setMinimumSize(440, 300)",
                         "self.clicked.connect(self.show_help)",
                         "def create_dialog(self)"):
            self.assertIn(fragment,content)

    def test_unsaved_pin_regression_handles_absent_settings_key(self):
        test = (ROOT / 'tests/test_qt_stage4b_pin_forecast.py').read_text(encoding='utf-8')
        self.assertIn(".get('pinned_anchor_keys', [])", test)
        self.assertNotIn("['pinned_anchor_keys']", test.split('def test_unsaved_pin_affects_snapshot_and_invalidates',1)[-1].split('def test_automatic_changes',1)[0])


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None, 'PySide6 not installed')
class QtSectionHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_tooltip_and_click_content(self):
        from PySide6.QtWidgets import QTextBrowser, QDialogButtonBox
        from desktop.qt_app.section_help import TOPICS, SectionHelpButton
        b = SectionHelpButton('native_project_template')
        self.addCleanup(b.close)
        self.assertEqual(b.toolTip(), TOPICS['native_project_template'].summary)
        self.assertIn('Native Project Template', b.accessibleName())
        dialog = b.create_dialog()
        self.addCleanup(dialog.close)
        self.assertIn('Native Project Template', dialog.windowTitle())
        self.assertIn('Remove every model', dialog.findChild(QTextBrowser).toPlainText())
        self.assertIsNotNone(dialog.findChild(QDialogButtonBox))

    def test_all_workspace_sections_have_help_buttons(self):
        import tempfile
        from desktop.qt_app.main_window import MainWindow
        from desktop.qt_app.section_help import SectionHelpButton
        with tempfile.TemporaryDirectory() as temporary:
            window = MainWindow(settings_path=Path(temporary) / 'ui.json')
            try:
                buttons = window.findChildren(SectionHelpButton)
                present = {b.topic_key for b in buttons}
                self.assertEqual(present, set(REQUIRED))
                self.assertFalse(hasattr(window, 'template_about'))
            finally:
                window.close()


if __name__ == '__main__':
    unittest.main()
