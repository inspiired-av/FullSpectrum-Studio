"""Focused regression checks for intended-dimensions dialog and warning copy."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
from desktop.qt_app.preview_scale_check import scale_warning
from tools.run_qt_tests_quiet import expected_offscreen_warning

ROOT = Path(__file__).resolve().parents[1]


class DimensionWarningCopyTests(unittest.TestCase):
    def test_small_obj_guides_to_exact_menu_action(self):
        notice = scale_warning((0, 0, 0, 0.293, 0.479, 0.331), 'hair.OBJ')
        self.assertIn('Unusually small model', notice)
        self.assertIn('File → Set Intended Dimensions', notice)
        self.assertIn('millimeters', notice)
        self.assertIn('original OBJ', notice)

    def test_normal_obj_does_not_gain_false_instruction(self):
        self.assertEqual(scale_warning((0, 0, 0, 200, 100, 120), 'head.obj'), '')

    def test_glb_advisory_does_not_offer_obj_only_command(self):
        notice = scale_warning((0, 0, 0, .5, .6, .7), 'mesh.glb')
        self.assertIn('meters', notice)
        self.assertNotIn('Set Intended Dimensions', notice)


class DialogResultAndQtMessageTests(unittest.TestCase):
    def test_dialog_does_not_shadow_inherited_result_method(self):
        src = (ROOT / 'desktop/qt_app/model_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertNotIn('self.result = QLabel()', src)
        self.assertIn('self.result_label = QLabel()', src)
        self.assertIn('self.result_label.setText(', src)

    def test_only_headless_known_messages_filtered(self):
        for message in ('This plugin does not support createPlatformOpenGLContext!',
                        'QOpenGLWidget: Failed to create context',
                        'QOpenGLWidget is not supported on this platform.'):
            self.assertTrue(expected_offscreen_warning(message, 'offscreen'))
            self.assertTrue(expected_offscreen_warning(message, 'minimal'))
            self.assertFalse(expected_offscreen_warning(message, 'windows'))
        for message in ('QBackingStore::endPaint() called with active painter',
                        'QOpenGLWidget: Failed to create context: GPU hardware unavailable',
                        'libshiboken: Internal C++ object already deleted'):
            self.assertFalse(expected_offscreen_warning(message, 'offscreen'))


if __name__ == '__main__':
    unittest.main()
