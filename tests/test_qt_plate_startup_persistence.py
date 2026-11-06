"""Regression checks: explicit Remember intent and eager async catalog warming.

These tests exercise real method bodies via AST but do not require Qt or GL.
A manual Windows restart and rendering check is still essential.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from desktop.qt_app.plate_workspace import read_workspace, write_workspace

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
PICKER = ROOT / 'desktop/qt_app/plate_ui.py'


def method(path, class_name, method_name, namespace=None):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    env = {} if namespace is None else dict(namespace)
    exec(compile(module, str(path), 'exec'), env)
    return env[method_name]


class FakeCheckBox:
    def __init__(self):
        self.checked = False
        self.enabled = True
    def setChecked(self, value):
        self.checked = bool(value)
    def isChecked(self):
        return self.checked
    def setEnabled(self, enabled):
        self.enabled = enabled


class FakeList:
    def __init__(self):
        self.item = None
    def currentItem(self):
        return self.item


class FakeItem:
    def __init__(self, asset):
        self.asset = asset
    def data(self, role):
        return self.asset


class PlateStartupPersistenceTests(TestCase):
    def _dialog(self, default=None):
        host=SimpleNamespace(
            saved_default=default or {},
            _remember_user_override=None,
            remember_default=FakeCheckBox(),
            list=FakeList(),
            clear_saved_default=False,
            buttons=SimpleNamespace(button=lambda button:SimpleNamespace(setEnabled=lambda enabled:None)),
        )
        qdbb=SimpleNamespace(StandardButton=SimpleNamespace(Ok=0))
        qt=SimpleNamespace(ItemDataRole=SimpleNamespace(UserRole=256))
        refresh=method(PICKER,'PlatePickerDialog','_refresh_actions',
                       {'QDialogButtonBox':qdbb,'Qt':qt})
        click=method(PICKER,'PlatePickerDialog','_remember_default_clicked')
        return host,refresh,click

    def test_user_checks_remember_before_choosing_plate(self):
        dialog,refresh,click=self._dialog()
        dialog.remember_default.setChecked(True)
        click(dialog, True)  # Qt clicked signal, not setChecked signal
        asset=SimpleNamespace(printer='H2C',vendor='BBL',source='Bambu Studio')
        dialog.list.item=FakeItem(asset)
        refresh(dialog)
        self.assertTrue(dialog.remember_default.isChecked())

    def test_user_unchecks_saved_default_then_switches_plate(self):
        saved={'printer':'H2C','vendor':'BBL','source':'Bambu Studio'}
        dialog,refresh,click=self._dialog(saved)
        dialog.list.item=FakeItem(SimpleNamespace(**saved))
        refresh(dialog)
        self.assertTrue(dialog.remember_default.isChecked())  # Initial auto-match.
        dialog.remember_default.setChecked(False)
        click(dialog, False)
        dialog.list.item=FakeItem(SimpleNamespace(printer='P1S',vendor='BBL',source='Bambu Studio'))
        refresh(dialog)
        self.assertFalse(dialog.remember_default.isChecked())

    def test_initial_saved_default_auto_matches_without_user_click(self):
        saved={'printer':'H2C','vendor':'BBL','source':'Bambu Studio'}
        dialog,refresh,click=self._dialog(saved)
        dialog.list.item=FakeItem(SimpleNamespace(**saved))
        refresh(dialog)
        self.assertTrue(dialog.remember_default.isChecked())
        dialog.list.item=FakeItem(SimpleNamespace(printer='A1',vendor='BBL',source='Bambu Studio'))
        refresh(dialog)
        self.assertFalse(dialog.remember_default.isChecked())

    def test_clear_then_choose_and_remember_persists_after_restart(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'plate_workspace.json'
            previous={'printer':'H2C','vendor':'BBL','source':'Bambu Studio'}
            write_workspace(path, {'default': previous, 'visible': True})
            replacement=SimpleNamespace(printer='P1S',vendor='BBL',source='OrcaSlicer',label='P1S')
            host=SimpleNamespace(
                _plate_catalog=SimpleNamespace(plates=[replacement]),
                _plate_default=previous,
                _plate_default_pending=False,
                _plate_selected=None,
                _plate_workspace=read_workspace(path),_plate_visible=True,
                _plate_custom_exes=[],_plate_custom_roots=[],_plate_settings_path=path,
                statusBar=lambda:SimpleNamespace(showMessage=Mock()),
            )
            save=method(MAIN,'MainWindow','_save_plate_workspace',{'write_workspace':write_workspace})
            clear=method(MAIN,'MainWindow','_clear_plate_default')
            remember=method(MAIN,'MainWindow','_make_selected_plate_default')
            host._save_plate_workspace=lambda: save(host)
            host._clear_plate_default=lambda: clear(host)
            host._make_selected_plate_default=lambda: remember(host)
            host._select_plate_asset=lambda asset:setattr(host,'_plate_selected',asset)
            dialog,refresh,click=self._dialog(previous)
            dialog.forget_default_button=SimpleNamespace(setVisible=Mock())
            dialog._refresh_actions=lambda:refresh(dialog)
            method(PICKER,'PlatePickerDialog','_forget_default')(dialog)
            dialog.remember_default.setChecked(True)
            click(dialog,True)
            dialog.list.item=FakeItem(replacement)
            refresh(dialog)
            self.assertTrue(dialog.remember_default.isChecked())
            dialog.selected_asset=replacement
            dialog.exec=lambda:1
            choose=method(MAIN,'MainWindow','_choose_plate',{
                'PlatePickerDialog':lambda *a,**k:dialog,
                'QDialog':SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
            })
            choose(host)
            # Simulate new process reading the persisted settings file.
            saved=read_workspace(path)
            self.assertEqual(saved['default'],{'printer':'P1S','vendor':'BBL','source':'OrcaSlicer'})
            self.assertFalse(host._plate_default_pending)
            self.assertIs(host._plate_selected,replacement)

    def test_early_click_joins_running_scan_without_duplicate_scan(self):
        choose=method(MAIN,'MainWindow','_choose_plate')
        host=SimpleNamespace(_plate_catalog=None,_plate_pending_picker=False,
                             _plate_catalog_task=object(),_refresh_plate_catalog=Mock())
        choose(host)
        self.assertTrue(host._plate_pending_picker)
        host._refresh_plate_catalog.assert_not_called()

    def test_click_without_running_scan_triggers_discovery(self):
        choose=method(MAIN,'MainWindow','_choose_plate')
        host=SimpleNamespace(_plate_catalog=None,_plate_pending_picker=False,
                             _plate_catalog_task=None,_refresh_plate_catalog=Mock())
        choose(host)
        host._refresh_plate_catalog.assert_called_once_with()

    def test_catalog_warms_without_saved_default(self):
        source=MAIN.read_text(encoding='utf-8-sig')
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='MainWindow')
        init=next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name=='__init__')
        init_code=ast.get_source_segment(source,init)
        self.assertIn('QTimer.singleShot(0, self._refresh_plate_catalog)',init_code)
        self.assertNotIn('if self._plate_default_pending:\n',init_code)

    def test_qt_clicked_wiring_exists_and_is_distinct_from_set_checked(self):
        source=PICKER.read_text(encoding='utf-8-sig')
        self.assertIn('self.remember_default.clicked.connect(self._remember_default_clicked)',source)
        self.assertIn('self._remember_user_override = None',source)
        self.assertNotIn('self.remember_default.toggled.connect(self._remember_default_clicked)',source)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class PlatePickerRealQtTests(TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_check_before_selection_survives_real_qt_signal(self):
        from desktop.qt_app.plate_catalog import PlateAsset
        from desktop.qt_app.plate_ui import PlatePickerDialog
        plate=PlateAsset('H2C', 'BBL', 'Bambu Studio', Path('bed.stl'), None,
                         Path('h2c.json'), Path('.'))
        dialog=PlatePickerDialog((plate,))
        try:
            dialog.remember_default.click()    # Real user action -> clicked signal.
            self.assertTrue(dialog.remember_default.isChecked())
            dialog.list.setCurrentRow(0)     # Qt itemSelectionChanged -> _refresh_actions.
            self.assertTrue(dialog.remember_default.isChecked())
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_clear_then_check_then_choose_new_plate_survives_qt(self):
        from desktop.qt_app.plate_catalog import PlateAsset
        from desktop.qt_app.plate_ui import PlatePickerDialog
        a=PlateAsset('H2C', 'BBL', 'Bambu Studio', Path('a.stl'), None,
                     Path('a.json'), Path('.'))
        b=PlateAsset('P1S', 'BBL', 'OrcaSlicer', Path('b.stl'), None,
                     Path('b.json'), Path('.'))
        saved={'printer':'H2C','vendor':'BBL','source':'Bambu Studio'}
        dialog=PlatePickerDialog((a,b),saved_default=saved)
        try:
            dialog.forget_default_button.click()
            self.assertTrue(dialog.clear_saved_default)
            dialog.remember_default.click()
            self.assertTrue(dialog.remember_default.isChecked())
            index=next(i for i in range(dialog.list.count())
                       if dialog.list.item(i).data(256).printer == 'P1S')
            dialog.list.setCurrentRow(index)
            self.assertTrue(dialog.remember_default.isChecked())
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
