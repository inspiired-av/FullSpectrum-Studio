"""Focused regression tests for clearing defaults and outlined camera controls.

Headless: no PySide6 or OpenGL imports are necessary.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT/'desktop/qt_app/main_window.py'
ICONS = ROOT/'desktop/qt_app/preview_toolbar_icons.py'


def extract_method(name, namespace):
    source = MAIN.read_text(encoding='utf-8-sig')
    klass = next(n for n in ast.parse(source).body
                 if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)
    node = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    env = dict(namespace)
    exec(compile(node, str(MAIN), 'exec'), env)
    return env[name]


class FakeSignal:
    def __init__(self):
        self.listeners = []

    def connect(self, callback):
        self.listeners.append(callback)

    def fire(self):
        for callback in self.listeners:
            callback()


class FakeButton:
    def __init__(self):
        self.clicked = FakeSignal()
        self.tooltip = ''

    def text(self):
        return 'Clear default'

    def setToolTip(self, text):
        self.tooltip = text


class FakePlateList:
    def __init__(self):
        self.selection_cleared = False
        self.current_row = 1

    def clearSelection(self):
        self.selection_cleared = True

    def setCurrentRow(self, row):
        self.current_row = row


class PlateDefaultCameraTests(TestCase):
    def test_clear_forgets_default_removes_current_plate_and_invalidates_worker(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'plate_workspace.json'
            def write_workspace(path_, value):
                Path(path_).write_text(json.dumps(value), encoding='utf-8')
            host = SimpleNamespace(
                _plate_default={'printer':'H2C','source':'Bambu Studio'},
                _plate_default_pending=True,
                _plate_load_serial=8,
                _plate_selected=SimpleNamespace(label='H2C'),
                _plate_loaded_mesh='STL mesh',
                _plate_workspace={'default':{'printer':'H2C'},'visible':True},
                _plate_visible=True, _plate_custom_exes=[], _plate_custom_roots=[],
                _plate_settings_path=path,
                preview_surface=SimpleNamespace(set_plate=Mock()),
                _update_plate_actions=Mock(),
                statusBar=lambda:SimpleNamespace(showMessage=Mock()),
            )
            save = extract_method('_save_plate_workspace', {'write_workspace':write_workspace})
            clear = extract_method('_clear_plate_default', {})
            host._save_plate_workspace=lambda:save(host)
            clear(host)
            self.assertIsNone(host._plate_default)
            self.assertIsNone(host._plate_selected)
            self.assertIsNone(host._plate_loaded_mesh)
            self.assertFalse(host._plate_default_pending)
            self.assertEqual(host._plate_load_serial,9)
            host.preview_surface.set_plate.assert_called_once_with(None)
            host._update_plate_actions.assert_called_once()
            saved=json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('default',saved)
            # What a new MainWindow would see after reopening the program.
            self.assertIsNone(saved.get('default'))
            self.assertFalse(saved.get('default') is not None)
            self.assertTrue(saved['visible'])

    def test_clear_button_persists_even_if_picker_is_cancelled(self):
        button=FakeButton()
        dialog=SimpleNamespace(
            list=FakePlateList(), selected_asset=SimpleNamespace(label='old'),
            clear_saved_default=True, remember_default=SimpleNamespace(isChecked=lambda:False),
            findChildren=lambda _type:[button],
        )
        dialog.exec=lambda:(button.clicked.fire(),0)[1]
        clear=Mock()
        host=SimpleNamespace(
            _plate_catalog=SimpleNamespace(plates=[object()]),
            _plate_default={'printer':'H2C'},
            _clear_plate_default=clear,
            _select_plate_asset=Mock(),
            _make_selected_plate_default=Mock(),
        )
        picker=extract_method('_choose_plate', {
            'PlatePickerDialog':lambda *args,**kwargs:dialog,
            'QDialog':SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
            'QPushButton':FakeButton,
        })
        picker(host)
        clear.assert_called_once()
        self.assertTrue(dialog.list.selection_cleared)
        self.assertEqual(dialog.list.current_row,-1)
        self.assertIsNone(dialog.selected_asset)
        host._select_plate_asset.assert_not_called()
        self.assertIn('Immediately forget',button.tooltip)

    def test_empty_picker_does_not_reselect_or_save_default(self):
        button=FakeButton()
        dialog=SimpleNamespace(
            list=FakePlateList(), selected_asset=None,
            clear_saved_default=True, remember_default=SimpleNamespace(isChecked=lambda:True),
            findChildren=lambda _type:[button],
        )
        dialog.exec=lambda:(button.clicked.fire(),1)[1]
        host=SimpleNamespace(
            _plate_catalog=SimpleNamespace(plates=[object()]),
            _plate_default={'printer':'H2C'},
            _clear_plate_default=Mock(),
            _select_plate_asset=Mock(),
            _make_selected_plate_default=Mock(),
        )
        picker=extract_method('_choose_plate', {
            'PlatePickerDialog':lambda *args,**kwargs:dialog,
            'QDialog':SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
            'QPushButton':FakeButton,
        })
        picker(host)
        host._clear_plate_default.assert_called_once()
        host._select_plate_asset.assert_not_called()
        host._make_selected_plate_default.assert_not_called()

    def test_reselect_and_remember_new_plate_after_clearing(self):
        button=FakeButton()
        replacement=SimpleNamespace(label='OrcaSlicer printer')
        dialog=SimpleNamespace(
            list=FakePlateList(), selected_asset=None,
            clear_saved_default=True, remember_default=SimpleNamespace(isChecked=lambda:True),
            findChildren=lambda _type:[button],
        )
        def run_dialog():
            button.clicked.fire()
            # A deliberate new choice after Clear is still valid.
            dialog.selected_asset = replacement
            return 1
        dialog.exec=run_dialog
        host=SimpleNamespace(
            _plate_catalog=SimpleNamespace(plates=[object()]),
            _plate_default={'printer':'H2C'},
            _clear_plate_default=Mock(),
            _select_plate_asset=Mock(),
            _make_selected_plate_default=Mock(),
        )
        picker=extract_method('_choose_plate', {
            'PlatePickerDialog':lambda *args,**kwargs:dialog,
            'QDialog':SimpleNamespace(DialogCode=SimpleNamespace(Accepted=1)),
            'QPushButton':FakeButton,
        })
        picker(host)
        host._clear_plate_default.assert_called_once()
        host._select_plate_asset.assert_called_once_with(replacement)
        host._make_selected_plate_default.assert_called_once()

    def test_camera_icons_point_ne_sw_and_reset_is_continuous(self):
        icon=ICONS.read_text(encoding='utf-8')
        ast.parse(icon)
        self.assertIn("name == 'expand'",icon)
        self.assertIn('QPointF(10, 14), QPointF(19, 5)',icon)
        self.assertIn('QPointF(14, 10), QPointF(5, 19)',icon)
        self.assertIn("name == 'restore'",icon)
        self.assertIn('QPointF(19, 5), QPointF(14, 10)',icon)
        self.assertIn('QPointF(5, 19), QPointF(10, 14)',icon)
        self.assertIn('curve.cubicTo(16.9, 3.4, 20.6, 7.1, 20.6, 12.0)',icon)
        self.assertNotIn('painter.drawArc(',icon)
        self.assertNotIn('QPointF(4.5, 4.5)',icon)

    def test_camera_action_handlers_remain_wired(self):
        code=MAIN.read_text(encoding='utf-8')
        self.assertIn('self.expand_preview_toggle.toggled.connect(self._set_expanded_preview)',code)
        self.assertIn('self.reset_camera_button.clicked.connect(self._reset_camera)',code)
        self.assertIn("'restore' if expanded else 'expand'",code)
        self.assertIn('self.preview_surface.reset_camera()',code)
        ast.parse(code)
