"""Pure source and optional GUI regression checks for Stage 4B forecast parity."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ForecastVisualContractTests(unittest.TestCase):
    def test_sources_compile(self):
        for f in ('main_window.py','forecast_visuals.py','section_help.py'):
            ast.parse((ROOT/'desktop/qt_app'/f).read_text(encoding='utf-8'))
    def test_old_forecast_cache_retained_on_invalidate(self):
        s=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.worst_match_panel.set_forecast(None)',s)
        self.assertIn('self.worst_match_panel.set_forecast(forecast)',s)
        self.assertIn('self.confidence_gauge.set_value(forecast[',s)
        self.assertIn('if not self._forecast_view.has_previous:',s)
    def test_help_has_square_circular_geometry(self):
        s=(ROOT/'desktop/qt_app/section_help.py').read_text(encoding='utf-8')
        self.assertIn('self.setFixedSize(20, 20)',s)
        self.assertIn('painter.drawEllipse(QPointF(center_x, center_y), radius, radius)',s)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.forecast_visuals import RingGauge, WorstMatchPanel, worst_pair
except ImportError:
    QApplication=None

@unittest.skipIf(QApplication is None,'PySide6 not installed')
class QtForecastVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])
    def test_render_real_worst_match_and_missing_state(self):
        self.assertEqual(worst_pair({'gapMessage':'Worst target #2088A0 becomes #4581A9 (dE 9.0).'}),('#2088A0','#4581A9'))
        self.assertIsNone(worst_pair({'gapMessage':'No mismatch'}))
        panel=WorstMatchPanel()
        panel.set_forecast({'gapMessage':'Worst target #2088A0 becomes #4581A9 (dE 9.0).','maximumDeltaE':9.0})
        self.assertIn('#2088A0',panel.source[1].toolTip())
        self.assertIn('#4581A9',panel.predicted[1].toolTip())
        panel.set_forecast({})
        self.assertIn('unavailable',panel.source[1].toolTip())
        panel.close()
    def test_clamps_invalid_progress(self):
        ring=RingGauge('Accuracy')
        ring.set_value(123)
        self.assertEqual(ring.value,100)
        ring.set_value(None)
        self.assertIsNone(ring.value)
        ring.close()
