"""Regression tests for the PLA-first unified library and quick palette files."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.qt_app import filament_library_store as library


def custom(name='Cyan',color='#08ABFB',brand='Polymaker',identity=None):
    item={'name':name,'brand':brand,'series':'PLA Translucent',
          'color':color,'material':'PLA','optics':'translucent',
          'source':'personal','color_source':'user-entered'}
    if identity:item['id']=identity
    return library.normalize(item,personal=True)


class UnifiedLibraryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings=Path(self.temp.name)/'settings.json'
        p=patch.object(library,'settings_path',return_value=self.settings)
        p.start();self.addCleanup(p.stop)

    def test_generic_records_flag_approximate_and_stable_ids(self):
        one=library.generic_filaments()
        two=library.generic_filaments()
        self.assertEqual([x['id'] for x in one],[x['id'] for x in two])
        self.assertTrue(all(x['color_source']=='approximate' for x in one))
        self.assertTrue(any(x['series']=='PLA Translucent' for x in one))

    def test_personal_add_edit_keep_stable_id(self):
        a=custom()
        rev=library.save_personal([a])
        self.assertIsNotNone(rev)
        existing,rev2=library.read_personal()
        self.assertEqual(existing[0]['id'],a['id'])
        edited={**existing[0], 'name':'Cyan v2'}
        library.save_personal([edited],expected_revision=rev2)
        loaded,_=library.read_personal()
        self.assertEqual(loaded[0]['id'],a['id'])
        self.assertEqual(loaded[0]['name'],'Cyan v2')

    def test_concurrent_changes_rejected(self):
        library.save_personal([custom()])
        with self.assertRaisesRegex(ValueError,'changed on disk'):
            library.save_personal([],expected_revision=None)

    def test_malformed_personal_is_not_clobbered(self):
        path=library.personal_file()
        path.parent.mkdir(parents=True)
        path.write_text('{broken',encoding='utf-8')
        before=path.read_bytes()
        with self.assertRaises(ValueError):library.read_personal()
        with self.assertRaises(ValueError):library.save_personal([])
        self.assertEqual(before,path.read_bytes())

    def test_legacy_personal_library_is_read_only_migrated(self):
        legacy=library.legacy_file()
        legacy.write_text(json.dumps({'filaments':[{'name':'Cyan','brand':'Panchroma',
                         'series':'PLA Basic','color':'#08ABFB'}]}),encoding='utf-8')
        loaded,rev=library.read_personal()
        self.assertEqual(loaded[0]['source'],'personal')
        self.assertEqual(rev,None)
        library.save_personal(loaded,expected_revision=None)
        self.assertTrue(library.personal_file().is_file())
        self.assertEqual(json.loads(legacy.read_text())['filaments'][0]['name'],'Cyan')

    def test_two_brands_same_hex_are_distinct_library_entries(self):
        one=custom(brand='Maker A',identity='personal:001')
        two=custom(brand='Maker B',identity='personal:002')
        merged=library.merged_filaments(personal=[one,two])
        self.assertIn('personal:001',{r['id'] for r in merged})
        self.assertIn('personal:002',{r['id'] for r in merged})
        # Same-HEX variants are distinct records, but a printable palette still
        # requires at least two different *colors* (not merely two products).
        with self.assertRaisesRegex(ValueError,'at least two'):
            library.activate_palette([one,two])

    def test_two_distinct_colors_activate_in_engine_format(self):
        items=[custom(),custom('Magenta','#D93B90')]
        path=library.activate_palette(items)
        result=json.loads(path.read_text())
        self.assertEqual(set(result),{'filaments','fullspectrum_selection'})
        self.assertEqual(len(result['filaments']),2)
        self.assertEqual(result['filaments'][0]['series'],'PLA Translucent')
        self.assertEqual(library.active_ids(),{r['id'] for r in items})

    def test_one_color_and_nonpla_refused_for_activation(self):
        with self.assertRaisesRegex(ValueError,'at least two'):
            library.activate_palette([custom()])
        t=custom('PETG','#D93B90')
        t['material']='PETG';t['experimental']=True
        with self.assertRaisesRegex(ValueError,'Non-PLA'):
            library.activate_palette([custom(),t])

    def test_quick_profile_stores_embedded_portable_entries(self):
        items=[custom(),custom('Magenta','#D93B90')]
        identity=library.save_profile('Five-Color Test',items)
        record=library.get_profile(identity)
        self.assertEqual(record['name'],'Five-Color Test')
        self.assertEqual([x['color'] for x in record['filaments']],
                         ['#08ABFB','#D93B90'])
        library.activate_palette(record['filaments'])
        self.assertEqual(len(json.loads(library.active_file().read_text())['filaments']),2)

    def test_duplicate_profile_name_refused(self):
        items=[custom(),custom('Magenta','#D93B90')]
        library.save_profile('My Kit',items)
        with self.assertRaisesRegex(ValueError,'already exists'):
            library.save_profile('my kit',items)

    def test_import_legacy_json_creates_vetted_profile_not_edit_source(self):
        source=Path(self.temp.name)/'outside.json'
        source.write_text(json.dumps({'filaments':[
            {'name':'Cyan','series':'PLA Basic','color':'#08ABFB'},
            {'name':'Magenta','series':'PLA Basic','color':'#D93B90'}]}),encoding='utf-8')
        before=source.read_bytes()
        key=library.import_profile(source)
        self.assertEqual(len(library.get_profile(key)['filaments']),2)
        self.assertEqual(before,source.read_bytes())

    def test_repeated_catalog_scans_do_not_duplicate(self):
        class FakeEngine:
            @staticmethod
            def catalog_palette(scope):
                assert scope=='all'
                return [{'name':'Bambu Blue','series':'PLA Basic','color':'#1122AA',
                         'brand':'Bambu Lab','filamentID':'GFA00'}]*3
            @staticmethod
            def anchor_option_payload(item):
                return dict(item)
        first=library.bambu_catalog_filaments(FakeEngine)
        second=library.bambu_catalog_filaments(FakeEngine)
        self.assertEqual(len(first),1)
        self.assertEqual(first[0]['id'],second[0]['id'])
        self.assertEqual(first[0]['color_source'],'bundled-fallback')

    def test_optical_type_is_not_silently_opaque(self):
        entry=custom()
        self.assertEqual(entry['optics'],'translucent')
        self.assertEqual(entry['color_source'],'user-entered')
        with self.assertRaises(ValueError):
            library.normalize({**entry,'optics':'mystery'})

    def test_profile_file_path_is_app_owned(self):
        records=[custom(),custom('Magenta','#D93B90')]
        ident=library.save_profile('Portable',records)
        path=library.profile_root()/(ident+'.json')
        self.assertEqual(path.parent,library.settings_path().parent/'palettes')
        self.assertTrue(path.is_file())


try:
    from PySide6.QtWidgets import QApplication, QTableView
    from desktop.qt_app.filament_library_dialog import FilamentEntryDialog, FilamentLibraryDialog
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 unavailable')
class UnifiedLibraryQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_entry_dialog_color_picker_and_hex_controls(self):
        dialog=FilamentEntryDialog()
        self.assertTrue(dialog.color.isEnabled())
        self.assertEqual(dialog.material.currentText(),'PLA')
        dialog.material.setCurrentText('PETG')
        self.assertFalse(dialog.series.isEnabled())
        dialog.close()

    def test_library_dialog_profile_actions_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(library,'settings_path',return_value=Path(folder)/'settings.json'):
                dialog=FilamentLibraryDialog()
                self.assertIsNotNone(dialog.findChild(QTableView,'unifiedFilamentTable'))
                dialog.close()


if __name__=='__main__':
    unittest.main()
