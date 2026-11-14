"""Stage 2A.2: same-HEX alternatives and safe profile selection integration.

Pure tests work without Qt. Repository integration tests use temporary app-owned
files and no printer, slicer, user palette, or export files.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app.filament_variant_profile_selection import (
    available_profile_variants, append_profile_variants)


def filament(identity, color, brand='A', *, material='PLA'):
    return {'id': identity, 'name': identity, 'brand': brand,
            'material': material, 'series': 'PLA Basic', 'color': color}


class VariantPolicyTests(unittest.TestCase):
    def setUp(self):
        self.a = filament('personal:one', '#000000', 'Brand A')
        self.b = filament('personal:two', '#000000', 'Brand B')
        self.white = filament('personal:white', '#FFFFFF', 'Brand C')

    def test_same_family_and_hex_are_distinct_addable_variants(self):
        result = available_profile_variants([self.a, self.b, self.white], [self.a])
        self.assertEqual([r['id'] for r in result], ['personal:two', 'personal:white'])

    def test_both_alternative_colors_can_join_portable_profile(self):
        combined = append_profile_variants([self.a, self.white], [self.b])
        self.assertEqual([r['id'] for r in combined],
                         ['personal:one', 'personal:white', 'personal:two'])
        self.assertEqual({r['color'] for r in combined}, {'#000000', '#FFFFFF'})

    def test_membership_never_replaces_historical_snapshot(self):
        previous = dict(self.a, name='Historical name', color='#010101')
        output = append_profile_variants([previous, self.white], [self.a, self.b])
        self.assertEqual(output[0], previous)
        self.assertEqual(output[-1], self.b)
        self.assertIs(output[0], previous)

    def test_live_catalog_wins_over_profile_snapshot_as_candidate(self):
        old = dict(self.a, name='Old snapshot')
        available = available_profile_variants([self.a, old, self.b], [self.white])
        self.assertEqual(available, [self.a, self.b])

    def test_duplicate_stable_ids_do_not_multiply_selection(self):
        self.assertEqual(append_profile_variants([self.a, self.white], [self.a, self.a]),
                         [self.a, self.white])
        self.assertEqual(available_profile_variants([self.b, self.b, self.a], []),
                         [self.b, self.a])

    def test_duplicate_ids_with_conflicting_requested_data_fail(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting candidate'):
            append_profile_variants([self.white], [self.a, dict(self.a, color='#222222')])

    def test_nonpla_available_entries_not_offered(self):
        tpu = filament('personal:flex', '#000000', 'Brand D', material='TPU')
        self.assertEqual(available_profile_variants([tpu, self.a], []), [self.a])
        with self.assertRaisesRegex(ValueError, 'Only PLA'):
            append_profile_variants([self.a, self.white], [tpu])

    def test_invalid_ids_are_rejected_without_mutating_selection(self):
        before = [self.a, self.white]
        with self.assertRaisesRegex(ValueError, 'stable ID'):
            append_profile_variants(before, [dict(self.b, id='')])
        self.assertEqual(before, [self.a, self.white])

    def test_original_inputs_not_mutated(self):
        choices = [self.a, self.b, self.white]
        previous = [self.a]
        original = json.dumps([choices, previous], sort_keys=True)
        available_profile_variants(choices, previous)
        append_profile_variants(previous, [self.b, self.white])
        self.assertEqual(json.dumps([choices, previous], sort_keys=True), original)


try:
    from desktop.qt_app import filament_library_store as store
    import fullspectrum_engine as engine
    from desktop.filament_options import selectable_filament_options
    from desktop.qt_app.filament_preferences import FilamentPreferences
except ImportError:
    store = engine = selectable_filament_options = FilamentPreferences = None


@unittest.skipIf(store is None or engine is None, 'Requires FullSpectrum repository')
class LivePaletteIntegrationTests(unittest.TestCase):
    def make(self, identity, color, brand):
        return store.normalize(filament(identity, color, brand), personal=True)

    def test_profile_save_activate_and_engine_selection_of_same_hex_variants(self):
        a = self.make('personal:one', '#000000', 'Brand A')
        b = self.make('personal:two', '#000000', 'Brand B')
        white = self.make('personal:white', '#FFFFFF', 'Brand C')
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, 'settings_path', return_value=Path(tmp) / 'settings.json'):
                saved_id = store.save_profile('Alternatives', [a, white, b])
                saved = store.get_profile(saved_id)['filaments']
                self.assertEqual([r['id'] for r in saved], [a['id'], white['id'], b['id']])
                path = store.activate_palette(saved)
                document = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(document['fullspectrum_selection'], [a['id'], white['id'], b['id']])
                options = engine.custom_palette(path)
                keys = [engine.anchor_key(o) for o in options]
                self.assertEqual(keys, [a['id'], 'PLA Basic|#FFFFFF', b['id']])
                choices = selectable_filament_options(engine, 'custom', None, str(path))
                self.assertEqual(len(choices), 3)
                self.assertEqual({o['key'] for o in choices if o['color'] == '#000000'},
                                 {a['id'], b['id']})

    def test_mixed_palette_with_same_hex_still_requires_two_distinct_colors(self):
        a = self.make('personal:one', '#000000', 'Brand A')
        b = self.make('personal:two', '#000000', 'Brand B')
        with self.assertRaisesRegex(ValueError, 'at least two different colors'):
            store._active_entries([a, b])

    def test_one_required_same_hex_variant_allowed_but_two_rejected(self):
        pref = object.__new__(FilamentPreferences)
        pref.disabled = set(); pref.pinned = set(); pref.solid_assignments = {}
        pref.saved = {'disabled_anchor_keys': [], 'pinned_anchor_keys': []}
        pref._dirty = False
        options = [
            {'key': 'personal:one', 'color': '#000000'},
            {'key': 'personal:two', 'color': '#000000'},
            {'key': 'personal:white', 'color': '#FFFFFF'},
        ]
        enabled = {x['key'] for x in options}
        pref.apply(options, enabled, {'personal:one'}, 6)
        self.assertEqual(pref.pinned, {'personal:one'})
        with self.assertRaisesRegex(ValueError, 'same displayed HEX'):
            pref.apply(options, enabled, {'personal:one', 'personal:two'}, 6)
        self.assertEqual(pref.pinned, {'personal:one'})


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.filament_profile_manager import ProfileFilamentPicker
    from desktop.qt_app.filament_library_profile_tab import FilamentProfileTab
except ImportError:
    QApplication = ProfileFilamentPicker = FilamentProfileTab = None


@unittest.skipIf(QApplication is None, 'PySide6 unavailable')
class QtProfilePickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_picker_lists_same_hex_alternative(self):
        a = filament('personal:one', '#000000')
        b = filament('personal:two', '#000000')
        white = filament('personal:white', '#FFFFFF')
        dialog = ProfileFilamentPicker([a, b, white], [a])
        try:
            self.assertEqual([r['id'] for r in dialog.records], ['personal:two', 'personal:white'])
        finally:
            dialog.close()

    def test_embedded_profile_tab_shows_same_hex_alternative(self):
        a = filament('personal:one', '#000000')
        b = filament('personal:two', '#000000')
        white = filament('personal:white', '#FFFFFF')
        from desktop.qt_app import filament_library_profile_tab as profile_tab_module
        with patch.object(profile_tab_module, 'profile_choices', return_value=[]):
            tab = FilamentProfileTab([a, b, white], selected_provider=lambda: [])
            try:
                tab._items = [a, white]
                tab._populate_available()
                self.assertIn('personal:two', tab._catalog)
            finally:
                tab.close()


if __name__ == '__main__':
    unittest.main()
