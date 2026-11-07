"""Fast regressions for Stage 6A3-D projection and safe Qt overlay painting."""
from __future__ import annotations

import ast
from contextlib import redirect_stderr
import importlib.util
from io import StringIO
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'desktop' / 'qt_app'


def import_helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


h = import_helper('measurements_runtime', SRC/'preview_grid_measurements.py')


class HomogeneousProjectionTests(unittest.TestCase):
    IDENTITY = (1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)

    def test_identity_maps_origin_to_screen_center(self):
        self.assertEqual(h.project_grid_point(self.IDENTITY,0,0,0,400,300),(200,150))
        self.assertEqual(h.project_grid_point(self.IDENTITY,1,-1,0,400,300),(400,300))

    def test_row_major_translation_and_scale(self):
        matrix = (0.5,0,0,0.25, 0,0.5,0,-0.5, 0,0,1,0, 0,0,0,1)
        self.assertEqual(h.project_grid_point(matrix,0,0,0,400,200),(250,150))
        self.assertEqual(h.project_grid_point(matrix,1,1,0,400,200),(350,100))

    def test_perspective_divides_by_w(self):
        matrix = (1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,1,2)
        self.assertEqual(h.project_grid_point(matrix,1,0,0,400,200),(300,100))
        self.assertIsNone(h.project_grid_point(matrix,0,0,-3,400,200))

    def test_clips_offscreen_points_and_invalid_matrix(self):
        self.assertIsNone(h.project_grid_point(self.IDENTITY,10,0,0,400,200))
        self.assertIsNone(h.project_grid_point(self.IDENTITY,0,0,2,400,200))
        self.assertIsNone(h.project_grid_point(self.IDENTITY,0,0,0,0,200))
        self.assertIsNone(h.project_grid_point(None,0,0,0,400,200))

    def test_grid_badge_describes_one_square(self):
        self.assertEqual(h.grid_spacing_label(10),'Grid cell: 10 × 10 mm')
        self.assertEqual(h.grid_spacing_label(.25),'Grid cell: 0.25 × 0.25 mm')

    def test_source_guards_qt_callbacks(self):
        src = (SRC/'preview_grid_measurement_overlay.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertIn("getattr(self, 'viewport', None)", src)
        self.assertIn('grid_spacing_label(self._step)', src)
        self.assertNotIn('def _axis_labels(', src)
        self.assertNotIn('QVector4D', src)
        self.assertIn('finally:', src)
        self.assertIn('painter.end()', src)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QtRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_badge_only_and_complete_paint(self):
        from PySide6.QtGui import QMatrix4x4
        from PySide6.QtWidgets import QWidget, QFrame
        from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
        root=QWidget()
        root.resize(780,430)
        root.show()
        forecast=QFrame(root)
        forecast.setObjectName('forecastCountdownOverlay')
        forecast.setGeometry(496,291,268,123)
        forecast.show()
        overlay=PerspectiveGridMeasurementOverlay(root)
        overlay.set_scene(QMatrix4x4(), .2, (-1,1,-1,1), 0)
        try:
            stderr=StringIO()
            with redirect_stderr(stderr):
                overlay.grab()
                self.app.processEvents()
            self.assertNotIn('Error calling Python override',stderr.getvalue())
            self.assertNotIn('QBackingStore::endPaint',stderr.getvalue())
        finally:
            overlay.close();forecast.close();root.close()

    def test_event_filter_survives_shutdown_state(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
        root=QWidget()
        widget=PerspectiveGridMeasurementOverlay(root)
        try:
            del widget.viewport
            self.assertFalse(widget.eventFilter(root,QEvent(QEvent.Type.Resize)))
        finally:
            widget.close();root.close()


if __name__=='__main__':
    unittest.main()
