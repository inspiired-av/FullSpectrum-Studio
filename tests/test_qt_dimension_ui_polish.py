"""Dimension dialog readability + visible path back to physical-size adjustment."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DimensionPolishSourceTests(unittest.TestCase):
    def test_manual_and_auto_dialogs_share_structured_cards(self):
        manual = (ROOT/'desktop/qt_app/model_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        auto = (ROOT/'desktop/qt_app/model_auto_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        ast.parse(manual)
        ast.parse(auto)
        for element in ('dimensionsSourceCard', 'dimensionsTargetCard',
                        'dimensionsResultCard', 'dimensionsUnitWarning'):
            self.assertIn(element,manual)
        self.assertIn('self.heading.setText',auto)
        self.assertIn('self.intro.setText',auto)
        self.assertNotIn('self.result = QLabel()',manual)
        self.assertIn('self.result_label.setText(',manual)
        self.assertIn("self.remember.setChecked(False)", auto)

    def test_colors_have_semantic_roles_and_source_is_unmodified(self):
        source = (ROOT/'desktop/qt_app/model_dimensions_dialog.py').read_text(encoding='utf-8-sig')
        self.assertIn('color: #eac17b',source)  # unit warning
        self.assertIn('color: #83dfd4',source)  # confirmed dimensions
        self.assertIn('color: #77bdd1',source)  # section titles
        self.assertIn('the original obj stays unchanged',source.lower())

    def test_adjustment_action_is_connected_and_not_a_camera_zoom(self):
        src=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(src)
        self.assertIn("self.preview_adjust_dimensions = QPushButton('Adjust Dimensions…')",src)
        self.assertIn('self.preview_adjust_dimensions.clicked.connect(self._set_intended_dimensions)',src)
        self.assertIn('self.preview_adjust_dimensions.show()',src)
        self.assertIn('self.preview_adjust_dimensions.hide()',src)
        self.assertIn('source_dimensions(self._unscaled_bounds)',src)
        self.assertIn('Original OBJ unchanged',src)
        self.assertIn('Physical size in mm not specified',src)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class DimensionPolishQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_manual_preserves_axis_scale_and_reset(self):
        from PySide6.QtWidgets import QFrame
        from desktop.qt_app.model_dimensions_dialog import IntendedDimensionsDialog
        dialog=IntendedDimensionsDialog((0,0,0,1,2,3),current_factor=10)
        self.assertIsNotNone(dialog.findChild(QFrame,'dimensionsSourceCard'))
        self.assertIsNotNone(dialog.findChild(QFrame,'dimensionsResultCard'))
        self.assertAlmostEqual(dialog.scale_factor,10)
        self.assertIn('30.00',dialog.result_label.text())
        dialog.axis.setCurrentIndex(0)
        self.assertAlmostEqual(dialog.target.value(),10)
        self.assertAlmostEqual(dialog.scale_factor,10)
        dialog.target.setValue(200)
        self.assertAlmostEqual(dialog.scale_factor,200)
        self.assertIn('Uniform scale',dialog.scale_note.text())
        dialog.reset.click()
        self.assertTrue(dialog.reset_requested)
        self.assertEqual(dialog.result(),dialog.DialogCode.Accepted)
        dialog.close()

    def test_auto_requires_explicit_edit_and_has_clear_skip(self):
        from PySide6.QtWidgets import QDialogButtonBox
        from desktop.qt_app.model_auto_dimensions_dialog import AutoIntendedDimensionsDialog
        dialog=AutoIntendedDimensionsDialog((0,0,0,.293,.479,.331))
        self.assertIn('CHECK MODEL',dialog.heading.text())
        self.assertFalse(dialog.remember_choice)
        ok=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel=dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.assertEqual(cancel.text(),'Skip')
        self.assertFalse(ok.isEnabled())
        self.assertIn('Enter a physical dimension',dialog.result_label.text())
        dialog.axis.setCurrentIndex(0)
        self.assertFalse(ok.isEnabled())
        self.assertIn('Enter a physical dimension',dialog.result_label.text())
        dialog.target.setValue(100)
        self.assertTrue(ok.isEnabled())
        self.assertIn('100.00',dialog.result_label.text())
        dialog.remember.setChecked(True)
        self.assertTrue(dialog.remember_choice)
        dialog.close()


if __name__ == '__main__':
    unittest.main()
