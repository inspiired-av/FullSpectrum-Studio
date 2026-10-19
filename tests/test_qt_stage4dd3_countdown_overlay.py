"""Stage 4D-D3: countdown runs only for scheduled automatic forecasts."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'desktop/qt_app/main_window.py'
OVERLAY = ROOT / 'desktop/qt_app/forecast_countdown_overlay.py'


def standalone_method(name):
    source = MAIN.read_text(encoding='utf-8')
    klass = next(node for node in ast.parse(source).body
                 if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    method = next(node for node in klass.body
                  if isinstance(node, ast.FunctionDef) and node.name == name)
    env = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
                 str(MAIN), 'exec'), env)
    return env[name]


class HeadlessCountdownContractTests(unittest.TestCase):
    def test_authoritative_six_second_timer_and_viewport_parent(self):
        source = MAIN.read_text(encoding='utf-8')
        self.assertIn('self._forecast_timer = ForecastCountdownTimer(self)', source)
        self.assertIn('self._forecast_timer.setInterval(6000)', source)
        self.assertIn('self._forecast_timer.timeout.connect(self._automatic_forecast_due)', source)
        self.assertIn('self.forecast_countdown = ForecastCountdownOverlay(self.preview_surface)', source)
        self.assertIn('self._forecast_timer.armed.connect(self._show_auto_forecast_countdown)', source)
        self.assertIn('self._forecast_timer.disarmed.connect(self._hide_auto_forecast_countdown)', source)
        self.assertIn('self._forecast_timer.timeout.connect(self._hide_auto_forecast_countdown)', source)

    def test_widget_updates_only_presentation_timer_not_forecast(self):
        source = OVERLAY.read_text(encoding='utf-8')
        self.assertIn('viewport.installEventFilter(self)', source)
        self.assertIn('width - self.width() - 16', source)
        self.assertIn('height - self.height() - 16', source)
        self.assertIn('self._display_tick.timeout.connect(self._refresh)', source)
        self.assertNotIn('ForecastWorker', source)
        self.assertNotIn('make_request(', source)

    def test_cancel_stops_only_pending_timer(self):
        state = Mock()
        state._forecast_timer.isActive.return_value = True
        standalone_method('_cancel_scheduled_forecast')(state)
        state._forecast_timer.stop.assert_called_once_with()
        state._request_forecast.assert_not_called()
        state.auto_forecast.setChecked.assert_not_called()
        self.assertIn('skipped', state._set_forecast_status.call_args.args[0].lower())

    def test_cancel_does_not_disturb_a_completed_countdown(self):
        state = Mock()
        state._forecast_timer.isActive.return_value = False
        standalone_method('_cancel_scheduled_forecast')(state)
        state._forecast_timer.stop.assert_not_called()
        state._set_forecast_status.assert_not_called()

    def test_run_now_one_worker_request_without_auto_rescheduling(self):
        state = Mock()
        state._filament_forecast_held = False
        state._forecast_timer.isActive.return_value = True
        standalone_method('_run_scheduled_forecast_now')(state)
        state._forecast_timer.stop.assert_called_once()
        state._request_forecast.assert_called_once()
        state._forecast_timer.start.assert_not_called()

    def test_run_now_obeys_late_edit_hold(self):
        state = Mock()
        state._filament_forecast_held = True
        state._forecast_timer.isActive.return_value = True
        standalone_method('_run_scheduled_forecast_now')(state)
        state._forecast_timer.stop.assert_called_once()
        state._request_forecast.assert_not_called()

    def test_auto_guard_prevents_staged_edit_overlay(self):
        state = Mock()
        state._filament_forecast_held = True
        state.auto_forecast.isChecked.return_value = True
        standalone_method('_show_auto_forecast_countdown')(state)
        state._forecast_timer.stop.assert_called_once()
        state.forecast_countdown.begin.assert_not_called()
        state._forecast_timer.stop.reset_mock()
        state._filament_forecast_held = False
        state.auto_forecast.isChecked.return_value = False
        standalone_method('_show_auto_forecast_countdown')(state)
        state._forecast_timer.stop.assert_called_once()
        state.forecast_countdown.begin.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class QtCountdownIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.qt_app.main_window import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = MainWindow(settings_path=Path(self.temp.name) / 'prefs.json')
        self.addCleanup(self.window.close)
        self.window._filament_forecast_held = False
        self.window.auto_forecast.setChecked(True)
        self.window._forecast_timer.stop()
        self.window.show()
        self.app.processEvents()

    def test_countdown_visible_on_filaments_tab_and_cancel_does_not_disable_auto(self):
        window = self.window
        window.tabs.setCurrentWidget(window.filaments_panel)
        window._forecast_timer.start()
        self.app.processEvents()
        self.assertFalse(window.forecast_countdown.isHidden())
        self.assertTrue(window.forecast_countdown.parentWidget() is window.preview_surface)
        self.assertTrue(window._forecast_timer.isActive())
        self.assertEqual(window.forecast_countdown.seconds.text(), 'Starting in 6 seconds')
        with patch.object(window, '_request_forecast') as launch:
            window.forecast_countdown.cancel_button.click()
            self.app.processEvents()
            self.assertFalse(window._forecast_timer.isActive())
            self.assertTrue(window.forecast_countdown.isHidden())
            self.assertTrue(window.auto_forecast.isChecked())
            launch.assert_not_called()

    def test_run_now_bypasses_countdown_and_runs_once(self):
        w = self.window
        with patch.object(w, '_request_forecast') as launch:
            w._forecast_timer.start()
            self.app.processEvents()
            w.forecast_countdown.run_button.click()
            self.app.processEvents()
            launch.assert_called_once()
            self.assertFalse(w._forecast_timer.isActive())
            self.assertTrue(w.forecast_countdown.isHidden())

    def test_staged_changes_hide_active_countdown_and_do_not_launch(self):
        w = self.window
        w._forecast_timer.start()
        self.app.processEvents()
        self.assertFalse(w.forecast_countdown.isHidden())
        with patch.object(w, '_invalidate_forecast'):
            w._hold_filament_forecast()
        self.app.processEvents()
        self.assertTrue(w.forecast_countdown.isHidden())
        self.assertFalse(w._forecast_timer.isActive())
        self.assertTrue(w._filament_forecast_held)

    def test_timer_restart_resets_countdown_and_resize_reanchors(self):
        w = self.window
        w._forecast_timer.start()
        self.app.processEvents()
        from PySide6.QtTest import QTest
        QTest.qWait(200)
        self.assertLess(w._forecast_timer.remainingTime(), 6000)
        w._forecast_timer.start()
        self.app.processEvents()
        self.assertGreater(w._forecast_timer.remainingTime(), 5800)
        viewport = w.preview_surface
        w.forecast_countdown.position_over_viewport()
        self.assertGreaterEqual(w.forecast_countdown.x(), 0)
        self.assertLessEqual(w.forecast_countdown.x() + w.forecast_countdown.width(), viewport.width())
        self.assertLessEqual(w.forecast_countdown.y() + w.forecast_countdown.height(), viewport.height())


if __name__ == '__main__':
    unittest.main()
