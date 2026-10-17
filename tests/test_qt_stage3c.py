"""Stage 3C: actual corner-color gradients, shader tags and protection UX."""
from __future__ import annotations
import ast
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from desktop.qt_app.mesh_loader import _build_mesh, load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces

ROOT=Path(__file__).resolve().parents[1]
CORE='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'

class SourceFidelityTests(unittest.TestCase):
    def test_vertex_gradients_are_not_replaced_by_face_average(self):
        source=f'''<model xmlns="{CORE}"><resources><colorgroup id="3"><color color="#FF0000"/><color color="#00FF00"/><color color="#0000FF"/></colorgroup><object id="4"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2" pid="3" p1="0" p2="1" p3="2"/></triangles></mesh></object></resources><build><item objectid="4"/></build></model>'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gradient.3mf'
            with ZipFile(path,'w') as z:z.writestr('3D/3dmodel.model',source)
            mesh=load_preview_mesh(path)
            self.assertEqual(mesh.face_colors,('#555555',))
            self.assertEqual(mesh.corner_colors,(('#FF0000','#00FF00','#0000FF'),))
            gpu=flatten_faces(mesh)
            self.assertEqual(len(gpu),36)
            self.assertEqual(tuple(gpu[6:9]),(1.,0.,0.))
            self.assertEqual(tuple(gpu[18:21]),(0.,1.,0.))
            self.assertEqual(tuple(gpu[30:33]),(0.,0.,1.))
            for i in (9,21,33):self.assertAlmostEqual(gpu[i],85/255,places=5)
            self.assertEqual(dict(mesh.palette_counts),{'#555555':1})

    def test_independent_faces_do_not_blend_across_color_seams(self):
        mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0),(1,1,0)],[(0,1,2),(1,3,2)],'seams',
                         ['#FF0000','#0000FF'])
        gpu=flatten_faces(mesh)
        self.assertEqual(tuple(gpu[6:9]),(1.,0.,0.))
        self.assertEqual(tuple(gpu[42:45]),(0.,0.,1.))
        self.assertEqual(tuple(gpu[9:12]),(1.,0.,0.))
        self.assertEqual(tuple(gpu[45:48]),(0.,0.,1.))

    def test_corner_color_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'Vertex source colors'):
            _build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'bad',corner_colors=[(),()])

    def test_shader_uses_flat_face_tags_and_gpu_overlays(self):
        shader=(ROOT/'desktop/qt_app/gl_viewport.py').read_text()
        self.assertIn('flat out vec3 sourceTag',shader)
        self.assertIn('flat in vec3 sourceTag',shader)
        self.assertIn('uniform vec3 selectedSourceColor',shader)
        self.assertIn('uniform vec3 protectedSourceColors[128]',shader)
        self.assertIn('def set_highlights(',shader)
        self.assertIn('gl.glVertexAttribPointer(3',shader)
        self.assertIn('gl.GL_TRUE',shader)
        self.assertIn('gl.glDrawArrays(gl.GL_TRIANGLES,0,self._verts)',shader)

    def test_highlight_selection_does_not_modify_source_mesh_or_render_buffer(self):
        file=ROOT/'desktop/qt_app/main_window.py'
        s=file.read_text(encoding='utf-8')
        self.assertIn('self.preview_surface.set_highlights(',s)
        self.assertIn('source_color_selected.connect(self._filament_color_selected)',s)
        self.assertIn('protections_changed.connect(self._protections_updated)',s)
        self.assertIn('self.filaments_panel.select_source_color(color)',s)
        self.assertIn("'Predicted', 'Color Loss', 'Anchor Influence'",s)

try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication=None

@unittest.skipUnless(QApplication is not None,'Qt GUI unavailable in this environment')
class Stage3CGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_select_and_protect_sync_without_model_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=MainWindow(settings_path=Path(tmp)/'settings.json')
            try:
                mesh=_build_mesh([(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],'test',['#FF0000'])
                w._preview_loaded(0,w.state.model_path,mesh,None)
                before=w.preview_surface._data
                w._select_palette_color('#FF0000')
                self.assertEqual(w.preview_surface.selected_source_color,'#FF0000')
                self.assertIs(before,w.preview_surface._data)
                w._protections_updated({'#FF0000':'anchor'})
                self.assertEqual(w.preview_surface.protected_source_colors,('#FF0000',))
                w._preview_mode_changed('Wireframe')
                self.assertEqual(w.preview_surface.selected_source_color,'#FF0000')
                w._select_palette_color(None)
                self.assertIsNone(w.preview_surface.selected_source_color)
            finally:w.close()

if __name__=='__main__':unittest.main()
