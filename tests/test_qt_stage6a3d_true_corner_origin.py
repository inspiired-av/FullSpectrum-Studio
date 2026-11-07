"""Pure geometry/regression checks for the actual shared ruler at the grid corner.

No Qt or graphics context required. This must use the grid's *generated* lines
and the same ruler anchors that the OpenGL viewport receives.
"""
from __future__ import annotations

import math
import unittest

from desktop.qt_app.preview_grid_geometry import world_grid_vertices
from desktop.qt_app.preview_grid_measurements import grid_xy_limits
from desktop.qt_app.preview_grid_ruler_gl import ruler_anchors

GREEN = (0.26, 0.60, 0.35, 0.75)
RED = (0.83, 0.32, 0.32, 0.75)


def lines(data):
    return ((data[i:i + 7], data[i + 7:i + 14]) for i in range(0, len(data), 14))


class TrueCornerOriginTests(unittest.TestCase):
    def inspect(self, bounds, *, intervals=60):
        floor = bounds[2] - 0.5
        verts, step = world_grid_vertices(bounds, floor, max_intervals=intervals)
        x0, x1, y0, y1 = grid_xy_limits(verts)
        anchors = ruler_anchors(step, (x0, x1, y0, y1), floor)
        origins = [p for role, label, p in anchors if role == 'O' and label == '0']
        self.assertEqual(len(origins), 1, f'Missing/duplicate origin: {anchors}')
        ox, oy = origins[0][:2]
        self.assertAlmostEqual(ox, x0, delta=step * 1e-4)
        self.assertAlmostEqual(oy, y0, delta=step * 1e-4)
        # The green Y ruler is the first X grid line, the red X ruler the
        # first Y grid line. Neither highlighted line is allowed internally.
        green, red = [], []
        for start, end in lines(verts):
            tint = tuple(float(c) for c in start[3:7])
            if all(abs(a - b) < 1e-5 for a, b in zip(tint, GREEN)):
                green.append((float(start[0]), float(end[0])))
            if all(abs(a - b) < 1e-5 for a, b in zip(tint, RED)):
                red.append((float(start[1]), float(end[1])))
        self.assertEqual(len(green), 1)
        self.assertEqual(len(red), 1)
        for x, end_x in green:
            self.assertAlmostEqual(x, x0, delta=step * 1e-4)
            self.assertAlmostEqual(end_x, x0, delta=step * 1e-4)
        for y, end_y in red:
            self.assertAlmostEqual(y, y0, delta=step * 1e-4)
            self.assertAlmostEqual(end_y, y0, delta=step * 1e-4)
        # Every side ends on a major grid line, not a minor line behind the ruler.
        for n in (x0, x1, y0, y1):
            self.assertAlmostEqual(n / (5 * step), round(n / (5 * step)), delta=2e-4)
        self.assertEqual(len(verts) % 14, 0)
        self.assertLessEqual(len(verts) // 14, 2 * (intervals + 9))
        self.assertTrue(all(math.isfinite(v) for v in verts))
        return step, (x0, x1, y0, y1), anchors

    def test_large_flat_model_corner_is_exact_ruler_zero(self):
        self.inspect((0, 0, 0, 600, 800, 2))

    def test_tall_narrow_model_corner_is_exact_ruler_zero(self):
        self.inspect((0, 0, 0, 3, 4, 120))

    def test_small_and_negative_world_space_values(self):
        self.inspect((-0.034, -0.01, 0, 0.067, 0.026, 0.15))
        self.inspect((-120, -180, 0, -85, -140, 20))

    def test_off_origin_model_does_not_move(self):
        bounds = (1000, -400, -10, 1080, -310, 25)
        _step, (x0, x1, y0, y1), labels = self.inspect(bounds)
        # Grid remains a display-only margin around the original model.
        self.assertLessEqual(x0, bounds[0]); self.assertGreaterEqual(x1, bounds[3])
        self.assertLessEqual(y0, bounds[1]); self.assertGreaterEqual(y1, bounds[4])
        self.assertNotEqual((x0, y0), (0., 0.))
        self.assertEqual(sum(text == '0' for _, text, _ in labels), 1)

    def test_small_requested_budget_stays_bounded(self):
        self.inspect((0, 0, 0, 100, 100, 100), intervals=8)

    def test_non_corner_line_does_not_get_zero(self):
        _, (_, _, _, _), anchors = self.inspect((1, 7, 2, 33, 48, 55))
        self.assertEqual(sum(role == 'O' for role, _, _ in anchors), 1)
        for role, text, _ in anchors:
            if role in ('X', 'Y'):
                self.assertNotEqual(text, '0')


if __name__ == '__main__':
    unittest.main()
