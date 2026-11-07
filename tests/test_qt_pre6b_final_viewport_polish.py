"""Focused final viewport polish checks; no OpenGL context required.

From repo root:
  python -m unittest discover -s tests -p 'test_qt_pre6b_final_viewport_polish.py' -v
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

from desktop.qt_app.preview_axis_layout import axis_marker_position
from desktop.qt_app.preview_grid_ruler_gl import ruler_anchors

ROOT = Path(__file__).resolve().parents[1]


class AxisLayoutTests(unittest.TestCase):
    def test_empty_scene_uses_legacy_lower_left(self):
        self.assertEqual(axis_marker_position(1000, 600, 104, 104), (9, 487))

    def test_color_loss_legend_moves_marker_to_free_right_corner(self):
        self.assertEqual(axis_marker_position(
            1000, 600, 104, 104, [(12, 502, 382, 79)]), (887, 487))

    def test_anchor_legend_and_countdown_choose_upper_right(self):
        self.assertEqual(axis_marker_position(
            1000, 600, 104, 104,
            [(12, 392, 460, 196), (735, 419, 253, 169)]), (887, 9))

    def test_estimate_badge_keeps_upper_left_free_if_lower_corners_occupied(self):
        self.assertEqual(axis_marker_position(
            1000, 600, 104, 104,
            [(12, 392, 460, 196), (735, 419, 253, 169), (12, 12, 120, 30)]),
            (887, 9))

    def test_restores_lower_left_after_legend_goes_away(self):
        _ = axis_marker_position(1000, 600, 104, 104, [(12, 502, 382, 79)])
        self.assertEqual(axis_marker_position(1000, 600, 104, 104), (9, 487))

    def test_crowded_or_small_viewport_can_hide_marker(self):
        self.assertIsNone(axis_marker_position(105, 130, 104, 104))
        self.assertIsNone(axis_marker_position(
            1000, 600, 104, 104,
            [(0, 0, 500, 600), (500, 0, 500, 600)]))


class RulerDirectionTests(unittest.TestCase):
    def test_one_zero_and_axis_markers_in_first_major_interval(self):
        labels = ruler_anchors(10, (0, 200, 0, 200), 0)
        o = next(x for x in labels if x[0] == 'O')
        mx = next(x for x in labels if x[0] == 'MX')
        my = next(x for x in labels if x[0] == 'MY')
        self.assertEqual(o[1], '0')
        self.assertEqual(sum(v[0] == 'O' for v in labels), 1)
        self.assertAlmostEqual(mx[2][0], 20)
        self.assertAlmostEqual(mx[2][1], 0)
        self.assertAlmostEqual(my[2][0], 0)
        self.assertAlmostEqual(my[2][1], 20)
        self.assertEqual([x[1] for x in labels if x[0]=='X'][:2], ['50','100'])

    def test_ruler_offset_world_coordinates_still_grid_relative(self):
        labels = ruler_anchors(50, (250, 1250, -500, 500), 0)
        origin = next(x for x in labels if x[0] == 'O')[2]
        mx = next(x for x in labels if x[0] == 'MX')[2]
        my = next(x for x in labels if x[0] == 'MY')[2]
        self.assertAlmostEqual(mx[0] - origin[0], 100)
        self.assertAlmostEqual(my[1] - origin[1], 100)
        self.assertAlmostEqual(mx[1], origin[1])
        self.assertAlmostEqual(my[0], origin[0])


class IntegrationContracts(unittest.TestCase):
    def test_grid_button_hides_native_menu_indicator_only_locally(self):
        src = (ROOT / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertIn('QToolButton#previewGridMenuButton::menu-indicator',src)
        self.assertIn('image: none; width: 0px; height: 0px;',src)
        self.assertIn('self.preview_grid_menu_button.setMenu(self.preview_grid_menu)',src)
        self.assertIn('self.preview_surface._axis_indicator.refresh_obstacles()',src)

    def test_axis_position_follows_legend_show_hide_and_resize(self):
        src = (ROOT / 'desktop/qt_app/preview_axis_indicator.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        for v in ('colorLossLegend', 'anchorInfluenceLegend', 'forecastCountdownOverlay',
                  'QEvent.Type.Show', 'QEvent.Type.Hide', 'QEvent.Type.Resize'):
            self.assertIn(v, src)
        self.assertIn('axis_marker_position(', src)

    def test_viewport_refreshes_axis_marker_on_mesh_and_setting_changes(self):
        src = (ROOT / 'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertEqual(src.count('self._axis_indicator.refresh_obstacles()'), 2)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class RealQtAxisPositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_legend_show_hide_moves_axis_without_opengl(self):
        from PySide6.QtWidgets import QWidget, QFrame
        from desktop.qt_app.preview_axis_indicator import ViewAxisIndicator

        viewport = QWidget()
        viewport.resize(1000, 600)
        viewport.mesh = object()
        viewport._grid_show_axes = True
        viewport.yaw, viewport.pitch = 0., 0.
        axis = ViewAxisIndicator(viewport)
        legend = QFrame(viewport)
        legend.setObjectName('colorLossLegend')
        legend.setGeometry(12, 502, 382, 79)
        viewport.show()
        axis.refresh_obstacles()
        self.app.processEvents()
        legend.hide()
        self.app.processEvents()
        self.assertEqual((axis.x(), axis.y()), (9, 487))
        legend.show()
        self.app.processEvents()
        self.assertEqual((axis.x(), axis.y()), (887, 487))
        legend.hide()
        self.app.processEvents()
        self.assertEqual((axis.x(), axis.y()), (9, 487))
        viewport.close()
        viewport.deleteLater()
        self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
