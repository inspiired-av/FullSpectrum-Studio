"""Stage 6A3-D: depth-tested world-grid text, isolated from plate and Qt badge.

The math and mocked OpenGL tests are headless. The optional real-QImage test
runs on Windows with PySide6; actual GPU depth behavior needs a viewport smoke
check, since headless mocks cannot verify graphics-driver depth comparisons.
"""
from __future__ import annotations

import ast
import importlib.util
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

PKG = Path(__file__).resolve().parents[1] / 'desktop' / 'qt_app'
spec = importlib.util.spec_from_file_location('stage6a3d_opengl_ruler', PKG/'preview_grid_ruler_gl.py')
ruler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ruler)


class RulerWorldGeometryTests(unittest.TestCase):
    def test_shared_corner_has_exactly_one_zero_for_both_rulers(self):
        labels = ruler.ruler_anchors(10, (140,260,140,260), -1)
        origins = [(axis,label,point) for axis,label,point in labels if label == '0']
        self.assertEqual(len(origins), 1)
        self.assertEqual(origins[0][0], 'O')
        self.assertEqual(origins[0][2][:2], (150.,150.))
        xs = [(label,pos[0],pos[1]) for axis,label,pos in labels if axis == 'X']
        ys = [(label,pos[0],pos[1]) for axis,label,pos in labels if axis == 'Y']
        self.assertEqual(xs, [('50',200.,150.),('100',250.,150.)])
        self.assertEqual(ys, [('50',150.,200.),('100',150.,250.)])
        self.assertEqual([(role,label) for role,label,_ in labels
                          if role in ('MX', 'MY')], [('MX','X'),('MY','Y')])
        self.assertTrue(all(point[2] > -1 for _,_,point in labels))

    def test_one_origin_even_when_model_is_far_from_world_zero(self):
        labels = ruler.ruler_anchors(50, (450,1250,-800,-200), -5)
        self.assertEqual(len([1 for _,text,_ in labels if text == '0']), 1)
        shared = next(p for role,text,p in labels if role == 'O')
        self.assertEqual(shared[:2], (500.,-750.))
        self.assertTrue(all(p[1]==shared[1] for role,_,p in labels
                            if role in ('X','MX')))
        self.assertTrue(all(p[0]==shared[0] for role,_,p in labels
                            if role in ('Y','MY')))
        self.assertTrue(all(float(t)>0 for role,t,_ in labels
                            if role in ('X','Y')))

    def test_axes_increase_in_positive_world_directions(self):
        labels = ruler.ruler_anchors(10, (-105,60,30,250), -3)
        ox,oy,_ = next(p for role,_,p in labels if role=='O')
        self.assertEqual((ox,oy), (-100.,50.))
        for role,_,(x,y,z) in labels:
            if role in ('X','MX'):
                self.assertGreater(x,ox)
                self.assertEqual(y,oy)
            elif role in ('Y','MY'):
                self.assertEqual(x,ox)
                self.assertGreater(y,oy)

    def test_at_most_one_origin_and_two_direction_markers(self):
        for scale in (.05, 5, 2500):
            labels = ruler.ruler_anchors(scale,(-13*scale,50*scale,
                                                -6*scale,59*scale),0,max_per_axis=5)
            self.assertEqual(sum(role=='O' for role,_,_ in labels),1)
            self.assertLessEqual(sum(role in ('MX','MY') for role,_,_ in labels),2)
            self.assertLessEqual(len(labels), 2*5+1)

    def test_invalid_geometry_never_generates_text(self):
        for step, limits, floor in [
            (0,(0,1,0,1),0),
            (float('nan'),(0,1,0,1),0),
            (1,(2,1,0,1),0),
            (1,(0,1,0,1),float('inf')),
        ]:
            self.assertEqual(ruler.ruler_anchors(step,limits,floor),())

    def test_pixel_quads_are_camera_facing_and_bounded(self):
        anchors=(('O','0',(10,20,-1)),('X','50',(0,30,-1)))
        rects=((0.,0.,.4,.2,40.,18.),(.4,0.,.8,.2,40.,18.))
        data=ruler.quad_vertices(anchors,rects,1.0)
        self.assertEqual(len(data),2*6*7)
        self.assertTrue(all(math.isfinite(v) for v in data))
        # Every triangle vertex preserves its own world-space ruler tick.
        self.assertEqual(set(data[i] for i in range(0,6*7,7)),{10.})
        self.assertEqual(set(data[i] for i in range(6*7,12*7,7)),{0.})
        self.assertEqual(set(data[i+2] for i in range(0,len(data),7)),{-1.})
        with self.assertRaises(ValueError):
            ruler.quad_vertices(anchors,rects[:1])

    def test_marker_quads_use_matching_axis_offsets(self):
        anchors=(('X','50',(0,0,-1)),('MX','X',(1,0,-1)),
                 ('Y','50',(0,1,-1)),('MY','Y',(0,2,-1)),
                 ('O','0',(0,0,-1)))
        rects=((0.,0.,.4,.2,40.,18.),)*len(anchors)
        data=ruler.quad_vertices(anchors,rects,1.0)
        quads=[data[i*42:(i+1)*42] for i in range(len(anchors))]
        self.assertEqual(tuple(quads[0][3:5]),tuple(quads[1][3:5]))
        self.assertEqual(tuple(quads[2][3:5]),tuple(quads[3][3:5]))
        self.assertNotEqual(tuple(quads[0][3:5]),tuple(quads[4][3:5]))
        with self.assertRaises(ValueError):
            ruler.quad_vertices((('alien','!',(0,0,0)),),rects[:1])


