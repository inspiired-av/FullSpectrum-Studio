"""D3: user filament edits are staged; automatic forecast runs only when appropriate."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'desktop/qt_app/main_window.py'
TAB=ROOT/'desktop/qt_app/filaments_tab.py'


def isolated_method(name):
    source=MAIN.read_text(encoding='utf-8')
    tree=ast.parse(source)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MainWindow')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    mod=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]))
    scope={}
    exec(compile(mod,str(MAIN),'exec'),scope)
    return scope[name]


class HeadlessStagingContracts(unittest.TestCase):
    def test_source_and_stage_controls_are_explicit(self):
        s=MAIN.read_text(encoding='utf-8')
        tab=TAB.read_text(encoding='utf-8')
        self.assertIn('UI prototype · Stage 4D-D3',s)
        self.assertIn("QPushButton('Update Forecast')",s)
        self.assertIn('self.filaments_panel.explicit_refresh_requested.connect(self._stage_filament_forecast)',s)
        self.assertIn('self._forecast_timer.timeout.connect(self._automatic_forecast_due)',s)
        self.assertIn('self.explicit_refresh_requested.emit()',tab)
        self.assertIn('self._filament_forecast_held = False  # A new model starts a new session.',s)

    def test_staged_edit_invalidates_once_but_never_requests_optimizer(self):
        state=Mock()
        isolated_method('_stage_filament_forecast')(state)
        state._hold_filament_forecast.assert_called_once_with()
        state._invalidate_forecast.assert_called_once_with()
        state._request_forecast.assert_not_called()

    def test_auto_timer_does_not_launch_when_hold_is_active(self):
        state=Mock()
        state._filament_forecast_held=True
        state.auto_forecast.isChecked.return_value=True
        isolated_method('_automatic_forecast_due')(state)
        state._request_forecast.assert_not_called()
        state._filament_forecast_held=False
        isolated_method('_automatic_forecast_due')(state)
        state._request_forecast.assert_called_once_with()
        state._request_forecast.reset_mock()
        state.auto_forecast.isChecked.return_value=False
        isolated_method('_automatic_forecast_due')(state)
        state._request_forecast.assert_not_called()

    def test_saving_only_persists_and_does_not_issue_another_invalidation(self):
        src=MAIN.read_text(encoding='utf-8')
        method=ast.get_source_segment(src,next(n for n in next(
            c for c in ast.parse(src).body if isinstance(c,ast.ClassDef) and c.name=='MainWindow'
        ).body if isinstance(n,ast.FunctionDef) and n.name=='_filament_activity'))
        self.assertNotIn("if title in ('Filaments', 'Protected colors')",method)
        self.assertIn("if title == 'Protected colors'",method)

    def test_model_loading_keeps_initial_automatic_workflow(self):
        src=MAIN.read_text(encoding='utf-8')
        self.assertIn("if (self.auto_forecast.isChecked() and self._filament_decision().ready\n                and not getattr(self, '_filament_forecast_held', False)):",src)
        self.assertIn('self._filament_forecast_held = False  # A new model starts a new session.',src)

    def test_editor_button_starts_only_a_requested_forecast(self):
        state=Mock()
        isolated_method('_update_filament_forecast')(state)
        state._forecast_timer.stop.assert_called_once_with()
        state._request_forecast.assert_called_once_with()

    def test_queued_work_cannot_bypass_new_edits(self):
        state=Mock()
        state._filament_forecast_held=True
        isolated_method('_resume_queued_forecast')(state)
        state._request_forecast.assert_not_called()
        state._filament_forecast_held=False
        isolated_method('_resume_queued_forecast')(state)
        state._request_forecast.assert_called_once()


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed')
class QtStagingIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.main_window import MainWindow
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w=MainWindow(settings_path=Path(self.tmp.name)/'settings.json')
        self.addCleanup(self.w.close)
        self.w.filaments_panel._options_loaded(self.w.filaments_panel._load_serial,[
            {'key':f'PLA Basic|#{i:06X}','name':f'Color {i}','color':f'#{i:06X}'}
            for i in range(1,5)
        ],None)
        self.w._filament_setup_confirmed=True
        self.w._filament_options_ready=True
        self.w.state.model_path=str(Path(self.tmp.name)/'model.3mf')
        Path(self.w.state.model_path).write_bytes(b'fake file: workers mocked')
        self.w._original_mesh=object()
        self.w.auto_forecast.setChecked(True)
        self.w._forecast_timer.stop()

    def test_twenty_changes_never_start_timer_and_keep_stale_result(self):
        tab=self.w.filaments_panel
        for index in range(20):
            check=tab._rows[index%4][2]
            check.setChecked(not check.isChecked())
        self.assertTrue(self.w._filament_forecast_held)
        self.assertFalse(self.w._forecast_timer.isActive())
        self.assertTrue(self.w.update_filament_forecast_button.isEnabled())
        self.assertIn('outdated',self.w.forecast_status.text().lower()) if self.w._forecast_view.has_previous else None

    def test_library_refresh_is_staged_but_startup_load_is_not(self):
        w=self.w
        w._filament_forecast_held=False
        w._forecast_timer.stop()
        with (patch.object(w.filaments_panel,'_source_settings',return_value=('custom','missing.json')),
              patch.object(w.filaments_panel,'_start')):
            w.filaments_panel.load_options(force=True)
        self.assertTrue(w._filament_forecast_held)
        self.assertFalse(w._forecast_timer.isActive())

    def test_explicit_forecast_button_builds_one_worker(self):
        w=self.w
        w.filaments_panel._rows[0][2].setChecked(True)
        self.assertTrue(w._filament_forecast_held)
        with (patch('desktop.qt_app.main_window.make_request',return_value=object()) as make,
              patch('desktop.qt_app.main_window.ForecastWorker') as worker):
            w.update_filament_forecast_button.click()
            make.assert_called_once()
            worker.return_value.start.assert_called_once()
        self.assertFalse(w._filament_forecast_held)
        self.assertFalse(w._forecast_timer.isActive())


if __name__=='__main__':
    unittest.main()
