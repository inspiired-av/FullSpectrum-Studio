"""Stage 6A3-D: shared grid-relative ruler origin matches highlighted XY axes.

Pure tests; no Qt/OpenGL context required. The model's world coordinates are
not changed by the ruler/grid and no build-plate rendering is involved.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import math
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'desktop' / 'qt_app'


def read_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, PKG / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


geo = read_module('grid_origin_geo', 'preview_grid_geometry.py')
measure = read_module('grid_origin_measure', 'preview_grid_measurements.py')


class GridOriginAlignmentTests(unittest.TestCase):
    @staticmethod
    def axes(bounds):
        verts, step = geo.world_grid_vertices(bounds, bounds[2] - 0.75)
        limits = measure.grid_xy_limits(verts)
        xticks = measure.major_ticks(limits[0], limits[1], step)
        yticks = measure.major_ticks(limits[2], limits[3], step)
        green_x, red_y = [], []
        positions = []
        for i in range(0, len(verts), 14):
            start, end = verts[i:i+7], verts[i+7:i+14]
            positions.append((tuple(start[:3]), tuple(end[:3])))
            rgba = tuple(start[3:7])
            if all(abs(rgba[j] - v) < 1.e-5
                   for j, v in enumerate((0.26, 0.60, 0.35, 0.75))):
                green_x.append(float(start[0]))
                assert abs(start[0] - end[0]) <= 1.e-5 * step
            if all(abs(rgba[j] - v) < 1.e-5
                   for j, v in enumerate((0.83, 0.32, 0.32, 0.75))):
                red_y.append(float(start[1]))
                assert abs(start[1] - end[1]) <= 1.e-5 * step
        return step, verts, limits, xticks, yticks, green_x, red_y, positions

    def test_shared_origin_colored_axes_match_ruler_zero(self):
        bounds_cases = (
            (0, 0, 0, 4, 3, 120),
            (-32, 50, -5, 121, 187, 96),
            (100, -50, 0, 120, -30, 20),
            (-1, -1, -1, 1, 1, 1),
            (0.15, 0.3, 0, 0.17, 0.32, 0.02),
        )
        for bounds in bounds_cases:
            with self.subTest(bounds=bounds):
                step, _, limits, xticks, yticks, green, red, _ = self.axes(bounds)
                self.assertTrue(xticks)
                self.assertTrue(yticks)
                self.assertEqual(len(green), 1)
                self.assertEqual(len(red), 1)
                self.assertAlmostEqual(green[0], xticks[0], delta=step*1.e-5)
                self.assertAlmostEqual(red[0], yticks[0], delta=step*1.e-5)

    def test_world_origin_does_not_create_second_highlight(self):
        bounds = (1000, 400, 0, 1040, 440, 100)
        step, _, _, xticks, yticks, green, red, _ = self.axes(bounds)
        self.assertNotEqual(green[0], 0)
        self.assertNotEqual(red[0], 0)
        self.assertAlmostEqual(green[0], xticks[0], delta=step*1.e-5)
        self.assertAlmostEqual(red[0], yticks[0], delta=step*1.e-5)

    def test_float32_edge_rounding_does_not_skip_first_major_tick(self):
        # Regression: a float32 edge may be 0.40000000596, not exactly 0.4.
        self.assertAlmostEqual(measure.major_ticks(0.4000000059604645,
                              0.6399999856948853, 0.02)[0], 0.4)
        self.assertAlmostEqual(measure.major_ticks(-0.05999999865889549,
                              -0.035999998450279236, 0.002)[0], -0.06)

    def test_grid_geometry_layout_is_unchanged_only_color_changes(self):
        verts, _ = geo.world_grid_vertices((0, 0, 0, 150, 75, 20), -0.75)
        self.assertEqual(len(verts) % 14, 0)
        self.assertTrue(all(math.isfinite(value) for value in verts))
        # The model and grid coordinates stay unmodified in the viewport.
        self.assertTrue(all(verts[i+2] == -0.75 for i in range(0, len(verts), 7)))

    def test_random_grid_centers_and_spacings_match_ruler_origin(self):
        r = random.Random(1363)
        for i in range(500):
            scale = 10 ** r.uniform(-3, 5)
            cx, cy = r.uniform(-8, 8)*scale, r.uniform(-8, 8)*scale
            bounds = (cx, cy, -scale*0.1,
                      cx+scale, cy+scale*0.8, scale*0.95)
            step, _, _, xticks, yticks, green, red, _ = self.axes(bounds)
            with self.subTest(i=i):
                self.assertEqual(len(green), 1)
                self.assertEqual(len(red), 1)
                self.assertAlmostEqual(green[0], xticks[0], delta=step*1.e-5)
                self.assertAlmostEqual(red[0], yticks[0], delta=step*1.e-5)


if __name__ == '__main__':
    unittest.main()