class RulerSourceContracts(unittest.TestCase):
    def test_only_opengl_ruler_draws_numbers(self):
        overlay=(PKG/'preview_grid_measurement_overlay.py').read_text(encoding='utf-8-sig')
        view=(PKG/'gl_viewport.py').read_text(encoding='utf-8-sig')
        plate=(PKG/'plate_gl.py').read_text(encoding='utf-8-sig')
        for name,src in [('overlay',overlay),('view',view),('ruler',Path(ruler.__file__).read_text())]:
            ast.parse(src,filename=name)
        self.assertNotIn('def _axis_labels(',overlay)
        self.assertNotIn('layout_grid_ruler_labels(',overlay)
        self.assertIn('grid_spacing_label(self._step)',overlay)
        self.assertIn('self._world_ruler.draw(',view)
        self.assertIn('if self._grid_show_measurements:',view)
        self.assertIn('if show_world_grid and not self._grid_failed:',view)
        self.assertIn('self._world_ruler.release(self._gl)',view)
        self.assertIn('vLocalPosition.xy / 10.0',plate)
        self.assertIn('vLocalPosition.xy / 50.0',plate)
        self.assertNotIn('WorldGridRulerRenderer',plate)

    def test_opengl_ruler_depth_test_and_state_cleanup(self):
        self.assertIn('clip.xy += 2.0 * pixelOffset',ruler.VERTEX_SHADER)
        self.assertIn('gl_Position = clip',ruler.VERTEX_SHADER)
        self.assertIn('gl.glEnable(gl.GL_DEPTH_TEST)',Path(ruler.__file__).read_text())
        self.assertIn('gl.glDepthMask(gl.GL_FALSE)',Path(ruler.__file__).read_text())
        self.assertIn('gl.glDepthMask(gl.GL_TRUE if depth_write else gl.GL_FALSE)',Path(ruler.__file__).read_text())
        self.assertIn('gl.glDeleteTextures',Path(ruler.__file__).read_text())


