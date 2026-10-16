"""Native object-color and UI relocation regression tests."""
from __future__ import annotations
import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED

# Works both inside the repository and inside the unextracted patch's tests/.
PACKAGE=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('native_object_colors_fixture',PACKAGE/'desktop/qt_app/native_object_colors.py')
scanner=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


def native_project(path, face_color=None, assign_all=True, mixed=False):
    from xml.etree.ElementTree import Element, SubElement, tostring
    root=Element('model')
    SubElement(root,'metadata',name='Application').text='BambuStudio-02.08.04.57'
    settings=Element('config')
    shapes=[(2,1,2), (4,2,3)]
    for objid,extruder,faces in shapes:
        o=SubElement(settings,'object',id=str(objid))
        SubElement(o,'metadata',key='extruder',value=str(extruder))
        if assign_all or objid==2:SubElement(o,'metadata',face_count=str(faces))
    cfg={'filament_colour':['#08ABFB','#D93B90'],
         'filament_is_mixed':['0','1' if mixed else '0']}
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('3D/3dmodel.model',tostring(root))
        z.writestr('Metadata/project_settings.config',json.dumps(cfg))
        z.writestr('Metadata/model_settings.config',tostring(settings))
        obj=Element('model')
        m=SubElement(obj,'mesh'); tris=SubElement(m,'triangles')
        for i in range(5):
            kw={'v1':'0','v2':'1','v3':'2'}
            if face_color is not None and i==0:kw['paint_color']=face_color
            SubElement(tris,'triangle',**kw)
        z.writestr('3D/Objects/object_1.model',tostring(obj))


class NativeColorsTests(unittest.TestCase):
    def test_user_supplied_five_solid_shapes_when_available(self):
        p=Path(os.environ.get('FULLSPECTRUM_SHAPES_3MF',''))
        if not p.is_file():self.skipTest('Optional original 3MF not distributed in public repository')
        data=scanner.scan_native_object_colors(p)
        self.assertEqual(data,{
            '#000000':380, '#08ABFB':1224, '#9199A4':3072,
            '#D93B90':1440, '#F9ED3D':12,
        })
        self.assertEqual(sum(data.values()),6128)

    def test_two_solid_native_shapes_are_detected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'two.3mf';native_project(p)
            self.assertEqual(scanner.scan_native_object_colors(p),{'#08ABFB':2,'#D93B90':3})

    def test_face_painting_is_not_silently_treated_as_object_color(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'painted.3mf';native_project(p,face_color='abc')
            with self.assertRaisesRegex(ValueError,'Face-painted'):
                scanner.scan_native_object_colors(p)

    def test_mixed_filament_native_project_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'mixed.3mf';native_project(p,mixed=True)
            with self.assertRaisesRegex(ValueError,'Mixed-filament'):
                scanner.scan_native_object_colors(p)

    def test_ambiguous_object_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'ambiguous.3mf';native_project(p,assign_all=False)
            with self.assertRaisesRegex(ValueError,'unambiguous'):
                scanner.scan_native_object_colors(p)

    def test_code_compiles_and_filament_source_is_under_filament_tab(self):
        for name in ('main_window.py','filaments_tab.py','filament_preferences.py','native_object_colors.py'):
            ast.parse((PACKAGE/'desktop/qt_app'/name).read_text(encoding='utf-8'))
        source=(PACKAGE/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        tab=(PACKAGE/'desktop/qt_app/filaments_tab.py').read_text(encoding='utf-8')
        self.assertIn('Manage Filament Colors…',source)
        self.assertIn("self.filament_source = QComboBox()",tab)
        self.assertNotIn('col.addWidget(_section_heading("Filament Source"))',source)


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 unavailable')
class QtSourceTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        from desktop.qt_app.main_window import MainWindow
        self.window=MainWindow(settings_path=Path(self.temp.name)/'settings.json')
        self.addCleanup(self.window.close)

    def test_source_selector_is_owned_by_filaments_tab(self):
        w=self.window
        # Stage 2B layout wraps the tab controls in a scroll-content widget.
        # Test ownership through the widget hierarchy, not direct parentage.
        self.assertTrue(w.filaments_panel.isAncestorOf(w.filament_source))
        self.assertIs(w.filament_source,w.filaments_panel.filament_source)
        self.assertIn('Filaments',w.tabs.tabText(1))
        self.assertEqual(w.plan_preferences.get('source'),'inventory')

    def test_filament_source_save_and_revert(self):
        from desktop.settings_store import load_settings
        w=self.window
        selected=w.filament_source.findData('exact-cmykw')
        w.filament_source.setCurrentIndex(selected)
        # No two selectable colors for CMYKW, so _accept_table allows saving.
        w.filaments_panel.save()
        self.assertEqual(load_settings(w.plan_preferences.path).get('source'),'exact-cmykw')
        self.assertFalse(w.plan_preferences.is_dirty)

if __name__=='__main__': unittest.main()
