"""Stage 4D-D1 cleanup: use only row selection plus two atomic bulk toggles.

Kept under its original test filename to supersede header-control tests from
Stage4DD1_HeaderPolish; the Use header no longer contains an action checkbox.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'desktop'/'qt_app'/'filaments_tab.py'


def extract(name):
    tree=ast.parse(TARGET.read_text(encoding='utf-8'))
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='FilamentsTab')
    method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name==name)
    ns={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),
                 str(TARGET),'exec'),ns)
    return ns[name]


class Check:
    def __init__(self,value):self.value=bool(value)
    def isChecked(self):return self.value


class HeadlessSelectionContracts(unittest.TestCase):
    def state(self,use,required,selected):
        return SimpleNamespace(
            _rows=[(None,Check(u),Check(r)) for u,r in zip(use,required)],
            _selected_filament_rows=lambda:tuple(selected),
            _bulk_change=Mock())

    def test_plain_use_header_has_no_global_action(self):
        source=TARGET.read_text(encoding='utf-8')
        self.assertIn("['Use', 'Color', 'Filament', 'Require']",source)
        self.assertIn('class FilamentSelectionTable(QTableWidget)',source)
        self.assertNotIn('use_all_header',source)
        self.assertNotIn('def _toggle_visible_use(',source)
        self.assertNotIn("QPushButton('Select Filtered')",source)
        self.assertNotIn("QPushButton('Clear')",source)
        self.assertIn('self.filaments.select_visible_requested.connect(self._select_filtered_filaments)',source)
        self.assertIn('self.bulk_use_button',source)
        self.assertIn('self.bulk_require_button',source)

    def test_use_selected_all_checked_requests_exclude(self):
        w=self.state([True,True,True],[False,True,False],[0,1])
        extract('_bulk_toggle_use')(w)
        w._bulk_change.assert_called_once_with('exclude')

    def test_use_selected_mixed_requests_enable(self):
        w=self.state([True,False,True],[False,False,False],[0,1])
        extract('_bulk_toggle_use')(w)
        w._bulk_change.assert_called_once_with('use')

    def test_require_selected_mixed_requests_require(self):
        w=self.state([True,True,True],[True,False,False],[0,1])
        extract('_bulk_toggle_required')(w)
        w._bulk_change.assert_called_once_with('require')

    def test_empty_selection_does_not_edit(self):
        w=self.state([True,False],[False,False],[])
        extract('_bulk_toggle_use')(w)
        extract('_bulk_toggle_required')(w)
        w._bulk_change.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtSelectionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'settings.json'
        self.tab=FilamentsTab(PlanPreferences(path),settings_path=path)
        self.tab.resize(650,900)
        self.tab.show()
        self.app.processEvents()
        self.addCleanup(self.tab.close)
        self.options=[{'key':f'PLA|#{i:06X}','name':f'Filament {i}',
                       'color':f'#{i:06X}'} for i in range(1,6)]
        self.tab._options_loaded(self.tab._load_serial,self.options,None)
        self.events=[]
        self.tab.planning_changed.connect(self.events.append)

    def test_use_header_is_label_not_global_checkbox(self):
        self.assertEqual(self.tab.filaments.horizontalHeaderItem(0).text(),'Use')
        self.assertFalse(hasattr(self.tab,'use_all_header'))
        self.assertEqual(self.tab.bulk_use_button.text(),'Use Selected')
        self.assertEqual(self.tab.bulk_require_button.text(),'Require Selected')
        self.assertFalse(self.tab.bulk_use_button.isEnabled())

    def test_ctrl_a_selects_filtered_rows_without_changing_use(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.tab.search.setText('Filament 3')
        before=[e.isChecked() for _opt,e,_req in self.tab._rows]
        self.tab.filaments.setFocus()
        QTest.keyClick(self.tab.filaments,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.tab._selected_filament_rows(),(2,))
        self.assertEqual(before,[e.isChecked() for _opt,e,_req in self.tab._rows])
        self.assertEqual(self.events,[])

    def test_clicking_sole_selected_row_again_clears(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        table=self.tab.filaments
        rect=table.visualRect(table.model().index(2,2))
        self.assertTrue(rect.isValid())
        QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
        self.assertEqual(self.tab._selected_filament_rows(),(2,))
        QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
        self.assertEqual(self.tab._selected_filament_rows(),())

    def test_invalid_selected_exclude_does_not_partially_edit(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.tab.filaments.setFocus()
        QTest.keyClick(self.tab.filaments,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.tab._selected_filament_rows(),(0,1,2,3,4))
        before=[(e.isChecked(),r.isChecked()) for _o,e,r in self.tab._rows]
        with patch('desktop.qt_app.filaments_tab.QMessageBox.warning') as warn:
            self.tab.bulk_use_button.click()
        warn.assert_called_once()
        self.assertEqual(before,[(e.isChecked(),r.isChecked()) for _o,e,r in self.tab._rows])
        self.assertEqual(self.events,[])

if __name__=='__main__':
    unittest.main()
