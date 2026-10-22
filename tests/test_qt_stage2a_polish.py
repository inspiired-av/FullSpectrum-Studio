"""Qt UI polish: settings independence and path editing, with optional UI checks."""
from __future__ import annotations
import importlib.util
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from desktop.qt_app.plan_preferences import PlanPreferences, MANAGED_KEYS
from desktop.settings_store import load_settings,save_settings


class SlicerExecutablePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/'settings.json'

    def test_separate_slicer_paths_are_managed(self):
        self.assertIn('bambu_studio_executable', MANAGED_KEYS)
        self.assertIn('orcaslicer_executable', MANAGED_KEYS)
        model=PlanPreferences(self.file)
        self.assertEqual(model.get('bambu_studio_executable'),'')
        self.assertEqual(model.get('orcaslicer_executable'),'')

    def test_persist_portable_and_standard_paths_independently(self):
        model=PlanPreferences(self.file)
        model.set('bambu_studio_executable',r'C:\Program Files\Bambu Studio\bambu-studio.exe')
        model.set('orcaslicer_executable',r'C:\Tools\Orca nightly\orca-slicer.exe')
        self.assertFalse(self.file.exists())
        model.save()
        again=PlanPreferences(self.file)
        self.assertEqual(again.get('orcaslicer_executable'),r'C:\Tools\Orca nightly\orca-slicer.exe')
        self.assertTrue(again.get('bambu_studio_executable').endswith('bambu-studio.exe'))

    def test_revert_and_auto_clear_only_selected_slicer(self):
        save_settings({'orcaslicer_executable':'portable.exe',
                       'bambu_studio_executable':'stable.exe'}, self.file)
        model=PlanPreferences(self.file)
        model.set('orcaslicer_executable','other.exe')
        model.revert()
        self.assertEqual(model.get('orcaslicer_executable'),'portable.exe')
        model.set('orcaslicer_executable','')
        model.save()
        self.assertEqual(load_settings(self.file)['bambu_studio_executable'],'stable.exe')
        self.assertEqual(load_settings(self.file)['orcaslicer_executable'],'')

    def test_save_preserves_unrelated_filament_pins(self):
        save_settings({'pinned_anchor_keys':['anchor-one'],
                       'disabled_anchor_keys':['anchor-two']},self.file)
        model=PlanPreferences(self.file)
        model.set('orcaslicer_executable','portable.exe')
        model.save()
        actual=load_settings(self.file)
        self.assertEqual(actual['pinned_anchor_keys'],['anchor-one'])
        self.assertEqual(actual['disabled_anchor_keys'],['anchor-two'])

    def test_invalid_executable_settings_are_rejected(self):
        model=PlanPreferences(self.file)
        with self.assertRaises(ValueError):
            model.set('orcaslicer_executable','invalid\x00name.exe')
        self.assertFalse(model.is_dirty)


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 is optional')
class QtSlicerControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.preferences=Path(self.temp.name)/'prefs.json'
        from desktop.qt_app.main_window import MainWindow
        self.window=MainWindow(settings_path=self.preferences)
        self.addCleanup(self.window.close)
        self.window.advanced_toggle.setChecked(True)

    def test_slicer_switch_and_auto_are_independent(self):
        from PySide6.QtWidgets import QFileDialog
        w=self.window
        exe=Path(self.temp.name)/'orcaslicer.exe'
        exe.write_bytes(b'MZ-not-executed')
        w.output_application.setCurrentIndex(w.output_application.findData('OrcaSlicer'))
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(exe),'')):
            w.slicer_executable_browse.click()
        self.assertEqual(w.plan_preferences.get('orcaslicer_executable'),str(exe))
        self.assertTrue(w.save_plan_button.isEnabled())
        self.assertIn(str(exe),w.slicer_executable_status.text())
        w.output_application.setCurrentIndex(w.output_application.findData('Bambu Studio'))
        self.assertIn('automatic executable detection',w.slicer_executable_status.text())
        w.output_application.setCurrentIndex(w.output_application.findData('OrcaSlicer'))
        w.save_plan_button.click()
        self.assertEqual(load_settings(self.preferences)['orcaslicer_executable'],str(exe))
        w.slicer_executable_auto.click()
        self.assertEqual(w.plan_preferences.get('orcaslicer_executable'),'')
        self.assertIn('automatic executable detection',w.slicer_executable_status.text())

    def test_template_status_and_warning_use_distinct_states(self):
        w=self.window
        self.assertEqual(w.template_status.objectName(),'templateStatusEmpty')
        self.assertEqual(w.template_compatibility.objectName(),'templateWarning')
        info={'path':'template.3mf','slicer':'Bambu Studio','slicerVersion':'02.08',
              'printerPreset':'Bambu Lab H2C 0.4 nozzle','nozzle':'0.4',
              'processPreset':'0.08mm High Quality'}
        from unittest.mock import patch
        with patch('native_project_template.inspect_template',return_value=info),\
             patch('orca_profile_warning.orca_h2c_warning',return_value='Template was saved by Bambu Studio, but output opens in OrcaSlicer.'):
            w.template_path.setText('template.3mf')
            w._refresh_template_status()
        self.assertEqual(w.template_status.objectName(),'templateStatusReady')
        self.assertIn('Bambu Studio',w.template_status.text())
        self.assertIn('OrcaSlicer',w.template_compatibility.text())
        w.template_path.clear()
        w._refresh_template_status()
        self.assertEqual(w.template_status.objectName(),'templateStatusEmpty')

if __name__=='__main__':unittest.main()
