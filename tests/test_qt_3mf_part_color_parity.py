"""Synthetic source-color parity tests; no private or licensed model assets bundled."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from desktop.qt_app.preview_3mf_part_assignments import read_native_part_defaults


CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PROD='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
MAT='http://schemas.microsoft.com/3dmanufacturing/material/2015/02'


def package(path, *, bad_part_slot=False):
    main = f'''<?xml version="1.0"?>
<model xmlns="{CORE}" xmlns:p="{PROD}" unit="millimeter">
 <resources><object id="13" type="model"><components>
  <component objectid="1" p:path="/3D/Objects/part.model"/>
  <component objectid="2" p:path="/3D/Objects/part.model"/>
  <component objectid="3" p:path="/3D/Objects/part.model"/>
  <component objectid="4" p:path="/3D/Objects/part.model"/>
 </components></object></resources><build><item objectid="13"/></build>
</model>'''
    objects = [f'<object id="{i}" type="model"><mesh><vertices>'
               '<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>'
               '<vertex x="0" y="1" z="0"/></vertices><triangles>'
               + ('<triangle v1="0" v2="1" v3="2" paint_color="4"/>' if i==3 else
                  '<triangle v1="0" v2="1" v3="2" pid="5" p1="0"/>' if i==4 else
                  '<triangle v1="0" v2="1" v3="2"/>')
               + '</triangles></mesh></object>' for i in range(1,5)]
    parts = (f'<model xmlns="{CORE}" xmlns:m="{MAT}"><resources>'
             f'<m:basematerials id="5"><m:base name="Gold" displaycolor="#12ABCD"/></m:basematerials>'
             + ''.join(objects) + '</resources></model>')
    invalid = '999' if bad_part_slot else '2'
    settings = (f'<config><object id="13"><metadata key="extruder" value="1"/>'
                f'<part id="1"><metadata key="extruder" value="{invalid}"/></part>'
                '<part id="2"><metadata key="name" value="inherited"/></part>'
                '<part id="3"><metadata key="extruder" value="3"/></part>'
                '<part id="4"><metadata key="extruder" value="3"/></part>'
                '</object></config>')
    with ZipFile(path,'w') as archive:
        archive.writestr('3D/3dmodel.model',main)
        archive.writestr('3D/Objects/part.model',parts)
        archive.writestr('Metadata/project_settings.config',json.dumps({
            'filament_colour':['#FF0000','#00FF00','#0000FF']}))
        archive.writestr('Metadata/model_settings.config',settings)


class NativePartAssignmentTests(unittest.TestCase):
    def test_part_extruder_override_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.3mf';package(path)
            with ZipFile(path) as archive:
                mapping=read_native_part_defaults(archive,('#FF0000','#00FF00','#0000FF'))
            self.assertEqual(mapping[('13','1')],'#00FF00')
            self.assertNotIn(('13','2'),mapping)
            self.assertEqual(mapping[('13','3')],'#0000FF')

    def test_invalid_explicit_part_does_not_inherit_parent_color(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.3mf';package(path,bad_part_slot=True)
            with ZipFile(path) as archive:
                mapping=read_native_part_defaults(archive,('#FF0000','#00FF00','#0000FF'))
            self.assertIn(('13','1'),mapping)
            self.assertIsNone(mapping[('13','1')])

    def test_missing_metadata_is_noop(self):
        with io.BytesIO() as stream:
            with ZipFile(stream,'w') as archive:archive.writestr('3D/3dmodel.model','x')
            stream.seek(0)
            with ZipFile(stream) as archive:
                self.assertEqual(read_native_part_defaults(archive,('#FF0000',)),{})

    def test_duplicate_part_rejected(self):
        with io.BytesIO() as stream:
            with ZipFile(stream,'w') as archive:
                archive.writestr('Metadata/model_settings.config',
                    '<config><object id="1"><part id="2"><metadata key="extruder" value="1"/>'
                    '</part><part id="2"><metadata key="extruder" value="1"/></part></object></config>')
            stream.seek(0)
            with ZipFile(stream) as archive:
                with self.assertRaises(ValueError):
                    read_native_part_defaults(archive,('#FF0000',))


class PreviewLoaderIntegrationTests(unittest.TestCase):
    def test_part_override_paint_and_standard_properties_precedence(self):
        # This integration test uses the production loader after installation.
        try:
            from desktop.qt_app.mesh_loader import load_3mf
        except ModuleNotFoundError as exc:
            if exc.name == 'desktop.qt_app.mesh_loader':
                self.skipTest('Integration test requires the FullSpectrum repository')
            raise
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.3mf';package(path)
            mesh=load_3mf(path)
            self.assertEqual(len(mesh.triangles),4)
            self.assertEqual(mesh.face_colors,('#00FF00','#FF0000','#FF0000','#12ABCD'))
            self.assertEqual(dict(mesh.palette_counts),{
                '#00FF00':1,'#FF0000':2,'#12ABCD':1})

    def test_invalid_assigned_slot_uses_neutral_not_wrong_parent(self):
        try:
            from desktop.qt_app.mesh_loader import load_3mf
        except ModuleNotFoundError as exc:
            if exc.name == 'desktop.qt_app.mesh_loader':
                self.skipTest('Integration test requires the FullSpectrum repository')
            raise
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.3mf';package(path,bad_part_slot=True)
            mesh=load_3mf(path)
            self.assertEqual(mesh.face_colors[0],None)
            self.assertEqual(mesh.face_colors[1],'#FF0000')


if __name__=='__main__':unittest.main()
