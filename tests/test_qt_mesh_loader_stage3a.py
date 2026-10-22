"""Stage 3A model geometry invariants, independent of Qt/OpenGL installation."""
from __future__ import annotations
import os
from pathlib import Path
import struct
import tempfile
import unittest
from zipfile import ZipFile
from desktop.qt_app.mesh_loader import (_matrix,_apply,_compose,load_preview_mesh,
                                        _build_mesh,IDENTITY)

MAIN='''<?xml version="1.0" encoding="utf-8"?>
<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
 xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
 unit="millimeter"><resources><object id="2"><components>
<component p:path="/3D/Objects/object_1.model" objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>
</components></object></resources><build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 100 200 5"/></build></model>'''
PART='''<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<resources><object id="1"><mesh><vertices>
<vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/>
<vertex x="0" y="10" z="0"/></vertices><triangles>
<triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources><build/></model>'''

class MeshLoaderTests(unittest.TestCase):
    def test_3mf_component_build_transform_keeps_handedness(self):
        with tempfile.TemporaryDirectory() as folder:
            filename=Path(folder)/'synthetic.3mf'
            with ZipFile(filename,'w') as z:
                z.writestr('3D/3dmodel.model',MAIN)
                z.writestr('3D/Objects/object_1.model',PART)
            mesh=load_preview_mesh(filename)
            self.assertEqual(mesh.source_triangles,1)
            self.assertEqual(mesh.vertices,((100.,200.,5.),(110.,200.,5.),(100.,210.,5.)))
            a,b,c=(mesh.vertices[i] for i in mesh.triangles[0])
            cross=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            self.assertGreater(cross,0.,'3MF preview must not mirror the build geometry')

    def test_composed_rotation_and_translation(self):
        # 90-degree CCW rotation about Z in 3MF's column-vector layout.
        r=_matrix('0 1 0 -1 0 0 0 0 1 5 3 1')
        t=_matrix('1 0 0 0 1 0 0 0 1 10 20 30')
        self.assertEqual(_apply(_compose(t,r),(1,0,0)),(15.,24.,31.))

    def test_rejects_nonfinite_and_missing_geometry(self):
        with self.assertRaisesRegex(ValueError,'Invalid 3MF'):
            _matrix('nan 0 0 0 1 0 0 0 1 0 0 0')
        with self.assertRaisesRegex(ValueError,'No renderable'):
            _build_mesh([(0,0,0)],[],'blank')

    def test_obj_triangulates_and_keeps_axes(self):
        with tempfile.TemporaryDirectory() as folder:
            obj=Path(folder)/'square.obj'
            obj.write_text('v 0 0 0\nv 10 0 0\nv 10 10 0\nv 0 10 0\nf 1 2 3 4\n',encoding='utf-8')
            mesh=load_preview_mesh(obj)
            self.assertEqual(mesh.source_triangles,2)
            self.assertEqual(mesh.bounds,(0.,0.,0.,10.,10.,0.))

    def test_glb_embedded_triangle_y_up_to_z_up(self):
        with tempfile.TemporaryDirectory() as folder:
            import json
            path=Path(folder)/'triangle.glb'
            verts=struct.pack('<9f',0,0,0,2,0,0,0,2,0)
            inds=struct.pack('<3H',0,1,2)
            js={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(verts)+len(inds)}],
                'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(verts)},
                               {'buffer':0,'byteOffset':len(verts),'byteLength':len(inds)}],
                'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'},
                             {'bufferView':1,'componentType':5123,'count':3,'type':'SCALAR'}],
                'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1}]}],
                'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
            data=json.dumps(js).encode('utf-8');data+=b' ' * ((-len(data))%4)
            bin_data=verts+inds;bin_data+=b'\0' * ((-len(bin_data))%4)
            body=struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(bin_data),0x004e4942)+bin_data
            path.write_bytes(b'glTF'+struct.pack('<II',2,12+len(body))+body)
            mesh=load_preview_mesh(path)
            self.assertEqual(mesh.source_triangles,1)
            self.assertEqual(mesh.vertices[2],(0.,-0.,2.))

    def test_large_mesh_rejects_unsafe_face_skipping(self):
        from unittest.mock import patch
        with patch('desktop.qt_app.mesh_loader.MAX_DRAW_TRIANGLES', 2):
            with self.assertRaisesRegex(ValueError, 'Triangle skipping has been disabled'):
                _build_mesh([(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)] * 7, 'sample')

    def test_optional_real_3mf_files(self):
        model=os.environ.get('FULLSPECTRUM_QT_STAGE3A_REAL_3MF')
        if not model or not Path(model).is_file():self.skipTest('Optional private 3MF not in repository')
        mesh=load_preview_mesh(model)
        self.assertGreater(mesh.source_triangles,0)
        self.assertGreater(mesh.bounds[5]-mesh.bounds[2],0)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.gl_viewport import ModelViewport
except ImportError:
    QApplication=None

@unittest.skipUnless(QApplication is not None,'Qt not installed')
class OptionalWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_viewport_camera_and_wireframe_without_gl_context(self):
        mesh=_build_mesh([(0,0,0),(10,0,0),(0,10,20)],[(0,1,2)],'synthetic')
        window=ModelViewport()
        self.addCleanup(window.close)
        window.set_mesh(mesh)
        self.assertIs(window.mesh,mesh)
        window.set_wireframe(True)
        self.assertTrue(window.wireframe)
        window.yaw=3.5
        window.reset_camera()
        self.assertAlmostEqual(window.yaw,-1.47)

if __name__=='__main__':unittest.main()
