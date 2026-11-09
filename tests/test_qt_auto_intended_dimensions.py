"""Automatic OBJ dimensions: streaming scan, remembered decisions, GUI contracts."""
from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.qt_app.model_size_preflight import (
    scan_obj_bounds, suspicious_obj_bounds, model_fingerprint,
    read_dimension_choice, save_dimension_choice, forget_dimension_choice,
)
from desktop.qt_app.model_intended_dimensions import uniform_scale, write_scaled_obj


class ObjPreflightTests(unittest.TestCase):
    def test_position_records_only_and_real_small_fixtures(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'head.OBJ'
            path.write_bytes(b'# sample\r\n'
                             b'v -0.14 1.32 -0.18\r\n'
                             b'vt 400 300\r\n'
                             b'vn 100 100 100\r\n'
                             b'v 0.15 1.80 0.15 0.9 0.7 0.5\r\n'
                             b'f 1/1/1 2/1/1 2/1/1\r\n')
            bounds = scan_obj_bounds(path)
            self.assertEqual(bounds, (-0.14, 1.32, -0.18, .15, 1.80, .15))
            self.assertTrue(suspicious_obj_bounds(bounds))
            self.assertFalse(suspicious_obj_bounds((0, 0, 0, 80, 130, 95)))
            self.assertTrue(suspicious_obj_bounds((0, 0, 0, 2000, 300, 300)))
            self.assertIsNone(scan_obj_bounds(path.with_suffix('.3mf')))

    def test_corrupt_or_incomplete_data_never_triggers_calibration(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t)/'broken.obj'
            path.write_text('v nan 2 3\nv 0 0 0\n')
            self.assertIsNone(scan_obj_bounds(path))
            self.assertFalse(suspicious_obj_bounds(None))
            self.assertFalse(suspicious_obj_bounds((0,0,0,0,0,0)))

    def test_cancellation_is_respected(self):
        with tempfile.TemporaryDirectory() as t:
            file = Path(t)/'big.obj'
            file.write_text('v 1 2 3\n'*512)
            with self.assertRaises(InterruptedError):
                scan_obj_bounds(file, cancelled=lambda: True)

    def test_single_full_preparation_after_preflight(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'colored.obj'
            source.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\n'
                              'vt 0.1 0.9\nusemtl blue\nf 1/1 2/1 3/1\n')
            bounds=scan_obj_bounds(source)
            self.assertTrue(suspicious_obj_bounds(bounds))
            scaled=Path(t)/'derived'/'colored.obj'
            factor=uniform_scale(bounds,'X',100)
            with patch('desktop.qt_app.model_intended_dimensions._stage_materials'):
                write_scaled_obj(source,scaled,factor)
            self.assertIn('v 100 0 0',scaled.read_text())
            self.assertIn('f 1/1 2/1 3/1',scaled.read_text())
            self.assertEqual(source.read_text().splitlines()[1],'v 1 0 0')


class ChoicePersistenceTests(unittest.TestCase):
    def test_skip_and_apply_saved_only_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            model=root/'hair.obj'; model.write_text('v 1 2 3\n')
            store=root/'settings'/'dimension_choices.json'
            self.assertIsNone(read_dimension_choice(store,model))
            save_dimension_choice(store,model,'skip')
            self.assertEqual(read_dimension_choice(store,model), {'action':'skip'})
            save_dimension_choice(store,model,'apply',factor=210.5)
            self.assertEqual(read_dimension_choice(store,model), {'action':'apply','factor':210.5})
            forget_dimension_choice(store,model)
            self.assertIsNone(read_dimension_choice(store,model))

    def test_path_size_and_mtime_invalidate_previous_choice(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            model=root/'frog.obj'; model.write_bytes(b'v 1 2 3\n')
            store=root/'settings.json'
            before=model_fingerprint(model)
            save_dimension_choice(store,model,'skip')
            model.write_bytes(b'v 1 2 3\nv 4 5 6\n')
            self.assertNotEqual(before,model_fingerprint(model))
            self.assertIsNone(read_dimension_choice(store,model))

    def test_invalid_and_corrupted_choices_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'m.obj'; source.write_text('v 0 0 0')
            store=root/'choices.json'
            for factor in (math.nan, 0, -5, math.inf):
                with self.subTest(factor=factor),self.assertRaises(ValueError):
                    save_dimension_choice(store,source,'apply',factor)
            store.write_text('not json')
            self.assertIsNone(read_dimension_choice(store,source))


class IntegrationContracts(unittest.TestCase):
    def test_preflight_precedes_only_full_preview_job(self):
        source=(Path(__file__).resolve().parents[1]/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        self.assertIn('self._start_model_size_preflight(path)',source)
        self.assertIn('def _model_size_preflight_done(',source)
        self.assertIn('self._begin_obj_scaling(dialog.scale_factor,',source)
        self.assertIn('self._load_preview(path)',source)
        self.assertIn('and not self._size_probe_active)',source)
        self.assertIn('self._active_geometry_path(), self.state.reference_path',source)
        self.assertIn('path = self._active_geometry_path()',source)
        self.assertIn('self._size_probe_threads',source)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 unavailable')
class DialogQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_two_buttons_remember_unchecked_and_deliberate_target(self):
        from desktop.qt_app.model_auto_dimensions_dialog import AutoIntendedDimensionsDialog
        from PySide6.QtWidgets import QDialogButtonBox
        d=AutoIntendedDimensionsDialog((0,0,0,.293,.479,.331))
        self.addCleanup(d.close)
        self.assertFalse(d.remember_choice)
        self.assertFalse(d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        self.assertEqual(d.buttons.button(QDialogButtonBox.StandardButton.Cancel).text(),'Skip')
        self.assertEqual(d.buttons.button(QDialogButtonBox.StandardButton.Ok).text(),'Apply Dimensions')
        d.target.setValue(100)
        self.assertTrue(d.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        d.remember.setChecked(True)
        self.assertTrue(d.remember_choice)

if __name__=='__main__':unittest.main()
