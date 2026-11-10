"""Migrated v5 regression coverage: profiles now share the single Library table."""
from __future__ import annotations
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from desktop.qt_app import filament_library_store as store


class LibrarySourceContracts(unittest.TestCase):
    def test_one_library_table_and_persistent_profiles_navigation(self):
        root = Path(__file__).resolve().parents[1]
        view = (root/'desktop/qt_app/filament_library_dialog.py').read_text(encoding='utf-8-sig')
        ast.parse(view)
        self.assertIn("QPushButton('All Filaments', sidebar)", view)
        self.assertIn('libraryProfileSidebar', view)
        self.assertIn('unifiedFilamentTable', view)
        self.assertNotIn('self.tabs.addTab(', view)
        self.assertNotIn('self.profile_tab =', view)
        self.assertIn('expected_revision=self._profile_revision', view)
        self.assertIn('profile_choices()', view)
        self.assertIn('_confirm_leave_profile()', view)

    def test_saved_profile_revisions_protect_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(store, 'settings_path', return_value=Path(folder)/'settings.json'):
                generic=store.generic_filaments()
                ident=store.save_profile('Portable test', generic[:3])
                before=store.saved_profile_revision(ident)
                now=store.update_saved_profile(ident, generic[:4],expected_revision=before)
                self.assertNotEqual(before, now)
                with self.assertRaisesRegex(ValueError,'changed on disk'):
                    store.update_saved_profile(ident,generic[:3],expected_revision=before)
                self.assertEqual(len(store.get_profile(ident)['filaments']),4)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QTableView
    from desktop.qt_app.filament_library_dialog import FilamentLibraryDialog
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 unavailable')
class LibraryQtMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.pref=patch.object(store,'settings_path',return_value=Path(self.dir.name)/'settings.json')
        self.pref.start();self.addCleanup(self.pref.stop)
        from desktop.qt_app import filament_library_dialog as ui
        self.catalog=patch.object(ui,'bambu_catalog_filaments',return_value=[])
        self.catalog.start();self.addCleanup(self.catalog.stop)

    def test_no_duplicate_profile_color_list(self):
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        self.assertEqual(len(dialog.findChildren(QTableView,'unifiedFilamentTable')),1)
        self.assertEqual(dialog.all_filaments_button.text(),'All Filaments')
        self.assertTrue(dialog.all_filaments_button.isChecked())
        self.assertFalse(hasattr(dialog,'profile_tab'))

    def test_imported_profile_colors_are_visible_and_checked(self):
        basic=store.generic_filaments()[:2]
        imported=store.normalize({**store.generic_filaments()[2],
                'id':store.stable_id('imported','external',3),'name':'Imported Cyan',
                'source':'imported'})
        identity=store.save_profile('Imported test',[*basic, imported])
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        target=next(dialog.profiles.item(i) for i in range(dialog.profiles.count())
                    if dialog.profiles.item(i).data(Qt.ItemDataRole.UserRole)==identity)
        dialog.profiles.setCurrentItem(target)
        self.assertEqual(len(dialog.model.selected_ids),3)
        self.assertTrue(any(r['id']==imported['id'] for r in dialog.model.records))
        self.assertEqual(dialog.model.records[0]['id'] in dialog.model.selected_ids,True)
        self.assertFalse(dialog.has_unsaved_changes)

    def test_builtin_read_only_can_be_copied(self):
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        built=next(dialog.profiles.item(i) for i in range(dialog.profiles.count())
                   if str(dialog.profiles.item(i).data(Qt.ItemDataRole.UserRole)).startswith('builtin:'))
        dialog.profiles.setCurrentItem(built)
        self.assertFalse(dialog.model.membership_editable)
        self.assertFalse(dialog.save_profile_button.isEnabled())
        self.assertTrue(dialog.duplicate_profile_button.isEnabled())


if __name__=='__main__': unittest.main()
