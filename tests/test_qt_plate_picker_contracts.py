"""Verify the new plate controls and C++ object-safe deferred Qt callbacks."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlatePickerContractTests(unittest.TestCase):
    def test_toolbar_has_two_independent_uses(self):
        main = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(main)
        self.assertIn("self.plate_button = QPushButton('Build Plate')",main)
        self.assertIn("self.plate_button.clicked.connect(self._choose_plate)",main)
        self.assertIn("self.plate_visibility_button.clicked.connect(self._toggle_plate_visibility)",main)
        self.assertIn("self.plate_visibility_button.setIcon(plate_eye_icon(False))",main)
        self.assertNotIn("self.plate_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)",main)

    def test_defaults_live_in_picker_not_toolbar_menu(self):
        ui = (ROOT/'desktop/qt_app/plate_ui.py').read_text(encoding='utf-8-sig')
        ast.parse(ui)
        self.assertIn('self.plates = preferred_plate_assets(plates)',ui)
        self.assertIn('self.remember_default = QCheckBox(',ui)
        self.assertIn('self.forget_default_button = QPushButton(',ui)
        self.assertNotIn('self.source_filter = QComboBox()',ui)
        self.assertNotIn('Detected sources:',ui)

    def test_deferred_callbacks_are_parented_and_guarded(self):
        main = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        results = (ROOT/'desktop/qt_app/results_tab.py').read_text(encoding='utf-8-sig')
        for text in (main,results): ast.parse(text)
        self.assertIn('self._initial_filament_ui_timer = QTimer(self)',main)
        self.assertIn('self._initial_filament_ui_timer.stop()',main)
        self.assertIn('self._initial_export_layout_timer.stop()',main)
        self.assertIn('self._qt_disposing = True',main)
        self.assertIn('self._qt_widgets_alive(',main)
        self.assertIn('self._export_resize_timer = QTimer(self)',results)
        self.assertIn('self._export_resize_timer.start(0)',results)
        self.assertIn('self._export_resize_timer.stop()',results)

if __name__ == '__main__':
    unittest.main()
