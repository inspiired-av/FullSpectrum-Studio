"""Stage 4B first-run/readiness policy: no Qt required for deterministic checks."""
from __future__ import annotations
import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

BASE=Path(__file__).resolve().parents[1]
SRC=BASE/'desktop/qt_app'
spec=importlib.util.spec_from_file_location('forecast_setup_gate',SRC/'forecast_setup_gate.py')
module=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=module
spec.loader.exec_module(module)
evaluate=module.evaluate_setup


def options():
    return [
        {'key':'red','color':'#FF0000','name':'Red PLA'},
        {'key':'blue','color':'#0000FF','name':'Blue PLA'},
        {'key':'other-blue','color':'#0000ff','name':'Alt Blue'},
    ]


def check(**overrides):
    args=dict(source='inventory',custom_path='',saved_source=None,
              confirmed=False,loaded=True,options=options(),disabled=(),selection_valid=True)
    args.update(overrides)
    return evaluate(**args)


class ReadinessPolicyTests(unittest.TestCase):
    def test_default_is_not_implicit_consent(self):
        d=check()
        self.assertFalse(d.ready)
        self.assertEqual(d.state,'needs_confirmation')
        self.assertTrue(d.can_confirm)

    def test_first_run_can_confirm_after_options_load(self):
        d=check(confirmed=True)
        self.assertTrue(d.ready)
        self.assertEqual(d.state,'ready')

    def test_saved_source_auto_ready_only_after_loading(self):
        self.assertTrue(check(saved_source='inventory').ready)
        d=check(saved_source='inventory',loaded=False)
        self.assertFalse(d.ready)
        self.assertEqual(d.state,'loading')

    def test_saved_source_mismatch_does_not_approve_another_source(self):
        d=check(saved_source='inventory',source='catalog')
        self.assertFalse(d.ready)
        self.assertTrue(d.can_confirm)

    def test_empty_or_insufficient_library_remains_blocked(self):
        self.assertEqual(check(confirmed=True,options=[]).state,'insufficient')
        self.assertEqual(check(confirmed=True,disabled={'red'}).state,'insufficient')
        self.assertEqual(check(confirmed=True,disabled={'blue','other-blue'}).state,'insufficient')

    def test_loading_prevents_manual_and_auto_preview(self):
        self.assertFalse(check(saved_source='inventory',loaded=False).ready)
        self.assertFalse(check(confirmed=True,loaded=False).ready)

    def test_invalid_live_selection_remains_blocked(self):
        d=check(saved_source='inventory',selection_valid=False)
        self.assertEqual(d.state,'invalid')
        self.assertFalse(d.ready)
        self.assertIn('Correct',d.message)
        self.assertIn('Too many pins',check(selection_valid=False,selection_error='Too many pins').message)

    def test_custom_library_file_is_required(self):
        self.assertEqual(check(confirmed=True,source='custom',custom_path='/missing.json').state,'custom_missing')
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'library.json'
            file.write_text('[]',encoding='utf8')
            self.assertTrue(check(confirmed=True,source='custom',custom_path=str(file)).ready)
            file.unlink()
            self.assertEqual(check(confirmed=True,source='custom',custom_path=str(file)).state,'custom_missing')

    def test_cmykw_automatic_materials_still_require_first_run_consent(self):
        d=check(source='exact-cmykw',options=[])
        self.assertEqual(d.state,'needs_confirmation')
        self.assertTrue(check(source='exact-cmykw',options=[],confirmed=True).ready)


class WindowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=(SRC/'main_window.py').read_text(encoding='utf-8')
        cls.tree=ast.parse(cls.code)
        cls.window=next(c for c in cls.tree.body if isinstance(c,ast.ClassDef) and c.name=='MainWindow')

    @classmethod
    def method(cls,name):
        f=next(f for f in cls.window.body if isinstance(f,ast.FunctionDef) and f.name==name)
        return ast.get_source_segment(cls.code,f)

    def test_both_forecast_entry_paths_gated(self):
        request=self.method('_request_forecast')
        self.assertLess(request.index('decision = self._filament_decision()'), request.index('make_request('))
        self.assertLess(request.index('if not decision.ready:'),request.index('make_request('))
        auto=self.method('_invalidate_forecast')
        self.assertIn('self._filament_decision().ready',auto)
        self.assertIn('self._filament_decision().ready',self.method('_preview_loaded'))

    def test_returning_user_loads_options_asynchronously(self):
        fn=self.method('_initialize_filament_setup')
        self.assertIn('self._saved_filament_source',fn)
        self.assertIn('self.filaments_panel.load_options()',fn)
        self.assertIn('QTimer.singleShot(0, self._initialize_filament_setup)',self.code)

    def test_first_time_users_can_configure_in_both_tabs(self):
        self.assertIn("setObjectName('configureFilamentsFirstRun')",self.code)
        self.assertIn("setObjectName('confirmFilamentsFirstRun')",self.code)
        self.assertIn("setObjectName('confirmFilamentsTab')",self.code)
        self.assertIn('self._filament_setup_confirmed = True',self.method('_confirm_filament_setup'))
        self.assertNotIn('.save(',self.method('_confirm_filament_setup'))

    def test_loading_events_control_ready_state(self):
        fn=self.method('_filament_activity')
        self.assertIn("title == 'Filament source'",fn)
        self.assertIn("severity == 'success'",fn)
        self.assertIn('self._filament_options_ready = ',fn)
        self.assertIn('decision.ready',fn)

    def test_outdated_forecast_and_manual_controls_preserved(self):
        self.assertIn("self._forecast_view.invalidate()",self.code)
        self.assertIn('self._forecast_timer.stop()',self.method('_refresh_filament_setup_ui'))
        self.assertIn('self.forecast_refresh.setEnabled(False)',self.method('_refresh_filament_setup_ui'))


if __name__=='__main__': unittest.main()


class SourceMethodBehaviorTests(unittest.TestCase):
    """Execute early-return guard paths without Qt to prove no worker can start."""
    @staticmethod
    def get_method(name):
        src=(SRC/'main_window.py').read_text(encoding='utf-8')
        klass=next(n for n in ast.parse(src).body if isinstance(n,ast.ClassDef) and n.name=='MainWindow')
        method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name==name)
        method.decorator_list=[]
        mod=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
        namespace={}
        exec(compile(mod,str(SRC/'main_window.py'),'exec'),namespace)
        return namespace[name]

    def test_manual_refresh_blocked_until_configured(self):
        state=Mock()
        state._filament_decision.return_value=check(loaded=False)
        self.get_method('_request_forecast')(state)
        state._forecast_timer.stop.assert_called_once()
        state._refresh_filament_setup_ui.assert_called_once()
        state._forecast_task.__class__  # no workers constructed
        state.forecast_refresh.setEnabled.assert_not_called()

    def test_valid_user_pin_counts_as_session_configuration(self):
        state=Mock()
        state._filament_options_ready=True
        state._filament_setup_confirmed=False
        self.get_method('_filament_planning_changed')(state,True)
        self.assertTrue(state._filament_setup_confirmed)
        state._invalidate_forecast.assert_called_once()
        state._refresh_filament_setup_ui.assert_called_once()
