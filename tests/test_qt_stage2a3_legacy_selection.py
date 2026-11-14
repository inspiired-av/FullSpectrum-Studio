"""Stage 2A.3 preference migration contracts; no user files or slicers touched."""
from __future__ import annotations

import unittest
from desktop.qt_app.filament_legacy_selection import (
    find_legacy_selection_conflicts, keys_to_retire, review_text, unresolved_message,
)

A = {'key':'personal:vendor-a-black','series':'PLA Basic','color':'#000000','name':'A Black'}
B = {'key':'personal:vendor-b-black','series':'PLA Basic','color':'#000000','name':'B Black'}
C = {'key':'PLA Basic|#FFFFFF','series':'PLA Basic','color':'#FFFFFF','name':'White'}
D = {'key':'personal:other-black','series':'PLA Matte','color':'#000000','name':'Matte Black'}
LEGACY = 'PLA Basic|#000000'


class PureCollisionTests(unittest.TestCase):
    def test_unambiguous_legacy_key_does_not_migrate(self):
        self.assertFalse(find_legacy_selection_conflicts([A,C], pinned=[LEGACY]))

    def test_distinct_material_families_do_not_collide(self):
        self.assertFalse(find_legacy_selection_conflicts([A,C,D], pinned=[LEGACY]))

    def test_collision_without_legacy_selection_does_not_migrate(self):
        self.assertFalse(find_legacy_selection_conflicts([A,B,C], pinned=[A['key']]))

    def test_both_old_disable_and_pin_detected_without_guess(self):
        result=find_legacy_selection_conflicts([A,B,C], disabled=[LEGACY], pinned=[LEGACY])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].kinds,('Excluded','Required'))
        self.assertEqual({key for key,_ in result[0].variants},{A['key'],B['key']})
        self.assertEqual(keys_to_retire(result),{LEGACY})

    def test_preserve_unrelated_legacy_keys(self):
        result=find_legacy_selection_conflicts([A,B,C], disabled=[LEGACY,'other|#123456'],pinned=['third'])
        self.assertEqual(keys_to_retire(result),{LEGACY})

    def test_case_insensitive_legacy_lookup_preserves_exact_saved_spellings(self):
        result=find_legacy_selection_conflicts([A,B,C],pinned=['pla basic|#000000'])
        self.assertEqual(result[0].pinned_keys,('pla basic|#000000',))

    def test_duplicate_option_key_is_not_falsely_a_variant_collision(self):
        self.assertFalse(find_legacy_selection_conflicts([A,A,C],pinned=[LEGACY]))

    def test_review_discloses_pin_removal_when_none_selected(self):
        result=find_legacy_selection_conflicts([A,B,C],pinned=[LEGACY])
        self.assertIn('CLEAR the old Required',review_text(result,{A['key'],B['key']},set()))
        self.assertIn('no physical variant',unresolved_message(result).lower())

    def test_review_shows_explicit_variant_choice(self):
        result=find_legacy_selection_conflicts([A,B,C],pinned=[LEGACY])
        msg=review_text(result,{A['key'],B['key']},{B['key']})
        self.assertIn('B Black',msg)
        self.assertIn('Require Yes',msg)


try:
    from desktop.qt_app.filament_preferences import FilamentPreferences
    from desktop.settings_store import save_settings,load_settings
except ImportError:
    FilamentPreferences=None

@unittest.skipUnless(FilamentPreferences is not None,'Run inside the FullSpectrum Studio repository')
class PreferencesIntegrationTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'

    def test_no_automatic_rewrite_and_explicit_reconciliation(self):
        save_settings({'disabled_anchor_keys':[LEGACY,'other-source-key'],
                       'pinned_anchor_keys':[LEGACY,'another-source-key'],
                       'max_output_colors':'24'},self.path)
        preferences=FilamentPreferences(self.path)
        old=self.path.read_bytes()
        self.assertEqual(len(preferences.legacy_conflicts([A,B,C])),1)
        self.assertEqual(self.path.read_bytes(),old)
        preferences.apply([A,B,C],{A['key'],B['key'],C['key']},{B['key']})
        self.assertEqual(self.path.read_bytes(),old)
        self.assertEqual(len(preferences.legacy_conflicts([A,B,C])),1)
        preferences.acknowledge_legacy_conflicts([A,B,C])
        self.assertFalse(preferences.legacy_conflicts([A,B,C]))
        preferences.save()
        saved=load_settings(self.path)
        self.assertNotIn(LEGACY,saved['disabled_anchor_keys'])
        self.assertNotIn(LEGACY,saved['pinned_anchor_keys'])
        self.assertIn('other-source-key',saved['disabled_anchor_keys'])
        self.assertIn('another-source-key',saved['pinned_anchor_keys'])
        self.assertIn(B['key'],saved['pinned_anchor_keys'])
        self.assertEqual(saved['max_output_colors'],'24')

    def test_revert_before_acknowledging_restores_legacy(self):
        save_settings({'pinned_anchor_keys':[LEGACY]},self.path)
        prefs=FilamentPreferences(self.path)
        prefs.apply([A,B,C],{A['key'],B['key'],C['key']},set())
        prefs.revert()
        self.assertTrue(prefs.legacy_conflicts([A,B,C]))
        self.assertIn(LEGACY,load_settings(self.path)['pinned_anchor_keys'])

    def test_collision_free_palette_cannot_rewrite_saved_setting(self):
        save_settings({'pinned_anchor_keys':[LEGACY]},self.path)
        prefs=FilamentPreferences(self.path)
        self.assertFalse(prefs.legacy_conflicts([A,C]))
        self.assertEqual(prefs.acknowledge_legacy_conflicts([A,C]),())
        self.assertFalse(prefs.is_dirty)



@unittest.skipUnless(FilamentPreferences is not None,'Run inside the FullSpectrum Studio repository')
class ServiceGuardIntegrationTests(unittest.TestCase):
    def test_forecast_rejects_ambiguous_pin_before_conversion(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from desktop.qt_app.forecast_service import ForecastRequest,run_plan
        with TemporaryDirectory() as folder:
            root=Path(folder)
            model=root/'frog.3mf';model.write_bytes(b'fixture')
            palette=root/'filaments.json';palette.write_text('{}',encoding='utf-8')
            request=ForecastRequest(str(model),None,{
                'strategy':'official','source':'custom','custom':str(palette),
                'smart_quality':False,'native_project_template':''},
                frozenset(),frozenset([LEGACY]),(),False)
            def no_convert(*a,**kw):
                self.fail('Conversion must not run with ambiguous pinned material')
            engine=SimpleNamespace(is_standard_colored_3mf=lambda p:False,convert=no_convert)
            with self.assertRaisesRegex(ValueError,'Saved filament preference'):
                run_plan(request,engine=engine,options_loader=lambda *_:[A,B,C])

    def test_export_rejects_ambiguous_disabled_before_conversion(self):
        from pathlib import Path
        from types import SimpleNamespace
        from desktop.qt_app.forecast_service import ForecastRequest
        from desktop.qt_app.export_service import _validate_options
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            palette=Path(folder)/'filaments.json'
            palette.write_text('{}',encoding='utf-8')
            request=ForecastRequest('frog.3mf',None,{
                'strategy':'official','source':'custom','custom':str(palette),
                'native_project_template':''},
                frozenset([LEGACY]),frozenset(),(),False)
            engine=SimpleNamespace(is_standard_colored_3mf=lambda p:False)
            with self.assertRaisesRegex(ValueError,'Saved filament preference'):
                _validate_options(request,engine,lambda *_:[A,B,C])

if __name__=='__main__': unittest.main()
