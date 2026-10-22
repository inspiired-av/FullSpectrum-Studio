"""Stage 4D-D2 v5: splitter auto-size and readable filament assignment tree."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
PANEL = ROOT / 'desktop/qt_app/source_assignments_panel.py'


class InspectorSourceTests(unittest.TestCase):
    def test_source_files_compile(self):
        ast.parse(MAIN.read_text(encoding='utf-8'))
        ast.parse(PANEL.read_text(encoding='utf-8'))

    def test_expansion_reallocates_existing_splitter_space_and_restores(self):
        source = MAIN.read_text(encoding='utf-8')
        self.assertIn('self.assignment_panel.details_toggled.connect(self._resize_palette_for_assignments)', source)
        self.assertIn('def _resize_palette_for_assignments(self, expanded):', source)
        self.assertIn('palette.setMinimumHeight(target)', source)
        self.assertIn('splitter.setSizes([max(0, total - target), target])', source)
        self.assertIn('palette.setMinimumHeight(94)', source)
        self.assertIn('abs(sizes[1] - automatic) <= 14', source)
        self.assertLess(source.index('palette_layout.addWidget(self.source_palette_content)'),
                        source.index('palette_layout.addWidget(self.assignment_panel)'))
        self.assertIn('self.source_palette_scroll.setWidget(self.source_palette_body)', source)

    def test_tree_resizes_name_column_and_includes_material_swatch(self):
        source = PANEL.read_text(encoding='utf-8')
        self.assertIn('QHeaderView.ResizeMode.Stretch', source)
        self.assertIn('self.tree.setColumnWidth(1, 82)', source)
        self.assertIn('group.setIcon(0, self._swatch_icon(opt.get(\'color\')))', source)
        self.assertIn('item.setIcon(0, self._swatch_icon(source))', source)
        self.assertIn('painter.drawRoundedRect(', source)
        self.assertIn('group.setToolTip(0', source)

    def test_clearing_last_assignment_releases_inspector_height(self):
        source = PANEL.read_text(encoding='utf-8')
        self.assertIn('details_toggled = Signal(bool)', source)
        self.assertIn('self.details_toggled.emit(bool(checked))', source)
        self.assertIn('if not self._assignments and self.toggle.isChecked():', source)
        self.assertIn('self.toggle.setChecked(False)', source)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class InspectorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_tree_uses_available_width_and_has_physical_swatch(self):
        from desktop.qt_app.source_assignments_panel import SourceAssignmentsPanel
        from PySide6.QtWidgets import QHeaderView
        panel = SourceAssignmentsPanel()
        try:
            panel.resize(650, 300)
            panel.show()
            self.app.processEvents()
            panel.set_assignments(
                {'#F2F2F2': 'white', '#000001': 'white'},
                [{'key':'white', 'name':'Example Brand Extra Long PLA Professional White Filament',
                  'color':'#FFFFFF'}],
                {'#F2F2F2': 12, '#000001': 7},
            )
            self.assertEqual(panel.tree.header().sectionResizeMode(0), QHeaderView.ResizeMode.Stretch)
            group = panel.tree.topLevelItem(0)
            self.assertFalse(group.icon(0).isNull())
            self.assertIn('Example Brand Extra Long', group.text(0))
            self.assertIn('#FFFFFF', group.toolTip(0))
            emitted = []
            panel.details_toggled.connect(emitted.append)
            panel.toggle.setChecked(True)
            self.assertEqual(emitted, [True])
            self.assertTrue(panel.details.isVisibleTo(panel))
            panel.set_assignments({}, [], {})
            self.assertEqual(emitted, [True, False])
            self.assertFalse(panel.toggle.isChecked())
        finally:
            panel.close()


if __name__ == '__main__':
    unittest.main()
