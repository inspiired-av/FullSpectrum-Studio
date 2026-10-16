"""Regression tests for the native template 3MF exporter (stdlib only)."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

from native_project_template import (
    CORE, PROD, REL, TemplateError, inspect_template, graft_native_project,
)


def fixture_template(path, *, empty=True, include_defaults=False, double_flush=False):
    metadata='<metadata name="Application">BambuStudio-02.08.04.57</metadata><metadata name="BambuStudio:3mfVersion">1</metadata>'
    root=f'<model xmlns="{CORE}" xmlns:p="{PROD}" requiredextensions="p">{metadata}<resources>'
    if not empty:
        root += '<object id="7" type="model"><mesh><vertices/><triangles/></mesh></object>'
    root += '</resources><build/></model>'
    data={
        'filament_colour':['#000000','#999999','#FF0000'],
        'filament_is_mixed':['0','0','1'],
        'filament_mixed_components':['','','1,2'],
        'filament_mixed_sublayer_ratios':['','','0.5000,0.5000'],
        'filament_settings_id':['Generic PLA']*3,
        'filament_ids':['A']*3,
        'filament_self_index':['1','1','2','2','3','3'],
        'filament_type':['PLA']*3,
        'filament_vendor':['Generic']*3,
        'filament_diameter':['1.75']*3,
        'flush_volumes_matrix':['0' if i==j else '120' for i in range(3) for j in range(3)],
        'printer_settings_id':'Bambu Lab H2C 0.4 nozzle',
        'printer_model':'Bambu Lab H2C',
        'print_settings_id':'0.08mm High Quality',
        'printer_variant':'0.4',
        'printable_area':['0x0','330x0','330x320','0x320'],
        'printable_height':'325',
    }
    if include_defaults:
        data['default_filament_colour'] = ['#101010','#202020','#303030']
    if double_flush:
        data['flush_volumes_matrix'] *= 2
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('3D/3dmodel.model',root)
        z.writestr('Metadata/project_settings.config',json.dumps(data))
        z.writestr('Metadata/model_settings.config','<config><plate/><assemble/></config>')
        z.writestr('Metadata/slice_info.config','<config><header/></config>')
        z.writestr('[Content_Types].xml',f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('_rels/.rels',f'<Relationships xmlns="{REL}"><Relationship Target="/3D/3dmodel.model"/></Relationships>')
    return data


def fixture_source(path, n=5):
    colors=['#000000','#999999','#FF0000','#AABBCC','#CCBBAA'][:n]
    settings={
        'filament_colour':colors,
        'default_filament_colour':['']*n,
        'filament_multi_colour':colors,
        'filament_is_mixed':['0','0']+['1']*(n-2),
        'filament_mixed_components':['','']+['1,2']*(n-2),
        'filament_mixed_sublayer_ratios':['','']+['0.5000,0.5000']*(n-2),
    }
    mesh=f'<model xmlns="{CORE}"><resources><object id="1" type="model"><mesh><vertices>' + (
         '<vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/>'
         '<vertex x="0" y="10" z="0"/>') + '</vertices><triangles>' + (
         '<triangle v1="0" v2="1" v3="2" paint_color="8"/>') + \
        '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>'
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('Metadata/project_settings.config',json.dumps(settings))
        z.writestr('3D/Objects/object_1.model',mesh)
    return settings


class NativeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.template=root/'blank.3mf'; self.source=root/'colored.3mf'; self.out=root/'native.3mf'
        self.t=fixture_template(self.template)
        self.p=fixture_source(self.source)

    def tearDown(self):self.tmp.cleanup()

    def test_rejects_nonempty_template(self):
        fixture_template(self.template,empty=False)
        with self.assertRaisesRegex(TemplateError,'not empty'):
            inspect_template(self.template)

    def test_template_metadata_inspection(self):
        t=inspect_template(self.template)
        self.assertEqual(t['printer'],'Bambu Lab H2C')
        self.assertEqual(t['nozzle'],'0.4')
        self.assertEqual(t['slicer'],'Bambu Studio')

    def test_native_main_and_relationships(self):
        graft_native_project(self.source,self.template,self.out,real_count=2)
        with ZipFile(self.out) as z:
            self.assertIn('3D/3dmodel.model',z.namelist())
            self.assertIn('3D/_rels/3dmodel.model.rels',z.namelist())
            root=ET.fromstring(z.read('3D/3dmodel.model'))
            children=root.findall(f'{"{"}{CORE}{"}"}resources/{"{"}{CORE}{"}"}object')
            self.assertEqual(len(children),1)
            comp=children[0].find(f'{"{"}{CORE}{"}"}components/{"{"}{CORE}{"}"}component')
            self.assertEqual(comp.get(f'{"{"}{PROD}{"}"}path'),'/3D/Objects/object_1.model')
            mesh=ET.fromstring(z.read('3D/Objects/object_1.model'))
            self.assertEqual(len(mesh.findall(f'.//{{{CORE}}}triangle')),1)
            self.assertEqual(len(mesh.findall(f'{"{"}{CORE}{"}"}build/{"{"}{CORE}{"}"}item')),0)

    def test_filament_mixture_and_template_process_are_preserved(self):
        graft_native_project(self.source,self.template,self.out,real_count=2)
        with ZipFile(self.out) as z: s=json.loads(z.read('Metadata/project_settings.config'))
        self.assertEqual(s['filament_is_mixed'], self.p['filament_is_mixed'])
        self.assertEqual(s['filament_mixed_components'], self.p['filament_mixed_components'])
        self.assertEqual(s['printer_settings_id'],self.t['printer_settings_id'])
        self.assertEqual(s['filament_diameter'], ['1.75']*5)
        self.assertEqual(len(s['filament_self_index']),10)
        self.assertEqual(len(s['flush_volumes_matrix']),25)
        self.assertFalse(any(float(s['flush_volumes_matrix'][i*5+j])==0 for i in range(5) for j in range(5) if i!=j))

    def test_preserves_imported_texture_resources(self):
        with ZipFile(self.source, 'a', ZIP_DEFLATED) as archive:
            archive.writestr('3D/Textures/source_texture.png', b'test-image-data')
        graft_native_project(self.source, self.template, self.out, real_count=2)
        with ZipFile(self.out) as archive:
            self.assertEqual(
                archive.read('3D/Textures/source_texture.png'), b'test-image-data'
            )

    def test_missing_template_default_filament_colour_uses_planned(self):
        # Older/custom native projects may omit this array entirely.
        graft_native_project(self.source, self.template, self.out, real_count=2)
        with ZipFile(self.out) as archive:
            result = json.loads(archive.read('Metadata/project_settings.config'))
        self.assertEqual(result['default_filament_colour'], ['']*5)

    def test_template_default_filament_colour_resizes_to_final_slot_count(self):
        # Current Bambu/Orca exports include this non-filament_-prefixed array.
        fixture_template(self.template, include_defaults=True)
        graft_native_project(self.source, self.template, self.out, real_count=2)
        with ZipFile(self.out) as archive:
            result = json.loads(archive.read('Metadata/project_settings.config'))
        self.assertEqual(result['default_filament_colour'],
                         ['#101010','#202020','#303030','#303030','#303030'])

    def test_native_template_two_purge_matrix_blocks_are_kept(self):
        # Real H2C profiles use two square purge-matrix blocks.
        fixture_template(self.template, double_flush=True)
        graft_native_project(self.source, self.template, self.out, real_count=2)
        with ZipFile(self.out) as archive:
            result = json.loads(archive.read('Metadata/project_settings.config'))
        self.assertEqual(len(result['flush_volumes_matrix']), 2*5*5)
        matrix=result['flush_volumes_matrix']
        for block in range(2):
            for row in range(5):
                for col in range(5):
                    if row != col:
                        self.assertGreater(float(matrix[block*25+row*5+col]),0)

    def test_rejects_overwriting_template_or_source(self):
        with self.assertRaisesRegex(TemplateError,'overwrite'):
            graft_native_project(self.source,self.template,self.template,real_count=2)
        with self.assertRaisesRegex(TemplateError,'overwrite'):
            graft_native_project(self.source,self.template,self.source,real_count=2)

    def test_preserves_original_inputs(self):
        orig=self.source.read_bytes(); temp=self.template.read_bytes()
        graft_native_project(self.source,self.template,self.out,real_count=2)
        self.assertEqual(orig,self.source.read_bytes())
        self.assertEqual(temp,self.template.read_bytes())

    def test_rejects_oversized_models_for_plate(self):
        data=json.loads(ZipFile(self.template).read('Metadata/project_settings.config'))
        data['printable_area']=['0x0','5x0','5x5','0x5']
        with ZipFile(self.template,'a',ZIP_DEFLATED) as z: pass
        # Replace ZIP member through a fresh archive to avoid duplicate entries.
        with ZipFile(self.template) as z: entries={n:z.read(n) for n in z.namelist()}
        entries['Metadata/project_settings.config']=json.dumps(data).encode()
        with ZipFile(self.template,'w',ZIP_DEFLATED) as z:
            for n,b in entries.items():z.writestr(n,b)
        with self.assertRaisesRegex(TemplateError,'exceeds'):
            graft_native_project(self.source,self.template,self.out,real_count=2)


if __name__=='__main__':unittest.main()
