"""Quality/waste slider and safe incremental installer regression checks."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app.plan_preferences import PlanPreferences
from desktop.settings_store import load_settings, save_settings


class QualitySettingsPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'

    def test_quality_bias_remains_integer_in_existing_settings(self):
        pref = PlanPreferences(self.path)
        pref.set('smart_quality', False)
        pref.set('quality_bias', 73)
        self.assertFalse(self.path.exists())
        pref.save()
        self.assertEqual(load_settings(self.path)['quality_bias'], 73)
        self.assertEqual(PlanPreferences(self.path).get('quality_bias'), 73)

    def test_smart_quality_does_not_erase_manual_value(self):
        pref = PlanPreferences(self.path)
        pref.set('quality_bias', 38)
        pref.set('smart_quality', True)
        pref.save()
        reloaded = PlanPreferences(self.path)
        self.assertTrue(reloaded.get('smart_quality'))
        self.assertEqual(reloaded.get('quality_bias'), 38)

    def test_revert_preserves_last_manual_value(self):
        save_settings({'smart_quality': False, 'quality_bias': 34}, self.path)
        pref = PlanPreferences(self.path)
        pref.set('quality_bias', 84)
        pref.revert()
        self.assertEqual(pref.get('quality_bias'), 34)
        self.assertFalse(pref.is_dirty)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Qt UI tests require PySide6')
class QualitySliderQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'settings.json'
        from desktop.qt_app.main_window import MainWindow
        self.window = MainWindow(settings_path=self.path)
        self.addCleanup(self.window.close)
        self.window.advanced_toggle.setChecked(True)

    def test_slider_is_disabled_by_smart_quality_and_keeps_value(self):
        from PySide6.QtWidgets import QSlider
        w = self.window
        self.assertIsInstance(w.quality_bias, QSlider)
        self.assertEqual(w.quality_bias.minimum(), 0)
        self.assertEqual(w.quality_bias.maximum(), 100)
        self.assertEqual(w.quality_bias.value(), 60)
        self.assertEqual(w.quality_bias_value.text(), '60')
        self.assertTrue(w.smart_quality.isChecked())
        self.assertFalse(w.quality_bias.isEnabled())
        self.assertFalse(w.quality_bias_value.isEnabled())
        w.smart_quality.setChecked(False)
        self.assertTrue(w.quality_bias.isEnabled())
        self.assertTrue(w.quality_bias_value.isEnabled())
        w.quality_bias.setValue(72)
        self.assertEqual(w.quality_bias_value.text(), '72')
        self.assertEqual(w.plan_preferences.get('quality_bias'), 72)
        w.smart_quality.setChecked(True)
        self.assertFalse(w.quality_bias.isEnabled())
        self.assertEqual(w.quality_bias.value(), 72)
        self.assertEqual(w.plan_preferences.get('quality_bias'), 72)

    def test_save_reopen_and_revert_update_slider_and_value(self):
        w = self.window
        w.smart_quality.setChecked(False)
        w.quality_bias.setValue(29)
        w.save_plan_button.click()
        self.assertEqual(load_settings(self.path)['quality_bias'], 29)
        self.assertFalse(w.save_plan_button.isEnabled())
        w.quality_bias.setValue(96)
        self.assertTrue(w.save_plan_button.isEnabled())
        w.revert_plan_button.click()
        self.assertEqual(w.quality_bias.value(), 29)
        self.assertEqual(w.quality_bias_value.text(), '29')
        self.assertTrue(w.quality_bias.isEnabled())
        self.assertFalse(w.save_plan_button.isEnabled())

    def test_initial_saved_smart_quality_disabled_state(self):
        self.window.close()
        save_settings({'smart_quality': False, 'quality_bias': 88}, self.path)
        from desktop.qt_app.main_window import MainWindow
        w = MainWindow(settings_path=self.path)
        self.addCleanup(w.close)
        self.assertFalse(w.smart_quality.isChecked())
        self.assertTrue(w.quality_bias.isEnabled())
        self.assertEqual(w.quality_bias.value(), 88)
        self.assertEqual(w.quality_bias_value.text(), '88')


if __name__ == '__main__':
    unittest.main()
