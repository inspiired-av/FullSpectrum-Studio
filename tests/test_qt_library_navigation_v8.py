"""Visual and behavioral contracts for the single-table library navigation."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

DIALOG_PATH = Path(__file__).resolve().parents[1] / 'desktop/qt_app/filament_library_dialog.py'


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DIALOG_PATH.read_text(encoding='utf-8-sig')

    def test_svg_is_well_formed_and_embedded(self):
        ast.parse(self.source)
        tree = ast.parse(self.source)
        svg = next(
            node.value.value for node in tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == '_ALL_FILAMENTS_SVG'
                for target in node.targets
            )
        )
        root = ET.fromstring(svg)
        self.assertEqual(root.tag, '{http://www.w3.org/2000/svg}svg')
        self.assertGreaterEqual(len(list(root)), 3)
        self.assertIn('QSvgRenderer', self.source)
        self.assertIn('self.all_filaments_button.setIcon(_all_filaments_icon())', self.source)

    def test_unselected_all_is_transparent_but_matches_profile_selected_color(self):
        self.assertIn('QPushButton#libraryAllFilaments {text-align: left; padding: 7px 9px;', self.source)
        self.assertIn('background: transparent; color: #d8e5ed; border: none;', self.source)
        self.assertIn('QPushButton#libraryAllFilaments:hover:!checked {background: #24333d;}', self.source)
        self.assertIn('QListWidget#libraryProfileList::item:hover:!selected {background: #24333d;}', self.source)
        self.assertIn('QPushButton#libraryAllFilaments:checked {background: #2b5361;', self.source)
        self.assertIn('QListWidget#libraryProfileList::item:selected {background: #2b5361;', self.source)
        self.assertEqual(self.source.count('border-left: 3px solid #77d9e3;'), 2)
        self.assertNotIn('QPushButton#libraryAllFilaments {text-align: left; padding: 9px;', self.source)

    def test_no_new_profile_editor_or_data_writes(self):
        self.assertEqual(self.source.count('self.table = QTableView(self)'), 1)
        self.assertIn('self.all_filaments_button.clicked.connect(self._select_all_filaments)', self.source)
        self.assertIn('self.profiles.currentItemChanged.connect(self._on_profile_selected)', self.source)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app import filament_library_dialog as ui
except (ImportError, OSError):
    QApplication = None


@unittest.skipIf(QApplication is None, 'PySide6 unavailable')
class NavigationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_vector_icon_is_rendered(self):
        icon = ui._all_filaments_icon()
        self.assertFalse(icon.isNull())
        bitmap = icon.pixmap(18, 18)
        self.assertFalse(bitmap.isNull())
        self.assertTrue(any(bitmap.toImage().pixelColor(x, y).alpha() > 0
                            for x in range(bitmap.width())
                            for y in range(bitmap.height())))

    def test_sidebar_selection_is_mutually_exclusive(self):
        from unittest.mock import patch
        import tempfile
        from desktop.qt_app import filament_library_store as store
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(store, 'settings_path', return_value=Path(temporary)/'settings.json'):
                with patch.object(ui, 'bambu_catalog_filaments', return_value=[]):
                    dialog = ui.FilamentLibraryDialog()
                    try:
                        self.assertTrue(dialog.all_filaments_button.isChecked())
                        self.assertTrue(dialog.all_filaments_button.icon().pixmap(18, 18).width() > 0)
                        self.assertTrue(dialog.profiles.count() > 0)
                        dialog.profiles.setCurrentRow(0)
                        self.assertFalse(dialog.all_filaments_button.isChecked())
                        self.assertEqual(dialog._profile_identity,
                                         dialog.profiles.currentItem().data(Qt.ItemDataRole.UserRole))
                        dialog.all_filaments_button.click()
                        self.assertTrue(dialog.all_filaments_button.isChecked())
                        self.assertIsNone(dialog._profile_identity)
                    finally:
                        dialog.close()


if __name__ == '__main__':
    unittest.main()
