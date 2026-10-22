"""Stage2B: native painted-face mapping and cross-source navigation regression."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

PACKAGE=Path(__file__).resolve().parents[1]


def load_helper(path,name):
    spec=importlib.util.spec_from_file_location(name,PACKAGE/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Keep the scanner tests independent of temporary patch installer scripts.
scanner=load_helper('desktop/qt_app/native_object_colors.py','stage2b_v3_scanner')


class ScannerTests(unittest.TestCase):
    def test_single_state_color_codes(self):
        self.assertEqual(scanner._single_painted_slot('8',8),2)
        self.assertEqual(scanner._single_painted_slot('0C',8),3)
        self.assertEqual(scanner._single_painted_slot('1C',8),4)
        self.assertEqual(scanner._single_painted_slot('4C',8),7)
        self.assertEqual(scanner._single_painted_slot('5C',8),8)

    def test_complex_split_code_rejected(self):
        for code in ('1','', 'A', '3C', 'F', '0C1'):
            # 3C is a valid extended single-state slot 6, not a split tree.
            if code == '3C':
                self.assertEqual(scanner._single_painted_slot(code,8),6)
                continue
            with self.subTest(code=code),self.assertRaises(ValueError):
                scanner._single_painted_slot(code,8)

    def test_out_of_range_code_rejected(self):
        with self.assertRaisesRegex(ValueError,'unavailable filament'):
            scanner._single_painted_slot('5C',5)

    def test_real_native_object_fixture_if_available(self):
        path=Path(os.environ.get('FULLSPECTRUM_QT_SHAPES_3MF') or '/mnt/data/Shapes Material-colored.3mf')
        if not path.is_file():self.skipTest('Private shape test model not distributed in repository')
        result=scanner.scan_native_object_colors(path)
        self.assertFalse(result.has_painted_faces)
        self.assertEqual(result,{'#000000':380,'#08ABFB':1224,'#9199A4':3072,
                                 '#D93B90':1440,'#F9ED3D':12})

    def test_real_native_painted_fixture_if_available(self):
        path=Path(os.environ.get('FULLSPECTRUM_QT_PAINTED_3MF') or '/mnt/data/3D_Printing_Test.3mf')
        if not path.is_file():self.skipTest('Private painted test model not distributed in repository')
        result=scanner.scan_native_object_colors(path)
        self.assertTrue(result.has_painted_faces)
        self.assertEqual(result,{
            '#000000':108,'#0000FF':2156,'#00FFFF':200,'#BCBCBC':814,
            '#E8AFCF':526,'#FF0000':200,'#FF8000':5940,'#FFFFFF':7900,
        })
        self.assertEqual(sum(result.values()),17844)

    @staticmethod
    def _make_painted_fixture(path, first_paint='4C'):
        import json
        import xml.etree.ElementTree as ET
        root=ET.Element('model')
        ET.SubElement(root,'metadata',name='Application').text='BambuStudio-02.08.04.57'
        resources=ET.SubElement(root,'resources')
        mainobj=ET.SubElement(resources,'object',id='2')
        comps=ET.SubElement(mainobj,'components')
        ET.SubElement(comps,'component',objectid='1',**{'{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path':'/3D/Objects/object_1.model'})
        ET.SubElement(root,'build')
        settings=ET.Element('config')
        ob=ET.SubElement(settings,'object',id='2')
        ET.SubElement(ob,'metadata',key='extruder',value='1')
        ET.SubElement(ob,'metadata',face_count='3')
        meshroot=ET.Element('model');mesh=ET.SubElement(meshroot,'mesh')
        ts=ET.SubElement(mesh,'triangles')
        ET.SubElement(ts,'triangle',v1='0',v2='1',v3='2',paint_color=first_paint)
        ET.SubElement(ts,'triangle',v1='0',v2='1',v3='2',paint_color='8')
        ET.SubElement(ts,'triangle',v1='0',v2='1',v3='2')
        project={'filament_colour':['#E8AFCF','#FFFFFF','#000000','#BCBCBC',
                                    '#0000FF','#FF0000','#FF8000','#00FFFF'],
                 'filament_is_mixed':['0']*8}
        with ZipFile(path,'w',ZIP_DEFLATED) as z:
            z.writestr('3D/3dmodel.model',ET.tostring(root))
            z.writestr('Metadata/model_settings.config',ET.tostring(settings))
            z.writestr('Metadata/project_settings.config',json.dumps(project))
            z.writestr('3D/Objects/object_1.model',ET.tostring(meshroot))

    def test_public_synthetic_native_facet_and_object_assignments(self):
        with tempfile.TemporaryDirectory() as t:
            file=Path(t)/'native-paint.3mf'
            self._make_painted_fixture(file)
            result=scanner.scan_native_object_colors(file)
            self.assertTrue(result.has_painted_faces)
            # Slot 7 from 4C, slot 2 from 8, fallback slot 1 (unpainted).
            self.assertEqual(result,{'#E8AFCF':1,'#FFFFFF':1,'#FF8000':1})

    def test_public_synthetic_split_paint_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            file=Path(t)/'native-split.3mf'
            self._make_painted_fixture(file,first_paint='1')
            with self.assertRaisesRegex(ValueError,'split-region'):
                scanner.scan_native_object_colors(file)

    def test_non_3mf_source_is_rejected(self):
        with self.assertRaises((OSError,ValueError)):
            scanner.scan_native_object_colors('/not/a/real/file.3mf')


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtSourceSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.main_window import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.window=MainWindow(settings_path=Path(self.temp.name)/'settings.json')
        self.addCleanup(self.window.close)

    def test_one_color_inventory_does_not_block_switch(self):
        panel=self.window.filaments_panel
        # Stop actual inventory IO. Populate one source with a single color.
        panel._start=lambda *args:None
        panel._source_signature=('inventory','')
        panel.options=[{'key':'only-black','name':'Black','color':'#000000','series':'PLA Basic'}]
        panel._populate_options()
        self.window.filament_source.setCurrentIndex(self.window.filament_source.findData('all-bambu'))
        self.assertEqual(self.window.plan_preferences.get('source'),'all-bambu')
        self.assertEqual(panel._source_signature[0],'all-bambu')
        self.assertEqual(panel.options,[])
        # Saving one color is *still* invalid, even though switching is allowed.
        with self.assertRaisesRegex(ValueError,'at least two'):
            panel.preferences.apply([{'key':'only-black','color':'#000000'}],
                                    {'only-black'},set())


if __name__=='__main__':unittest.main()
