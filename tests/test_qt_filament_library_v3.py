"""Regressions for profile edits, physical slot error messaging, and UI labels."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.qt_app import filament_library_store as lib
from desktop.qt_app.filament_forecast_errors import describe_forecast_failure


class SavedProfileMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        context = patch.object(lib,'settings_path',return_value=Path(self.temp.name)/'settings.json')
        context.start()
        self.addCleanup(context.stop)
        self.items = [lib.normalize(dict(name=f'Color {n}',brand='User',series='PLA Basic',
                         color=color,source='personal'),personal=True)
                      for n,color in enumerate(['#08ABFB','#D93B90','#F9ED3D','#9199A4','#000000'])]

    def test_remove_one_from_saved_profile_without_removing_filament(self):
        identity=lib.save_profile('My five colors',self.items)
        revision=lib.saved_profile_revision(identity)
        new_revision=lib.update_saved_profile(identity,self.items[:4],expected_revision=revision)
        self.assertNotEqual(revision,new_revision)
        self.assertEqual(len(lib.get_profile(identity)['filaments']),4)
        self.assertEqual(len(self.items),5)

    def test_profile_edits_require_two_distinct_colors(self):
        identity=lib.save_profile('My five colors',self.items)
        with self.assertRaisesRegex(ValueError,'at least two'):
            lib.update_saved_profile(identity,self.items[:1],
                                     expected_revision=lib.saved_profile_revision(identity))
        self.assertEqual(len(lib.get_profile(identity)['filaments']),5)

    def test_concurrent_edits_fail_closed(self):
        identity=lib.save_profile('My five colors',self.items)
        old=lib.saved_profile_revision(identity)
        lib.update_saved_profile(identity,self.items[:4],expected_revision=old)
        with self.assertRaisesRegex(ValueError,'changed on disk'):
            lib.update_saved_profile(identity,self.items[:3],expected_revision=old)
        with self.assertRaisesRegex(ValueError,'changed on disk'):
            lib.delete_saved_profile(identity,expected_revision=old)
        self.assertEqual(len(lib.get_profile(identity)['filaments']),4)

    def test_deleting_saved_profile_does_not_remove_personal_entry(self):
        lib.save_personal(self.items,expected_revision=None)
        identity=lib.save_profile('My five colors',self.items)
        lib.delete_saved_profile(identity,expected_revision=lib.saved_profile_revision(identity))
        self.assertEqual(len(lib.list_profiles()),0)
        self.assertEqual(len(lib.read_personal()[0]),5)

    def test_builtin_is_not_editable_or_deletable(self):
        for operation in (
            lambda: lib.saved_profile_revision('builtin:generic-cmykw'),
            lambda: lib.delete_saved_profile('builtin:generic-cmykw',expected_revision=None),
        ):
            with self.assertRaises(ValueError):operation()


class ForecastErrorTests(unittest.TestCase):
    def test_repeated_shortage_points_to_advanced_setting(self):
        raw=('Smart quality planning failed: 85: Filament source contains fewer than 6 distinct colors; '
             '50: Filament source contains fewer than 6 distinct colors; '
             '100: Filament source contains fewer than 6 distinct colors')
        rendered=describe_forecast_failure(raw,'6',5)
        self.assertIn('Plan → Advanced Settings',rendered)
        self.assertIn('Physical slots is set to 6',rendered)
        self.assertIn('5 distinct enabled colors',rendered)
        self.assertEqual(rendered.count('Filament source contains'),0)

    def test_auto_does_not_mislabel_user_requested_slots(self):
        error='85: Filament source contains fewer than 6 distinct colors'
        rendered=describe_forecast_failure(error,'auto',5)
        self.assertIn('Automatic slot',rendered)
        self.assertNotIn('is set to 6',rendered)

    def test_repeated_unrelated_errors_are_deduplicated(self):
        raw='Smart quality planning failed: 85: bad configuration; 50: bad configuration'
        self.assertEqual(describe_forecast_failure(raw),'Smart quality planning failed: bad configuration')

    def test_other_messages_preserved(self):
        self.assertEqual(describe_forecast_failure('Bad texture data'),'Bad texture data')


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.filament_profile_manager import FilamentProfileManager
except (ImportError, OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 not installed')
class ProfileUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_profile_edit_and_remove_buttons_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(lib,'settings_path',return_value=Path(folder)/'settings.json'):
                records=[lib.normalize({'name':str(n),'brand':'Generic','series':'PLA Basic',
                           'color':hex,'source':'personal'},personal=True)
                         for n,hex in enumerate(('#000000','#FFFFFF','#00FFFF'))]
                lib.save_profile('Test',records)
                dialog=FilamentProfileManager()
                self.assertEqual(dialog.profiles.count(),1)
                self.assertEqual(dialog.filaments.count(),3)
                self.assertTrue(dialog.delete.isEnabled())
                dialog.close()


if __name__=='__main__':unittest.main()
