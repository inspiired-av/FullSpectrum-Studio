"""Stage D2 v4: readable assignment inspector and fail-safe legacy contracts."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'desktop' / 'qt_app'


class LayoutAndHelpContracts(unittest.TestCase):
    def test_palette_swatches_precede_assigned_colors(self):
        source = (UI / 'main_window.py').read_text(encoding='utf-8')
        self.assertLess(
            source.index('palette_layout.addWidget(self.source_palette_content)'),
            source.index('palette_layout.addWidget(self.assignment_panel)'))
        self.assertIn('self.source_palette_scroll.setWidget(self.source_palette_body)', source)
        self.assertIn('palette_outer.addWidget(self.source_palette_scroll)', source)
        self.assertIn("SectionHelpButton('source_palette_assignments')", source)

    def test_source_help_explains_fidelity_and_reservation(self):
        source = (UI / 'section_help.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn("'source_palette_assignments': HelpTopic(", source)
        self.assertIn('cannot participate in mixed recipes', source)
        self.assertIn('Every occurrence', source)
        self.assertIn('standard material-colored 3MF', source)

    def test_unreserved_legacy_mixer_signature_is_preserved(self):
        source = (ROOT / 'fullspectrum_engine.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertIn("if reserved_filament_keys else {})", source)
        self.assertIn('**mixing_kwargs,', source)

    def test_legacy_assignment_warning_never_blocks_gui_tests(self):
        source = (ROOT / 'tests' / 'test_qt_stage4dd1_bulk.py').read_text(encoding='utf-8')
        self.assertIn("patch('desktop.qt_app.filaments_tab.QMessageBox.warning')", source)
        self.assertIn('test_excluding_assignment_target_is_rejected', source)


if __name__ == '__main__':
    unittest.main()
