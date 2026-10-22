"""Phase 4 read-only 3MF validator regression tests (no external fixtures)."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from phase4_slicer_roundtrip import (InputError, check_roundtrip, cli, snapshot,
                                      template_details, format_catalog)

CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'

def write_project(path, *, mixed=1, printer='Bambu Lab H2C', nozzle='0.4',
                  preset='Panchroma PLA Translucent', colors=None, paint='4FC',
                  triangle_x=0.0, is_blank=False, bad_ratio=False):
    colors = colors or ['#08ABFB','#9199A4','#000000','#235CA1']
    physical=len(colors)-mixed
    n=len(colors)
    cfg={
        'filament_colour': colors,
        'filament_is_mixed': ['0']*physical+['1']*mixed,
        'filament_mixed_components': ['']*physical+['1,3']*mixed,
        'filament_mixed_sublayer_ratios': ['']*physical+[('0.1,0.1' if bad_ratio else '0.6,0.4')]*mixed,
        'filament_settings_id': [preset]*n,
        'filament_ids': ['PMPL13']*n,
        'filament_multi_colour':colors[:],
        'filament_flow_ratio':['0.96','nil']*n,
        'printer_model':printer,
        'printer_settings_id':f'{printer} {nozzle} nozzle',
        'printer_variant':nozzle,
        'print_settings_id':'0.08mm High Quality',
    }
    root=ET.Element('model',xmlns=CORE)
    ET.SubElement(root,'metadata',name='Application').text='BambuStudio-02.08.04.57'
    ET.SubElement(root,'resources');ET.SubElement(root,'build')
    child=ET.Element('model',xmlns=CORE)
    resources=ET.SubElement(child,'resources')
    obj=ET.SubElement(resources,'object',id='1')
    mesh=ET.SubElement(obj,'mesh');verts=ET.SubElement(mesh,'vertices')
    for x,y,z in ((0,0,0),(1+triangle_x,0,0),(0,1,0)):
        ET.SubElement(verts,'vertex',x=str(x),y=str(y),z=str(z))
    tris=ET.SubElement(mesh,'triangles')
    ET.SubElement(tris,'triangle',v1='0',v2='1',v3='2',paint_color=paint)
    ET.SubElement(child,'build')
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('Metadata/project_settings.config',json.dumps(cfg))
        z.writestr('3D/3dmodel.model',ET.tostring(root))
        if not is_blank: z.writestr('3D/Objects/object_1.model',ET.tostring(child))
        z.writestr('Metadata/model_settings.config','<config/>')
        z.writestr('Metadata/slice_info.config','<config/>')
    return cfg

class NativeRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a=Path(self.temp.name)/'a.3mf'; self.b=Path(self.temp.name)/'b.3mf'
        write_project(self.a);write_project(self.b)

    def test_equal_projects_pass(self):
        result=check_roundtrip(self.a,self.b)
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['before']['slots'],4)
        self.assertEqual(result['before']['mesh']['triangles'],1)

    def test_recipe_change_is_failure(self):
        write_project(self.b,bad_ratio=True)
        result=check_roundtrip(self.a,self.b)
        self.assertTrue(any('recipe' in x or 'palette' in x for x in result['errors']))

    def test_paint_change_is_failure(self):
        write_project(self.b,paint='8C')
        self.assertTrue(any('paint assignments' in x for x in check_roundtrip(self.a,self.b)['errors']))

    def test_geometry_change_is_failure(self):
        write_project(self.b,triangle_x=0.4)
        self.assertTrue(any('shape' in x for x in check_roundtrip(self.a,self.b)['errors']))

    def test_nozzle_change_is_failure(self):
        write_project(self.b,nozzle='0.2')
        self.assertTrue(any('printer_variant' in x for x in check_roundtrip(self.a,self.b)['errors']))

    def test_palette_size_change_is_failure(self):
        write_project(self.b, mixed=0)
        self.assertTrue(check_roundtrip(self.a,self.b)['errors'])

    def test_material_identity_change_is_notice(self):
        write_project(self.b,preset='Panchroma PLA Translucent Project')
        result=check_roundtrip(self.a,self.b)
        self.assertEqual(result['errors'],[])
        self.assertTrue(any('preset identity' in x for x in result['warnings']))

    def test_flow_change_is_notice(self):
        with ZipFile(self.b) as z:
            files={p:z.read(p) for p in z.namelist()}
        cfg=json.loads(files['Metadata/project_settings.config'])
        cfg['filament_flow_ratio']=['0.97','nil']*4
        files['Metadata/project_settings.config']=json.dumps(cfg)
        with ZipFile(self.b,'w') as z:
            for p,v in files.items():z.writestr(p,v)
        result=check_roundtrip(self.a,self.b)
        self.assertEqual(result['errors'],[])
        self.assertTrue(any('material parameter' in x for x in result['warnings']))

    def test_invalid_component_is_audit_error(self):
        with ZipFile(self.b) as z: files={p:z.read(p) for p in z.namelist()}
        cfg=json.loads(files['Metadata/project_settings.config'])
        cfg['filament_mixed_components'][-1]='1,99'
        files['Metadata/project_settings.config']=json.dumps(cfg)
        with ZipFile(self.b,'w') as z:
            for p,v in files.items():z.writestr(p,v)
        self.assertTrue(any('component' in x for x in snapshot(self.b)['errors']))

    def test_blank_project_cannot_pass_painted_model_audit(self):
        write_project(self.b,is_blank=True)
        self.assertTrue(any('No printable' in x for x in snapshot(self.b)['errors']))
        d=template_details(self.b)
        self.assertTrue(d['blank'])

    def test_template_matrix_exposes_nozzle_mismatch(self):
        b=template_details(self.b)
        self.assertEqual(b['nozzle'],'0.4')
        self.assertIn('3MF',format_catalog([self.b]).upper())

    def test_cli_exit_failure_on_changed_paint(self):
        write_project(self.b,paint='999')
        self.assertEqual(cli(['compare',str(self.a),str(self.b)]),1)

    def test_installer_target_repo_is_not_required_for_standalone_use(self):
        self.assertEqual(cli(['audit',str(self.a)]),0)

if __name__=='__main__':unittest.main()
