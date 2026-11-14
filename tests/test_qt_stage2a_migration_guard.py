"""Stage 2A migration preflight: no source writes or lossy identity merging."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import importlib.util
import unittest

# This test is runnable outside the checkout against the supplied pure module;
# within the checkout it uses the same module at its installed location.
try:
    from desktop.qt_app import filament_migration_guard as guard
except ModuleNotFoundError:
    location = Path(__file__).resolve().parents[1] / 'desktop' / 'qt_app' / 'filament_migration_guard.py'
    spec = importlib.util.spec_from_file_location('filament_migration_guard', location)
    guard = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = guard
    spec.loader.exec_module(guard)


def sample(identity, color, *, brand='Polymaker', name='Cyan', series='PLA Translucent', **extra):
    return {'id': identity, 'name': name, 'brand': brand,
            'material': 'PLA', 'series': series, 'color': color, 'finish': 'Standard',
            'optics': 'translucent', 'source': 'personal', 'color_source': 'user-entered',
            **extra}


class FakeV2:
    """A deliberately tiny v2 contract double for pure migration-guard tests."""
    def __init__(self):
        self.drop_profile = False

    def project_legacy_state(self, *, generic=(), catalog=(), personal=(), profiles=()):
        products = {}
        variants = {}
        references = {}
        for row in (*generic, *catalog, *personal):
            pid = row.get('product_id', f"product:{row['brand']}:{row['series']}")
            products[pid] = {'id': pid, 'brand': row['brand'],
                             'material': row['material'],
                             'identity_status': 'explicit' if 'product_id' in row
                             else 'provisional-family'}
            variants.setdefault(row['id'], {
                'id': row['id'], 'name': row['name'], 'product_id': pid,
                'color': {'hex': row['color'], 'provenance': row['color_source']},
                'optical': {'class': row['optics']}, 'preset_refs': [],
                'origin': row.get('source', 'personal'),
                'legacy_record': dict(row)})
        pdocs = []
        for p in profiles:
            for row in p['filaments']:
                if row['id'] not in variants:
                    pid = row.get('product_id', f"product:{row['brand']}:{row['series']}")
                    products[pid] = {'id': pid, 'brand': row['brand'],
                                     'material': row['material'],
                                     'identity_status': 'provisional-family'}
                    variants[row['id']] = {
                        'id': row['id'], 'name': row['name'], 'product_id': pid,
                        'color': {'hex': row['color'], 'provenance': row['color_source']},
                        'optical': {'class': row['optics']}, 'preset_refs': [],
                        'origin': 'profile-snapshot'}
            pdocs.append({'id': p['id'], 'name': p['name'],
                          'member_variant_ids': [r['id'] for r in p['filaments']],
                          'legacy_filaments': ([] if self.drop_profile else
                                               [dict(r) for r in p['filaments']])})
        return {'schema': 2, 'kind': 'filament_library_index',
                'products': list(products.values()),
                'variants': list(variants.values()),
                'preset_references': list(references.values()),
                'profiles': pdocs}

    def validate_document(self, d):
        if d.get('schema') != 2:
            raise ValueError('bad schema')
        return d

    def legacy_profile_from_document(self, d, identity):
        found = next(x for x in d['profiles'] if x['id'] == identity)
        return {'schema': 1, 'kind': 'palette', 'name': found['name'],
                'filaments': found['legacy_filaments']}


class MigrationGuardPureTests(unittest.TestCase):
    def setUp(self):
        self.v2 = FakeV2()
        self.cyan = sample('personal:cyan', '#08ABFB')
        self.magenta = sample('personal:magenta', '#D93B90', name='Magenta')

    def audit(self, **kwargs):
        return guard.audit_legacy_sources(identity_module=self.v2, **kwargs)

    def test_preserves_two_identical_hex_variants_as_separate_identities(self):
        other = sample('personal:other', '#08ABFB', brand='Other', name='Other Cyan')
        report = self.audit(personal=[self.cyan, other])
        self.assertEqual(report.summary['variants'], 2)
        manifest = guard.selection_manifest(report.document,
            ['personal:cyan', 'personal:other'], identity_module=self.v2)
        self.assertEqual(len(manifest['filaments']), 2)
        self.assertEqual(manifest['distinct_colors'], 1)
        self.assertFalse(manifest['can_forecast_pla'])
        self.assertNotEqual(manifest['filaments'][0]['product_id'],
                            manifest['filaments'][1]['product_id'])

    def test_primary_id_collision_with_different_color_is_not_silently_merged(self):
        with self.assertRaisesRegex(guard.MigrationGuardError, 'conflicting primary'):
            self.audit(personal=[self.cyan],
                       catalog=[dict(self.cyan, color='#000000')])

    def test_primary_id_collision_with_different_metadata_is_not_merged(self):
        with self.assertRaisesRegex(guard.MigrationGuardError, 'conflicting primary'):
            self.audit(personal=[self.cyan],
                       catalog=[dict(self.cyan, preset_refs=[{
                           'slicer': 'orcaslicer', 'preset_name': 'some preset'}])])

    def test_exact_repeated_scan_records_are_allowed(self):
        report = self.audit(catalog=[self.cyan, dict(self.cyan)])
        self.assertEqual(report.summary['primary_variants'], 1)
        self.assertEqual(report.summary['variants'], 1)

    def test_ids_differing_only_in_case_fail(self):
        with self.assertRaisesRegex(guard.MigrationGuardError, 'differ only by case'):
            self.audit(personal=[self.cyan, dict(self.cyan, id='personal:CYAN')])

    def test_frozen_palette_snapshot_is_not_rewritten_by_live_variant(self):
        frozen = dict(self.cyan, color='#00AAFF')
        profile = {'id': 'builtin:snapshot', 'name': 'Snapshot',
                   'filaments': [frozen, self.magenta]}
        before = deepcopy(profile)
        report = self.audit(personal=[self.cyan, self.magenta], profiles=[profile])
        self.assertEqual(before, profile)
        self.assertEqual(report.summary['saved_profiles'], 1)
        self.assertEqual(report.summary['historical_profile_snapshot_rows'], 1)
        self.assertEqual(report.summary['primary_variants'], 2)
        self.assertEqual(report.document['profiles'][0]['legacy_filaments'],
                         [frozen, self.magenta])

    def test_profile_id_case_collision_is_rejected(self):
        profiles = [
            {'id': 'builtin:Two', 'name': 'One', 'filaments': [self.cyan]},
            {'id': 'builtin:two', 'name': 'Two', 'filaments': [self.magenta]},
        ]
        with self.assertRaisesRegex(guard.MigrationGuardError, 'Profile identity collision'):
            self.audit(personal=[self.cyan, self.magenta], profiles=profiles)

    def test_profile_snapshot_loss_is_detected_before_any_write(self):
        self.v2.drop_profile = True
        with self.assertRaisesRegex(guard.MigrationGuardError, 'does not round-trip'):
            self.audit(personal=[self.cyan], profiles=[{
                'id': 'builtin:one', 'name': 'One', 'filaments': [self.cyan]}])

    def test_historical_profile_only_variant_is_preserved(self):
        old = sample('personal:old', '#FFFFFF', name='Old White')
        report = self.audit(personal=[self.cyan], profiles=[{
            'id': 'builtin:old', 'name': 'Old', 'filaments': [old]}])
        self.assertEqual(report.summary['snapshot_only_variants'], 1)
        self.assertTrue(any('historical variant' in n for n in report.notices))

    def test_selected_presets_remain_separate_from_color(self):
        report = self.audit(personal=[self.cyan, self.magenta])
        manifest = guard.selection_manifest(report.document,
            ['personal:magenta', 'personal:cyan'], identity_module=self.v2)
        self.assertEqual([r['variant_id'] for r in manifest['filaments']],
                         ['personal:magenta', 'personal:cyan'])
        self.assertEqual([r['color'] for r in manifest['filaments']],
                         ['#D93B90', '#08ABFB'])
        self.assertTrue(manifest['can_forecast_pla'])
        self.assertEqual(manifest['filaments'][0]['series'], 'PLA Translucent')
        self.assertEqual(manifest['filaments'][0]['source'], 'personal')
        self.assertEqual(manifest['filaments'][0]['preset_references'], [])

    def test_duplicate_or_unknown_selected_ids_fail_closed(self):
        report = self.audit(personal=[self.cyan, self.magenta])
        for ids, phrase in [(['personal:cyan', 'personal:cyan'], 'duplicate'),
                            (['personal:unknown'], 'Unknown'),
                            ([], '1–32')]:
            with self.subTest(ids=ids):
                with self.assertRaisesRegex(guard.MigrationGuardError, phrase):
                    guard.selection_manifest(report.document, ids, identity_module=self.v2)

    def test_input_objects_not_mutated_and_projection_is_deterministic(self):
        rows = [self.cyan, self.magenta]
        original = deepcopy(rows)
        a = self.audit(personal=rows)
        b = self.audit(personal=rows)
        self.assertEqual(rows, original)
        self.assertEqual(a.document, b.document)


try:
    from desktop.qt_app import filament_identity_v2 as real_v2
    from desktop.qt_app import filament_library_store as real_store
except (ImportError, OSError):
    real_v2 = real_store = None


@unittest.skipIf(real_v2 is None or real_store is None,
                 'Checkout not available; run in FullSpectrum repository for real v2 integration')
class RealLegacyIntegrationTests(unittest.TestCase):
    def test_project_real_schema_v2_and_restore_saved_snapshot(self):
        cyan = self._as_personal(self.cyan_data('#08ABFB', 'personal:a'))
        white = self._as_personal(self.cyan_data('#FFFFFF', 'personal:b'))
        profile = {'id': 'builtin:test', 'name': 'Unchanged colors',
                   'filaments': [white, cyan]}
        report = guard.audit_legacy_sources(
            personal=[cyan, white], profiles=[profile], identity_module=real_v2)
        self.assertEqual(report.summary['saved_profiles'], 1)
        self.assertEqual(report.summary['variants'], 2)
        self.assertEqual(real_v2.legacy_profile_from_document(report.document, profile['id'])['filaments'],
                         [white, cyan])
        selected = guard.selection_manifest(report.document, ['personal:a', 'personal:b'],
                                            identity_module=real_v2)
        self.assertTrue(selected['can_forecast_pla'])

    @staticmethod
    def cyan_data(color, identity):
        return {'id': identity, 'name': 'Test filament', 'brand': 'Polymaker',
                'material': 'PLA', 'series': 'PLA Translucent', 'color': color,
                'source': 'personal'}

    @staticmethod
    def _as_personal(row):
        return real_store.normalize(row, personal=True)

    def test_app_adapter_uses_no_nonlocal_filenames(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as folder:
            with patch.object(real_store, 'settings_path',
                              return_value=Path(folder) / 'settings.json'):
                a = self._as_personal(self.cyan_data('#08ABFB', 'personal:a'))
                b = self._as_personal(self.cyan_data('#FFFFFF', 'personal:b'))
                real_store.save_personal([a,b])
                pid = real_store.save_profile('Two colors', [b,a])
                p_before = (real_store.profile_root()/(pid+'.json')).read_bytes()
                a_before = real_store.personal_file().read_bytes()
                report = guard.audit_installed_library(catalog=(), store=real_store,
                                                       identity_module=real_v2)
                self.assertEqual(report.summary['saved_profiles'], 2) # 1 saved + builtin
                self.assertEqual(p_before,(real_store.profile_root()/(pid+'.json')).read_bytes())
                self.assertEqual(a_before,real_store.personal_file().read_bytes())
                self.assertFalse((Path(folder)/'filaments'/'catalog_index_v2.json').exists())


if __name__ == '__main__':
    unittest.main()
