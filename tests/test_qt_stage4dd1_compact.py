"""Stage 4D-D1 compact two-toggle controls: headless decisions and GUI regressions."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TAB = ROOT / 'desktop/qt_app/filaments_tab.py'


def _method(name):
    """Extract GUI-independent dispatcher to exercise it without PySide6."""
    tree = ast.parse(TAB.read_text(encoding='utf-8'))
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == 'FilamentsTab')
    method = next(node for node in klass.body if isinstance(node, ast.FunctionDef)
                  and node.name == name)
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(TAB), 'exec'), namespace)
    return namespace[name]


class DummyCheck:
    def __init__(self, checked):
        self.checked = bool(checked)

    def isChecked(self):
        return self.checked


class ToggleDecisionTests(unittest.TestCase):
    def state(self, uses, requirements, selection):
        w = SimpleNamespace(
            _rows=[(None, DummyCheck(u), DummyCheck(r))
                   for u, r in zip(uses, requirements)],
            _selected_filament_rows=lambda: tuple(selection),
            _bulk_change=Mock(),
        )
        return w

    def test_use_all_checked_excludes_every_selected(self):
        w = self.state([True, True, False], [False, True, False], [0, 1])
        _method('_bulk_toggle_use')(w)
        w._bulk_change.assert_called_once_with('exclude')

    def test_use_mixed_selection_enables_every_selected(self):
        w = self.state([True, False, True], [False, False, False], [0, 1, 2])
        _method('_bulk_toggle_use')(w)
        w._bulk_change.assert_called_once_with('use')

    def test_require_all_checked_unrequires_every_selected(self):
        w = self.state([True, True], [True, True], [0, 1])
        _method('_bulk_toggle_required')(w)
        w._bulk_change.assert_called_once_with('optional')

    def test_require_mixed_selection_requires_every_selected(self):
        w = self.state([True, True, False], [True, False, False], [0, 1, 2])
        _method('_bulk_toggle_required')(w)
        w._bulk_change.assert_called_once_with('require')

    def test_empty_selection_is_noop(self):
        w = self.state([True], [False], [])
        _method('_bulk_toggle_use')(w)
        _method('_bulk_toggle_required')(w)
        w._bulk_change.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class ToggleWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'settings.json'
        self.tab = FilamentsTab(PlanPreferences(path), settings_path=path)
        self.addCleanup(self.tab.close)
        self.options = [
            {'key': f'PLA|#{i:06X}', 'name': f'Filament {i}', 'color': f'#{i:06X}'}
            for i in range(1, 6)
        ]
        self.tab._options_loaded(self.tab._load_serial, self.options, None)
        self.events = []
        self.tab.planning_changed.connect(self.events.append)

    def select(self, *rows):
        from PySide6.QtCore import QItemSelectionModel
        table = self.tab.filaments
        table.clearSelection()
        for row in rows:
            table.selectionModel().select(
                table.model().index(row, 2),
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows,
            )

    def test_two_buttons_and_selection_feedback(self):
        self.select(0, 1)
        self.assertIn('2 selected', self.tab.selection_hint.text())
        self.assertEqual(self.tab.bulk_use_button.text(), 'Exclude Selected')
        self.assertEqual(self.tab.bulk_require_button.text(), 'Require Selected')
        self.tab.bulk_use_button.click()
        self.assertEqual(self.events, [True])
        self.assertEqual(self.tab.bulk_use_button.text(), 'Use Selected')
        self.assertFalse(self.tab._rows[0][1].isChecked())
        self.assertFalse(self.tab._rows[1][1].isChecked())
        self.tab.bulk_use_button.click()
        self.assertEqual(self.events, [True, True])
        self.assertTrue(self.tab._rows[0][1].isChecked())
        self.assertTrue(self.tab._rows[1][1].isChecked())

    def test_mixed_require_then_unrequire(self):
        self.select(0)
        self.tab.bulk_require_button.click()
        self.select(0, 1)
        self.assertEqual(self.tab.bulk_require_button.text(), 'Require Selected')
        self.tab.bulk_require_button.click()
        self.assertEqual(self.tab.bulk_require_button.text(), 'Unrequire Selected')
        self.assertTrue(all(self.tab._rows[i][2].isChecked() for i in (0, 1)))
        self.tab.bulk_require_button.click()
        self.assertEqual(self.tab.bulk_require_button.text(), 'Require Selected')
        self.assertTrue(all(self.tab._rows[i][1].isChecked() for i in (0, 1)))
        self.assertTrue(all(not self.tab._rows[i][2].isChecked() for i in (0, 1)))
        self.assertEqual(self.events, [True, True, True])

    def test_invalid_require_keeps_everything_unchanged(self):
        self.tab.plan_preferences.set('real_slots', '2')
        self.select(0, 1, 2)
        before = [(a.isChecked(), b.isChecked()) for _o, a, b in self.tab._rows]
        with patch('desktop.qt_app.filaments_tab.QMessageBox.warning') as message:
            self.tab.bulk_require_button.click()
        message.assert_called_once()
        self.assertEqual(before, [(a.isChecked(), b.isChecked())
                                  for _o, a, b in self.tab._rows])
        self.assertEqual(self.events, [])
        self.assertEqual(self.tab.bulk_require_button.text(), 'Require Selected')

    def test_filter_select_and_dynamic_labels(self):
        self.tab.search.setText('Filament 3')
        self.tab._select_filtered_filaments()  # UI path is Ctrl+A
        self.assertEqual(self.tab._selected_filament_rows(), (2,))
        self.assertIn('1 selected', self.tab.selection_hint.text())
        self.tab.bulk_use_button.click()
        self.assertIn(self.options[2]['key'], self.tab.preferences.disabled)
        self.assertEqual(self.tab.bulk_use_button.text(), 'Use Selected')


if __name__ == '__main__':
    unittest.main()
