"""Regression checks for correct Windows camera handedness and front/back visibility."""
import math
import unittest

from desktop.windows_mesh_preview import _project, render_depth_image


class WindowsCameraOrientationTests(unittest.TestCase):
    def test_front_facing_model_is_not_horizontally_mirrored(self):
        # In a +Z-up 3MF model viewed from the -X side, +Y is screen-left.
        # The previous version put +Y screen-right, mirroring all lettering.
        locations = [(0.0, -1.0, 0.0), (0.0, +1.0, 0.0)]
        p0, p1 = _project(locations, 300, 300, -math.pi / 2, 0.0, 1.0)
        self.assertLess(p1[0], p0[0])

    def test_model_depth_along_camera_axis_is_preserved(self):
        # Flipping the projected horizontal axis must not reverse which
        # triangles are in front of other triangles.
        locations = [(-1.0, 0.0, 0.0), (+1.0, 0.0, 0.0)]
        front, back = _project(locations, 300, 300, -math.pi / 2, 0.0, 1.0)
        self.assertGreater(front[2], back[2])

    def test_protected_overlay_renders_only_when_requested(self):
        vertices = [(-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.0, 0.0, 0.5)]
        face = (0, 1, 2, (144, 152, 168), '#9098A8')
        original = render_depth_image(vertices, [face], 320, 320, yaw=0, pitch=0)
        protected = render_depth_image(vertices, [face], 320, 320, yaw=0, pitch=0,
                                       protected_colors={'#9098A8'})
        self.assertEqual(original.getpixel((160, 160)), (125, 132, 146))
        self.assertEqual(protected.getpixel((160, 160)), (45, 230, 215))


if __name__ == '__main__':
    unittest.main()
