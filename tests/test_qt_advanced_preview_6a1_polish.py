"""Stage 6A1 final polish: forecast badge star and fair countdown visibility."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHROME = ROOT / 'desktop/qt_app/preview_chrome.py'
OVERLAY = ROOT / 'desktop/qt_app/forecast_countdown_overlay.py'


class PreviewPolishContracts(unittest.TestCase):
    def test_valid_python_and_no_second_forecast_scheduler(self):
        chrome = CHROME.read_text(encoding='utf-8')
        overlay = OVERLAY.read_text(encoding='utf-8')
        ast.parse(chrome)
        ast.parse(overlay)
        self.assertIn('QTimer.start(timer)', overlay)
        self.assertIn('self._reset_on_first_paint = True', overlay)
        self.assertNotIn('ForecastWorker', overlay)
        self.assertNotIn('make_request(', overlay)

    def test_sparkle_is_a_real_vector_icon_not_a_font_character(self):
        code = CHROME.read_text(encoding='utf-8')
        self.assertIn('def _estimate_sparkle(', code)
        self.assertIn('QPainterPath()', code)
        self.assertIn('previewEstimateSparkle', code)
        self.assertIn("'#71d7dc'", code)
        self.assertIn('padding: 5px 9px 5px 29px', code)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class QtPreviewPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_badge_icon_exists_and_is_visually_centered(self):
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_chrome import PreviewChrome
        parent = QWidget()
        parent.resize(640, 480)
        parent.show()
        self.addCleanup(parent.close)
        chrome = PreviewChrome(parent)
        chrome.set_estimate(91.2)
        self.app.processEvents()
        self.assertFalse(chrome.estimate_symbol.pixmap().isNull())
        self.assertEqual(chrome.estimate_label.x(), 12)
        self.assertEqual(chrome.estimate_label.y(), 12)
        self.assertTrue(chrome.estimate_label.text().startswith('91.2%'))
        self.assertGreater(chrome.estimate_label.width(), chrome.estimate_symbol.width())
        chrome.mark_outdated()
        self.assertIn('outdated', chrome.estimate_label.text().lower())

    def test_countdown_is_rearmed_on_first_visible_paint(self):
        from PySide6.QtWidgets import QWidget
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        from desktop.qt_app.forecast_countdown_overlay import (
            ForecastCountdownTimer, ForecastCountdownOverlay)
        parent = QWidget()
        parent.resize(640, 480)
        parent.show()
        self.addCleanup(parent.close)
        timer = ForecastCountdownTimer()
        timer.setInterval(1000)
        timer.setSingleShot(True)
        self.addCleanup(timer.stop)
        overlay = ForecastCountdownOverlay(parent)
        timer.start()
        QTest.qWait(250)
        before = timer.remainingTime()
        self.assertLess(before, 900)
        overlay.begin(timer)
        self.app.processEvents()
        self.assertTrue(overlay.isVisible())
        self.assertGreater(timer.remainingTime(), before + 100)
        self.assertGreater(timer.remainingTime(), 850)
        timer.stop()
        overlay.dismiss()


if __name__ == '__main__':
    unittest.main()
