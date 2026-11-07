"""Stage 6A3-D follow-up: perspective-grid tick occlusion and edge selection.

Fast math tests are independent of Qt and graphics hardware; optional Qt
integration checks exercise actual overlay label placement on Windows.
"""
from __future__ import annotations

import ast
import importlib.util
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'desktop'/'qt_app'

spec=importlib.util.spec_from_file_location('a3d_label_helpers', PACKAGE/'preview_grid_measurements.py')
helpers=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

IDENTITY=(1.,0,0,0, 0,1.,0,0, 0,0,1.,0, 0,0,0,1.)


class ModelSilhouetteTests(unittest.TestCase):
    def test_projected_bounds_excludes_numbers_over_geometry(self):
        bounds=(-.4,-.2,-.1, .4,.2,.1)
        rect=helpers.projected_model_bounds(IDENTITY,bounds,800,600,margin=0)
        self.assertAlmostEqual(rect[0],240)
        self.assertAlmostEqual(rect[1],240)
        self.assertAlmostEqual(rect[2],320)
        self.assertAlmostEqual(rect[3],120)
        self.assertTrue(helpers.intersects(rect,(390,280,24,20)))
        self.assertFalse(helpers.intersects(rect,(60,70,24,20)))

    def test_partial_offscreen_model_still_blocks_labels(self):
        bounds=(.75,-.5,-.2,1.5,.5,.2)
        rect=helpers.projected_model_bounds(IDENTITY,bounds,1000,600)
        # Unclipped x coordinate extends beyond the viewport.
        self.assertGreater(rect[0]+rect[2],1000)
        self.assertTrue(helpers.intersects(rect,(915,270,48,18)))

    def test_closeup_camera_near_plane_is_conservative(self):
        # Unsafe near-plane/projection cases should not allow foreground labels.
        bounds=(-.2,-.2,-2,.2,.2,.1)
        self.assertEqual(helpers.projected_model_bounds(IDENTITY,bounds,800,600),
                         (0,0,800,600))

    def test_invalid_geometry_and_model_absence(self):
        self.assertIsNone(helpers.projected_model_bounds(IDENTITY,None,800,600))
        self.assertEqual(helpers.projected_model_bounds(IDENTITY,(2,0,0,1,1,1),800,600),
                         (0,0,800,600))
        self.assertEqual(helpers.projected_model_bounds(IDENTITY,(float('nan'),0,0,1,1,1),800,600),
                         (0,0,800,600))

    def test_projection_is_not_independently_rescaled(self):
        model=helpers.projected_model_bounds(IDENTITY,(-.5,-.5,-.1,.5,.5,.1),1000,600)
        small=helpers.projected_model_bounds(IDENTITY,(-.5,-.5,-.1,.5,.5,.1),500,300)
        self.assertGreater(model[2],small[2]);self.assertGreater(model[3],small[3])


class LabelOverlayContracts(unittest.TestCase):
    def test_world_labels_use_depth_not_a_screen_space_silhouette(self):
        overlay=(PACKAGE/'preview_grid_measurement_overlay.py').read_text(encoding='utf-8-sig')
        ruler=(PACKAGE/'preview_grid_ruler_gl.py').read_text(encoding='utf-8-sig')
        ast.parse(overlay);ast.parse(ruler)
        self.assertNotIn('def _axis_labels(',overlay)
        self.assertIn('gl.glEnable(gl.GL_DEPTH_TEST)',ruler)
        self.assertIn('gl.glDepthMask(gl.GL_FALSE)',ruler)
        self.assertIn('clip.xy +=',ruler)
        self.assertIn('finally:',overlay)
        self.assertIn('painter.end()',overlay)
        self.assertIn("'forecastCountdownOverlay'",overlay)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class QtLabelRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_badge_renders_without_projecting_model_geometry(self):
        from PySide6.QtGui import QMatrix4x4
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
        parent=QWidget();parent.resize(900,600);parent.show()
        overlay=PerspectiveGridMeasurementOverlay(parent)
        overlay.set_scene(QMatrix4x4(), .1, (-.7,.7,-.7,.7), 0.)
        try:
            self.assertFalse(hasattr(overlay,'_axis_labels'))
            self.assertFalse(overlay.grab().isNull())
        finally:
            overlay.close();parent.close()


if __name__=='__main__':
    unittest.main()
