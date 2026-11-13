"""Stage 2A.3 — variant IDs survive active palette / engine selection.

Uses temp files only. No modification of installed slicers, user preferences,
local library/profile data, or the real 3MF exporter is performed here.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from desktop.qt_app import filament_library_store as store
from desktop.qt_app.filament_preferences import FilamentPreferences
from desktop.filament_options import selectable_filament_options
import fullspectrum_engine as engine


def record(identity, brand, name, hexcolor, *, series='PLA Basic'):
    return store.normalize({
        'id':identity, 'source':'personal', 'name':name, 'brand':brand,
        'series':series, 'color':hexcolor, 'optics':'opaque',
        'material':'PLA', 'finish':'Standard',
    }, personal=True)


class VariantSlotsTests(TestCase):
    def setUp(self):
        self.black_a = record('personal:variant-A', 'Vendor A', 'Vendor A Black', '#000000')
        self.black_b = record('personal:variant-B', 'Vendor B', 'Vendor B Black', '#000000')
        self.white = record('personal:variant-white', 'Vendor C', 'White', '#FFFFFF')
        self.entries = [self.black_a,self.black_b,self.white]

    def _palette(self, destination, records=None):
        value = store._active_entries(records if records is not None else self.entries)
        file = Path(destination) / 'test-palette.json'
        file.write_text(json.dumps({'filaments':value}),encoding='utf8')
        return file

    def test_same_color_variants_are_kept_by_stable_identity(self):
        entries=store._active_entries(self.entries)
        self.assertEqual([r['id'] for r in entries],
                         [r['id'] for r in self.entries])
        self.assertEqual(len({r['color'] for r in entries}),2)

    def test_active_palette_stores_both_ids_and_engine_distinguishes_them(self):
        with TemporaryDirectory() as directory:
            target=Path(directory)/'active_palette.json'
            with patch.object(store, 'active_file', return_value=target):
                store.activate_palette(self.entries)
                self.assertEqual(store.active_ids(), {r['id'] for r in self.entries})
            data=json.loads(target.read_text())
            self.assertEqual(data['fullspectrum_selection'], [r['id'] for r in self.entries])
            options=engine.custom_palette(target)
            self.assertEqual([engine.anchor_key(o) for o in options],
                             [self.black_a['id'],self.black_b['id'],'PLA Basic|#FFFFFF'])
            self.assertEqual(len(options),3)
            self.assertEqual({o['color'] for o in options},{'#000000','#FFFFFF'})

    def test_exact_variant_required_pin_wins(self):
        with TemporaryDirectory() as directory:
            options=engine.custom_palette(self._palette(directory))
        pinned=engine.resolve_pinned_anchors(options,[self.black_b['id']])
        self.assertEqual([o.get('variant_id') for o in pinned],[self.black_b['id']])
        self.assertEqual([engine.anchor_key(o) for o in
                          engine.restrict_allowed_anchors(options,[self.black_a['id']])],
                         [self.black_a['id']])
        self.assertTrue(engine.anchor_matches_key(options[0],'PLA Basic|#000000'))

    def test_two_same_color_required_variants_are_actionable_error(self):
        with TemporaryDirectory() as directory:
            options=engine.custom_palette(self._palette(directory))
        with self.assertRaisesRegex(RuntimeError,'same displayed HEX'):
            engine.resolve_pinned_anchors(options,[self.black_a['id'],self.black_b['id']])
        with self.assertRaisesRegex(RuntimeError,'multiple physical variants'):
            engine.resolve_pinned_anchors(options,['PLA Basic|#000000'])

    def test_legacy_palette_keys_unchanged_when_no_collisions(self):
        with TemporaryDirectory() as directory:
            options=engine.custom_palette(self._palette(directory,[self.black_a,self.white]))
        self.assertEqual([engine.anchor_key(o) for o in options],
                         ['PLA Basic|#000000','PLA Basic|#FFFFFF'])
        self.assertEqual([o['variant_id'] for o in options],
                         [self.black_a['id'],self.white['id']])

    def test_selector_has_two_distinct_black_variants(self):
        with TemporaryDirectory() as directory:
            file=self._palette(directory)
            options=selectable_filament_options(engine,'custom',None,file)
        self.assertEqual(len(options),3)
        blacks=[o for o in options if o['color']=='#000000']
        self.assertEqual({o['key'] for o in blacks},
                         {self.black_a['id'],self.black_b['id']})

    def test_mixed_identified_and_unidentified_duplicate_colors_fail_closed(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'custom.json'
            entries=store._active_entries(self.entries)
            entries[0].pop('id')
            path.write_text(json.dumps({'filaments':entries}), encoding='utf8')
            with self.assertRaisesRegex(RuntimeError,'Assign a unique stable id'):
                engine.custom_palette(path)

    def test_legacy_unidentified_duplicates_use_one_selector_key(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.json'
            data=[{'name':'Black One','series':'PLA Basic','color':'#000000'},
                  {'name':'Black Two','series':'PLA Basic','color':'#000000'},
                  {'name':'White','series':'PLA Basic','color':'#FFFFFF'}]
            path.write_text(json.dumps({'filaments':data}), encoding='utf8')
            options=engine.custom_palette(path)
            self.assertEqual(len(options),3)  # Legacy engine input is unchanged.
            self.assertEqual([engine.anchor_key(o) for o in options],
                             ['PLA Basic|#000000','PLA Basic|#000000','PLA Basic|#FFFFFF'])
            selector=selectable_filament_options(engine,'custom',None,str(path))
            self.assertEqual(len(selector),2)  # The UI adapter collapses aliases.

    def test_duplicate_variant_id_fails_closed(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'custom.json'
            entries=store._active_entries(self.entries)
            entries[1]['id']=entries[0]['id']
            path.write_text(json.dumps({'filaments':entries}), encoding='utf8')
            with self.assertRaisesRegex(RuntimeError,'duplicate stable filament IDs'):
                engine.custom_palette(path)

    def test_require_duplicate_same_hex_rejected_in_filaments_ui_preferences(self):
        # Pure-model path; no window or filesystem settings are read.
        pref=object.__new__(FilamentPreferences)
        pref.disabled=set()
        pref.pinned=set()
        pref.solid_assignments={}
        pref._dirty=False
        pref.saved={'disabled_anchor_keys':[], 'pinned_anchor_keys':[]}
        opts=[{'key':self.black_a['id'],'color':'#000000'},
              {'key':self.black_b['id'],'color':'#000000'},
              {'key':self.white['id'],'color':'#FFFFFF'}]
        enabled={row['key'] for row in opts}
        with self.assertRaisesRegex(ValueError,'same displayed HEX'):
            pref.apply(opts,enabled,{self.black_a['id'],self.black_b['id']},6)
        self.assertEqual(pref.pinned,set())  # Rejection is atomic.

    def test_legacy_custom_without_ids_still_supported(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'old.json'
            path.write_text(json.dumps({'filaments':[
                {'name':'Black','series':'PLA Basic','color':'#000000'},
                {'name':'White','series':'PLA Basic','color':'#FFFFFF'},
            ]}),encoding='utf8')
            result=engine.custom_palette(path)
        self.assertEqual([engine.anchor_key(r) for r in result],
                         ['PLA Basic|#000000','PLA Basic|#FFFFFF'])

    def test_stable_id_survives_record_rename_and_recolor(self):
        before=dict(self.black_a)
        after=store.normalize(dict(before,name='Renamed',color='#111111'),personal=True)
        self.assertEqual(after['id'],before['id'])


if __name__ == '__main__':
    main()
