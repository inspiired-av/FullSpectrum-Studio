"""Small isolated checks for the additive v11 Filament Library controls."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'desktop/qt_app/filament_library_dialog.py'
PATCH = ROOT / 'desktop/qt_app/filament_library_interactions_v11.py'


class SourceContracts(unittest.TestCase):
    def test_installer_call_is_present_exactly_once(self):
        source = SOURCE.read_text(encoding='utf-8-sig')
        ast.parse(source)
        self.assertEqual(source.count('# FULLSPECTRUM_LIBRARY_USABILITY_V11'), 1)
        self.assertIn('install_library_usability_v11(self)', source)

    def test_controls_are_additive_and_not_storage_changes(self):
        source = PATCH.read_text(encoding='utf-8-sig')
        ast.parse(source)
        self.assertIn('ExtendedSelection', source)
        self.assertIn('SelectRows', source)
        self.assertIn('setIconSize(QSize(22, 22))', source)
        self.assertIn("setObjectName('libraryResetSortButton')", source)
        self.assertIn('model.sort(-1, Qt.SortOrder.AscendingOrder)', source)
        self.assertNotIn('write_palette', source)
        self.assertNotIn('save_profile', source)

    def test_sort_reset_svg_is_valid(self):
        tree=ast.parse(PATCH.read_text(encoding='utf-8-sig'))
        svg=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='_SORT_RESET_SVG'
                         for t in n.targets))
        root=ET.fromstring(svg)
        self.assertEqual(root.attrib['viewBox'], '0 0 24 24')
        self.assertGreaterEqual(len(root.findall('{http://www.w3.org/2000/svg}path')), 2)


try:
    from PySide6.QtCore import Qt, QSortFilterProxyModel
    from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon
    from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QTableView, QListWidget, QPushButton, QComboBox, QAbstractItemView
    from desktop.qt_app.filament_library_interactions_v11 import install_library_usability_v11, _sort_default, _update_reset_visibility
except (ImportError, OSError):
    QApplication = None


@unittest.skipIf(QApplication is None, 'PySide6 unavailable')
class QtIsolatedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dialog = QDialog()
        self.dialog._profile_identity = None
        root = QVBoxLayout(self.dialog)
        filters = QHBoxLayout()
        self.dialog.sources = QComboBox(self.dialog)
        self.dialog.sources.addItem('All sources')
        filters.addWidget(self.dialog.sources)
        root.addLayout(filters)
        self.dialog.all_filaments_button = QPushButton('All Filaments', self.dialog)
        root.addWidget(self.dialog.all_filaments_button)
        self.dialog.profiles = QListWidget(self.dialog)
        root.addWidget(self.dialog.profiles)
        self.dialog.table = QTableView(self.dialog)
        self.dialog.table.setSortingEnabled(True)
        original = QStandardItemModel(self.dialog)
        original.setHorizontalHeaderLabels(['Filament'])
        for value in ('C', 'A', 'B'):
            original.appendRow(QStandardItem(value))
        self.dialog.original = original
        proxy = QSortFilterProxyModel(self.dialog)
        proxy.setSourceModel(original)
        self.dialog.proxy = proxy
        self.dialog.table.setModel(proxy)
        root.addWidget(self.dialog.table)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()

    def test_spool_and_multiselection_are_installed(self):
        install_library_usability_v11(self.dialog)
        self.assertTrue(self.dialog._library_usability_v11_installed)
        self.assertEqual(self.dialog.all_filaments_button.iconSize().width(), 22)
        self.assertEqual(self.dialog.table.selectionMode(),
                         QAbstractItemView.SelectionMode.ExtendedSelection)
        self.assertEqual(self.dialog.table.selectionBehavior(),
                         QAbstractItemView.SelectionBehavior.SelectRows)
        install_library_usability_v11(self.dialog)  # idempotent
        self.assertEqual(len(self.dialog.findChildren(type(self.dialog.library_reset_sort_button_v11))), 1)

    def test_sort_reset_restores_source_order_without_touching_source(self):
        install_library_usability_v11(self.dialog)
        self.dialog.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        rows=lambda:[self.dialog.proxy.index(r,0).data() for r in range(3)]
        self.assertEqual(rows(), ['A','B','C'])
        self.dialog.library_reset_sort_button_v11.click()
        self.assertEqual(rows(), ['C','A','B'])
        self.assertEqual([self.dialog.original.item(r,0).text() for r in range(3)], ['C','A','B'])

    def test_sort_reset_only_visible_in_all_filaments(self):
        install_library_usability_v11(self.dialog)
        self.dialog._profile_identity = 'profile:some-profile'
        _update_reset_visibility(self.dialog)
        self.assertFalse(self.dialog.library_reset_sort_button_v11.isEnabled())
        self.dialog._profile_identity = None
        _update_reset_visibility(self.dialog)
        self.assertTrue(self.dialog.library_reset_sort_button_v11.isEnabled())


if __name__ == '__main__':
    unittest.main()
