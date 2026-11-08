"""Tests for the independent split-paint source-color verification fallback."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from desktop.qt_app.native_split_color_area import _area_mm2, split_source_surface_areas


def mesh(*, split=1, regions=2, colors=('#111111', '#222222'), status='2 source colors'):
    # Two half-area display triangles (0.5 mm2 each): one original source face.
    return SimpleNamespace(vertices=((0,0,0),(1,0,0),(0,1,0),(.5,0,0)),
        triangles=((0,3,2),(3,1,2)), source_triangles=1,
        face_colors=colors, color_status=status,
        split_painted_faces=split,split_paint_regions=regions)


class NativePaintCoverageTests(unittest.TestCase):
    def test_triangle_area_is_true_square_millimeters(self):
        self.assertAlmostEqual(_area_mm2((0,0,0),(2,0,0),(0,3,0)),3.)
        self.assertAlmostEqual(_area_mm2((1,2,3),(3,2,3),(1,5,3)),3.)

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_split_facets_are_surface_area_not_face_counts(self, load):
        load.return_value=mesh()
        result=split_source_surface_areas('fixture.3mf')
        self.assertEqual(set(result),{'#111111','#222222'})
        self.assertAlmostEqual(result['#111111'],.25)
        self.assertAlmostEqual(result['#222222'],.25)
        self.assertAlmostEqual(sum(result.values()),.5)

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_uniform_color_accumulates_from_subtriangles(self, load):
        load.return_value=mesh(colors=('#ABCDEF','#ABCDEF'))
        self.assertAlmostEqual(split_source_surface_areas('fixture.3mf')['#ABCDEF'],.5)

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_whole_face_only_must_not_use_split_path(self, load):
        load.return_value=mesh(split=0,regions=0)
        with self.assertRaisesRegex(ValueError,'No decoded'):
            split_source_surface_areas('fixture.3mf')

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_unresolved_color_fails_closed(self, load):
        load.return_value=mesh(status='2 source colors · 1 unsupported/unknown faces rendered neutral')
        with self.assertRaisesRegex(ValueError,'coverage is incomplete'):
            split_source_surface_areas('fixture.3mf')

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_missing_color_fails_closed(self, load):
        load.return_value=mesh(colors=('#000000',None))
        with self.assertRaisesRegex(ValueError,'Unassigned'):
            split_source_surface_areas('fixture.3mf')

    @patch('desktop.qt_app.mesh_loader.load_3mf')
    def test_invalid_geometry_fails_closed(self, load):
        load.return_value=SimpleNamespace(**{**vars(mesh()), 'vertices': ((0,0,0),)*4})
        with self.assertRaisesRegex(ValueError,'Degenerate'):
            split_source_surface_areas('fixture.3mf')

    @unittest.skipUnless(os.environ.get('FULLSPECTRUM_PAINT_FIXTURE'),
                         'Set FULLSPECTRUM_PAINT_FIXTURE to a valid split-painted 3MF')
    def test_real_frog_contains_all_eight_colors(self):
        path=Path(os.environ['FULLSPECTRUM_PAINT_FIXTURE'])
        result=split_source_surface_areas(path)
        self.assertEqual(len(result),8)
        self.assertGreater(result['#61C680'],result['#FFFFFF'])
        self.assertGreater(sum(result.values()),0)


class NativeScannerDispatchTests(unittest.TestCase):
    @unittest.skipUnless(__import__('importlib').util.find_spec('fullspectrum_engine'),
                         'Requires FullSpectrum repository engine')
    def test_long_split_paint_uses_verified_area_fallback_only(self):
        from tempfile import TemporaryDirectory
        from desktop.qt_app.filament_preferences import scan_source_colors
        with TemporaryDirectory() as d:
            path=Path(d)/'fixture.3mf';path.write_bytes(b'fixture')
            with patch('fullspectrum_engine.is_standard_colored_3mf',return_value=False), \
                 patch('desktop.qt_app.native_object_colors.scan_native_object_colors',
                       side_effect=ValueError('Invalid native face paint state')), \
                 patch('desktop.qt_app.native_split_color_area.split_source_surface_areas',
                       return_value={'#123456':5.5}):
                result=scan_source_colors(path)
        self.assertEqual(result.source_kind,'native_split_surface_area')
        self.assertEqual(result,{'#123456':5.5})

    @unittest.skipUnless(__import__('importlib').util.find_spec('fullspectrum_engine'),
                         'Requires FullSpectrum repository engine')
    def test_unrelated_native_scanner_failure_does_not_bypass_validation(self):
        from tempfile import TemporaryDirectory
        from desktop.qt_app.filament_preferences import scan_source_colors
        with TemporaryDirectory() as d:
            path=Path(d)/'fixture.3mf';path.write_bytes(b'fixture')
            with patch('fullspectrum_engine.is_standard_colored_3mf',return_value=False), \
                 patch('desktop.qt_app.native_object_colors.scan_native_object_colors',
                       side_effect=ValueError('Mixed-filament project slots are not exact')), \
                 patch('desktop.qt_app.native_split_color_area.split_source_surface_areas') as fallback:
                with self.assertRaisesRegex(ValueError,'Mixed-filament'):
                    scan_source_colors(path)
                fallback.assert_not_called()


if __name__=='__main__':unittest.main()
