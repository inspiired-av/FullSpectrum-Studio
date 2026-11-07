"""Stage 6A3-D: exact perspective grid scale, safe overlays, persistence.

Headless tests do not import PySide6; optional Qt checks run on Windows.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'desktop' / 'qt_app'


def load_local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


measurements = load_local('stage6a3d_measurements', PKG / 'preview_grid_measurements.py')
policy = load_local('stage6a3d_policy', PKG / 'preview_grid_policy.py')
geometry = load_local('stage6a3d_geometry', PKG / 'preview_grid_geometry.py')


class PerspectiveMeasurementTests(unittest.TestCase):
    def test_actual_step_is_displayed_in_millimeters(self):
        for span in (0.25, 4, 80, 1000, 80000):
            vertices, step = geometry.world_grid_vertices((0, 0, 0, span, span, span), -0.75)
            self.assertEqual(measurements.grid_spacing_label(step),
                             'Grid cell: ' + measurements.format_millimeters(step) + ' × ' +
                             measurements.format_millimeters(step) + ' mm')
            self.assertEqual(len(vertices) % 14, 0)

    def test_axis_ticks_align_to_fifth_actual_minor_line(self):
        vertices, step = geometry.world_grid_vertices((-17, -12, -4, 22, 25, 19), -4.75)
        x0, x1, y0, y1 = measurements.grid_xy_limits(vertices)
        for lower, upper in ((x0, x1), (y0, y1)):
            ticks = measurements.major_ticks(lower, upper, step)
            self.assertTrue(ticks)
            for number in ticks:
                self.assertGreaterEqual(number, lower - 1e-4)
                self.assertLessEqual(number, upper + 1e-4)
                self.assertAlmostEqual(number/(step*5), round(number/(step*5)), places=6)

    def test_small_grid_and_off_origin_grid(self):
        for bounds in ((0, 0, 0, 2, 1, 0.1), (900, -100, 0, 1000, 0, 70)):
            vertices, step = geometry.world_grid_vertices(bounds, -0.2)
            limits = measurements.grid_xy_limits(vertices)
            self.assertLess(limits[0], limits[1]); self.assertLess(limits[2], limits[3])
            self.assertGreater(step, 0)

    def test_formatting_positive_negative_fractional(self):
        self.assertEqual(measurements.format_millimeters(0), '0')
        self.assertEqual(measurements.format_millimeters(-0.), '0')
        self.assertEqual(measurements.format_millimeters(0.05), '0.05')
        self.assertEqual(measurements.format_millimeters(100), '100')
        self.assertEqual(measurements.format_millimeters(-50), '-50')
        with self.assertRaises(ValueError):
            measurements.grid_spacing_label(0)

    def test_forecast_popup_lower_right_does_not_overlap_badge(self):
        # Screenshot-style layout: bottom-right 268x123 forecast countdown.
        width, height = 980, 520
        toast = (width-284, height-139, 268, 123)
        rect = measurements.choose_badge_rect(width, height, 125, 30, [toast])
        self.assertIsNotNone(rect)
        self.assertFalse(measurements.intersects(rect, toast, 7))
        self.assertEqual(rect[:2], (width-137, 12))

    def test_badge_moves_if_another_overlay_occupies_upper_right(self):
        upper_right = (810, 0, 180, 90)
        toast = (706, 381, 268, 123)
        badge = measurements.choose_badge_rect(990, 520, 140, 30, [upper_right, toast])
        self.assertIsNotNone(badge)
        self.assertFalse(any(measurements.intersects(badge, obstacle, 7)
                             for obstacle in (upper_right, toast)))

    def test_badge_hides_instead_of_overlapping_when_small(self):
        self.assertIsNone(measurements.choose_badge_rect(100, 30, 125, 32))
        all_positions = [(0, 0, 400, 300)]
        self.assertIsNone(measurements.choose_badge_rect(400, 300, 130, 30, all_positions))

    def test_preferences_upgrade_from_stage6a3(self):
        old = {'mode': 'automatic', 'last_mode': 'automatic', 'axes': True}
        new = policy.normalize_settings(old)
        self.assertTrue(new['measurements'])
        self.assertEqual(new['mode'], old['mode'])
        self.assertEqual(policy.normalize_settings(dict(new, measurements=False))['measurements'], False)
        with TemporaryDirectory() as tmp:
            file = Path(tmp)/'preview_grid.json'
            policy.write_grid_settings(file, dict(new, measurements=False))
            self.assertFalse(policy.read_grid_settings(file)['measurements'])
            self.assertEqual(policy.read_grid_settings(file)['mode'], 'automatic')

    def test_plate_grid_policy_is_not_changed_by_measurement_option(self):
        for mode in policy.GRID_MODES:
            for plate in (False, True):
                expected = policy.choose_grid_layers(mode, plate_visible=plate, plate_has_art=True)
                for opt in (False, True):
                    settings = policy.normalize_settings({'mode': mode, 'measurements': opt})
                    actual = policy.choose_grid_layers(settings['mode'], plate_visible=plate,
                                                       plate_has_art=True)
                    self.assertEqual(actual, expected)

    def test_grid_metadata_still_bounded(self):
        with self.assertRaises(ValueError):
            measurements.grid_xy_limits([])
        with self.assertRaises(ValueError):
            measurements.major_ticks(0, 5, 0)
        with self.assertRaises(ValueError):
            measurements.major_ticks(20, 5, 1)


class MeasurementSourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (PKG/'main_window.py').read_text(encoding='utf-8-sig')
        cls.view = (PKG/'gl_viewport.py').read_text(encoding='utf-8-sig')
        cls.grid = (PKG/'preview_grid_gl.py').read_text(encoding='utf-8-sig')
        cls.plate = (PKG/'plate_gl.py').read_text(encoding='utf-8-sig')
        cls.overlay = (PKG/'preview_grid_measurement_overlay.py').read_text(encoding='utf-8-sig')
        for name, code in [('main', cls.main), ('view', cls.view), ('grid', cls.grid),
                           ('plate', cls.plate), ('overlay', cls.overlay)]:
            ast.parse(code, filename=name)

    def test_render_measurements_only_after_world_grid_success(self):
        viewport = self.view[self.view.index('            if show_world_grid and not self._grid_failed:'):
                             self.view.index("        except Exception as exc:\n            self._error='Unable to render model:")]
        self.assertIn('self._world_grid.draw(gl, mvp, self._mesh.bounds, floor_z)', viewport)
        self.assertIn('self._grid_measurements.set_scene(', viewport)
        self.assertIn('self._grid_measurements.clear_scene()', viewport)
        self.assertIn('else:', viewport)

    def test_plate_grid_shader_and_spacing_left_untouched(self):
        self.assertIn('vLocalPosition.xy / 10.0', self.plate)
        self.assertIn('vLocalPosition.xy / 50.0', self.plate)
        self.assertNotIn('grid_measurements', self.plate)
        self.assertNotIn('grid_step', self.plate)

    def test_ui_persistence_only_perspective(self):
        self.assertIn('Show perspective grid measurements', self.main)
        self.assertIn('self._grid_settings[\'measurements\']', self.main)
        self.assertIn("self.preview_measurements_action.setEnabled(", self.main)
        self.assertIn('PerspectiveGridMeasurementOverlay(self)', self.view)
        self.assertIn('self._grid_measurements.clear_scene()', self.view)
        self.assertIn("'forecastCountdownOverlay'", self.overlay)
        self.assertIn('WA_TransparentForMouseEvents', self.overlay)
        self.assertIn('grid_xy_limits(data)', self.grid)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Needs PySide6')
class MeasurementQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_overlay_avoids_visible_forecast(self):
        from PySide6.QtGui import QMatrix4x4
        from PySide6.QtWidgets import QFrame, QWidget
        from desktop.qt_app.preview_grid_measurement_overlay import PerspectiveGridMeasurementOverlay
        parent = QWidget()
        parent.resize(750, 360)
        parent.show()
        toast = QFrame(parent)
        toast.setObjectName('forecastCountdownOverlay')
        toast.setGeometry(466, 221, 268, 123)
        toast.show()
        overlay = PerspectiveGridMeasurementOverlay(parent)
        overlay.set_scene(QMatrix4x4(), 10, (-50, 50, -50, 50), -1)
        occupied = overlay._occupied_rects()
        self.assertTrue(any(rect[2:] == (268, 123) for rect in occupied))
        badge = measurements.choose_badge_rect(750, 360, 125, 30, occupied)
        self.assertFalse(measurements.intersects(badge, (466, 221, 268, 123), gap=7))
        overlay.close(); toast.close(); parent.close()


if __name__ == '__main__':
    unittest.main()
