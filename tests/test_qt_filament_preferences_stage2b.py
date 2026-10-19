"""Stage 2B settings and solid-selection regressions, no Qt installation needed."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.settings_store import load_settings,save_settings
from desktop.qt_app.filament_preferences import FilamentPreferences

OPTIONS=[
 {'key':'cyan','name':'Cyan','color':'#08ABFB','series':'Panchroma'},
 {'key':'magenta','name':'Magenta','color':'#D93B90','series':'Panchroma'},
 {'key':'black','name':'Black','color':'#000000','series':'PLA Basic'},
]

class FilamentPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'
        self.prefs=FilamentPreferences(self.path)

    def test_defaults_and_no_early_file_writes(self):
        self.assertFalse(self.prefs.is_dirty)
        self.assertTrue(all(self.prefs.selected(o['key']) for o in OPTIONS))
        self.assertFalse(self.path.exists())

    def test_enable_pin_and_explicit_save(self):
        self.prefs.apply(OPTIONS,{'cyan','black'},{'black'},max_slots=2)
        self.assertTrue(self.prefs.is_dirty)
        self.assertFalse(self.prefs.selected('magenta'))
        self.assertFalse(self.path.exists())
        self.prefs.save()
        result=load_settings(self.path)
        self.assertEqual(result['disabled_anchor_keys'],['magenta'])
        self.assertEqual(result['pinned_anchor_keys'],['black'])
        self.assertFalse(self.prefs.is_dirty)

    def test_requires_two_distinct_enabled_colors(self):
        with self.assertRaisesRegex(ValueError,'two distinct'):
            self.prefs.apply(OPTIONS,{'cyan'},set())
        self.assertFalse(self.prefs.is_dirty)
        duplicate=[dict(OPTIONS[0]),dict(OPTIONS[1],color='#08abfb')]
        with self.assertRaisesRegex(ValueError,'two distinct'):
            self.prefs.apply(duplicate,{'cyan','magenta'},set())

    def test_pin_only_enabled_and_limit(self):
        with self.assertRaisesRegex(ValueError, r'Required filaments must also have Use checked'):
            self.prefs.apply(OPTIONS,{'cyan','black'},{'magenta'})
        with self.assertRaisesRegex(ValueError,'at most 1'):
            self.prefs.apply(OPTIONS,{'cyan','black'},{'cyan','black'},max_slots=1)

    def test_other_source_keys_preserved_and_does_not_override_plan(self):
        save_settings({'output_color_strategy':'fill_palette',
                       'pinned_anchor_keys':['legacy-other'],
                       'disabled_anchor_keys':['legacy-disabled']},self.path)
        self.prefs=FilamentPreferences(self.path)
        self.prefs.apply(OPTIONS,{'cyan','black'},{'black'})
        updated=load_settings(self.path);updated['max_output_colors']='24'
        save_settings(updated,self.path)
        self.prefs.save()
        resulting=load_settings(self.path)
        self.assertEqual(resulting['max_output_colors'],'24')
        self.assertEqual(resulting['output_color_strategy'],'fill_palette')
        self.assertEqual(resulting['pinned_anchor_keys'],['black','legacy-other'])
        self.assertEqual(resulting['disabled_anchor_keys'],['legacy-disabled','magenta'])

    def test_revert(self):
        save_settings({'disabled_anchor_keys':['magenta']},self.path)
        self.prefs=FilamentPreferences(self.path)
        self.prefs.apply(OPTIONS,{'cyan','magenta'},{'cyan'})
        self.assertTrue(self.prefs.is_dirty)
        self.prefs.revert()
        self.assertFalse(self.prefs.selected('magenta'))
        self.assertFalse(self.prefs.is_pinned('cyan'))
        self.assertFalse(self.prefs.is_dirty)

    def test_protections_are_validated_and_model_specific(self):
        self.prefs.use_model('one.3mf')
        self.prefs.protect('#9199a4','black',{'#9199A4':32},OPTIONS)
        self.assertEqual(self.prefs.solid_assignments,{'#9199A4':'black'})
        with self.assertRaisesRegex(ValueError,'exact color'):
            self.prefs.protect('#abcdef','black',{'#9199A4':32},OPTIONS)
        with self.assertRaisesRegex(ValueError,'enabled'):
            self.prefs.protect('#9199A4','not a key',{'#9199A4':32},OPTIONS)
        self.prefs.save()
        self.assertNotIn('solid_color_overrides',load_settings(self.path))
        self.prefs.use_model('one.3mf')
        self.assertEqual(len(self.prefs.solid_assignments),1)
        self.prefs.use_model('different.3mf')
        self.assertEqual(self.prefs.solid_assignments,{})

    def test_disabled_filament_removed_from_protected_mappings(self):
        self.prefs.use_model('one.3mf')
        self.prefs.protect('#9199a4','black',{'#9199A4':1},OPTIONS)
        self.prefs.apply(OPTIONS,{'cyan','magenta'},set())
        self.assertFalse(self.prefs.solid_assignments)

    def test_save_does_not_write_model_or_solid_data(self):
        self.prefs.use_model('C:/models/sample.3mf')
        self.prefs.protect('#9199A4','cyan',{'#9199A4':1},OPTIONS)
        self.prefs.apply(OPTIONS,{'cyan','black'},{'black'})
        self.prefs.save()
        result=load_settings(self.path)
        self.assertNotIn('model_path',result)
        self.assertNotIn('solid_color_overrides',result)

if __name__=='__main__':unittest.main()
