"""Stage 4B: invalidation on unsaved filament edits, and source compatibility."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'desktop/qt_app'


def function_from_source(file, cls, function):
    tree = ast.parse((MODULES / file).read_text(encoding='utf-8'))
    parent = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls)
    target = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == function)
    target.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[target], type_ignores=[]))
    ns = {}
    exec(compile(module, str(MODULES/file), 'exec'), ns)
    return ns[function]


class PinForecastContractTests(unittest.TestCase):
    def test_filament_table_stages_before_invalidation(self):
        func = function_from_source('filaments_tab.py','FilamentsTab','_table_changed')
        state = Mock()
        state.preferences.solid_assignments = {}
        state.selection_error = ''
        state.selection_is_valid = True
        state._accept_table.return_value = True
        func(state)
        state._accept_table.assert_called_once_with(show_error=False)
        state._sync_status.assert_called_once_with(table_pending=False)
        state.planning_changed.emit.assert_called_once_with(True)
        self.assertTrue(state._accept_table.call_args_list)

    def test_invalid_table_does_not_issue_valid_planning_event(self):
        func = function_from_source('filaments_tab.py','FilamentsTab','_table_changed')
        state = Mock()
        state.preferences.solid_assignments = {}
        state.selection_error = 'Too many pinned filaments.'
        state.summary.text.return_value = '6 pinned'
        state._accept_table.return_value = False
        func(state)
        self.assertFalse(state.selection_is_valid)
        state.planning_changed.emit.assert_called_once_with(False)
        state.summary.setText.assert_called_once_with('6 pinned · Invalid: Too many pinned filaments.')

    def test_dropping_disabled_protection_notifies_ui(self):
        func = function_from_source('filaments_tab.py','FilamentsTab','_table_changed')
        state = Mock()
        state.preferences.solid_assignments = {'#ABCDEF':'PLA Basic|#ABCDEF'}
        def accept(*args,**kwargs):
            state.preferences.solid_assignments = {}
            return True
        state._accept_table.side_effect = accept
        func(state)
        state._populate_solid_colors.assert_called_once()
        state.protections_changed.emit.assert_called_once_with({})

    def test_main_window_valid_edits_invalidate_forecast(self):
        func = function_from_source('main_window.py','MainWindow','_filament_planning_changed')
        state = Mock()
        func(state,True)
        state._invalidate_forecast.assert_called_once()
        state._forecast_timer.stop.assert_not_called()

    def test_invalid_edits_stop_auto_refresh(self):
        func = function_from_source('main_window.py','MainWindow','_filament_planning_changed')
        state = Mock()
        state.filaments_panel.selection_error = 'Too few enabled colors.'
        func(state,False)
        state._invalidate_forecast.assert_called_once()
        state._forecast_timer.stop.assert_called_once()
        state._set_forecast_status.assert_called_once_with(
            'Filament selection unavailable: Too few enabled colors.', 'error')

    def test_forecast_preflight_guards_invalid_live_pins(self):
        tree=ast.parse((MODULES/'main_window.py').read_text(encoding='utf-8'))
        cls=next(c for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='MainWindow')
        method=next(c for c in cls.body if isinstance(c,ast.FunctionDef) and c.name=='_request_forecast')
        source=ast.get_source_segment((MODULES/'main_window.py').read_text(encoding='utf-8'),method)
        self.assertIn('selection_is_valid',source)
        self.assertIn('return',source.split('selection_is_valid',1)[-1].split('self._forecast_task',1)[0])

    def test_qcombobox_subclass_still_used(self):
        tab=(MODULES/'filaments_tab.py').read_text(encoding='utf-8')
        wheels=(MODULES/'wheel_safe_combo.py')
        self.assertIn('self.filament_source = WheelSafeComboBox()',tab)
        if wheels.is_file():
            self.assertIn('class WheelSafeComboBox(QComboBox)',wheels.read_text(encoding='utf-8'))



# The full GUI tests exercise actual checkbox signals on Windows. These skip
# cleanly in headless packaging environments without PySide6.
import importlib.util
import os
import tempfile

@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'PySide6 not installed')
class QtPinIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from desktop.qt_app.main_window import MainWindow
        self.w=MainWindow(settings_path=Path(self.temp.name)/'settings.json')
        self.addCleanup(self.w.close)
        self.panel=self.w.filaments_panel
        self.panel._options_loaded(self.panel._load_serial,[
            {'key':'PLA Basic|#FF0000','name':'Red','color':'#FF0000'},
            {'key':'PLA Basic|#00FF00','name':'Green','color':'#00FF00'},
            {'key':'PLA Basic|#0000FF','name':'Blue','color':'#0000FF'},
        ],None)

    def test_unsaved_pin_affects_snapshot_and_invalidates(self):
        from desktop.qt_app.forecast_service import make_request
        self.w.auto_forecast.setChecked(False)
        original_serial=self.w._forecast_serial
        self.panel._rows[1][2].setChecked(True)
        key='PLA Basic|#00FF00'
        self.assertIn(key,self.panel.preferences.pinned)
        self.assertTrue(self.panel.preferences.is_dirty)
        self.assertGreater(self.w._forecast_serial,original_serial)
        snapshot=make_request('unused.3mf','',self.w.plan_preferences,self.panel.preferences)
        self.assertIn(key,snapshot.pinned)
        from desktop.settings_store import load_settings
        self.assertNotIn(key,load_settings(self.w.plan_preferences.path).get('pinned_anchor_keys', []))

    def test_automatic_changes_restart_debounce(self):
        source=Path(self.temp.name)/'temporary.3mf'
        source.write_bytes(b'not processed: only used to activate debounce')
        self.w.state.model_path=str(source)
        self.w._original_mesh=object()
        self.w.auto_forecast.setChecked(True)
        self.w._forecast_timer.stop()
        self.panel._rows[0][2].setChecked(True)
        self.assertTrue(self.w._forecast_timer.isActive())

    def test_invalid_extra_pins_do_not_replace_valid_snapshot(self):
        self.w.plan_preferences.set('real_slots','2')
        for i in range(2): self.panel._rows[i][2].setChecked(True)
        stored=set(self.panel.preferences.pinned)
        self.panel._rows[2][2].setChecked(True)
        self.assertFalse(self.panel.selection_is_valid)
        self.assertEqual(self.panel.preferences.pinned,stored)
        self.assertIn('pinned',self.panel.selection_error.lower())

if __name__ == "__main__": unittest.main()
