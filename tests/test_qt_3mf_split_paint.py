"""Regression coverage for read-only Bambu/Orca split-face paint preview.

Set FULLSPECTRUM_PAINT_FIXTURE to Minecraft_Frog_Multicolor.3mf for extra
sample-file validation. The synthetic 3MF test runs without external assets.
"""
from __future__ import annotations

from collections import Counter
from math import sqrt
import json
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from desktop.qt_app.preview_3mf_split_paint import (
    PaintDecodeError, decode_paint_regions)


ABC=((0.,0.,0.),(2.,0.,0.),(0.,2.,0.))


def _cross(tri):
    a,b,c=tri
    x,y,z=(b[i]-a[i] for i in range(3))
    p,q,r=(c[i]-a[i] for i in range(3))
    return (y*r-z*q,z*p-x*r,x*q-y*p)


def _oriented_area_ratio(original,regions):
    normal=_cross(original)
    denom=sum(k*k for k in normal)
    return sum(sum(x*y for x,y in zip(normal,_cross(region.points)))
               for region in regions)/denom


class PaintTreeTests(unittest.TestCase):
    def test_whole_face_codes_include_default_and_extended_slots(self):
        for code,wanted in [('0',0),('4',1),('8',2),('0C',3),('1C',4),('0FC',18)]:
            with self.subTest(code=code):
                regions=decode_paint_regions(ABC,code,24)
                self.assertEqual(len(regions),1)
                self.assertEqual(regions[0].slot,wanted)
                self.assertEqual(regions[0].points,ABC)

    def test_two_three_four_child_splits_tile_parent_with_ccw_orientation(self):
        # Root split code is last hex character (nibbles are read in reverse).
        cases=(('441',2),('4442',3),('44443',4))
        normal=_cross(ABC)
        for code,total in cases:
            with self.subTest(code=code):
                regions=decode_paint_regions(ABC,code,4)
                self.assertEqual(len(regions),total)
                self.assertAlmostEqual(_oriented_area_ratio(ABC,regions),1.,places=12)
                self.assertTrue(all(sum(x*y for x,y in zip(normal,_cross(r.points)))>0
                                    for r in regions))

    def test_special_side_rotation_conserves_area(self):
        for split in (1,2,3):
            for special in (0,1,2):
                code=split + (special << 2)
                encoded='4'*(split+1)+format(code,'X')
                with self.subTest(split=split,special=special):
                    regions=decode_paint_regions(ABC,encoded,4)
                    self.assertEqual(len(regions),split+1)
                    self.assertAlmostEqual(_oriented_area_ratio(ABC,regions),1.,places=12)

    def test_multiple_filament_colors_and_inherited_regions(self):
        # Two children: first in stream is slot 2, second is inherited default.
        regions=decode_paint_regions(ABC,'081',4)
        self.assertEqual({r.slot for r in regions},{0,2})

    def test_unknown_splits_and_malformed_stream_are_rejected(self):
        for value in ('3','G','0X','', '44F','6', '0C00', '0'*100001):
            with self.subTest(value=value[:12]):
                with self.assertRaises(PaintDecodeError):
                    decode_paint_regions(ABC,value,8)

    def test_out_of_range_slot_and_region_budget_are_rejected(self):
        with self.assertRaises(PaintDecodeError):
            decode_paint_regions(ABC,'1C',3)
        with self.assertRaises(PaintDecodeError):
            decode_paint_regions(ABC,'44443',4,max_regions=3)

    def test_nonfinite_geometry_is_rejected(self):
        with self.assertRaises(PaintDecodeError):
            decode_paint_regions(((0.,0.,0.),(float('nan'),0.,0.),(0.,1.,0.)),'4',4)

    @unittest.skipUnless(importlib.util.find_spec('desktop.qt_app.mesh_loader'),
                         'Integration test runs in FullSpectrum-Studio repository')
    def test_synthetic_3mf_preview_keeps_source_count_and_override_colors(self):
        from desktop.qt_app.mesh_loader import load_preview_mesh
        from desktop.qt_app.preview_quality import build_quality_preview
        from desktop.qt_app.preview_performance import (
            preview_performance_snapshot,format_preview_performance,
            preview_resource_estimate)
        model='''<?xml version="1.0" encoding="utf-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter">
<resources><object id="1" type="model"><mesh>
<vertices><vertex x="0" y="0" z="0"/><vertex x="2" y="0" z="0"/>
<vertex x="0" y="2" z="0"/><vertex x="0" y="0" z="2"/></vertices>
<triangles><triangle v1="0" v2="1" v3="2" paint_color="481"/>
<triangle v1="0" v2="2" v3="3"/></triangles></mesh></object></resources>
<build><item objectid="1"/></build></model>'''
        settings='<config><object id="1"><metadata key="extruder" value="3"/></object></config>'
        project={'filament_colour':['#F00000','#00F000','#0000F0']}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'simple.3mf'
            with ZipFile(path,'w') as archive:
                archive.writestr('3D/3dmodel.model',model)
                archive.writestr('Metadata/model_settings.config',settings)
                archive.writestr('Metadata/project_settings.config',json.dumps(project))
            mesh=load_preview_mesh(path)
        self.assertEqual(mesh.source_triangles,2)
        self.assertEqual(len(mesh.triangles),3)
        self.assertEqual(mesh.split_painted_faces,1)
        self.assertEqual(mesh.split_paint_regions,2)
        self.assertEqual(Counter(mesh.face_colors),Counter({'#F00000':1,'#00F000':1,'#0000F0':1}))
        self.assertIn('split-painted source faces',mesh.color_status)
        estimate=preview_resource_estimate(mesh)
        self.assertEqual(estimate.source_triangles,2)
        self.assertEqual(estimate.triangles,3)
        snap=preview_performance_snapshot(mesh)
        display=format_preview_performance(snap)
        self.assertIn('Source triangles: 2',display)
        self.assertIn('Drawn triangles: 3',display)
        self.assertIn('Paint display regions: 2',display)
        lod=build_quality_preview(mesh,'performance')
        self.assertIs(lod.mesh,mesh)
        self.assertEqual(lod.effective,'full')

    @unittest.skipUnless(os.environ.get('FULLSPECTRUM_PAINT_FIXTURE'),
                         'Set FULLSPECTRUM_PAINT_FIXTURE to a real painted 3MF')
    def test_frog_split_facet_counts_and_area(self):
        path=Path(os.environ['FULLSPECTRUM_PAINT_FIXTURE'])
        if not path.is_file():self.fail('Fixture not found: '+str(path))
        split=[]
        with ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith('.model'):continue
                root=ET.fromstring(archive.read(name))
                vertices=[tuple(float(v.get(k)) for k in 'xyz') for v in root.iter()
                          if v.tag.rsplit('}',1)[-1]=='vertex']
                for facet in root.iter():
                    if facet.tag.rsplit('}',1)[-1]!='triangle':continue
                    code=facet.get('paint_color','')
                    if len(code)<=128:continue
                    tri=tuple(vertices[int(facet.get(k))] for k in ('v1','v2','v3'))
                    regions=decode_paint_regions(tri,code,8)
                    split.append((len(regions),_oriented_area_ratio(tri,regions)))
        self.assertEqual(sorted(n for n,_ in split),[1168,11443])
        for _,ratio in split:self.assertAlmostEqual(ratio,1.,places=9)
        if not importlib.util.find_spec('desktop.qt_app.mesh_loader'):
            return  # decoder geometry was validated above; loader needs repo
        from desktop.qt_app.mesh_loader import load_preview_mesh
        mesh=load_preview_mesh(path)
        self.assertEqual(mesh.source_triangles,424)
        self.assertEqual(len(mesh.triangles),13033)
        self.assertEqual(mesh.split_painted_faces,2)
        self.assertEqual(mesh.split_paint_regions,12611)


if __name__=='__main__':unittest.main()
