"""Stage 4C visual polish: tests must run from the installed repo, not ZIP."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINDOW = ROOT / 'desktop/qt_app/main_window.py'
VISUALS = ROOT / 'desktop/qt_app/forecast_visuals.py'
HELP = ROOT / 'desktop/qt_app/section_help.py'
LEGEND = ROOT / 'desktop/qt_app/preview_legend.py'


def pure_forecast_guidance():
    """Isolate a pure helper without requiring Qt in headless engine CI."""
    source = ast.parse(VISUALS.read_text(encoding='utf-8'))
    func = next(node for node in source.body
                if isinstance(node, ast.FunctionDef) and node.name == 'forecast_guidance')
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[])),
                 str(VISUALS), 'exec'), ns)
    return ns['forecast_guidance']


class VisualPolishContractTests(unittest.TestCase):
    def test_sources_are_utf8_and_parseable(self):
        for path in (WINDOW, VISUALS, HELP, LEGEND):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding='utf-8'))

    def test_preview_help_is_by_mode_selector_not_section_heading(self):
        text = WINDOW.read_text(encoding='utf-8')
        self.assertIn("SectionHelpButton('preview_modes')", text)
        self.assertIn('row.addWidget(self.preview_mode_help)', text)
        self.assertNotIn('help_heading("model_preview"', text)
        self.assertIn("'preview_modes': HelpTopic(", HELP.read_text(encoding='utf-8'))

    def test_help_has_truthful_explanations(self):
        help_text = HELP.read_text(encoding='utf-8')
        for phrase in ('**Original**', '**Predicted**', '**Color Loss**',
                       '**Anchor Influence**', '**Wireframe**', 'OUTDATED'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, help_text)

    def test_color_loss_key_is_viewport_overlay(self):
        window = WINDOW.read_text(encoding='utf-8')
        code = LEGEND.read_text(encoding='utf-8')
        self.assertIn('ColorLossLegend(self.preview_surface)', window)
        self.assertIn("self.preview_legend.setVisible(name == 'Color Loss'", window)
        self.assertIn('viewport.installEventFilter(self)', code)
        self.assertIn('WA_TransparentForMouseEvents', code)
        for key in ('#37C977', '#F5D725', '#F54A1F', 'ΔE ≤ 2', 'ΔE 2–6', 'ΔE > 6'):
            with self.subTest(key=key):
                self.assertIn(key, code)

    def test_worst_match_has_only_one_maximum_error_display(self):
        window = WINDOW.read_text(encoding='utf-8')
        self.assertIn('"Mean ΔE"', window)
        self.assertIn("(result.get('quality') or {}).get('estimatedDeltaE')", window)
        self.assertNotIn("self.forecast_metrics['Worst match']", window)
        self.assertIn('self.worst_match_panel.set_forecast(forecast)', window)
        self.assertIn('forecast_guidance(forecast, warnings)', window)
        visuals = VISUALS.read_text(encoding='utf-8')
        self.assertIn("self.delta.setText(f'ΔE {value:.1f}'", visuals)

    def test_guidance_does_not_repeat_colors(self):
        guidance = pure_forecast_guidance()
        forecast = {'gapMessage': 'Worst target #000000 becomes #FFFFFF (dE 20.0).'}
        self.assertEqual(guidance(forecast, []), '')
        self.assertEqual(guidance(forecast, ['Catalog colors are estimates.']),
                         'Note: Catalog colors are estimates.')
        forecast['suggestion'] = {'name': 'PLA Blue', 'availability': 'not in My Inventory'}
        message = guidance(forecast, [])
        self.assertIn('PLA Blue', message)
        self.assertNotIn('Worst target', message)
        self.assertNotIn('dE 20', message)

    def test_preview_is_still_read_only_and_source_is_untouched(self):
        window = WINDOW.read_text(encoding='utf-8')
        self.assertIn('self._live_preview_stale', window)
        self.assertIn('self.preview_surface.set_mesh(target, preserve_camera=True)', window)
        self.assertIn('No native 3MF was exported', window)


try:
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtCore import Qt
    from desktop.qt_app.preview_legend import ColorLossLegend
    from desktop.qt_app.section_help import SectionHelpButton
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, 'PySide6 not installed')
class OptionalQtVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_color_legend_fits_parent_and_ignores_mouse(self):
        view = QWidget()
        view.resize(520, 350)
        legend = ColorLossLegend(view)
        try:
            legend.show()
            self.assertEqual(legend.parentWidget(), view)
            self.assertTrue(legend.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertEqual(len(legend.segments), 3)
            view.resize(310, 240)
            self.app.processEvents()
            legend.position_over_viewport()
            self.assertLessEqual(legend.x() + legend.width(), view.width())
            self.assertLessEqual(legend.y() + legend.height(), view.height())
        finally:
            view.close()

    def test_new_help_button_is_a_visible_circle(self):
        btn = SectionHelpButton('preview_modes')
        try:
            self.assertEqual(btn.size().width(), btn.size().height())
            self.assertEqual(btn.text(), '?')
            self.assertIn('Model Preview Modes', btn.accessibleName())
        finally:
            btn.close()


if __name__ == '__main__':
    unittest.main()
