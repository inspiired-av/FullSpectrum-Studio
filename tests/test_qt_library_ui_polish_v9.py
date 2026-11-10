"""Qt UI polish without editing filament/profile membership or storage."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

DIALOG = Path(__file__).resolve().parents[1] / 'desktop/qt_app/filament_library_dialog.py'


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DIALOG.read_text(encoding='utf-8-sig')
        cls.tree = ast.parse(cls.source)

    def test_title_case_bold_headings(self):
        self.assertIn("QLabel('Filament Library', sidebar)", self.source)
        self.assertIn("QLabel('Saved Profiles', sidebar)", self.source)
        self.assertIn('QLabel#librarySidebarTitle, QLabel#librarySavedProfilesHeading {',self.source)
        self.assertIn('font-weight: 700;',self.source)
        self.assertNotIn("QLabel('FILAMENT LIBRARY', sidebar)",self.source)

    def test_svg_is_a_small_size_cmyk_filament_spool(self):
        svg=next(node.value.value for node in self.tree.body
                 if isinstance(node,ast.Assign) and
                 any(isinstance(t,ast.Name) and t.id == '_ALL_FILAMENTS_SVG' for t in node.targets))
        root=ET.fromstring(svg)
        self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
        fills = {node.get('fill') for node in root.iter()}
        self.assertTrue({'#00CFFF','#FF2D95','#F5D600'} <= fills)
        self.assertGreaterEqual(len(root.findall('{http://www.w3.org/2000/svg}ellipse')), 3)
        self.assertIn('renderer.render(painter, QRectF(0.0, 0.0, 48.0, 48.0))',self.source)
        self.assertLess(self.source.index('painter.end()'),self.source.index('pixmap.setDevicePixelRatio(2.0)'))

    def test_sidebar_wraps_without_scrolling_or_modifying_ids(self):
        self.assertIn('self.profiles.setWordWrap(True)',self.source)
        self.assertIn('self.profiles.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)',self.source)
        self.assertIn('self.profiles.setTextElideMode(Qt.TextElideMode.ElideNone)',self.source)
        self.assertIn("str(profile['name']).replace('_', '_\\u200b')",self.source)
        self.assertIn("item.setData(Qt.ItemDataRole.UserRole, profile['id'])",self.source)

    def test_in_profile_column_is_not_fixed_to_use_width(self):
        self.assertIn("horizontalAdvance('In Profile') + 24",self.source)
        self.assertIn('self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)',self.source)
        self.assertNotIn('((0, 45)',self.source)
        self.assertEqual(self.source.count('self.table = QTableView(self)'),1)


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app import filament_library_dialog as ui
except (ImportError,OSError):
    QApplication=None


@unittest.skipIf(QApplication is None,'PySide6 not installed')
class WidgetChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_icon_draws_spool_at_sidebar_size(self):
        icon=ui._all_filaments_icon()
        self.assertFalse(icon.isNull())
        for size in (18, 24):
            image=icon.pixmap(size,size).toImage()
            self.assertFalse(image.isNull())
            w, h = image.width(), image.height()
            left = sum(image.pixelColor(x,y).alpha() > 0
                       for y in range(h) for x in range(w//2))
            right = sum(image.pixelColor(x,y).alpha() > 0
                        for y in range(h) for x in range(w//2,w))
            self.assertGreater(left, 0)
            self.assertGreater(right, 0)

    def test_layout_configuration(self):
        import tempfile
        from unittest.mock import patch
        from desktop.qt_app import filament_library_store as store
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store,'settings_path',return_value=Path(tmp)/'settings.json'):
                with patch.object(ui,'bambu_catalog_filaments',return_value=[]):
                    dialog=ui.FilamentLibraryDialog()
                    try:
                        self.assertTrue(dialog.profiles.wordWrap())
                        self.assertEqual(dialog.profiles.horizontalScrollBarPolicy(),
                                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                        self.assertGreaterEqual(dialog.table.columnWidth(0),92)
                        self.assertGreaterEqual(dialog.table.columnWidth(0),
                                                dialog.table.horizontalHeader().fontMetrics().horizontalAdvance('In Profile')+24)
                    finally:
                        dialog.close()


if __name__=='__main__':
    unittest.main()
