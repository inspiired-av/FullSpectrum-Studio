"""Uniform, non-destructive intended dimensions for unitless OBJ models."""
from __future__ import annotations

import ast
import importlib.util
import math
import os
from pathlib import Path
import tempfile
import unittest

from desktop.qt_app.model_intended_dimensions import (
    scaled_dimensions, source_dimensions, uniform_scale, write_scaled_obj,
)


class IntendedDimensionsGeometryTests(unittest.TestCase):
    BOUNDS = (-1, 0, -2, 1, 5, 2)

    def test_scale_one_axis_and_keep_aspect_ratio(self):
        f = uniform_scale(self.BOUNDS, 'Z', 160)
        self.assertEqual(f, 40)
        self.assertEqual(scaled_dimensions(self.BOUNDS, f), (80, 200, 160))
        self.assertEqual(source_dimensions(self.BOUNDS), (2, 5, 4))

    def test_other_axes(self):
        self.assertAlmostEqual(uniform_scale(self.BOUNDS, 'X', 60), 30)
        self.assertAlmostEqual(uniform_scale(self.BOUNDS, 'Y', 100), 20)

    def test_invalid_dimensions_never_clamp_or_guess(self):
        for value in (0, -1, math.inf, math.nan, 1e7):
            with self.subTest(value=value), self.assertRaises(ValueError):
                uniform_scale(self.BOUNDS, 'Z', value)
        with self.assertRaises(ValueError):
            uniform_scale((0, 0, 0, 10, 10, 0), 'Z', 100)
        with self.assertRaises(ValueError):
            uniform_scale(self.BOUNDS, 'W', 100)

    def test_obj_keeps_faces_normals_uvs_and_vertex_rgb(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / 'source' / 'frog.obj'
            original.parent.mkdir()
            raw = ('mtllib frog.mtl\n'
                   'v 1 2 3 0.4 0.5 0.6\n'
                   'v -1 0 0\n'
                   'v 0 2 0\n'
                   'vt 0.2 0.3\n'
                   'vn 0 0 1\n'
                   'usemtl Green\n'
                   'f 1/1/1 2/1/1 3/1/1\n')
            original.write_text(raw, encoding='utf-8')
            (original.parent/'frog.mtl').write_text('newmtl Green\nKd 0.3 0.8 0.5\n')
            out = root / 'derived' / 'frog.obj'
            write_scaled_obj(original, out, 25)
            self.assertEqual(original.read_text(encoding='utf-8'), raw)
            data = out.read_text(encoding='utf-8')
            self.assertIn('v 25 50 75 0.4 0.5 0.6', data)
            self.assertIn('v -25 0 0', data)
            for line in ('vt 0.2 0.3', 'vn 0 0 1', 'usemtl Green',
                         'f 1/1/1 2/1/1 3/1/1'):
                self.assertIn(line, data)
            self.assertEqual((out.parent/'frog.mtl').read_text(),
                             (original.parent/'frog.mtl').read_text())
            # The engine and preview scanner see the same RGB and triangle count.
            from desktop.qt_app.mesh_loader import load_obj
            a, b = load_obj(original), load_obj(out)
            self.assertEqual(a.palette_counts, b.palette_counts)
            self.assertEqual(a.source_triangles, b.source_triangles)
            for before, after in zip(a.vertices, b.vertices):
                for i in range(3):
                    self.assertAlmostEqual(after[i], before[i]*25, places=7)

    def test_mtl_texture_reference_copied_when_local(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'original'
            folder.mkdir()
            (folder/'paint.obj').write_text('mtllib paint.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            (folder/'paint.mtl').write_text('newmtl x\nmap_Kd textures/diffuse.png\n')
            (folder/'textures').mkdir()
            (folder/'textures/diffuse.png').write_bytes(b'mock texture')
            out = Path(temp)/'scaled'/'paint.obj'
            write_scaled_obj(folder/'paint.obj', out, 10)
            self.assertEqual((out.parent/'textures/diffuse.png').read_bytes(),b'mock texture')

    def test_cancellation_never_leaves_usable_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'input.obj'
            source.write_text('v 1 2 3\n')
            target = Path(temp)/'out.obj'
            with self.assertRaises(InterruptedError):
                write_scaled_obj(source,target,10,cancelled=lambda: True)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.obj.partial').exists())

    def test_does_not_overwrite_existing_model(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.obj'
            path.write_text('v 1 2 3\n')
            with self.assertRaises(ValueError):
                write_scaled_obj(path,path,2)
            out=Path(temp)/'other.obj'
            out.write_text('original')
            with self.assertRaises(FileExistsError):
                write_scaled_obj(path,out,2)
            self.assertEqual(out.read_text(), 'original')


class ScaleIntegrationContracts(unittest.TestCase):
    def test_one_effective_source_for_preview_forecast_export(self):
        source=(Path(__file__).resolve().parents[1]/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(source)
        self.assertIn('geometry_path = self._active_geometry_path()',source)
        self.assertIn('task = ModelLoadWorker(geometry_path, self',source)
        self.assertIn('path = self._active_geometry_path()\n',source)
        self.assertIn('            self._active_geometry_path(), self.state.reference_path,',source)
        self.assertIn('self._invalidate_forecast(clear_inspection=True)',source)
        self.assertIn('self._scale_workspaces.clear()',source)
        self.assertIn('if self._scale_task is not None:',source)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class IntendedDimensionsDialogQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_shows_uniform_dimensions_and_preserves_scale_when_axis_changes(self):
        from desktop.qt_app.model_dimensions_dialog import IntendedDimensionsDialog
        dialog = IntendedDimensionsDialog((0, 0, 0, 1, 2, 3), current_factor=10)
        self.assertEqual(dialog.axis.currentData(), 'Z')
        self.assertAlmostEqual(dialog.target.value(), 30)
        self.assertAlmostEqual(dialog.scale_factor, 10)
        dialog.axis.setCurrentIndex(0)
        self.assertAlmostEqual(dialog.target.value(), 10)
        self.assertAlmostEqual(dialog.scale_factor, 10)
        dialog.target.setValue(200)
        self.assertAlmostEqual(dialog.scale_factor, 200)
        dialog.reset.click()
        self.assertTrue(dialog.reset_requested)
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        dialog.close()


if __name__=='__main__':
    unittest.main()
