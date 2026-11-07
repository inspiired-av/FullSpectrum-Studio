"""Fast non-GPU regression coverage for the pre-6B UI/worker hotfix."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'desktop' / 'qt_app'
spec = importlib.util.spec_from_file_location('model_open_location', SOURCE / 'model_open_location.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ModelFolderTests(unittest.TestCase):
    def test_initial_directory_prefers_default_then_recent_then_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); (base / 'Documents').mkdir()
            (base / 'Recent').mkdir(); (base / 'Chosen').mkdir()
            prefs = {'default_directory': str(base / 'Chosen'), 'last_directory': str(base / 'Recent')}
            self.assertEqual(mod.initial_directory(prefs, base), str((base / 'Chosen').resolve()))
            (base / 'Chosen').rmdir()
            self.assertEqual(mod.initial_directory(prefs, base), str((base / 'Recent').resolve()))
            (base / 'Recent').rmdir()
            self.assertEqual(mod.initial_directory(prefs, base), str((base / 'Documents').resolve()))

    def test_save_roundtrip_and_cancellation_does_not_change_recent(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            prefs=mod.location_path(base / 'plate_workspace.json')
            self.assertEqual(prefs.name,'model_open_location.json')
            model=base/'test.3mf';model.write_bytes(b'example')
            current=mod.with_last_opened_model({}, model)
            self.assertEqual(current['last_directory'],str(base.resolve()))
            self.assertEqual(mod.with_last_opened_model(current, '')['last_directory'],str(base.resolve()))
            mod.write_location(prefs,current)
            self.assertEqual(mod.read_location(prefs),mod.normalize_location(current))
            self.assertFalse((base/'plate_workspace.json').exists())

    def test_invalid_saved_paths_are_safe_and_default_clears_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            path=base/'locations.json'
            path.write_text('{broken',encoding='utf-8')
            self.assertEqual(mod.read_location(path),mod.normalize_location({}))
            data=mod.with_default_folder({'last_directory':str(base)},base)
            data['default_directory']=''
            self.assertEqual(data['last_directory'],str(base))
            self.assertEqual(mod.normalize_location({'last_directory':'\0bad'})['last_directory'],'')


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main=(SOURCE/'main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(cls.main)

    def test_grid_settings_attached_to_grid_button_not_prediction_overflow(self):
        self.assertIn("self.preview_grid_menu = QMenu('Grid and Axes', self)",self.main)
        self.assertIn('self.preview_grid_menu_button.setMenu(self.preview_grid_menu)',self.main)
        self.assertIn('ToolButtonPopupMode.InstantPopup',self.main)
        self.assertIn('self.preview_grid_button,\n            self.preview_grid_menu_button',self.main)
        self.assertNotIn('ToolButtonPopupMode.MenuButtonPopup',self.main)
        self.assertNotIn("self.preview_options_menu.addMenu('Grid and Axes')",self.main)

    def test_shutdown_guard_checks_deleted_qt_children(self):
        self.assertIn('if not self._qt_widgets_alive(self.plate_button):',self.main)
        self.assertIn('if getattr(self, \'_qt_disposing\', False):',self.main)

    def test_folder_dialog_and_independent_preferences(self):
        self.assertIn('self._model_location = read_model_location(self._model_location_path)',self.main)
        self.assertIn('initial_model_directory(self._model_location)',self.main)
        self.assertIn('with_last_opened_model(self._model_location, path)',self.main)
        self.assertIn('Set Default Model Folder…',self.main)
        self.assertIn('Use Last Opened Model Folder',self.main)

    def test_palette_combo_is_compact_without_engine_limit_change(self):
        self.assertIn('self.palette_limit_custom',self.main)
        self.assertIn('QInputDialog.getInt(',self.main)
        self.assertNotIn('for i in range(2, 33)',self.main)
        settings=(ROOT/'desktop'/'settings_store.py').read_text(encoding='utf-8-sig')
        self.assertIn('range(2,33)',settings)

if __name__=='__main__':
    unittest.main()
