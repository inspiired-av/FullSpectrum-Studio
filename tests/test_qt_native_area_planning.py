"""Isolated optimizer-area tests plus optional real native split-paint fixture."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from desktop.qt_app.native_area_planning import (
    enabled, facet_slot_areas, native_surface_slot_weights, triangle_area_mm2)


class NativeAreaPlanningTests(unittest.TestCase):
    def setUp(self):
        self.mesh = SimpleNamespace(
            vertices=((0,0,0),(2,0,0),(0,2,0),
                      (0,0,1),(1,0,1),(0,1,1)),
            triangles=((0,1,2),(3,4,5)),
            face_colors=('#61C680','#FFFFFF'),
            corner_colors=(('#61C680',)*3,('#FFFFFF',)*3),
            color_status='2 source colors',
            source_triangles=2)

    def test_area_not_leaf_or_triangle_count(self):
        self.assertEqual(facet_slot_areas(self.mesh,('#61C680','#FFFFFF')),
                         Counter({1:2.0,2:0.5}))

    def test_respects_missing_part_slot(self):
        with self.assertRaisesRegex(ValueError,'does not match'):
            facet_slot_areas(self.mesh,('#61C680','#000000'))

    def test_requires_distinct_swatches(self):
        with self.assertRaisesRegex(ValueError,'distinct'):
            facet_slot_areas(self.mesh,('#61C680','#61C680'))

    def test_rejects_incomplete_paint(self):
        self.mesh.color_status='3 unsupported/unknown faces rendered neutral'
        with self.assertRaisesRegex(ValueError,'undecodable'):
            facet_slot_areas(self.mesh,('#61C680','#FFFFFF'))

    def test_rejects_corner_gradient(self):
        self.mesh.corner_colors=(('#61C680','#61C680','#FFFFFF'),('#FFFFFF',)*3)
        with self.assertRaisesRegex(ValueError,'corner'):
            facet_slot_areas(self.mesh,('#61C680','#FFFFFF'))

    def test_rejects_degenerate_facet(self):
        self.mesh.triangles=((0,0,2),(3,4,5))
        with self.assertRaisesRegex(ValueError,'indices'):
            facet_slot_areas(self.mesh,('#61C680','#FFFFFF'))

    def test_rejects_nan_area(self):
        with self.assertRaisesRegex(ValueError,'Invalid or degenerate'):
            triangle_area_mm2((0,0,0),(float('nan'),0,0),(0,1,0))

    def test_slot_reader_must_match_engine_palette(self):
        with self.assertRaisesRegex(ValueError,'differ'):
            native_surface_slot_weights('test.3mf',('#61C680','#FFFFFF'),
                loader=lambda path:self.mesh,
                validated_swatches=lambda path,count:('#FFFFFF','#61C680'))

    def test_expected_slot_reader_and_loader_path(self):
        calls=[]
        def validator(path,count):
            calls.append(('validate',path,count))
            return ('#61C680','#FFFFFF')
        def load(path):
            calls.append(('load',path))
            return self.mesh
        out=native_surface_slot_weights('frog.3mf',('#61C680','#FFFFFF'),
                                         loader=load,validated_swatches=validator)
        self.assertEqual(out,Counter({1:2.0,2:0.5}))
        self.assertEqual(calls,[('validate','frog.3mf',2),('load','frog.3mf')])

    def test_default_on_and_explicit_opt_out(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(enabled())
        for value in ('auto', '1', 'true', 'yes', 'on'):
            with self.subTest(value=value), patch.dict(os.environ,
                    {'FULLSPECTRUM_NATIVE_AREA_WEIGHTS':value}):
                self.assertTrue(enabled())
        for value in ('0', 'false', 'off', 'no', 'unsupported'):
            with self.subTest(value=value), patch.dict(os.environ,
                    {'FULLSPECTRUM_NATIVE_AREA_WEIGHTS':value}):
                self.assertFalse(enabled())

    @unittest.skipUnless(os.environ.get('FULLSPECTRUM_PAINT_FIXTURE'),
                         'Set FULLSPECTRUM_PAINT_FIXTURE for actual painted 3MF')
    def test_real_split_paint_area_matches_verified_source(self):
        import json
        from zipfile import ZipFile
        from desktop.qt_app.native_split_color_area import split_source_surface_areas
        path=Path(os.environ['FULLSPECTRUM_PAINT_FIXTURE'])
        self.assertTrue(path.is_file())
        with ZipFile(path) as z:
            colors=tuple(json.loads(z.read('Metadata/project_settings.config'))['filament_colour'])
        areas=native_surface_slot_weights(path,colors)
        by_color=split_source_surface_areas(path)
        self.assertAlmostEqual(sum(areas.values()),sum(by_color.values()),places=5)
        for slot,area in areas.items():
            self.assertAlmostEqual(area,by_color[colors[slot-1].upper()],places=5)
        self.assertGreater(sum(areas.values()),0)

if __name__=='__main__':
    unittest.main()
