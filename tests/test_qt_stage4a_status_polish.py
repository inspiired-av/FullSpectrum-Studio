"""Regression: automatic forecasts never show an obsolete amber refresh prompt.

Exercise Qt status methods through AST without a GPU or a PySide6 dependency.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from desktop.qt_app.forecast_view_state import ForecastViewState

MODULE_PATH = Path(__file__).resolve().parents[1] / 'desktop/qt_app/main_window.py'
METHODS = ('_show_previous_forecast', '_present_forecast_pending',
           '_invalidate_forecast', '_update_plan_value', '_forecast_done')


def behavior_class():
    tree = ast.parse(MODULE_PATH.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    selected = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in METHODS]
    assert len(selected) == len(METHODS), 'Stage 4A status functions missing'
    harness = ast.ClassDef(name='BehaviorHarness', bases=[], keywords=[], body=selected, decorator_list=[])
    code = compile(ast.fix_missing_locations(ast.Module(body=[harness], type_ignores=[])),
                   str(MODULE_PATH), 'exec')
    namespace = {}
    exec(code, namespace)
    return namespace['BehaviorHarness']


class Label:
    def __init__(self, text=''):
        self.text_value = text
        self.style = ''
        self.enabled = None
    def setText(self, text):
        self.text_value = text
    def setStyleSheet(self, style):
        self.style = style
    def clear(self):
        self.text_value = ''
    def setEnabled(self, enabled):
        self.enabled = enabled
    def setProperty(self, key, value):
        setattr(self, key, value)


class Toggle:
    def __init__(self, enabled=False):
        self.checked = enabled
    def isChecked(self):
        return self.checked


class Timer:
    def __init__(self):
        self.started = 0
        self.stopped = 0
    def start(self):
        self.started += 1
    def stop(self):
        self.stopped += 1


FORECAST = {'forecast': {'accuracy': 91.0, 'confidence': 64.0, 'maximumDeltaE': 6.2,
                         'slotSummary': '5 physical + 27 mixed',
                         'colors': ['#000000', '#FFFFFF']}, 'warnings': []}


def fake_window(auto=False, existing=True, model='example.3mf'):
    cls = behavior_class()
    w = cls()
    w.state = SimpleNamespace(model_path=model)
    w._original_mesh = object() if model else None
    w.auto_forecast = Toggle(auto)
    w._forecast_view = ForecastViewState()
    w._forecast_view.reset(model)
    if existing:
        assert w._forecast_view.accept(model, FORECAST)
    w._forecast_serial = 0
    w._inspection_serial = 0
    w._forecast_timer = Timer()
    w._forecast_pending = False
    w._forecast_task = None
    w.accuracy = Label('91%' if existing else '—')
    w.forecast_metrics = {'Confidence': Label('64%' if existing else '—')}
    w.forecast_palette_label = Label('2 planned output colors')
    w.forecast_warning = Label('Worst match details')
    w.forecast_status = Label('Forecast ready')
    w.forecast_refresh = Label()
    w.source_inspection = Label('Metadata inspected')
    w._drawn_colors = ['#000000', '#FFFFFF'] if existing else []
    w._render_forecast_palette = lambda colors: setattr(w, '_drawn_colors', list(colors))
    w._set_forecast_status = lambda message, severity='normal': (w.forecast_status.setText(message),
                                                                   w.forecast_status.setStyleSheet(severity))
    w._refresh_dependent_plan_widgets = lambda: None
    w._update_plan_dirty_state = lambda: None
    w._loading_plan_ui = False
    w.plan_preferences = SimpleNamespace(set=lambda field, value: None)
    return w


class ForecastStatusTests(unittest.TestCase):
    def test_manual_changes_have_one_refresh_instruction(self):
        w = fake_window(auto=False)
        w._invalidate_forecast()
        self.assertEqual(w.forecast_status.style, 'stale')
        self.assertIn('Refresh Forecast', w.forecast_status.text_value)
        self.assertNotIn('refresh', w.forecast_palette_label.text_value.lower())
        self.assertEqual(w._drawn_colors, ['#000000', '#FFFFFF'])
        self.assertEqual(w.accuracy.text_value, '91%')
        self.assertEqual(w._forecast_timer.started, 0)

    def test_automatic_changes_have_no_amber_and_queue_refresh(self):
        w = fake_window(auto=True)
        w._invalidate_forecast()
        self.assertEqual(w.forecast_status.style, 'busy')
        self.assertIn('automatically', w.forecast_status.text_value)
        self.assertNotIn('Refresh Forecast', w.forecast_status.text_value)
        self.assertNotIn('refresh', w.forecast_palette_label.text_value.lower())
        self.assertEqual(w.forecast_palette_label.style, '')
        self.assertEqual(w._forecast_timer.started, 1)
        self.assertEqual(w._drawn_colors, ['#000000', '#FFFFFF'])

    def test_manual_initial_state_only_one_prompt(self):
        w = fake_window(auto=False, existing=False)
        w._invalidate_forecast()
        self.assertEqual(w.forecast_status.text_value.count('Refresh Forecast'), 1)
        self.assertEqual(w.forecast_palette_label.text_value, 'No forecast yet')
        self.assertEqual(w._drawn_colors, [])

    def test_auto_initial_state_is_neutral(self):
        w = fake_window(auto=True, existing=False)
        w._invalidate_forecast()
        self.assertEqual(w.forecast_status.style, 'busy')
        self.assertIn('automatically', w.forecast_status.text_value)
        self.assertEqual(w.forecast_palette_label.text_value, 'No forecast yet')

    def test_switching_models_discards_previous_result(self):
        w = fake_window(auto=False)
        w.state.model_path = 'different.3mf'
        w._invalidate_forecast(clear_inspection=True)
        self.assertFalse(w._forecast_view.has_previous)
        self.assertEqual(w.accuracy.text_value, '—')
        self.assertEqual(w._drawn_colors, [])

    def test_toggle_automatic_scheduling_does_not_invalidate_forecast(self):
        w = fake_window(auto=False)
        w._forecast_view.invalidate()
        w._present_forecast_pending()
        w.auto_forecast.checked = True
        w._update_plan_value('auto_preview', True)
        self.assertEqual(w.forecast_status.style, 'busy')
        self.assertEqual(w._forecast_timer.started, 1)
        self.assertTrue(w._forecast_view.has_previous)
        w._forecast_pending = True
        w.auto_forecast.checked = False
        w._update_plan_value('auto_preview', False)
        self.assertEqual(w.forecast_status.style, 'stale')
        self.assertFalse(w._forecast_pending)
        self.assertEqual(w._forecast_timer.stopped, 1)
        self.assertEqual(w.accuracy.text_value, '91%')

    def test_error_still_uses_red_status(self):
        w = fake_window(auto=True)
        w.results_panel = SimpleNamespace(record_event=lambda *args: None)
        w._forecast_done(w._forecast_serial, None, 'Invalid palette size')
        self.assertEqual(w.forecast_status.style, 'error')
        self.assertIn('Invalid palette size', w.forecast_status.text_value)
        self.assertTrue(w._forecast_view.has_previous)


if __name__ == '__main__':
    unittest.main()
