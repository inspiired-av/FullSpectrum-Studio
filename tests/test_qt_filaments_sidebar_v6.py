"""Migrated v6 checks: no sidebar in Filaments tab; Library owns profile edits."""
from __future__ import annotations
import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from desktop.qt_app import filament_library_store as store


class LibrarySidebarContracts(unittest.TestCase):
    def test_library_sidebar_replaces_in_workspace_profile_editor(self):
        root=Path(__file__).resolve().parents[1]
        tab=(root/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8-sig')
        dlg=(root/'desktop/qt_app/filament_library_dialog.py').read_text(encoding='utf-8-sig')
        ast.parse(tab);ast.parse(dlg)
        self.assertNotIn('filamentsProfilesSplitter',tab)
        self.assertNotIn('toggleProfileSidebar',tab)
        self.assertNotIn('browse_only=True',tab)
        self.assertIn('quick_profile_combo',tab)
        self.assertIn('libraryProfileSidebar',dlg)
        self.assertIn("QPushButton('All Filaments', sidebar)",dlg)
        self.assertNotIn('self.tabs.addTab(',dlg)

    def test_existing_user_profiles_preserve_embedded_filament_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store,'settings_path',return_value=Path(tmp)/'settings.json'):
                entries=store.generic_filaments()
                revision=store.save_personal([],expected_revision=None)
                ident=store.save_profile('Existing palette',entries[:3])
                rev=store.saved_profile_revision(ident)
                store.update_saved_profile(ident,entries[:4],expected_revision=rev)
                self.assertEqual(len(store.get_profile(ident)['filaments']),4)
                self.assertEqual(store.file_revision(store.personal_file()),revision)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.filament_library_dialog import FilamentLibraryDialog
    from desktop.qt_app.plan_preferences import PlanPreferences
    from desktop.qt_app.filaments_tab import FilamentsTab
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 unavailable')
class LibrarySidebarQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ps=patch.object(store,'settings_path',return_value=Path(self.tmp.name)/'settings.json')
        ps.start();self.addCleanup(ps.stop)

    def test_workspace_has_profile_dropdown_but_no_second_editor(self):
        preferences=PlanPreferences(Path(self.tmp.name)/'settings.json')
        tab=FilamentsTab(preferences)
        self.addCleanup(tab.close)
        self.assertFalse(hasattr(tab,'profile_sidebar'))
        self.assertFalse(hasattr(tab,'profiles_toggle'))
        self.assertTrue(hasattr(tab,'quick_profile_combo'))
        self.assertIn('selection-background-color: #2b5361',tab.filaments.styleSheet())

    def test_library_has_all_filaments_even_from_workspace(self):
        from desktop.qt_app import filament_library_dialog as ui
        with patch.object(ui,'bambu_catalog_filaments',return_value=[]):
            dlg=FilamentLibraryDialog(browse_only=True)
            self.addCleanup(dlg.close)
            self.assertTrue(dlg.all_filaments_button.isChecked())
            self.assertTrue(dlg.profiles.isVisible() or not dlg.isVisible())
            dlg.close()
            self.assertFalse(dlg.worker.isRunning())


if __name__=='__main__':unittest.main()
