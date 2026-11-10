"""Regression tests for CMYK spool navigation, profile rename and source labels."""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIALOG = ROOT / 'desktop/qt_app/filament_library_dialog.py'
MAIN = ROOT / 'desktop/qt_app/main_window.py'
V9_TEST = ROOT / 'tests/test_qt_library_ui_polish_v9.py'


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dialog = DIALOG.read_text(encoding='utf-8-sig')
        cls.main = MAIN.read_text(encoding='utf-8-sig')
        tree = ast.parse(cls.dialog)
        cls.svg = next(node.value.value for node in tree.body
                       if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == '_ALL_FILAMENTS_SVG'
                               for t in node.targets))

    def test_valid_svg_spool_has_three_filenames_colors(self):
        root = ET.fromstring(self.svg)
        self.assertEqual(root.attrib['viewBox'], '0 0 24 24')
        fills = [n.get('fill') for n in root.iter()]
        for color in ('#00CFFF', '#FF2D95', '#F5D600'):
            self.assertIn(color, fills)
        self.assertGreaterEqual(len(root.findall('{http://www.w3.org/2000/svg}ellipse')), 3)

    def test_spool_is_embedded_not_file_dependent(self):
        self.assertIn('QSvgRenderer(QByteArray(_ALL_FILAMENTS_SVG.encode', self.dialog)
        self.assertIn('self.all_filaments_button.setIcon(_all_filaments_icon())', self.dialog)
        self.assertNotIn('file://', self.svg)

    def test_double_click_preserves_existing_rename_safeguards(self):
        self.assertIn('self.profiles.itemDoubleClicked.connect(self._rename_profile_from_double_click)', self.dialog)
        self.assertIn("if identity is None or identity != self._profile_identity:", self.dialog)
        self.assertIn('if self._profile_revision is None:', self.dialog)
        self.assertIn('if self._profile_dirty:', self.dialog)
        self.assertIn('self._rename_profile()', self.dialog)

    def test_left_aligned_headings_without_new_column_grid(self):
        self.assertIn('Qt.ItemDataRole.TextAlignmentRole', self.dialog)
        self.assertIn('Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter', self.dialog)
        self.assertIn('Qt.AlignmentFlag.AlignCenter if section == 0', self.dialog)
        self.assertIn('self.table.setShowGrid(False)', self.dialog)

    def test_source_labels_only_no_raw_key_changes(self):
        self.assertIn("raw.replace('_', ' ').title(), raw", self.dialog)
        self.assertIn("self.proxy.origin = self.sources.currentData() or 'All sources'", self.dialog)
        self.assertIn('widget is self.sources else widget.currentText()', self.dialog)

    def test_legacy_forecast_error_harness_graceful(self):
        self.assertIn("panel = getattr(self, 'filaments_panel', None)", self.main)
        self.assertIn("self._set_forecast_status('Forecast unavailable: ' + str(error), 'error')", self.main)
        self.assertIn("self._set_forecast_status('Forecast unavailable: ' + message, 'error')", self.main)

    def test_old_v9_icon_grid_assertion_is_replaced(self):
        code = V9_TEST.read_text(encoding='utf-8-sig')
        self.assertNotIn('test_svg_is_simple_crisp_four_tile_grid', code)
        self.assertIn('test_svg_is_a_small_size_cmyk_filament_spool', code)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.filament_library_dialog import FilamentLibraryDialog, _all_filaments_icon
    from desktop.qt_app import filament_library_store as store
except (OSError, ImportError):
    QApplication = None


@unittest.skipIf(QApplication is None, 'PySide6 unavailable')
class QtChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_icon_is_drawn_at_sidebar_size(self):
        icon = _all_filaments_icon()
        for size in (18, 24):
            pixmap = icon.pixmap(size, size)
            self.assertFalse(pixmap.isNull())
            image = pixmap.toImage()
            self.assertTrue(any(image.pixelColor(x,y).alpha() > 0
                                for y in range(image.height())
                                for x in range(image.width())))

    def test_sources_are_displayed_capitalized_with_raw_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, 'settings_path', return_value=Path(tmp)/'settings.json'):
                with patch('desktop.qt_app.filament_library_dialog.bambu_catalog_filaments', return_value=[]):
                    dialog = FilamentLibraryDialog()
                    try:
                        dialog.worker.wait()
                        self.app.processEvents()
                        for i in range(dialog.sources.count()):
                            key = dialog.sources.itemData(i)
                            if key not in ('All sources', None):
                                self.assertEqual(dialog.sources.itemText(i), str(key).replace('_',' ').title())
                    finally:
                        dialog.close()

    def test_double_click_uses_rename_only_for_editable_profile(self):
        from PySide6.QtWidgets import QListWidgetItem
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, 'settings_path', return_value=Path(tmp)/'settings.json'):
                with patch('desktop.qt_app.filament_library_dialog.bambu_catalog_filaments', return_value=[]):
                    dialog = FilamentLibraryDialog()
                    try:
                        item = QListWidgetItem('Saved Test')
                        item.setData(Qt.ItemDataRole.UserRole, 'saved:test')
                        dialog._profile_identity = 'saved:test'
                        dialog._profile_revision = 'test-revision'
                        dialog._profile_dirty = False
                        with patch.object(dialog, '_rename_profile') as rename:
                            dialog._rename_profile_from_double_click(item)
                            rename.assert_called_once_with()
                            dialog._profile_revision = None
                            dialog._rename_profile_from_double_click(item)
                            rename.assert_called_once_with()
                    finally:
                        dialog.close()


if __name__ == '__main__':
    unittest.main()
