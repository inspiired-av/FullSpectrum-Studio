"""Focused Stage 6A3-D grid clipping and explicit camera framing contracts.

No PySide6 or GPU is needed for pure bounds/clip checks. Real OpenGL should be
verified manually on Windows to distinguish frustum clipping from intentional
screen-edge cropping during user zoom.
"""
from __future__ import annotations

import ast
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT/'desktop'/'qt_app'


def load_helper():
    spec = importlib.util.spec_from_file_location('stage6a3d_grid_camera', PKG/'preview_grid_camera.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

camera = load_helper()


class GridCameraMathTests(unittest.TestCase):
    def test_footprint_matches_exact_major_aligned_geometry(self):
        from desktop.qt_app.preview_grid_geometry import world_grid_vertices
        for model in ((0,0,0,120,10,60), (100,-250,0,500,130,1),
                      (-1.2,-2.1,-3,1.2,2.1,3), (0,0,0,4,3,120)):
            vertices, _step = world_grid_vertices(model, 0)
            x0,x1,y0,y1 = camera.world_grid_footprint(model)
            self.assertEqual((x0,x1,y0,y1),
                             (min(vertices[0::7]),max(vertices[0::7]),
                              min(vertices[1::7]),max(vertices[1::7])))
        self.assertGreaterEqual(camera.world_grid_footprint.cache_info().hits, 0)

    def test_far_plane_includes_all_grid_corners(self):
        eye = (0, -80, 150)
        target = (0,0,0)
        xy = (-200,400,-400,300)
        near, far = camera.expand_clip_for_grid(eye, target, (1.0,175.0),xy,-1.0)
        self.assertGreaterEqual(far + 1e-8, 1.08 * max(
            sum((p[i]-eye[i])*(target[i]-eye[i])/math.dist(eye,target)
                for i in range(3))
            for p in ((x,y,-1.0) for x in (xy[0],xy[1]) for y in (xy[2],xy[3]))))
        self.assertGreater(near,0)

    def test_model_near_far_preserved_when_grid_already_fits(self):
        near,far=camera.expand_clip_for_grid((0,0,100),(0,0,0),(1,1000),(-20,20,-20,20),0)
        self.assertEqual((near,far),(1.0,1000.0))

    def test_grid_behind_camera_does_not_corrupt_projection(self):
        self.assertEqual(camera.expand_clip_for_grid(
            (0,0,0),(0,0,10),(1,20),(-1,1,-1,1),-10),(1.,20.))

    def test_near_plane_expands_only_when_all_corners_in_front(self):
        near,far=camera.expand_clip_for_grid((0,0,10),(0,0,0),(5,20),(-2,2,-2,2),0)
        self.assertLessEqual(near,5)
        self.assertGreater(far,near)

    def test_invalid_bounds_and_camera_rejected(self):
        with self.assertRaises(ValueError):
            camera.expand_clip_for_grid((0,0,5),(0,0,0),(1,20),(10,-10,-2,2),0)
        with self.assertRaises(ValueError):
            camera.expand_clip_for_grid((0,0,5),(0,0,0),(1,20),(-2,2,-2,2),math.nan)

    def test_fit_bounds_enclose_model_and_exact_grid(self):
        model=(100,200,0,102,202,180)
        box=camera.scene_grid_bounds(model,-0.75)
        self.assertLessEqual(box[0],model[0])
        self.assertLessEqual(box[1],model[1])
        self.assertLessEqual(box[2],-.75)
        self.assertGreaterEqual(box[3],model[3])
        self.assertGreaterEqual(box[4],model[4])
        self.assertGreaterEqual(box[5],model[5])

    def test_fit_zoom_adapts_to_narrow_viewports(self):
        self.assertGreater(camera.fit_grid_zoom(1400,750),
                           camera.fit_grid_zoom(260,700))
        for shape in ((640,480),(1400,800),(160,700),(1000,1000)):
            self.assertTrue(0 < camera.fit_grid_zoom(*shape) <= 1)


class SourceWiringTests(unittest.TestCase):
    def test_viewport_extends_clip_before_projection_without_changing_export(self):
        s=(PKG/'gl_viewport.py').read_text(encoding='utf-8-sig')
        ast.parse(s)
        self.assertIn('expand_clip_for_grid(',s)
        self.assertIn('def fit_perspective_grid(self):',s)
        self.assertLess(s.index('near, far = expand_clip_for_grid('),
                        s.index('projection.perspective(45.'))
        self.assertIn('self._world_grid.draw(',s)

    def test_fit_action_is_explicit_and_available_in_grid_menu(self):
        s=(PKG/'main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(s)
        self.assertIn("self.preview_fit_grid_action = self.preview_grid_menu.addAction('Fit Perspective Grid')",s)
        self.assertIn('def _fit_perspective_grid(self):',s)
        self.assertIn('self.preview_surface.fit_perspective_grid()',s)


if __name__ == '__main__':
    unittest.main()
