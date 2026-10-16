"""Focused regressions for Windows 3D visibility and exact solid-color previews."""
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from desktop.windows_mesh_preview import read_colored_obj, render_depth_image
    from desktop.source_color_preview import read_standard_color_mesh
except ModuleNotFoundError:
    from windows_mesh_preview import read_colored_obj, render_depth_image
    from source_color_preview import read_standard_color_mesh


class ColoredPreviewTests(unittest.TestCase):
    def test_depth_visibility_is_independent_of_polygon_order(self):
        # Two fully overlapping triangles. The closer blue surface must win
        # regardless of the order of triangles in OBJ or painter's draw order.
        points = [(-.5,0,-.5),(.5,0,-.5),(0,0,.5),
                  (-.5,.25,-.5),(.5,.25,-.5),(0,.25,.5)]
        back=(0,1,2,(240,35,35),None)
        front=(3,4,5,(35,35,240),None)
        for ordered in ([front,back],[back,front]):
            image=render_depth_image(points,ordered,320,320,yaw=0,pitch=0)
            self.assertEqual(image.getpixel((160,160)),(30,30,208))

    def test_highlights_are_exact_source_hex_only(self):
        points=[(-.5,0,-.5),(.5,0,-.5),(0,0,.5)]
        colored=[(0,1,2,(144,152,168),'#9098A8')]
        image=render_depth_image(points,colored,320,320,yaw=0,pitch=0,
                                 selected_color='#9098A8')
        self.assertEqual(image.getpixel((160,160)),(255,190,40))
        other=render_depth_image(points,colored,320,320,yaw=0,pitch=0,
                                 selected_color='#9199A4')
        self.assertEqual(other.getpixel((160,160)),(125,132,146))

    def test_protected_color_has_distinct_indicator(self):
        points=[(-.5,0,-.5),(.5,0,-.5),(0,0,.5)]
        face=(0,1,2,(144,152,168),'#9098A8')
        image=render_depth_image(points,[face],320,320,yaw=0,pitch=0,
                                 protected_colors={'#9098A8'})
        self.assertEqual(image.getpixel((160,160)),(45,230,215))

    def test_obj_reader_preserves_materials(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'test.obj'
            p.with_suffix('.mtl').write_text('newmtl slot_1\nKd 0.8 0.6 0.4\n')
            p.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl slot_1\nf 1 2 3\n')
            _,faces,count=read_colored_obj(p)
            self.assertEqual(count,1)
            self.assertEqual(faces[0][3],(204,153,102))

    def test_primed3d_actual_mesh_when_provided(self):
        sample=Path(__file__).resolve().parents[2]/'VSLA v4_SOLID_NoFilter.3mf'
        if not sample.is_file():
            self.skipTest('Primed3D sample not included with public repository')
        vertices,faces=read_standard_color_mesh(sample)
        self.assertEqual((len(vertices),len(faces)),(660,1304))
        self.assertIn('#9098A8',{face[4] for face in faces})


if __name__=='__main__':
    unittest.main()
