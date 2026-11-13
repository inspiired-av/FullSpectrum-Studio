"""Stage 2A.2: preserve metadata through personal edits and palette snapshots."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app import filament_library_store as store
from desktop.qt_app.filament_identity_v2 import project_legacy_state, legacy_profile_from_document
from desktop.qt_app.filament_metadata_v2 import retain_optional_metadata


def personal(name='Cyan', hex='#08ABFB', identity='personal:cyan'):
    return store.normalize({
        'id': identity, 'name': name, 'brand': 'Polymaker',
        'series': 'PLA Translucent', 'material': 'PLA',
        'color': hex, 'source': 'personal', 'optics': 'translucent',
        'finish': 'Translucent', 'color_source': 'manufacturer-published',
        'sku': 'SKU-CYAN', 'product_series': 'Panchroma Translucent',
        'product_id': 'product:polymaker-panchroma',
        'manufacturer_url': 'https://example.org/filaments/cyan',
        'last_verified': '2026-11-12',
        'measured_lab': {'L': 50.5, 'a': -15.2, 'b': -28.6},
        'transmission_distance_mm': 0.6,
        'optical_calibration': {'method': 'test-illustrative', 'confidence': 'unverified'},
        'preset_refs': [
            {'slicer': 'orcaslicer', 'preset_name': 'Panchroma on H2C',
             'filament_id': 'PM-123', 'printer_model': 'H2C',
             'nozzle_mm': '0.4', 'verification': 'unverified'},
            {'slicer': 'bambu_studio', 'preset_name': 'PLA Translucent',
             'printer_model': 'P1S', 'nozzle_mm': '0.4'}
        ]}, personal=True)


class MetadataTests(unittest.TestCase):
    def test_fields_survive_normalizing_again(self):
        original = personal()
        reloaded = store.normalize(original, personal=True)
        self.assertEqual(reloaded, original)
        self.assertEqual(reloaded['id'], 'personal:cyan')
        self.assertEqual(len(reloaded['preset_refs']), 2)

    def test_name_change_does_not_clear_identity_or_preset_refs(self):
        original = personal()
        renamed = store.normalize({**original, 'name': 'Cyan Updated'}, personal=True)
        self.assertEqual(original['id'], renamed['id'])
        self.assertEqual(original['preset_refs'], renamed['preset_refs'])
        self.assertEqual(original['optical_calibration'], renamed['optical_calibration'])
        self.assertEqual(original['manufacturer_url'], renamed['manufacturer_url'])

    def test_different_brand_same_hex_remain_distinct(self):
        a = personal()
        b = store.normalize({**a, 'id': 'personal:cyan2', 'brand': 'Other Brand'}, personal=True)
        merged = store.merged_filaments(personal=[a, b])
        self.assertEqual(len([x for x in merged if x['id'] in (a['id'], b['id'])]), 2)

    def test_schema_projection_keeps_preset_and_optical_data(self):
        cyan, magenta = personal(), personal('Magenta', '#D93B90', 'personal:magenta')
        doc = project_legacy_state(personal=[cyan, magenta], profiles=[{
            'id': 'builtin:unit-test', 'name': 'Five colors subset',
            'filaments': [cyan, magenta],
        }])
        self.assertEqual(legacy_profile_from_document(doc, 'builtin:unit-test')['filaments'], [cyan, magenta])
        indexed = next(v for v in doc['variants'] if v['id'] == cyan['id'])
        self.assertEqual(len(indexed['preset_refs']), 2)
        self.assertEqual(indexed['optical']['transmission_distance_mm'], 0.6)

    def test_invalid_or_untrusted_metadata_rejected(self):
        row = personal()
        bad = [
            ('manufacturer_url', 'file:///etc/passwd'),
            ('product_id', 'not a proper id with spaces'),
            ('last_verified', '2026-22-99'),
            ('measured_lab', {'L': float('nan'), 'a': 0, 'b': 0}),
            ('transmission_distance_mm', float('inf')),
            ('preset_refs', [{'slicer': 'orcaslicer', 'preset_name': 'PLA', 'evil': '1'}]),
            ('preset_refs', [{'slicer': 'untrusted', 'preset_name': 'PLA'}]),
            ('optical_calibration', {'value': float('nan')}),
        ]
        for key, value in bad:
            with self.subTest(key=key, value=str(value)):
                with self.assertRaises(ValueError):
                    store.normalize({**row, key: value}, personal=True)

    def test_legacy_v1_records_remain_valid(self):
        legacy = store.normalize({'id':'personal:legacy', 'name':'Old Cyan',
                                  'brand':'Generic', 'series':'PLA Basic',
                                  'color':'#00ffff', 'source':'personal'}, personal=True)
        self.assertNotIn('preset_refs', legacy)
        self.assertNotIn('product_id', legacy)
        self.assertEqual(legacy['color'], '#00FFFF')


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = Path(tmp.name) / 'settings.json'
        ctx = patch.object(store, 'settings_path', return_value=settings)
        ctx.start()
        self.addCleanup(ctx.stop)

    def test_personal_and_profile_roundtrip_without_schema_change(self):
        cyan = personal()
        magenta = personal('Magenta', '#D93B90', 'personal:magenta')
        before_id = cyan['id']
        store.save_personal([cyan, magenta], expected_revision=None)
        loaded, rev = store.read_personal()
        self.assertEqual(loaded[0]['id'], before_id)
        self.assertEqual(loaded[0]['manufacturer_url'], cyan['manufacturer_url'])
        updated = store.normalize({**loaded[0], 'name': 'Cyan v2'}, personal=True)
        store.save_personal([updated, loaded[1]], expected_revision=rev)
        profile_id = store.save_profile('My Panchroma', [updated, loaded[1]])
        profile = store.get_profile(profile_id)
        self.assertEqual(profile['filaments'][0]['name'], 'Cyan v2')
        self.assertEqual(profile['filaments'][0]['preset_refs'], cyan['preset_refs'])
        self.assertEqual(profile['filaments'][0]['id'], before_id)
        data = json.loads((store.profile_root() / (profile_id + '.json')).read_text(encoding='utf8'))
        self.assertEqual(data['schema'], 1)  # Deliberate v1 compatibility.
        doc = store.build_identity_index_v2(catalog=[])
        embedded = next(p for p in doc['profiles'] if p['id'] == profile_id)
        self.assertEqual(embedded['member_variant_ids'][0], before_id)
        self.assertEqual(embedded['legacy_filaments'][0]['manufacturer_url'], cyan['manufacturer_url'])


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.filament_library_dialog import FilamentEntryDialog
except (OSError, ImportError):
    QApplication = None


@unittest.skipIf(QApplication is None, 'PySide6 is unavailable')
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_name_keeps_identity_provenance_and_preset_refs(self):
        initial = personal()
        dialog = FilamentEntryDialog(initial)
        try:
            dialog.name.setText('New Display Name')
            dialog._accept()
            self.assertEqual(dialog.entry['id'], initial['id'])
            self.assertEqual(dialog.entry['preset_refs'], initial['preset_refs'])
            self.assertEqual(dialog.entry['measured_lab'], initial['measured_lab'])
            self.assertEqual(dialog.entry['color_source'], initial['color_source'])
            self.assertEqual(dialog.entry['manufacturer_url'], initial['manufacturer_url'])
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()
