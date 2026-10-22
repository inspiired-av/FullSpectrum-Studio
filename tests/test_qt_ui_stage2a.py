"""Stage 2A preferences tests; Qt itself remains an optional dependency."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app.plan_preferences import (
    PlanPreferences, MANAGED_KEYS, DEFAULTS, PALETTE_STRATEGIES,
    FILAMENT_SOURCES, validate_plan_change,
)
from desktop.settings_store import load_settings, save_settings


class PlanPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'preferences.json'

    def test_defaults_match_established_engine(self):
        preferences = PlanPreferences(self.destination)
        self.assertEqual(preferences.get('output_color_strategy'), 'maximum_fidelity')
        self.assertEqual(preferences.get('max_output_colors'), '32')
        self.assertEqual(preferences.get('source'), 'inventory')
        self.assertEqual(preferences.get('planner_mode'), 'best')
        self.assertTrue(preferences.get('smart_quality'))
        self.assertFalse(preferences.is_dirty)
        self.assertFalse(self.destination.exists())

    def test_preference_changes_do_not_write_until_explicit_save(self):
        plan = PlanPreferences(self.destination)
        plan.set('max_output_colors', '24')
        plan.set('source', 'custom')
        plan.set('custom', r'C:\Library\filaments.json')
        self.assertTrue(plan.is_dirty)
        self.assertFalse(self.destination.exists())
        plan.save()
        self.assertFalse(plan.is_dirty)
        loaded = PlanPreferences(self.destination)
        self.assertEqual(loaded.get('max_output_colors'), '24')
        self.assertEqual(loaded.get('custom'), r'C:\Library\filaments.json')
        self.assertEqual(loaded.get('source'), 'custom')
        self.assertIn('"version"', self.destination.read_text(encoding='utf-8'))

    def test_shared_settings_and_unrelated_fields_survive_save(self):
        save_settings({
            'max_output_colors': '16',
            'disabled_anchor_keys': ['anchor-a'],
            'pinned_anchor_keys': ['anchor-b'],
            'bambu_studio_executable': r'C:\Program Files\Bambu Studio\bambu-studio.exe',
            'native_project_template': 'base.3mf',
        }, self.destination)
        plan = PlanPreferences(self.destination)
        self.assertEqual(plan.get('max_output_colors'), '16')
        # Simulate concurrent changes by the Tkinter shell while Qt is open.
        latest = load_settings(self.destination)
        latest['pinned_anchor_keys'] = ['anchor-new']
        latest['source'] = 'catalog'
        save_settings(latest, self.destination)
        plan.set('max_output_colors', '32')
        plan.save()
        actual = load_settings(self.destination)
        self.assertEqual(actual['source'], 'catalog')
        self.assertEqual(actual['pinned_anchor_keys'], ['anchor-new'])
        self.assertEqual(actual['disabled_anchor_keys'], ['anchor-a'])
        self.assertEqual(actual['max_output_colors'], '32')
        self.assertIn('bambu_studio_executable', actual)
        self.assertEqual(actual['native_project_template'], 'base.3mf')

    def test_revert_reloads_latest_saved_state(self):
        plan = PlanPreferences(self.destination)
        plan.set('strategy','cmykw')
        self.assertTrue(plan.is_dirty)
        plan.revert()
        self.assertFalse(plan.is_dirty)
        self.assertEqual(plan.get('strategy'), 'official')
        save_settings({'strategy':'cmykw'}, self.destination)
        plan.revert()
        self.assertEqual(plan.get('strategy'), 'cmykw')

    def test_reverting_field_to_saved_value_clears_dirty_state(self):
        plan = PlanPreferences(self.destination)
        plan.set('source', 'custom')
        plan.set('source', 'inventory')
        self.assertFalse(plan.is_dirty)

    def test_settings_validation_rejects_invalid_values(self):
        plan = PlanPreferences(self.destination)
        for name, value in (
            ('max_output_colors', '33'), ('real_slots', '12'),
            ('planner_mode','medium'), ('strategy', 'unknown'),
            ('quality_bias', True), ('source','secret'),
            ('custom', 'bad\x00path'),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    plan.set(name,value)
        with self.assertRaises(KeyError):
            plan.set('disabled_anchor_keys',['a'])
        self.assertFalse(plan.is_dirty)

    def test_explicit_auto_option_is_supported(self):
        plan = PlanPreferences(self.destination)
        plan.set('max_output_colors', 'auto')
        self.assertEqual(plan.get('max_output_colors'), 'auto')
        self.assertTrue(plan.is_dirty)

    def test_model_and_library_paths_are_not_copied_to_unrelated_fields(self):
        plan = PlanPreferences(self.destination)
        plan.set('native_project_template', r'C:\Templates\H2C.3mf')
        plan.set('custom', r'C:\Files\palette.json')
        plan.save()
        data=json.loads(self.destination.read_text(encoding='utf-8'))
        self.assertNotIn('model_path',data)
        self.assertNotIn('reference_path',data)
        self.assertEqual(data['native_project_template'],r'C:\Templates\H2C.3mf')

    def test_ui_options_have_unique_engine_values(self):
        for options in (PALETTE_STRATEGIES,FILAMENT_SOURCES):
            values=[v for label,v in options]
            self.assertEqual(len(values),len(set(values)))
            self.assertTrue(all(isinstance(label,str) and label.strip() for label,v in options))
        self.assertTrue({'source','native_project_template','output_color_strategy'} <= MANAGED_KEYS)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 is optional')
class OptionalQtPlanTests(unittest.TestCase):
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

    def test_plan_widgets_are_live_but_conversion_remains_disabled(self):
        w = self.window
        self.assertTrue(w.palette_strategy.isEnabled())
        self.assertTrue(w.filament_source.isEnabled())
        self.assertFalse(w.compose_button.isEnabled())
        self.assertEqual(w.palette_limit.currentData(), '32')
        w.palette_strategy.setCurrentIndex(w.palette_strategy.findData('balanced'))
        w.palette_limit.setCurrentIndex(w.palette_limit.findData('24'))
        self.assertTrue(w.save_plan_button.isEnabled())
        w.save_plan_button.click()
        self.assertEqual(load_settings(self.path)['max_output_colors'], '24')
        self.assertFalse(w.save_plan_button.isEnabled())

    def test_advanced_preferences_and_custom_source_toggle(self):
        w=self.window
        self.assertFalse(w.advanced_toggle.isChecked())
        w.advanced_toggle.click()
        self.assertTrue(w.advanced_toggle.isChecked())
        w.smart_quality.setChecked(False)
        self.assertTrue(w.quality_bias.isEnabled())
        w.filament_source.setCurrentIndex(w.filament_source.findData('custom'))
        self.assertTrue(not w.custom_file_row.isHidden())
        w._revert_plan_settings()
        self.assertEqual(w.filament_source.currentData(),'inventory')
        self.assertTrue(w.smart_quality.isChecked())

    def test_invalid_native_template_is_rejected_without_changing_saved_settings(self):
        w=self.window
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from unittest.mock import patch
        fake = self.path.parent/'bad.3mf'
        fake.write_text('Not a zip',encoding='utf-8')
        with patch.object(QFileDialog,'getOpenFileName', return_value=(str(fake),'')):
            with patch.object(QMessageBox,'warning'):
                w.template_browse.click()
        self.assertEqual(w.template_path.text(),'')
        self.assertFalse(w.plan_preferences.is_dirty)


if __name__ == '__main__':
    unittest.main()
