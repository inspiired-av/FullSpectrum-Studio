"""6A2-B follow-up: clip union, defaults, safe local asset detection and controls."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import tempfile
import struct
import json
import unittest
from types import SimpleNamespace

from desktop.qt_app.plate_mesh import combined_scene_bounds, plate_offset, scene_clip_planes
from desktop.qt_app.plate_workspace import (workspace_path, read_workspace,
                                             write_workspace, find_default_plate)
from desktop.qt_app.plate_catalog import _profile_root, discover_installed_plates

ROOT = Path(__file__).resolve().parents[1]


class PlateStabilityTests(unittest.TestCase):
    def test_plate_and_model_union_is_physical_and_unscaled(self):
        model = (0,0,0,10,10,12)
        bed = (0,0,-2,300,320,1)
        self.assertEqual(plate_offset(model,bed),(-145,-155,-1.5))
        self.assertEqual(combined_scene_bounds(model,bed),(-145,-155,-3.5,155,165,12))

    def test_camera_clips_scene_even_when_model_is_small(self):
        model = (0,0,0,10,10,12)
        bed = (0,0,-2,300,320,1)
        near,far = scene_clip_planes((5,-30,30), model, bed, (0.05,70))
        self.assertGreater(far,200)
        self.assertLessEqual(near,0.05)
        self.assertGreater(far,near)
        self.assertEqual(scene_clip_planes((5,-30,30),model,None,(0.05,70)),(0.05,70))

    def test_explicit_orca_profile_folder_is_correctly_labeled(self):
        with tempfile.TemporaryDirectory() as root:
            profiles = Path(root) / 'OrcaSlicer' / 'resources' / 'profiles'
            machine = profiles / 'Creality' / 'machine'
            machine.mkdir(parents=True)
            (machine/'K1.json').write_text(json.dumps({'type':'machine_model',
                'name':'Creality K1', 'bed_model':'bed.stl'}), encoding='utf-8')
            mesh = profiles/'Creality'/'bed.stl'
            mesh.write_bytes(b'plate'+bytes(75)+struct.pack('<I',1)
                +struct.pack('<12fH',*([0.,0.,1.]+[0.,0.,0.]+[100.,0.,0.]+[0.,100.,0.]),0))
            result = discover_installed_plates(resource_roots=[profiles],
                environ={}, registry_candidates=[], path_lookup=lambda _:None)
            self.assertEqual(len(result.plates),1)
            self.assertEqual(result.plates[0].source,'OrcaSlicer')
            self.assertEqual(result.plates[0].printer,'Creality K1')

    def test_settings_separate_from_export_preferences(self):
        with tempfile.TemporaryDirectory() as root:
            path = workspace_path(Path(root)/'plan.json')
            self.assertEqual(path.name,'plate_workspace.json')
            state = {'default':{'printer':'H2C','vendor':'BBL','source':'Bambu Studio'},
                     'visible':False,'slicer_executables':['C:/Orca/OrcaSlicer.exe'],
                     'resource_roots': []}
            write_workspace(path,state)
            self.assertEqual(read_workspace(path),state)
            self.assertFalse((Path(root)/'plan.json').exists())

    def test_stale_settings_do_not_crash(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'broken.json'
            path.write_text('{broken',encoding='utf-8')
            self.assertEqual(read_workspace(path),{})

    def test_default_source_falls_back_only_to_same_printer(self):
        p=SimpleNamespace(printer='H2C',vendor='BBL',source='OrcaSlicer')
        q=SimpleNamespace(printer='H2S',vendor='BBL',source='Bambu Studio')
        catalog=SimpleNamespace(plates=(p,q))
        self.assertIs(find_default_plate(catalog,{'printer':'H2C','vendor':'BBL','source':'Bambu Studio'}),p)
        self.assertIsNone(find_default_plate(catalog,{'printer':'H3C','vendor':'BBL','source':'Bambu Studio'}))

    def test_profiles_discovered_from_bin_sibling(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            profiles=root/'resources'/'profiles'
            (profiles/'BBL'/'machine').mkdir(parents=True)
            exe=root/'bin'/'OrcaSlicer.exe'
            exe.parent.mkdir()
            exe.write_bytes(b'MZ')
            self.assertEqual(_profile_root(exe),profiles.resolve())

    def test_patches_have_expected_public_controls(self):
        main=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        gl=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        ast.parse(main);ast.parse(gl)
        self.assertIn("self.plate_button = QPushButton('Build Plate')",main)
        self.assertIn('self.plate_visibility_button',main)
        self.assertIn('def _toggle_plate_visibility(self):',main)
        self.assertIn('def _make_selected_plate_default(self):',main)
        self.assertIn('scene_clip_planes(',gl)
        self.assertIn('self._plate_loaded_mesh = mesh',main)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class PlateControlsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_split_button_has_menu_and_toggle_action(self):
        from desktop.qt_app.main_window import MainWindow
        from qt_test_cleanup import dispose_test_widget
        with tempfile.TemporaryDirectory() as root:
            window=MainWindow(settings_path=Path(root)/'prefs.json')
            try:
                button=window.plate_button
                self.assertEqual(button.text(),'Build Plate')
                self.assertIsNone(button.menu())
                self.assertIsNotNone(window.plate_visibility_button)
                self.assertTrue(hasattr(window,'_toggle_plate_visibility'))
            finally:
                dispose_test_widget(window)


if __name__ == '__main__':
    unittest.main()
