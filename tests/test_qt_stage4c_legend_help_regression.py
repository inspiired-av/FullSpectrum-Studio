"""Stage 4C: legend QSS is valid and help-topic lists agree with the UI."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'desktop/qt_app'

class LegendAndHelpRegressionTests(unittest.TestCase):
    def test_segment_qss_has_one_brace_pair_per_rule(self):
        tree = ast.parse((UI/'preview_legend.py').read_text(encoding='utf-8'))
        style_calls = [node for node in ast.walk(tree)
                       if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute)
                       and node.func.attr == 'setStyleSheet'
                       and isinstance(node.func.value, ast.Name)
                       and node.func.value.id == 'swatch']
        self.assertEqual(len(style_calls), 1)
        expr = ast.Expression(body=style_calls[0].args[0])
        style = eval(compile(ast.fix_missing_locations(expr), str(UI/'preview_legend.py'), 'eval'),
                     {'__builtins__': {}}, {'color': '#37C977'})
        self.assertEqual(style.count('{'), 1)
        self.assertEqual(style.count('}'), 1)
        self.assertTrue(style.strip().endswith('}'))
        self.assertIn('background-color: #37C977;', style)
        self.assertIn('border-radius: 3px;', style)

    def test_stage4c_topic_is_registered_and_wired_only_to_preview_selector(self):
        help_file = (UI/'section_help.py').read_text(encoding='utf-8')
        main_file = (UI/'main_window.py').read_text(encoding='utf-8')
        results_file = (UI/'results_tab.py').read_text(encoding='utf-8')
        self.assertIn("'preview_modes': HelpTopic(", help_file)
        self.assertIn("SectionHelpButton('preview_modes')", main_file)
        self.assertNotIn("SectionHelpButton('preview_modes')", results_file)
        self.assertNotIn("SectionHelpButton('model_preview')", main_file)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,
                     'PySide6 unavailable in this environment')
class QtLegendParsingTests(unittest.TestCase):
    def test_qt_does_not_report_malformed_legend_stylesheet(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication, QWidget
        from desktop.qt_app.preview_legend import ColorLossLegend
        app = QApplication.instance() or QApplication([])
        warnings = []
        def handler(level, context, message):
            warnings.append(str(message))
        previous = qInstallMessageHandler(handler)
        parent = QWidget()
        try:
            parent.resize(490, 310)
            legend = ColorLossLegend(parent)
            parent.show()
            legend.show()
            app.processEvents()
            self.assertEqual(len(legend.segments), 3)
        finally:
            parent.close()
            qInstallMessageHandler(previous)
        self.assertFalse([msg for msg in warnings
                          if 'Could not parse stylesheet' in msg], warnings)

if __name__ == '__main__':
    unittest.main()
