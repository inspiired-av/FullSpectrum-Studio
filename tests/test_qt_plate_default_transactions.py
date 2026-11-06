"""Additional headless contracts for transactional plate default behavior.

No PySide6/OpenGL imports. These tests execute the real method bodies from the
working tree via AST, so the source cannot simply pass by matching a string.
"""
from __future__ import annotations

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from desktop.qt_app.plate_workspace import read_workspace, write_workspace

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
PICKER = ROOT / 'desktop/qt_app/plate_ui.py'


def method(path, klass, name, globals_=None):
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == klass)
    fn=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name == name)
    module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    namespace={} if globals_ is None else dict(globals_)
    exec(compile(module,str(path),'exec'),namespace)
    return namespace[name]


class PlateDefaultTransactionTests(TestCase):
    def test_dialog_clear_is_staged_and_does_not_write(self):
        host=SimpleNamespace(
            clear_saved_default=False,
            saved_default={'printer':'old'},
            remember_default=SimpleNamespace(setChecked=Mock()),
            forget_default_button=SimpleNamespace(setVisible=Mock()),
            _refresh_actions=Mock(),
        )
        method(PICKER,'PlatePickerDialog','_forget_default')(host)
        self.assertTrue(host.clear_saved_default)
        self.assertEqual(host.saved_default,{})
        host.remember_default.setChecked.assert_called_once_with(False)
        host._refresh_actions.assert_called_once()

    def test_clear_without_selection_enables_ok(self):
        ok=SimpleNamespace(setEnabled=Mock())
        host=SimpleNamespace(
            clear_saved_default=True,
            list=SimpleNamespace(currentItem=lambda:None),
            remember_default=SimpleNamespace(setEnabled=Mock()),
            buttons=SimpleNamespace(button=lambda _:ok),
        )
        qdbb=SimpleNamespace(StandardButton=SimpleNamespace(Ok=0))
        method(PICKER,'PlatePickerDialog','_refresh_actions',{'QDialogButtonBox':qdbb})(host)
        ok.setEnabled.assert_called_once_with(True)

    def test_clear_without_selection_accepts_dialog(self):
        host=SimpleNamespace(
            clear_saved_default=True,
            list=SimpleNamespace(currentItem=lambda:None),
            selected_asset=object(),
            accept=Mock(),
        )
        method(PICKER,'PlatePickerDialog','_accept')(host)
        self.assertIsNone(host.selected_asset)
        host.accept.assert_called_once()

    def test_no_selection_and_no_clear_do_not_accept(self):
        host=SimpleNamespace(
            clear_saved_default=False,
            list=SimpleNamespace(currentItem=lambda:None),
            selected_asset=None,
            accept=Mock(),
        )
        method(PICKER,'PlatePickerDialog','_accept')(host)
        host.accept.assert_not_called()

    def test_remember_new_plate_survives_settings_reload(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'plate_workspace.json'
            asset=SimpleNamespace(printer='H2C',vendor='BBL',source='OrcaSlicer',label='H2C')
            host=SimpleNamespace(
                _plate_selected=asset, _plate_default=None, _plate_default_pending=True,
                _plate_workspace={'visible':True},_plate_visible=True,
                _plate_custom_exes=[],_plate_custom_roots=[],_plate_settings_path=path,
                statusBar=lambda: SimpleNamespace(showMessage=Mock()),
            )
            save=method(MAIN,'MainWindow','_save_plate_workspace',{'write_workspace':write_workspace})
            host._save_plate_workspace=lambda:save(host)
            method(MAIN,'MainWindow','_make_selected_plate_default')(host)
            self.assertEqual(read_workspace(path)['default'],{
                'printer':'H2C','vendor':'BBL','source':'OrcaSlicer'})
            self.assertFalse(host._plate_default_pending)
