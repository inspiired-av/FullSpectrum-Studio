"""Stage 6A3-D: grid-relative ruler ticks and visibility across camera angles.

Pure-Python tests run without Qt/OpenGL. Optional Qt test exercises the real
overlay and reproduces small-preview measurement placement.
"""
from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

PKG = Path(__file__).resolve().parents[1] / 'desktop' / 'qt_app'
spec = importlib.util.spec_from_file_location('grid_ruler_helpers', PKG / 'preview_grid_measurements.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def measure(text):
    return len(text) * 7, 13


class RulerLabelTests(unittest.TestCase):
    def test_cell_size_is_distinct_from_coordinate_distance(self):
        self.assertEqual(helpers.grid_spacing_label(10), 'Grid cell: 10 × 10 mm')
        values = helpers.grid_ruler_ticks(140, 260, 10)
        self.assertEqual(values, ((150, 0), (200, 50), (250, 100)))
        # World positions 150..250 are translated into a local 0..100 mm ruler.
        self.assertEqual([helpers.format_millimeters(d) for _, d in values],
                         ['0', '50', '100'])

    def test_both_grid_ends_considered_for_each_tick(self):
        # The upper boundary is clipped; the lower edge remains usable.
        def project(x,y,z):
            if y > 55:
                return None
            return (110 + 3*x, 430 - .4*x)
        rows = helpers.layout_grid_ruler_labels(10,(0,100,0,100),0,650,500,
                                                project,measure)
        self.assertGreaterEqual(sum(a == 'X' for a,_,_ in rows), 2)
        self.assertTrue(any(label == 'X 0' for _,label,_ in rows))

    def test_visible_tick_labels_survive_rotation(self):
        # Two distinct perspective orientations with the same measured grid.
        for angle in (.15, .8, 1.40, 2.25):
            with self.subTest(angle=angle):
                c, s = math.cos(angle), math.sin(angle)
                def project(x,y,z):
                    dx,dy=x-120,y-170
                    return (400 + c*dx*2 - s*dy*1.6,
                            285 + s*dx*.9 + c*dy*1.2)
                rows = helpers.layout_grid_ruler_labels(
                    10,(40,200,90,250),0,800,580,project,measure,
                    model_rect=(362,247,82,70))
                self.assertGreaterEqual(len(rows), 4)
                self.assertTrue(any(axis=='X' for axis,_,_ in rows))
                self.assertTrue(any(axis=='Y' for axis,_,_ in rows))
                boxes=[rect for _,_,rect in rows]
                self.assertTrue(all(not helpers.intersects(r, (362,247,82,70),5) for r in boxes))
                for i,a in enumerate(boxes):
                    self.assertTrue(all(not helpers.intersects(a,b,5) for b in boxes[i+1:]))

    def test_forecast_popup_and_badge_are_never_covered(self):
        def project(x,y,z):
            return (430 + 2*x, 300 + .6*y)
        blocked=((620,350,268,123),(740,10,145,34))
        rows=helpers.layout_grid_ruler_labels(10,(-100,100,-120,120),0,900,600,
                                               project,measure,blocked)
        self.assertTrue(rows)
        self.assertTrue(all(not any(helpers.intersects(rect,b,5) for b in blocked)
                            for _,_,rect in rows))

    def test_model_occludes_labels_but_not_distant_grid_edges(self):
        def project(x,y,z): return (450 + x*2.5,300 + y*2)
        box=(335,240,230,120)
        rows=helpers.layout_grid_ruler_labels(10,(-110,110,-90,90),0,900,600,
                                               project,measure,model_rect=box)
        self.assertGreater(len(rows),2)
        self.assertTrue(all(not helpers.intersects(rect,box,5) for _,_,rect in rows))

    def test_bad_geometry_returns_empty(self):
        for bounds in ((0,-1,0,1),(0,1,9,1),(float('nan'),1,0,1)):
            self.assertEqual(helpers.layout_grid_ruler_labels(
                10,bounds,0,100,100,lambda *args:(50,50),measure), ())

    def test_model_and_grid_unmodified_source_contract(self):
        overlay=(PKG/'preview_grid_measurement_overlay.py').read_text(encoding='utf-8-sig')
        ruler=(PKG/'preview_grid_ruler_gl.py').read_text(encoding='utf-8-sig')
        self.assertNotIn('layout_grid_ruler_labels(',overlay)
        self.assertNotIn('def _axis_labels(',overlay)
        self.assertIn('ruler_anchors(',ruler)
        self.assertIn('gl.glEnable(gl.GL_DEPTH_TEST)',ruler)
        self.assertIn('finally:',overlay)
        self.assertIn('painter.end()',overlay)
        self.assertIn("'forecastCountdownOverlay'",overlay)
        self.assertIn('grid_spacing_label(self._step)',overlay)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class RulerQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_badge_and_atlas_have_distinct_rendering_paths(self):
        from PySide6.QtWidgets import QWidget
        from PySide6.QtGui import QMatrix4x4
        from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
        from desktop.qt_app.preview_grid_ruler_gl import WorldGridRulerRenderer, ruler_anchors
        parent=QWidget();parent.resize(900,600);parent.show()
        overlay=PerspectiveGridMeasurementOverlay(parent)
        overlay.set_scene(QMatrix4x4(),10,(0,200,0,200),0)
        try:
            self.assertFalse(overlay.grab().isNull())
            items=ruler_anchors(10,(0,200,0,200),0)
            image,rects=WorldGridRulerRenderer._raster_atlas(items,1.0)
            self.assertFalse(image.isNull())
            self.assertEqual(len(rects),len(items))
        finally:
            overlay.close();parent.close()


if __name__ == '__main__':
    unittest.main()
