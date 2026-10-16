"""Installer + optional Qt UI tests for Stage 2B."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'
        from desktop.qt_app.main_window import MainWindow
        self.window=MainWindow(settings_path=self.path)
        self.addCleanup(self.window.close)

    def test_tab_exists_without_loading_engine_on_start(self):
        self.assertEqual(self.window.tabs.tabText(1),'Filaments')
        self.assertFalse(self.window.compose_button.isEnabled())
        self.assertEqual(self.window.filaments_panel.options,[])

    def test_color_table_search_pins_and_saving(self):
        from desktop.settings_store import load_settings
        panel=self.window.filaments_panel
        panel._source_signature=('custom','fixture')
        panel._options_loaded(0,[{'key':'a','name':'Cyan','color':'#00FFFF'},
                                 {'key':'b','name':'Blue','color':'#0000FF'},
                                 {'key':'c','name':'Black','color':'#000000'}],None)
        self.assertEqual(panel.filaments.rowCount(),3)
        panel.search.setText('Blue')
        self.assertTrue(panel.filaments.isRowHidden(0))
        self.assertFalse(panel.filaments.isRowHidden(1))
        panel.search.clear()
        panel._rows[2][1].setChecked(False)
        panel._rows[1][2].setChecked(True)
        panel.save()
        self.assertEqual(load_settings(self.path)['disabled_anchor_keys'],['c'])
        self.assertEqual(load_settings(self.path)['pinned_anchor_keys'],['b'])

    def test_protection_is_cleared_on_new_model(self):
        panel=self.window.filaments_panel
        panel._source_signature=('custom','fixture')
        panel._options_loaded(0,[{'key':'a','name':'Cyan','color':'#00FFFF'},
                                 {'key':'b','name':'Blue','color':'#0000FF'}],None)
        panel.set_model('first.3mf')
        panel.source_colors={'#9199A4':15}
        panel._populate_solid_colors()
        panel.solid_table.selectRow(0)
        panel.target.setCurrentIndex(0)
        panel._protect()
        self.assertEqual(len(panel.preferences.solid_assignments),1)
        panel.set_model('next.3mf')
        self.assertFalse(panel.preferences.solid_assignments)

if __name__=='__main__':unittest.main()
