"""Quality slider visual and interaction regressions for Stage 2A."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
PKG = BASE / 'desktop/qt_app'


class QualityVisualCodeTests(unittest.TestCase):
    def test_slider_track_is_fully_styled_without_native_rectangular_background(self):
        theme = (PKG / 'theme.py').read_text(encoding='utf-8')
        self.assertIn('QSlider#qualityBiasSlider::add-page:horizontal', theme)
        self.assertIn('QSlider#qualityBiasSlider::groove:horizontal', theme)
        self.assertIn('QSlider#qualityBiasSlider::sub-page:horizontal:disabled', theme)
        self.assertIn('QSlider#qualityBiasSlider::add-page:horizontal:disabled', theme)
        self.assertIn('background: transparent; border: none;', theme)
        self.assertNotIn('QSlider#qualityBiasSlider:disabled::sub-page:horizontal', theme)

    def test_smart_quality_keeps_auto_chip_enabled_and_disables_only_manual_controls(self):
        code = (PKG / 'main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.quality_auto_badge.setVisible(not manual_quality)', code)
        self.assertIn('self.quality_bias.setEnabled(manual_quality)', code)
        self.assertIn('self.quality_bias_value.setEnabled(manual_quality)', code)
        self.assertNotIn('self.quality_bias_row.setEnabled(manual_quality)', code)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 required for Qt interaction tests')
class QualityVisualQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.main_window import MainWindow
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.window = MainWindow(settings_path=Path(self.tmp.name)/'settings.json')
        self.addCleanup(self.window.close)
        self.window.advanced_toggle.setChecked(True)

    def test_smart_mode_is_obviously_disabled_and_labelled_auto(self):
        w = self.window
        self.assertTrue(w.smart_quality.isChecked())
        self.assertFalse(w.quality_bias.isEnabled())
        self.assertFalse(w.quality_bias_value.isEnabled())
        self.assertEqual(w.quality_auto_badge.text(), 'AUTO')
        self.assertFalse(w.quality_auto_badge.isHidden())
        self.assertTrue(w.quality_auto_badge.isEnabled())
        self.assertIn('managed automatically', w.quality_bias.toolTip())
        self.assertEqual(w.quality_bias.value(), 60)

    def test_manual_mode_is_enabled_and_keeps_value_when_reenabled_auto(self):
        w = self.window
        w.smart_quality.setChecked(False)
        self.assertTrue(w.quality_auto_badge.isHidden())
        self.assertTrue(w.quality_bias.isEnabled())
        w.quality_bias.setValue(72)
        w.smart_quality.setChecked(True)
        self.assertEqual(w.quality_bias.value(), 72)
        self.assertFalse(w.quality_bias.isEnabled())
        self.assertFalse(w.quality_auto_badge.isHidden())
        w.smart_quality.setChecked(False)
        self.assertTrue(w.quality_bias.isEnabled())
        self.assertEqual(w.quality_bias.value(), 72)

    def test_save_and_revert_preserve_actual_quality_setting(self):
        from desktop.settings_store import load_settings
        w = self.window
        w.smart_quality.setChecked(False)
        w.quality_bias.setValue(41)
        w.save_plan_button.click()
        self.assertEqual(load_settings(w.plan_preferences.path)['quality_bias'], 41)
        w.quality_bias.setValue(95)
        w.revert_plan_button.click()
        self.assertEqual(w.quality_bias.value(), 41)
        self.assertTrue(w.quality_bias.isEnabled())


if __name__ == '__main__':
    unittest.main()
