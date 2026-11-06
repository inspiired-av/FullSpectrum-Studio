"""6A2-B follow-up: readable toolbar and truthful slicer source choices."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlateUxSourceContracts(unittest.TestCase):
    def test_toolbar_text_and_slicer_fallback_path(self):
        text = (ROOT / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        ast.parse(text)
        self.assertIn("self.plate_button = QPushButton('Build Plate')", text)
        self.assertIn("self.reset_camera_button.setIcon(preview_toolbar_icon('reset'))", text)
        self.assertIn("self.reset_camera_button.setAccessibleName('Reset camera')", text)
        self.assertIn('def _choose_plate_slicer_executable(self):', text)
        self.assertIn('slicer_executables=tuple(self._plate_custom_exes)', text)
        self.assertIn("self.plate_visibility_button.clicked.connect(self._toggle_plate_visibility)", text)
        self.assertIn('not self._plate_rescan_pending', text)

    def test_source_filter_and_discovery_worker_contract(self):
        text = (ROOT / 'desktop/qt_app/plate_ui.py').read_text(encoding='utf-8-sig')
        ast.parse(text)
        self.assertIn('preferred_plate_assets(plates)', text)
        self.assertIn('self.remember_default', text)
        self.assertIn('slicer_executables=self.slicer_executables', text)
        self.assertIn('asset.source', text)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class PlateUxSourceQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_shows_distinct_installed_source_filter(self):
        from desktop.qt_app.plate_catalog import PlateAsset
        from desktop.qt_app.plate_ui import PlatePickerDialog, PlateCatalogWorker
        from qt_test_cleanup import dispose_test_widget
        a = PlateAsset('Creality K1 Max', 'Creality', 'Bambu Studio',
                       Path('a.stl'), None, Path('a.json'), Path('.'))
        b = PlateAsset('Creality K1 Max', 'Creality', 'OrcaSlicer',
                       Path('b.stl'), None, Path('b.json'), Path('.'))
        dialog = PlatePickerDialog((a, b))
        self.addCleanup(dispose_test_widget, dialog)
        self.assertEqual(dialog.list.count(), 1)
        self.assertIn('OrcaSlicer', dialog.list.item(0).text())
        self.assertEqual(dialog.list.item(0).data(256), b)  # Qt.UserRole
        worker = PlateCatalogWorker(slicer_executables=(Path('OrcaSlicer.exe'),))
        self.addCleanup(worker.deleteLater)
        self.assertEqual(worker.slicer_executables, (Path('OrcaSlicer.exe'),))


if __name__ == '__main__':
    unittest.main()
