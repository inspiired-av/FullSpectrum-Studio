"""6A2-B: printer-independent plate geometry, scene isolation and Qt controls."""
from __future__ import annotations

from array import array
from pathlib import Path
import ast
import importlib.util
import os
import struct
import tempfile
import unittest

from desktop.qt_app.plate_mesh import load_plate_mesh, plate_offset

ROOT = Path(__file__).resolve().parents[1]


def binary_stl(path, triangles):
    with Path(path).open('wb') as out:
        out.write(b'build plate' + bytes(80-len('build plate')))
        out.write(struct.pack('<I', len(triangles)))
        for triangle in triangles:
            normal = (0., 0., 1.)
            out.write(struct.pack('<12fH', *(normal + sum((tuple(v) for v in triangle), ())), 0))


class PlateGeometryTests(unittest.TestCase):
    def test_binary_plate_reads_faces_coordinates_and_uvs(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bed.stl'
            binary_stl(path, [((0, 0, 0), (200, 0, 0), (0, 250, 0))])
            mesh = load_plate_mesh(path)
            self.assertEqual(mesh.faces, 1)
            self.assertEqual(mesh.bounds, (0, 0, 0, 200, 250, 0))
            self.assertEqual(len(mesh.vertices), 24)
            self.assertEqual(list(mesh.vertices[6:8]), [0., 1.])
            self.assertAlmostEqual(mesh.vertices[8+6], 1.)

    def test_ascii_stl_supported(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bed.stl'
            path.write_text('solid plate\nfacet normal 0 0 1\nouter loop\n'
                            'vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n'
                            'endloop\nendfacet\nendsolid\n', encoding='utf-8')
            mesh = load_plate_mesh(path)
            self.assertEqual(mesh.faces, 1)
            self.assertEqual(mesh.bounds[3:5], (1., 1.))

    def test_invalid_and_nonfinite_stl_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bed.stl'
            path.write_bytes(b'malformed STL')
            with self.assertRaises(ValueError):
                load_plate_mesh(path)
            binary_stl(path, [((0, 0, 0), (float('nan'), 1, 0), (1, 0, 0))])
            with self.assertRaisesRegex(ValueError, 'Nonfinite'):
                load_plate_mesh(path)

    def test_no_model_transform_or_preview_scaling(self):
        self.assertEqual(plate_offset((10, 20, 2, 20, 30, 40),
                                      (0, 0, -2, 100, 100, 1)),
                         (-35., -25., .5))

    def test_plate_stays_separate_from_model_pipeline(self):
        gl = (ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        renderer = (ROOT/'desktop/qt_app/plate_gl.py').read_text(encoding='utf-8')
        main = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        for filename in ('plate_ui.py','plate_gl.py','plate_mesh.py'):
            ast.parse((ROOT/'desktop/qt_app'/filename).read_text(encoding='utf-8'))
        self.assertIn('PlateGpuRenderer()', gl)
        self.assertIn('self._plate_renderer.draw(', gl)
        self.assertIn('self._plate_renderer.release(', gl)
        self.assertIn('def _choose_plate(self):', main)
        self.assertNotIn('self._build_menus()\n        QTimer.singleShot(0, self._refresh_plate_catalog)', main)
        self.assertIn('def _plate_loaded(', main)
        self.assertNotIn('fullspectrum_engine', renderer)
        self.assertNotIn('make_export_request', renderer)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class PlateQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_picker_filters_vendor_and_printer(self):
        from desktop.qt_app.plate_catalog import PlateAsset
        from desktop.qt_app.plate_ui import PlatePickerDialog
        from qt_test_cleanup import dispose_test_widget
        a = PlateAsset('H2C','BBL','Bambu Studio',Path('a.stl'),None,
                       Path('a.json'),Path('.'))
        b = PlateAsset('K1 Max','Creality','OrcaSlicer',Path('b.stl'),None,
                       Path('b.json'),Path('.'))
        dialog = PlatePickerDialog((a,b))
        self.addCleanup(dispose_test_widget, dialog)
        self.assertEqual(dialog.list.count(),2)
        dialog.filter.setText('creality')
        self.assertEqual(dialog.list.count(),1)
        dialog.list.setCurrentRow(0)
        dialog._accept()
        self.assertIs(dialog.selected_asset,b)

if __name__ == '__main__':
    unittest.main()
