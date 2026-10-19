"""Stage 4D-D1: bulk filament edits, one-shot invalidation, Require UI naming.

Headless contracts run without Qt. Integration tests exercise real PySide6 widgets.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
TAB=ROOT/'desktop/qt_app/filaments_tab.py'
PREFS=ROOT/'desktop/qt_app/filament_preferences.py'


class StaticContracts(unittest.TestCase):
    def test_renamed_controls_preserve_saved_key_contract(self):
        tab=TAB.read_text(encoding='utf-8')
        prefs=PREFS.read_text(encoding='utf-8')
        self.assertIn("['Use', 'Color', 'Filament', 'Require']",tab)
        self.assertIn('self.filaments.select_visible_requested.connect(self._select_filtered_filaments)',tab)
        self.assertIn('Require Selected',tab)
        self.assertIn('Unrequire Selected',tab)
        self.assertIn("current['pinned_anchor_keys']",prefs)
        self.assertIn('self.preferences.apply(self.options,enabled,pinned,self._max_pins())',tab)
        self.assertIn('self._table_changed()  # One snapshot, one planning_changed emission.',tab)

    def test_new_methods_parse_as_class_members(self):
        tree=ast.parse(TAB.read_text(encoding='utf-8'))
        klass=next(node for node in tree.body if isinstance(node,ast.ClassDef)
                   and node.name=='FilamentsTab')
        methods={node.name for node in klass.body if isinstance(node,ast.FunctionDef)}
        self.assertTrue({'_bulk_change','_selected_filament_rows',
                         '_select_filtered_filaments'} <= methods)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class BulkSelectionIntegration(unittest.TestCase):
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
        self.panel=FilamentsTab(PlanPreferences(Path(self.tmp.name)/'plan.json'),
                                settings_path=Path(self.tmp.name)/'plan.json')
        self.addCleanup(self.panel.close)
        self.options=[{'key':f'Bambu|#{i:06X}','name':name,'color':f'#{i:06X}','series':'PLA Basic'}
                      for i,name in [(1,'Red'),(2,'Blue'),(3,'Green'),(4,'White')]]
        self.panel._options_loaded(self.panel._load_serial,self.options,None)
        self.events=[]
        self.panel.planning_changed.connect(self.events.append)

    def _select_rows(self,*rows):
        from PySide6.QtCore import QItemSelectionModel
        table=self.panel.filaments
        table.clearSelection()
        for i in rows:
            table.selectionModel().select(
                table.model().index(i,2),
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows)

    def test_multi_require_staged_once_and_noop_ignored(self):
        self._select_rows(0,2)
        self.panel._bulk_change('require')
        self.assertEqual(self.events,[True])
        self.assertEqual(self.panel.preferences.pinned,
                         {self.options[0]['key'],self.options[2]['key']})
        self.assertTrue(self.panel.preferences.is_dirty)
        self.panel._bulk_change('require')
        self.assertEqual(self.events,[True])  # no-op is not another forecast
        self.panel._bulk_change('optional')
        self.assertEqual(self.events,[True,True])
        self.assertFalse(self.panel.preferences.pinned)

    def test_filter_select_visible_then_exclude_is_single_change(self):
        self.panel.search.setText('Blue')
        self.panel._select_filtered_filaments()
        self.assertEqual(self.panel._selected_filament_rows(),(1,))
        self.panel._bulk_change('exclude')
        self.assertEqual(self.events,[True])
        self.assertIn(self.options[1]['key'],self.panel.preferences.disabled)
        self.assertNotIn(self.options[0]['key'],self.panel.preferences.disabled)
        self.panel.search.setText('Green')
        self.assertEqual(self.panel._selected_filament_rows(),())

    def test_invalid_require_is_fully_atomic(self):
        self.panel.plan_preferences.set('real_slots','2')
        self._select_rows(0,1,2)
        before=[(e.isChecked(),r.isChecked()) for _,e,r in self.panel._rows]
        with patch('desktop.qt_app.filaments_tab.QMessageBox.warning') as warn:
            self.panel._bulk_change('require')
        warn.assert_called_once()
        self.assertEqual(before,[(e.isChecked(),r.isChecked()) for _,e,r in self.panel._rows])
        self.assertFalse(self.panel.preferences.pinned)
        self.assertFalse(self.events)

    def test_excluding_assignment_target_emits_protection_once(self):
        self.panel.preferences.solid_assignments={'#AABBCC':self.options[0]['key']}
        protection_events=[]
        self.panel.protections_changed.connect(protection_events.append)
        self._select_rows(0)
        self.panel._bulk_change('exclude')
        self.assertEqual(protection_events,[{}])
        self.assertEqual(self.events,[True])
        self.assertNotIn('#AABBCC',self.panel.preferences.solid_assignments)

    def test_require_makes_excluded_filament_usable(self):
        self._select_rows(3)
        self.panel._bulk_change('exclude')
        self.panel._bulk_change('require')
        self.assertTrue(self.panel._rows[3][1].isChecked())
        self.assertTrue(self.panel._rows[3][2].isChecked())
        self.assertNotIn(self.options[3]['key'],self.panel.preferences.disabled)
        self.assertIn(self.options[3]['key'],self.panel.preferences.pinned)
        self.assertEqual(self.events,[True,True])


if __name__=='__main__':
    unittest.main()