class MockOpenGLTests(unittest.TestCase):
    class GL:
        GL_VERTEX_SHADER=1;GL_FRAGMENT_SHADER=2;GL_COMPILE_STATUS=3;GL_LINK_STATUS=4
        GL_ARRAY_BUFFER=5;GL_STATIC_DRAW=6;GL_FLOAT=7;GL_FALSE=0;GL_TRUE=1
        GL_TEXTURE2=2;GL_TEXTURE0=0;GL_TEXTURE_2D=50;GL_TEXTURE_MIN_FILTER=51
        GL_TEXTURE_MAG_FILTER=52;GL_TEXTURE_WRAP_S=53;GL_TEXTURE_WRAP_T=54
        GL_LINEAR=55;GL_CLAMP_TO_EDGE=56;GL_RGBA8=57;GL_RGBA=58;GL_UNSIGNED_BYTE=59
        GL_BLEND=60;GL_DEPTH_TEST=61;GL_DEPTH_WRITEMASK=62
        GL_SRC_ALPHA=63;GL_ONE_MINUS_SRC_ALPHA=64;GL_TRIANGLES=65
        def __init__(self):
            self.uploads=[];self.draw_calls=0;self.deleted=[];self.enabled={self.GL_DEPTH_TEST}
            self.depth_write=True;self.texture_uploads=0;self.texture_units=[]
        def glIsEnabled(self,x):return x in self.enabled
        def glGetBooleanv(self,x):return self.depth_write
        def glEnable(self,x):self.enabled.add(x)
        def glDisable(self,x):self.enabled.discard(x)
        def glDepthMask(self,x):self.depth_write=bool(x)
        def glActiveTexture(self,x):self.texture_units.append(x)
        def glCreateShader(self,*args):return 1
        def glCreateProgram(self):return 2
        def glGetShaderiv(self,*args):return True
        def glGetProgramiv(self,*args):return True
        def glGenVertexArrays(self,*args):return 3
        def glGenBuffers(self,*args):return 4
        def glGenTextures(self,*args):return 5
        def glGetUniformLocation(self,*args):return 1
        def glBufferData(self,*args):self.uploads.append(args)
        def glTexImage2D(self,*args):self.texture_uploads+=1
        def glDrawArrays(self,*args):self.draw_calls+=1
        def glDeleteTextures(self,*args):self.deleted.append('texture')
        def glDeleteBuffers(self,*args):self.deleted.append('vbo')
        def glDeleteVertexArrays(self,*args):self.deleted.append('vao')
        def glDeleteProgram(self,*args):self.deleted.append('program')
        def __getattr__(self,name):
            if name.startswith('gl'):return lambda *args: None
            raise AttributeError(name)

    def test_geometry_upload_reused_on_camera_orbit_and_resources_cleaned(self):
        obj=ruler.WorldGridRulerRenderer()
        image=SimpleNamespace(width=lambda:128,height=lambda:64,
                              constBits=lambda: b'\x00'*(128*64*4))
        def atlas(anchors,dpr):
            return image, tuple((0,0,.5,.5,44.,18.) for _ in anchors)
        obj._raster_atlas=atlas
        fake=self.GL()
        identity=SimpleNamespace(copyDataTo=lambda:[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.])
        bounds=(0,200,0,200)
        obj.draw(fake,identity,10,bounds,-2,viewport_pixels=(1000,600),dpr=1)
        self.assertEqual(len(fake.uploads),1)
        self.assertEqual(fake.texture_uploads,1)
        self.assertEqual(fake.draw_calls,1)
        self.assertTrue(fake.depth_write)
        self.assertNotIn(fake.GL_BLEND,fake.enabled)
        self.assertIn(fake.GL_DEPTH_TEST,fake.enabled)
        obj.draw(fake,identity,10,bounds,-2,viewport_pixels=(1200,800),dpr=1)
        self.assertEqual(len(fake.uploads),1)  # camera / resize: only uniforms change
        self.assertEqual(fake.draw_calls,2)
        obj.draw(fake,identity,5,bounds,-2,viewport_pixels=(1200,800),dpr=1)
        self.assertEqual(len(fake.uploads),2)
        self.assertEqual(fake.texture_uploads,2)
        obj.release(fake)
        self.assertIn('texture',fake.deleted)
        self.assertIn('vbo',fake.deleted)
        self.assertEqual(obj._count,0)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Needs PySide6')
class RealQtAtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_atlas_contains_real_text_pixels(self):
        anchors=ruler.ruler_anchors(10,(0,200,0,200),-1)
        img,rectangles=ruler.WorldGridRulerRenderer._raster_atlas(anchors,1.0)
        self.assertFalse(img.isNull())
        self.assertEqual(len(rectangles),len(anchors))
        self.assertGreater(sum(bool(img.pixelColor(x,y).alpha())
                               for x in range(img.width()) for y in range(img.height())),0)


if __name__=='__main__':
    unittest.main()
