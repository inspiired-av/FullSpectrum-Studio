"""Precision-only dialog patch. No source/output rescaling changes."""
from __future__ import annotations

import ast
import importlib.util
import math
import os
from pathlib import Path
import unittest

from desktop.qt_app.dimension_precision import (
    INPUT_DECIMALS,
    compact_input_value,
    display_result_mm,
    display_scale_factor,
    display_source_extent,
)
from desktop.qt_app.model_intended_dimensions import scaled_dimensions, uniform_scale

ROOT = Path(__file__).resolve().parents[1]


class PrecisionFormattingTests(unittest.TestCase):
    def test_source_and_result_display_are_compact(self):
        self.assertEqual(display_source_extent(.293009), '0.2930')
        self.assertEqual(display_source_extent(.479456), '0.4795')
        self.assertEqual(display_result_mm(91.6689823), '91.67')
        self.assertEqual(display_result_mm(150.0), '150.00')
        self.assertEqual(display_scale_factor(312.851233), '312.85')

    def test_tiny_nonzero_values_do_not_display_as_zero(self):
        self.assertNotEqual(display_source_extent(.0000036), '0.0000')
        self.assertNotEqual(display_result_mm(.00125), '0.00')
        self.assertNotEqual(display_scale_factor(.00001234), '0.00')
        self.assertEqual(display_result_mm(0), '0.00')

    def test_eight_decimal_input_without_excess_zeros(self):
        self.assertEqual(INPUT_DECIMALS, 8)
        self.assertEqual(compact_input_value(150), '150')
        self.assertEqual(compact_input_value(150.12), '150.12')
        self.assertEqual(compact_input_value(150.12345678), '150.12345678')
        self.assertEqual(compact_input_value(.00123456), '0.00123456')
        self.assertEqual(compact_input_value(150.125, decimal_point=','), '150,125')

    def test_display_formatting_never_changes_geometry_scaling(self):
        bounds = (0, 0, 0, .293009, .479456, .331268)
        actual_value = 150.12345678
        factor = uniform_scale(bounds, 'Y', actual_value)
        size = scaled_dimensions(bounds, factor)
        self.assertAlmostEqual(size[1], actual_value, places=7)
        self.assertNotEqual(size[0], float(display_result_mm(size[0])))
        self.assertNotEqual(factor, float(display_scale_factor(factor)))

    def test_dialog_is_only_presentation_change(self):
        source = (ROOT/'desktop/qt_app/model_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        auto = (ROOT/'desktop/qt_app/model_auto_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        ast.parse(source)
        ast.parse(auto)
        self.assertIn('self.target.setDecimals(INPUT_DECIMALS)', source)
        self.assertIn('compact_input_value(', source)
        self.assertIn('display_source_extent(extent)', source)
        self.assertIn('display_result_mm(d)', source)
        self.assertIn('display_scale_factor(factor)', source)
        self.assertIn('self.target.value())', source) # no display-string feedback into scale
        self.assertIn('self.remember = QCheckBox("Don\'t show again for this model")', auto)
        self.assertIn('self.remember.setChecked(False)', auto)
        self.assertIn('self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(\'Skip\')',auto)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class DimensionPrecisionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_exact_input_and_compact_labels(self):
        from desktop.qt_app.model_dimensions_dialog import IntendedDimensionsDialog
        dialog = IntendedDimensionsDialog((0, 0, 0, .293009, .479456, .331268))
        self.assertEqual(dialog.target.decimals(), 8)
        self.assertEqual(dialog.source_axis_values[0].text(), '0.2930')
        self.assertTrue(dialog.target.text().endswith(' mm'))
        self.assertNotIn('00000000 mm', dialog.target.text())
        dialog.target.setValue(150.12345678)
        self.assertEqual(dialog.target.text(), '150.12345678 mm')
        chosen_axis = dialog.axis.currentData()
        self.assertAlmostEqual(dialog.scale_factor,
                               150.12345678 / { 'X': .293009, 'Y': .479456, 'Z': .331268 }[chosen_axis],
                               places=7)
        self.assertIn(' mm', dialog.result_label.text())
        dialog.close()

    def test_auto_dialog_keeps_skip_remember_and_apply_contract(self):
        from PySide6.QtWidgets import QDialogButtonBox
        from desktop.qt_app.model_auto_dimensions_dialog import AutoIntendedDimensionsDialog
        dialog = AutoIntendedDimensionsDialog((0, 0, 0, .293009, .479456, .331268))
        ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(ok.isEnabled())
        self.assertEqual(dialog.remember.text(), "Don't show again for this model")
        dialog.target.setValue(150.12345678)
        self.assertTrue(ok.isEnabled())
        self.assertEqual(dialog.target.text(), '150.12345678 mm')
        self.assertTrue(dialog.result_label.text().endswith(' mm'))
        dialog.close()


if __name__ == '__main__':
    unittest.main()
