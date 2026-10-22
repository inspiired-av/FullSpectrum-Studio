"""Stage 4A UX: stale forecasts are explicitly labelled, not destroyed."""
import unittest
import tempfile
from pathlib import Path

from desktop.qt_app.forecast_view_state import ForecastViewState


SAMPLE = {'forecast': {'accuracy': 91, 'confidence': 64,
                       'maximumDeltaE': 6.2, 'slotSummary': '5 physical + 27 mixed',
                       'colors': ['#111111', '#222222'], 'gapMessage': ''},
          'warnings': []}


class ForecastViewTests(unittest.TestCase):
    def test_invalidate_preserves_previous_for_same_model(self):
        state = ForecastViewState()
        state.reset('a.3mf')
        self.assertTrue(state.accept('a.3mf', SAMPLE))
        state.invalidate()
        self.assertTrue(state.stale)
        self.assertIs(state.previous, SAMPLE)
        self.assertEqual(state.previous['forecast']['colors'], ['#111111', '#222222'])

    def test_model_change_discards_result(self):
        state = ForecastViewState()
        state.reset('a.3mf')
        state.accept('a.3mf', SAMPLE)
        state.reset('b.3mf')
        self.assertFalse(state.has_previous)
        self.assertFalse(state.stale)
        self.assertFalse(state.accept('a.3mf', SAMPLE))
        self.assertFalse(state.has_previous)

    def test_success_replaces_previous_and_clears_stale(self):
        state = ForecastViewState()
        state.reset('a.3mf')
        state.accept('a.3mf', SAMPLE)
        state.invalidate()
        new = {'forecast': {'accuracy': 88, 'colors': ['#ABCDEF']}}
        self.assertTrue(state.accept('a.3mf', new))
        self.assertFalse(state.stale)
        self.assertIs(state.previous, new)

    def test_no_previous_is_not_stale(self):
        state = ForecastViewState()
        state.reset('a.3mf')
        state.invalidate()
        self.assertFalse(state.stale)
        self.assertFalse(state.has_previous)

    def test_source_has_explicit_stale_and_error_presentations(self):
        code = (Path(__file__).resolve().parents[1]/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('Previous forecast · {count} planned colors', code)
        self.assertIn("'Forecast unavailable: ' + str(error), 'error'", code)
        self.assertIn("if field == 'auto_preview':", code)
        self.assertIn('self._forecast_view.reset(self.state.model_path)', code)
        self.assertIn("self.forecast_palette_label.setStyleSheet", code)


class OptionalQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PySide6  # noqa
        except ImportError:
            raise unittest.SkipTest('PySide6 not installed in this environment')

    def test_previous_forecast_stays_until_refresh_or_model_change(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.qt_app.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d:
            w = MainWindow(settings_path=Path(d)/'settings.json')
            try:
                w.state.select_model(str(Path(d)/'a.3mf'))
                w._forecast_view.reset(w.state.model_path)
                w._forecast_done(w._forecast_serial, SAMPLE, None)
                self.assertEqual(w.accuracy.text(), '91%')
                self.assertEqual(w.forecast_swatch_grid.count(), 2)
                w.auto_forecast.setChecked(False)
                self.assertFalse(w._forecast_view.stale)
                w._update_plan_value('max_output_colors', '8')
                self.assertTrue(w._forecast_view.stale)
                self.assertIn('Previous forecast', w.forecast_palette_label.text())
                self.assertEqual(w.accuracy.text(), '91%')
                self.assertEqual(w.forecast_swatch_grid.count(), 2)
                w._forecast_done(w._forecast_serial, None, 'Sample validation error')
                self.assertIn('Forecast unavailable', w.forecast_status.text())
                self.assertIn('color:', w.forecast_status.styleSheet())
                self.assertEqual(w.forecast_swatch_grid.count(), 2)
                w.state.select_model(str(Path(d)/'b.3mf'))
                w._invalidate_forecast(clear_inspection=True)
                self.assertEqual(w.accuracy.text(), '—')
                self.assertEqual(w.forecast_swatch_grid.count(), 0)
            finally:
                w.close()


if __name__ == '__main__':
    unittest.main()
