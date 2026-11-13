"""Regression coverage for legacy series|HEX duplicates after Stage 2A.3.

This tests backward compatibility without any modifications to saved profiles.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main

import fullspectrum_engine as engine
from desktop.filament_options import selectable_filament_options


class LegacyDuplicateCompatibility(TestCase):
    def palette(self, folder, records):
        path = Path(folder) / 'palette.json'
        path.write_text(json.dumps({'filaments': records}), encoding='utf-8')
        return path

    def test_legacy_duplicates_preserve_single_selector_key(self):
        with TemporaryDirectory() as folder:
            path = self.palette(folder, [
                {'name': 'Black One', 'series': 'PLA Basic', 'color': '#000000'},
                {'name': 'Black Two', 'series': 'PLA Basic', 'color': '#000000'},
                {'name': 'White', 'series': 'PLA Basic', 'color': '#FFFFFF'},
            ])
            candidates = engine.custom_palette(path)
            options = selectable_filament_options(engine, 'custom', None, str(path))
        self.assertEqual(len(candidates), 3)  # Legacy planner input unchanged.
        self.assertEqual([engine.anchor_key(a) for a in candidates], [
            'PLA Basic|#000000', 'PLA Basic|#000000', 'PLA Basic|#FFFFFF'])
        self.assertEqual(len(options), 2)
        self.assertEqual({o['key'] for o in options},
                         {'PLA Basic|#000000', 'PLA Basic|#FFFFFF'})

    def test_legacy_same_hex_can_still_appear_with_real_palette_colors(self):
        with TemporaryDirectory() as folder:
            colors = [
                {'name': name, 'color': hexcode}
                for name, hexcode in engine.BAMBU_PLA
            ]
            colors += [{'name': 'Extra duplicate black', 'color': '#000000'}]
            path = self.palette(folder, colors)
            options = engine.custom_palette(path)
        self.assertGreaterEqual(len({c['color'] for c in options}), 2)
        self.assertTrue(all(not c.get('identity_collision') for c in options))

    def test_explicit_ids_keep_same_color_variants_separate(self):
        with TemporaryDirectory() as folder:
            path = self.palette(folder, [
                {'id': 'personal:vendorA', 'name': 'A Black', 'series': 'PLA Basic', 'color': '#000000'},
                {'id': 'personal:vendorB', 'name': 'B Black', 'series': 'PLA Basic', 'color': '#000000'},
                {'id': 'personal:white', 'name': 'White', 'series': 'PLA Basic', 'color': '#FFFFFF'},
            ])
            result = selectable_filament_options(engine, 'custom', None, str(path))
        blacks = [r for r in result if r['color'] == '#000000']
        self.assertEqual({r['key'] for r in blacks}, {'personal:vendorA', 'personal:vendorB'})
        self.assertEqual(len(result), 3)

    def test_partial_ids_in_collision_still_rejected(self):
        with TemporaryDirectory() as folder:
            path = self.palette(folder, [
                {'id': 'personal:vendorA', 'name': 'A', 'series': 'PLA Basic', 'color': '#000000'},
                {'name': 'Unidentified B', 'series': 'PLA Basic', 'color': '#000000'},
                {'name': 'White', 'series': 'PLA Basic', 'color': '#FFFFFF'},
            ])
            with self.assertRaisesRegex(RuntimeError, 'Assign a unique stable id'):
                engine.custom_palette(path)

    def test_two_entries_cannot_share_same_stable_id(self):
        with TemporaryDirectory() as folder:
            path = self.palette(folder, [
                {'id': 'personal:duplicate', 'name': 'A', 'series': 'PLA Basic', 'color': '#000000'},
                {'id': 'personal:duplicate', 'name': 'B', 'series': 'PLA Basic', 'color': '#000000'},
                {'name': 'White', 'series': 'PLA Basic', 'color': '#FFFFFF'},
            ])
            with self.assertRaisesRegex(RuntimeError, 'duplicate stable filament IDs'):
                engine.custom_palette(path)


if __name__ == '__main__':
    main()
