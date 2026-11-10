"""Regression checks for legacy manufacturer series, profile edits, and worker shutdown."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.qt_app import filament_library_store as lib


SAMPLE = {'filaments': [
    {'name':'Generic PLA Basic - Black', 'brand':'Generic',
     'series':'PLA Basic', 'color':'#000000'},
    {'name':'Generic PLA Basic - White', 'brand':'Generic',
     'series':'PLA Basic', 'color':'#FFFFFF'},
    {'name':'Polymaker Panchroma Translucent PLA - Translucent Cyan',
     'brand':'Polymaker','series':'Panchroma Translucent PLA','color':'#08ABFB'},
    {'name':'Polymaker Panchroma Translucent PLA - Translucent Magenta',
     'brand':'Polymaker','series':'Panchroma Translucent PLA','color':'#D93B90'},
    {'name':'Polymaker Panchroma Translucent PLA - Translucent Yellow',
     'brand':'Polymaker','series':'Panchroma Translucent PLA','color':'#F9ED3D'},
    {'name':'Polymaker Panchroma Translucent PLA - Translucent Grey',
     'brand':'Polymaker','series':'Panchroma Translucent PLA','color':'#9199A4'},
]}


class ImportAndProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher=patch.object(lib,'settings_path',
                             return_value=Path(self.temp.name)/'settings.json')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source=Path(self.temp.name)/'FSS_Filaments_Generic_Black_White_Panchroma_CMYG.json'
        self.source.write_text(json.dumps(SAMPLE,indent=2),encoding='utf-8')

    def test_exact_six_color_panchroma_sample_imports(self):
        before=self.source.read_bytes()
        title,entries=lib.parse_import_profile(self.source)
        self.assertEqual(title,self.source.stem)
        self.assertEqual(len(entries),6)
        self.assertEqual([e['series'] for e in entries[2:]],['PLA Translucent']*4)
        self.assertEqual([e['product_series'] for e in entries[2:]],
                         ['Panchroma Translucent PLA']*4)
        self.assertTrue(all(e['optics']=='translucent' for e in entries[2:]))
        identity=lib.import_profile(self.source)
        profile=lib.get_profile(identity)
        self.assertEqual([e['color'] for e in profile['filaments']],
                         [r['color'] for r in SAMPLE['filaments']])
        self.assertEqual(self.source.read_bytes(),before)
        active=lib.activate_palette(profile['filaments'])
        engine=json.loads(active.read_text())['filaments']
        self.assertEqual(engine[2]['series'],'PLA Translucent')
        self.assertEqual(engine[2]['brand'],'Polymaker')
        self.assertNotIn('preset',engine[2])  # Never invent a native exact preset.

    def test_import_does_not_silently_map_unrecognized_manufacturer_family(self):
        data=dict(SAMPLE)
        data['filaments']=[dict(r) for r in SAMPLE['filaments']]
        data['filaments'][2]['series']='Unknown Exotic PLA'
        self.source.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Unknown PLA slicer profile'):
            lib.import_profile(self.source)
        self.assertFalse(lib.profile_root().exists())

    def test_import_duplicate_never_silently_overwrites(self):
        old=lib.import_profile(self.source)
        saved=lib.get_profile(old)
        with self.assertRaisesRegex(ValueError,'already exists'):
            lib.import_profile(self.source)
        self.assertEqual(saved,lib.get_profile(old))
        self.assertEqual(len(lib.list_profiles()),1)

    def test_explicit_import_replacement_keeps_profile_id(self):
        identity=lib.import_profile(self.source)
        revision=lib.saved_profile_revision(identity)
        original=lib.get_profile(identity)
        data=json.loads(self.source.read_text())
        data['filaments'][2]['color']='#07A9F1'
        self.source.write_text(json.dumps(data),encoding='utf-8')
        replaced=lib.import_profile(self.source,replace_profile_id=identity,
                                     expected_revision=revision)
        self.assertEqual(replaced,identity)
        self.assertEqual(len(lib.list_profiles()),1)
        self.assertNotEqual(original['filaments'][2]['color'],
                            lib.get_profile(identity)['filaments'][2]['color'])
        self.assertEqual(lib.get_profile(identity)['filaments'][2]['product_series'],
                         'Panchroma Translucent PLA')

    def test_explicit_replacement_requires_revision_and_matching_name(self):
        ident=lib.import_profile(self.source)
        oldrev=lib.saved_profile_revision(ident)
        records=lib.get_profile(ident)['filaments']
        lib.update_saved_profile(ident,records[:5],expected_revision=oldrev)
        with self.assertRaisesRegex(ValueError,'changed on disk'):
            lib.import_profile(self.source,replace_profile_id=ident,
                               expected_revision=oldrev)
        with self.assertRaisesRegex(ValueError,'same name'):
            lib.import_profile(self.source,name='Another Profile',
                               replace_profile_id=ident,expected_revision=oldrev)
        self.assertEqual(len(lib.get_profile(ident)['filaments']),5)

    def test_saved_profile_can_add_then_remove_without_editing_library(self):
        records=[lib.normalize({**r, 'id':lib.stable_id('personal',i),
                                'source':'personal', 'series':(
                                'PLA Translucent' if i>=2 else 'PLA Basic')},personal=True)
                 for i,r in enumerate(SAMPLE['filaments'])]
        rev=lib.save_personal(records,expected_revision=None)
        ident=lib.save_profile('Five colors',records[:5])
        profile_rev=lib.saved_profile_revision(ident)
        lib.update_saved_profile(ident,[*records[:5],records[5]],
                                expected_revision=profile_rev)
        self.assertEqual(len(lib.get_profile(ident)['filaments']),6)
        nextrev=lib.saved_profile_revision(ident)
        lib.update_saved_profile(ident,records[:4],expected_revision=nextrev)
        self.assertEqual(len(lib.get_profile(ident)['filaments']),4)
        self.assertEqual(len(lib.read_personal()[0]),6)
        self.assertEqual(lib.file_revision(lib.personal_file()),rev)

    def test_legacy_example_standard_series_still_imports(self):
        data={'filaments':[{'name':'Natural White','brand':'Example Brand','series':'PLA Basic','color':'#F4F1EA'},
                           {'name':'Deep Black','brand':'Example Brand','series':'PLA Basic','color':'#101214'},
                           {'name':'Ocean Blue','brand':'Example Brand','series':'PLA Basic','color':'#2479A7'}]}
        self.source.write_text(json.dumps(data),encoding='utf-8')
        ident=lib.import_profile(self.source)
        self.assertEqual(len(lib.get_profile(ident)['filaments']),3)
        self.assertFalse(any('product_series' in e for e in lib.get_profile(ident)['filaments']))


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialog
    from desktop.qt_app.filament_library_dialog import FilamentLibraryDialog
    from desktop.qt_app.filament_profile_manager import FilamentProfileManager, ProfileFilamentPicker
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 unavailable')
class QtProfileAndThreadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_picker_uses_library_records_and_excludes_already_present(self):
        records=lib.generic_filaments()
        picker=ProfileFilamentPicker(records,[records[0]])
        self.assertEqual(len(picker.records),len(records)-1)
        picker.list.item(0).setSelected(True)
        picker._accept()
        self.assertEqual(picker.result(),QDialog.DialogCode.Accepted.value)
        self.assertEqual(len(picker.selected_records),1)
        self.assertNotEqual(picker.selected_records[0]['id'],records[0]['id'])
        picker.close()

    def test_profile_manager_add_from_library_opens_picker(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(lib,'settings_path',return_value=Path(folder)/'settings.json'):
                records=lib.generic_filaments()
                lib.save_profile('Test Profile',records[:3])
                manager=FilamentProfileManager(library_records=records)
                self.assertTrue(manager.add.isEnabled())
                self.assertEqual(manager.filaments.count(),3)
                manager.close()

    def test_close_library_waits_for_catalog_worker(self):
        import time
        from desktop.qt_app import filament_library_dialog as ui
        with tempfile.TemporaryDirectory() as folder:
            with (patch.object(lib,'settings_path',return_value=Path(folder)/'settings.json'),
                  patch.object(ui,'bambu_catalog_filaments',side_effect=lambda: (time.sleep(.1),[])[1])):
                dialog=FilamentLibraryDialog()
                dialog.close()  # Previously left a live parented QThread.
                self.assertFalse(dialog.worker.isRunning())


if __name__=='__main__':unittest.main()
