"""One-table library with always-visible profile sidebar and safe membership edits."""
from __future__ import annotations
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from desktop.qt_app import filament_library_store as store
from desktop.qt_app.filament_library_membership import (
    merge_with_profile, sorted_for_profile, reconcile_membership,
    membership_signature, checked_visible_with_filters,
)


class MembershipPureTests(unittest.TestCase):
    def setUp(self):
        self.records=store.generic_filaments()

    def test_imported_record_only_appears_when_overlay_requested(self):
        imported={**self.records[0], 'id':'imported:outside', 'source':'imported'}
        displayed=merge_with_profile(self.records,[imported])
        self.assertEqual(len(displayed),len(self.records)+1)
        self.assertEqual(len(self.records),len(store.generic_filaments()))

    def test_checked_first_and_sorted(self):
        picked={self.records[-1]['id'],self.records[-2]['id']}
        result=sorted_for_profile(self.records,picked)
        self.assertEqual({x['id'] for x in result[:2]},picked)
        self.assertTrue(all(x['id'] not in picked for x in result[2:]))

    def test_reconcile_add_and_remove_preserves_embedded_snapshots(self):
        imported={**self.records[0], 'id':'imported:outside','name':'Out-of-catalog'}
        prior=[self.records[0],imported]
        selected={imported['id'],self.records[1]['id']}
        shown=merge_with_profile(self.records,[imported])
        result=reconcile_membership(prior,shown,selected)
        self.assertEqual([r['id'] for r in result],[imported['id'],self.records[1]['id']])
        self.assertEqual(membership_signature(result),frozenset(selected))
        self.assertTrue(checked_visible_with_filters(imported,selected,True))
        self.assertFalse(checked_visible_with_filters(imported,selected,False))

    def test_storage_rename_requires_revision_and_keeps_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store,'settings_path',return_value=Path(tmp)/'settings.json'):
                ident=store.save_profile('Old title',self.records[:3])
                initial=store.saved_profile_revision(ident)
                after=store.rename_saved_profile(ident,'New title',expected_revision=initial)
                self.assertEqual(store.get_profile(ident)['name'],'New title')
                self.assertEqual(len(store.get_profile(ident)['filaments']),3)
                self.assertNotEqual(initial,after)
                with self.assertRaisesRegex(ValueError,'changed on disk'):
                    store.rename_saved_profile(ident,'Stale name',expected_revision=initial)
                self.assertEqual(store.get_profile(ident)['name'],'New title')

    def test_python_sources_parse_and_no_duplicate_profile_editor(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('filament_library_dialog.py','filament_library_membership.py'):
            ast.parse((root/'desktop/qt_app'/name).read_text(encoding='utf-8-sig'))
        dialog=(root/'desktop/qt_app/filament_library_dialog.py').read_text(encoding='utf-8-sig')
        self.assertEqual(dialog.count('self.table = QTableView(self)'),1)
        self.assertNotIn('filament_library_profile_tab import',dialog)
        self.assertNotIn('ProfileFilamentPicker(',dialog)
        self.assertIn('self.profiles.currentItemChanged.connect(self._on_profile_selected)',dialog)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    from desktop.qt_app.filament_library_dialog import FilamentLibraryDialog
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 unavailable')
class SharedTableQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pref=patch.object(store,'settings_path',return_value=Path(self.temp.name)/'settings.json')
        self.pref.start();self.addCleanup(self.pref.stop)
        from desktop.qt_app import filament_library_dialog as ui
        self.patch_catalog=patch.object(ui,'bambu_catalog_filaments',return_value=[])
        self.patch_catalog.start();self.addCleanup(self.patch_catalog.stop)

    def _choose(self,dialog,identity):
        if identity == '__all__':
            dialog.all_filaments_button.click()
            return
        item=next(dialog.profiles.item(i) for i in range(dialog.profiles.count())
                  if dialog.profiles.item(i).data(Qt.ItemDataRole.UserRole)==identity)
        dialog.profiles.setCurrentItem(item)

    def test_all_is_default_and_checkboxes_are_not_editable(self):
        dialog=FilamentLibraryDialog(browse_only=True)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.all_filaments_button.isChecked())
        self.assertFalse(dialog.model.membership_editable)
        self.assertFalse(dialog.model.flags(dialog.model.index(0,0)) & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertTrue(dialog.add.isEnabled())
        self.assertFalse(dialog.save_profile_button.isVisible() if dialog.isVisible() else dialog.save_profile_button.isEnabled())

    def test_editing_profile_uses_same_table_saves_without_activating(self):
        entries=store.generic_filaments()
        identity=store.save_profile('Edited set',entries[:3])
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        self._choose(dialog,identity)
        self.assertTrue(dialog.model.membership_editable)
        self.assertEqual(len(dialog.model.selected_ids),3)
        next_record=next(r for r in dialog.model.records if r['id'] not in dialog.model.selected_ids)
        idx=dialog.model.index(dialog.model.records.index(next_record),0)
        self.assertTrue(dialog.model.setData(idx,Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole))
        self.app.processEvents()
        self.assertTrue(dialog.has_unsaved_changes)
        self.assertEqual(len(store.get_profile(identity)['filaments']),3)
        self.assertFalse(store.active_file().exists())
        self.assertTrue(dialog._save_profile())
        self.assertEqual(len(store.get_profile(identity)['filaments']),4)
        self.assertFalse(dialog.has_unsaved_changes)
        self.assertFalse(store.active_file().exists())
        self._choose(dialog,'__all__')
        self.assertFalse(dialog.model.membership_editable)

    def test_selected_stay_visible_despite_search(self):
        entries=store.generic_filaments()
        identity=store.save_profile('Filter set',entries[:3])
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        self._choose(dialog,identity)
        dialog.search.setText('no such color should match')
        self.assertEqual(dialog.proxy.rowCount(),3)

    def test_cancel_discards_nothing_when_switching_profile(self):
        entries=store.generic_filaments()
        identity=store.save_profile('Switch test',entries[:3])
        dialog=FilamentLibraryDialog()
        self.addCleanup(dialog.close)
        self._choose(dialog,identity)
        added=next(i for i,r in enumerate(dialog.model.records)
                   if r['id'] not in dialog.model.selected_ids)
        dialog.model.setData(dialog.model.index(added,0),Qt.CheckState.Checked,
                             Qt.ItemDataRole.CheckStateRole)
        self.app.processEvents()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
            self._choose(dialog,'__all__')
        self.assertEqual(dialog._profile_identity,identity)
        self.assertTrue(dialog.has_unsaved_changes)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
            self._choose(dialog,'__all__')
        self.assertIsNone(dialog._profile_identity)
        self.assertEqual(len(store.get_profile(identity)['filaments']),3)

    def test_shutdown_stops_catalog_worker(self):
        import time
        from desktop.qt_app import filament_library_dialog as ui
        with patch.object(ui,'bambu_catalog_filaments',side_effect=lambda: (time.sleep(.1),[])[1]):
            dialog=FilamentLibraryDialog()
            dialog.close()
            self.assertFalse(dialog.worker.isRunning())


if __name__=='__main__': unittest.main()
