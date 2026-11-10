"""Personal filament storage tests + optional real Qt UI and engine adapter."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop.qt_app.personal_filament_library import (
    FAMILIES, filament_key, load_personal_library, normalize_filament,
    ready_for_planning, save_personal_library,
)


CYAN = {'name':'Panchroma Cyan', 'brand':'Polymaker',
        'series':'PLA Basic', 'color':'#08abfb'}
MAGENTA = {'name':'Panchroma Magenta', 'brand':'Polymaker',
           'series':'PLA Basic', 'color':'#D93B90'}


class PersonalFilamentStorageTests(unittest.TestCase):
    def test_start_empty(self):
        with TemporaryDirectory() as folder:
            self.assertEqual(load_personal_library(Path(folder)/'mine.json'),[])
            self.assertFalse(ready_for_planning([]))

    def test_two_colors_roundtrip_engine_compatible_schema(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/'mine.json'
            save_personal_library([CYAN, MAGENTA],file)
            data=load_personal_library(file)
            self.assertTrue(ready_for_planning(data))
            self.assertEqual(data[0]['color'],'#08ABFB')
            self.assertEqual(data[1]['series'],'PLA Basic')
            self.assertEqual(sorted(json.loads(file.read_text())['filaments'][0]),
                             ['brand','color','name','series'])

    def test_one_color_can_be_saved_as_draft_without_being_plannable(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/'mine.json'
            save_personal_library([CYAN],file)
            self.assertFalse(ready_for_planning(load_personal_library(file)))
            save_personal_library([CYAN,MAGENTA],file)
            self.assertTrue(ready_for_planning(load_personal_library(file)))

    def test_duplicate_identity_rejected_even_with_new_brand(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/'mine.json'
            save_personal_library([CYAN],file)
            previous=file.read_bytes()
            with self.assertRaisesRegex(ValueError,'one filament per'):
                save_personal_library([CYAN,{**CYAN,'brand':'Other'}],file)
            self.assertEqual(file.read_bytes(),previous)

    def test_same_color_other_series_valid_entry_but_not_distinct_color(self):
        item={**CYAN,'series':'PLA Matte'}
        self.assertNotEqual(filament_key(item),filament_key(CYAN))
        self.assertFalse(ready_for_planning([CYAN,item]))

    def test_rejects_invalid_hex_and_control_characters(self):
        for item in ({**CYAN,'color':'#ffffff00'},
                     {**CYAN,'color':'#GGGGGG'},
                     {**CYAN,'name':'Control\nCharacter'}):
            with self.subTest(item=item),self.assertRaises(ValueError):
                normalize_filament(item)

    def test_rejects_unknown_profiles_not_supported_by_engine(self):
        self.assertIn('PLA Translucent',FAMILIES)
        with self.assertRaisesRegex(ValueError,'supported PLA'):
            normalize_filament({**CYAN,'series':'PETG HF'})

    def test_malformed_existing_file_never_overwritten(self):
        with TemporaryDirectory() as folder:
            file=Path(folder)/'mine.json';file.write_text('{bad json',encoding='utf-8')
            existing=file.read_bytes()
            with self.assertRaisesRegex(ValueError,'malformed'):
                save_personal_library([CYAN,MAGENTA],file)
            self.assertEqual(file.read_bytes(),existing)

    def test_custom_file_does_not_touch_other_sources(self):
        with TemporaryDirectory() as folder:
            external=Path(folder)/'external.json';external.write_text('External data',encoding='utf-8')
            mine=Path(folder)/'mine.json'
            save_personal_library([CYAN,MAGENTA],mine)
            self.assertEqual(external.read_text(),'External data')

    def test_engine_custom_palette_reads_saved_data(self):
        import fullspectrum_engine as engine
        with TemporaryDirectory() as folder:
            file=Path(folder)/'mine.json'
            save_personal_library([CYAN,MAGENTA],file)
            palette=engine.custom_palette(file)
            self.assertEqual({item['color'] for item in palette},{'#08ABFB','#D93B90'})
            options=[engine.anchor_option_payload(entry) for entry in palette]
            self.assertEqual({item['key'] for item in options},
                             {'PLA Basic|#08ABFB','PLA Basic|#D93B90'})


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.personal_filament_dialog import PersonalFilamentsDialog, FilamentEntryDialog
except ImportError:
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 not installed')
class PersonalFilamentsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_dialog_lists_personal_filaments(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'my.json'
            save_personal_library([CYAN,MAGENTA],path)
            dlg=PersonalFilamentsDialog(path=path)
            self.assertEqual(dlg.table.rowCount(),2)
            self.assertEqual(dlg.table.item(0,0).text(),'#08ABFB')
            self.assertTrue(dlg.ready)
            dlg.close()

    def test_entry_validates_material_name(self):
        dlg=FilamentEntryDialog(CYAN)
        self.assertEqual(dlg.color.text(),'#08abfb')
        self.assertEqual(dlg.series.currentText(),'PLA Basic')
        dlg.close()

    def test_filaments_page_exposes_add_filament_action(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        with TemporaryDirectory() as folder:
            prefs=PlanPreferences(Path(folder)/'settings.json')
            page=FilamentsTab(prefs,settings_path=prefs.path)
            self.assertEqual(page.library_button.objectName(),'manageFilamentLibrary')
            self.assertTrue(page.library_button.isEnabled())
            page.close()


if __name__=='__main__':
    unittest.main()
