"""D2 v9 regression: switching models releases assignment-only filament locks."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
TAB=ROOT/'desktop/qt_app/filaments_tab.py'


class ModelLockSourceContracts(unittest.TestCase):
    def test_model_reset_synchronizes_existing_rows(self):
        src=TAB.read_text(encoding='utf-8')
        tree=ast.parse(src)
        klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FilamentsTab')
        method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='set_model')
        body=ast.get_source_segment(src,method)
        self.assertLess(body.index('self.preferences.use_model(self.model_path)'),
                        body.index('self._sync_assignment_widgets()'))
        self.assertIn('if self._rows and not self._population_active:',body)


@unittest.skipUnless(importlib.util.find_spec('PySide6') is not None,'PySide6 not available')
class ModelLockQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.filaments_tab import FilamentsTab
        from desktop.qt_app.plan_preferences import PlanPreferences
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        config=Path(self.folder.name)/'settings.json'
        self.tab=FilamentsTab(PlanPreferences(config),settings_path=config)
        self.addCleanup(self.tab.close)
        self.opts=[
            dict(key='blue',name='Blue',color='#0000FF',series='PLA Basic'),
            dict(key='white',name='White',color='#FFFFFF',series='PLA Basic'),
            dict(key='black',name='Black',color='#000000',series='PLA Basic'),
        ]
        self.tab._options_loaded(self.tab._load_serial,self.opts,None)
        self.assertEqual(len(self.tab._rows),3)

    def test_model_switch_releases_auto_lock_but_keeps_manual_require(self):
        prefs=self.tab.preferences
        prefs.pinned.add('black')  # Manually required, unrelated to source assignments
        self.tab.set_model('first.3mf')
        prefs.solid_assignments['#AA00AA']='white'
        self.tab._sync_assignment_widgets()
        white=self.tab._rows[1]
        black=self.tab._rows[2]
        self.assertTrue(white[2].isChecked())
        self.assertFalse(white[2].isEnabled())
        self.assertIn('🔒',self.tab.filaments.item(1,2).text())
        self.tab.set_model('second.3mf')
        self.assertEqual(prefs.solid_assignments,{})
        self.assertTrue(white[1].isEnabled())
        self.assertTrue(white[2].isEnabled())
        self.assertFalse(white[2].isChecked())
        self.assertNotIn('🔒',self.tab.filaments.item(1,2).text())
        self.assertTrue(black[2].isChecked())
        self.assertTrue(black[2].isEnabled())

    def test_reopening_same_model_keeps_assignments(self):
        self.tab.set_model('first.3mf')
        self.tab.preferences.solid_assignments['#AA00AA']='white'
        self.tab._sync_assignment_widgets()
        self.tab.set_model('first.3mf')
        self.assertEqual(self.tab.preferences.solid_assignments,{'#AA00AA':'white'})
        self.assertFalse(self.tab._rows[1][2].isEnabled())

if __name__=='__main__': unittest.main()
