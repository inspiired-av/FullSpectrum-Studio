"""Stage 2A: source-independent, non-destructive v1 -> v2 projection tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from desktop.qt_app import filament_identity_v2 as v2


def entry(ident, color, *, brand='Polymaker', name='Panchroma',
          material='PLA', series='PLA Translucent', optics='translucent',
          preset=None, source='personal'):
    row = {
        'id': ident, 'name': name, 'brand': brand, 'material': material,
        'series': series, 'optics': optics, 'color': color,
        'finish': 'Standard', 'source': source,
        'color_source': 'user-entered',
    }
    if preset is not None:
        row['preset'] = preset
    return row


class FilamentIdentityV2Tests(unittest.TestCase):
    def setUp(self):
        self.cyan = entry('personal:cyan', '#08ABFB', name='Panchroma Cyan')
        self.magenta = entry('personal:magenta', '#D93B90', name='Panchroma Magenta')

    def project(self, records=None, profiles=()):
        return v2.project_legacy_state(
            personal=[self.cyan, self.magenta] if records is None else records,
            profiles=profiles)

    def test_product_and_variant_are_distinct_entities(self):
        document = self.project()
        self.assertEqual(document['schema'], 2)
        self.assertEqual(len(document['products']), 1)
        self.assertEqual(len(document['variants']), 2)
        self.assertEqual({v['id'] for v in document['variants']}, {'personal:cyan', 'personal:magenta'})
        self.assertEqual(len({v['product_id'] for v in document['variants']}), 1)
        self.assertEqual(document['products'][0]['identity_status'], 'provisional-family')

    def test_same_hex_different_brand_or_same_brand_remains_distinct(self):
        first = entry('personal:one', '#000000', brand='Maker A', name='Black 1')
        second = entry('personal:two', '#000000', brand='Maker B', name='Black 2')
        third = entry('personal:three', '#000000', brand='Maker A', name='Black 3')
        snapshot = self.project([first,second,third])
        self.assertEqual(len(snapshot['variants']), 3)
        self.assertEqual(len(snapshot['products']), 2)

    def test_editing_name_or_hex_does_not_change_variant_id(self):
        a = self.project([self.cyan])
        modified = dict(self.cyan, name='Updated name', color='#25A5FA')
        b = self.project([modified])
        self.assertEqual(a['variants'][0]['id'], b['variants'][0]['id'])
        self.assertEqual(a['variants'][0]['product_id'], b['variants'][0]['product_id'])

    def test_legacy_preset_is_unverified_and_not_claimed_native(self):
        row = dict(self.cyan, preset='Bambu PLA Translucent @BBL', filamentID='GFA00')
        snap = self.project([row])
        p = snap['preset_references'][0]
        self.assertEqual(p['verification'], 'legacy-unverified')
        self.assertEqual(p['slicer'], 'unknown')
        self.assertEqual(p['preset_name'], row['preset'])
        self.assertEqual(len(snap['variants'][0]['preset_refs']), 1)

    def test_distinct_printer_preset_variants_coexist(self):
        base = dict(self.cyan)
        base['preset_refs'] = [
            {'slicer':'orcaslicer', 'preset_name':'My PLA',
             'filament_id':'GFA00','printer_model':'P1S','nozzle_mm':'0.4'},
            {'slicer':'orcaslicer', 'preset_name':'My PLA',
             'filament_id':'GFA00','printer_model':'H2C','nozzle_mm':'0.4'},
        ]
        snap = self.project([base])
        self.assertEqual(len(snap['preset_references']), 2)
        self.assertEqual(len(snap['variants'][0]['preset_refs']), 2)

    def test_profile_membership_preserves_order_and_embedded_snapshots(self):
        saved = {'id':'builtin:legacy-kit','name':'Old kit',
                 'filaments':[dict(self.magenta),dict(self.cyan)]}
        snap = self.project(profiles=[saved])
        self.assertEqual(snap['profiles'][0]['member_variant_ids'],
                         ['personal:magenta','personal:cyan'])
        copy = v2.legacy_profile_from_document(snap,'builtin:legacy-kit')
        self.assertEqual(copy,{'schema':1,'kind':'palette','name':'Old kit',
                               'filaments':saved['filaments']})

    def test_saved_profile_color_snapshot_is_not_overwritten_by_changed_library(self):
        saved = dict(self.cyan, color='#09AABB')
        snap = self.project(profiles=[{'id':'builtin:test','name':'Test',
                                      'filaments':[saved,self.magenta]}])
        canonical = next(x for x in snap['variants'] if x['id']=='personal:cyan')
        self.assertEqual(canonical['color']['hex'],'#08ABFB')
        profile = v2.legacy_profile_from_document(snap,'builtin:test')
        self.assertEqual(profile['filaments'][0]['color'],'#09AABB')

    def test_orphan_embedded_profile_is_preserved(self):
        old = entry('imported:old','#EACC00', name='Old Yellow')
        snap = self.project(records=[self.cyan], profiles=[{'id':'builtin:old',
            'name':'Old', 'filaments':[old]}])
        orphan = next(x for x in snap['variants'] if x['id']=='imported:old')
        self.assertEqual(orphan['origin'],'profile-snapshot')
        self.assertEqual(snap['profiles'][0]['member_variant_ids'],['imported:old'])

    def test_read_only_projection_does_not_mutate_source_objects(self):
        records = [self.cyan, self.magenta]
        baseline = deepcopy(records)
        one = self.project(records)
        two = self.project(records)
        self.assertEqual(records, baseline)
        self.assertEqual(one,two)

    def test_profile_duplicate_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'duplicate variant IDs'):
            self.project(profiles=[{'id':'builtin:bad','name':'Bad',
                                    'filaments':[self.cyan,self.cyan]}])

    def test_invalid_orphan_native_reference_is_rejected(self):
        snap = self.project()
        snap['variants'][0]['preset_refs']=['preset:does-not-exist']
        with self.assertRaisesRegex(ValueError,'Unresolved preset'):
            v2.validate_document(snap)

    def test_invalid_optical_class_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'optical'):
            self.project([dict(self.cyan,optics='mystery')])

    def test_optical_fields_do_not_invent_measurements(self):
        snap = self.project()
        optics = snap['variants'][0]['optical']
        self.assertEqual(optics['class'],'translucent')
        self.assertIsNone(optics['transmission_distance_mm'])
        self.assertIsNone(optics['calibration'])

    def test_index_write_is_explicit_atomic_revision_checked_and_v1_unchanged(self):
        snap = self.project()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root/'personal.json'
            legacy.write_text('{"schema":1}',encoding='utf-8')
            before = legacy.read_bytes()
            dest = root/'filaments'/'catalog_index_v2.json'
            self.assertFalse(dest.exists())
            revision = v2.write_index(snap,path=dest)
            self.assertEqual(v2.read_index(dest),snap)
            self.assertEqual(before, legacy.read_bytes())
            with self.assertRaisesRegex(ValueError,'changed'):
                v2.write_index(snap,path=dest)
            v2.write_index(snap,path=dest,expected_revision=revision)
            with self.assertRaisesRegex(ValueError,'outside'):
                v2.write_index(snap,path=root/'out.json')

    def test_corrupt_v2_index_never_deleted_or_clobbered(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)/'filaments'/'catalog_index_v2.json'
            dest.parent.mkdir(parents=True)
            dest.write_text('{not valid',encoding='utf-8')
            previous = dest.read_bytes()
            with self.assertRaisesRegex(ValueError,'Invalid'):
                v2.read_index(dest)
            with self.assertRaisesRegex(ValueError,'changed'):
                v2.write_index(self.project(),path=dest)
            self.assertEqual(previous,dest.read_bytes())


try:
    from desktop.qt_app import filament_library_store as store
except (ImportError, OSError):
    store = None


@unittest.skipIf(store is None, 'Legacy FullSpectrum store unavailable')
class StoreIntegrationTests(unittest.TestCase):
    def test_read_only_snapshot_uses_current_profile_ids(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store,'settings_path',return_value=Path(tmp)/'settings.json'):
                rows=[entry('personal:cyan','#08ABFB'), entry('personal:magenta','#D93B90')]
                store.save_personal(rows,expected_revision=None)
                saved_id = store.save_profile('Two colors', rows)
                document = store.build_identity_index_v2(catalog=())
                self.assertIn(saved_id,{p['id'] for p in document['profiles']})
                self.assertEqual({r['id'] for r in rows},
                                 set(next(p['member_variant_ids'] for p in document['profiles']
                                          if p['id']==saved_id)))
                self.assertFalse((Path(tmp)/'filaments'/'catalog_index_v2.json').exists())

    def test_explicit_export_never_changes_v1_personal_or_profile(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store,'settings_path',return_value=Path(tmp)/'settings.json'):
                rows=[entry('personal:cyan','#08ABFB'),entry('personal:magenta','#D93B90')]
                store.save_personal(rows)
                saved_id = store.save_profile('Two colors',rows)
                before_personal=store.personal_file().read_bytes()
                before_profile=(store.profile_root()/(saved_id+'.json')).read_bytes()
                revision=store.export_identity_index_v2(catalog=())
                self.assertIsInstance(revision,str)
                self.assertEqual(before_personal,store.personal_file().read_bytes())
                self.assertEqual(before_profile,(store.profile_root()/(saved_id+'.json')).read_bytes())
                with self.assertRaisesRegex(ValueError,'changed'):
                    store.export_identity_index_v2(catalog=())

if __name__ == '__main__':
    unittest.main()
