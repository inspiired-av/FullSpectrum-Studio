"""Stage 3B color fidelity and crease smoothing; no Qt or OpenGL needed."""
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from desktop.qt_app.mesh_loader import _build_mesh, load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces

CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'

def colored_3mf():
    return f'''<model xmlns="{CORE}" unit="millimeter"><resources>
<colorgroup id="4"><color color="#0088DDFF"/><color color="#FF0000FF"/></colorgroup>
<object id="2"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>
<vertex x="0" y="1" z="0"/><vertex x="1" y="1" z="0"/></vertices><triangles>
<triangle v1="0" v2="1" v3="2" pid="4" p1="0"/>
<triangle v1="1" v2="3" v3="2" pid="4" p1="1"/></triangles></mesh></object>
</resources><build><item objectid="2"/></build></model>'''

class Stage3BColors(unittest.TestCase):
    def test_standard_exact_face_colors_match_viewer_and_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'painted.3mf'
            with ZipFile(file,'w') as z:z.writestr('3D/3dmodel.model',colored_3mf())
            mesh=load_preview_mesh(file)
            self.assertEqual(mesh.face_colors,('#0088DD','#FF0000'))
            self.assertEqual(dict(mesh.palette_counts),{'#0088DD':1,'#FF0000':1})
            self.assertEqual(mesh.triangles,((0,1,2),(1,3,2)))

    def test_native_unpainted_default_and_painted_slot_have_distinct_colors(self):
        main=f'''<model xmlns="{CORE}" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06">
<metadata name="Application">BambuStudio-02.08.04.57</metadata>
<resources><object id="2"><components><component p:path="/3D/Objects/object_1.model" objectid="1"/></components></object></resources>
<build><item objectid="2"/></build></model>'''
        part=f'''<model xmlns="{CORE}"><resources><object id="1"><mesh><vertices>
<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>
<vertex x="0" y="1" z="0"/><vertex x="1" y="1" z="0"/></vertices><triangles>
<triangle v1="0" v2="1" v3="2"/>
<triangle v1="1" v2="3" v3="2" paint_color="8"/></triangles></mesh></object></resources></model>'''
        settings='<config><object id="2"><metadata key="extruder" value="1"/><metadata face_count="2"/></object></config>'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'native.3mf'
            with ZipFile(path,'w') as z:
                z.writestr('3D/3dmodel.model',main)
                z.writestr('3D/Objects/object_1.model',part)
                z.writestr('Metadata/model_settings.config',settings)
                z.writestr('Metadata/project_settings.config','{"filament_colour":["#0000FF","#00FF00"]}')
            mesh=load_preview_mesh(path)
            self.assertEqual(mesh.face_colors,('#0000FF','#00FF00'))
            self.assertEqual(sum(n for _,n in mesh.palette_counts),2)

    def test_color_counts_use_complete_surface_without_sampling(self):
        mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)]*7,
                         'large',['#00AA00']*5+['#AA0000']*2)
        self.assertEqual(mesh.source_triangles,7)
        self.assertEqual(len(mesh.triangles),7)
        self.assertFalse(mesh.sampled)
        self.assertEqual(dict(mesh.palette_counts),{'#00AA00':5,'#AA0000':2})
        self.assertEqual(len(mesh.face_colors),len(mesh.triangles))

    def test_uncolored_files_do_not_invent_source_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'plain.obj'
            file.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            mesh=load_preview_mesh(file)
            self.assertEqual(mesh.palette_counts,())
            self.assertEqual(mesh.face_colors,(None,))

    def test_existing_predicted_obj_local_mtl_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'predicted.obj'
            file.write_text('mtllib predicted.mtl\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl predicted_1\nf 1 2 3\n')
            file.with_suffix('.mtl').write_text('newmtl predicted_1\nKd 0 0.5 1\n')
            mesh=load_preview_mesh(file)
            self.assertEqual(mesh.face_colors,('#0080FF',))

    def test_normals_smooth_across_shallow_angle_only(self):
        shallow=_build_mesh([(0,0,0),(1,0,0),(0,1,0),(0,1,.25)],
                            [(0,1,2),(0,1,3)],'curve')
        gpu=flatten_faces(shallow)
        first=tuple(gpu[3:6]);second=tuple(gpu[39:42])
        for a,b in zip(first,second):self.assertAlmostEqual(a,b,places=5)
        self.assertGreater(first[2],.9)
        edge=_build_mesh([(0,0,0),(1,0,0),(0,1,0),(0,0,1)],
                         [(0,1,2),(0,1,3)],'hard')
        data=flatten_faces(edge)
        dot=sum(a*b for a,b in zip(data[3:6],data[39:42]))
        self.assertLess(abs(dot),.01,'90 degree mechanical edges must remain sharp')

    def test_shaded_color_is_source_color_not_material_guess(self):
        mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'red',['#FF0000'])
        values=flatten_faces(mesh)
        self.assertEqual(tuple(values[6:9]),(1.,0.,0.))
        self.assertEqual(len(values),36)

    def test_optional_real_source_when_requested(self):
        path=os.environ.get('FULLSPECTRUM_QT_STAGE3B_REAL_3MF')
        if not path or not Path(path).is_file():self.skipTest('Optional source 3MF not distributed')
        mesh=load_preview_mesh(path)
        self.assertEqual(len(mesh.face_colors),len(mesh.triangles))
        self.assertLessEqual(sum(n for c,n in mesh.palette_counts),mesh.source_triangles)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication=None

@unittest.skipUnless(QApplication is not None,'PySide6 unavailable in local test environment')
class Stage3BWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_original_palette_is_visible_with_colors(self):
        with tempfile.TemporaryDirectory() as tmp:
            widget=MainWindow(settings_path=Path(tmp)/'settings.json')
            try:
                mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'color',['#112233'])
                widget._preview_loaded(0,widget.state.model_path,mesh,None)
                self.assertFalse(widget.source_palette_scroll.isHidden())
                self.assertIn('source colors',widget.source_palette_message.text())
                self.assertTrue(widget.load_predicted_button.isEnabled())
            finally:widget.close()

if __name__=='__main__':unittest.main()
