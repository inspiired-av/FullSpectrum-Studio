"""Stage 4B: retain Stage 4A status-test compatibility without bypassing first-run gating."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parents[1]
SRC = HERE / 'desktop' / 'qt_app'
METHODS = ('_show_previous_forecast', '_present_forecast_pending', '_invalidate_forecast',
           '_update_plan_value', '_forecast_done')


def method_functions():
    path = SRC/'main_window.py'
    tree = ast.parse(path.read_text(encoding='utf8'))
    klass = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name == 'MainWindow')
    nodes = [n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in METHODS]
    assert len(nodes)==len(METHODS)
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),str(path),'exec'),namespace)
    return namespace


class Label:
    def __init__(self,text=''):
        self.value=text
        self.style=''
        self.enabled=None
    def setText(self,value): self.value=value
    def setStyleSheet(self,value): self.style=value
    def clear(self):self.value=''
    def setEnabled(self,flag):self.enabled=flag

class Toggle:
    def __init__(self,checked=False):self.checked=checked
    def isChecked(self):return self.checked

class Timer:
    def __init__(self):self.start_count=0;self.stop_count=0
    def start(self):self.start_count+=1
    def stop(self):self.stop_count+=1

class State:
    def __init__(self,model):self.model=model;self.previous=None;self.stale=False
    @property
    def has_previous(self):return self.previous is not None
    def reset(self,model):self.model=model;self.previous=None;self.stale=False
    def invalidate(self):self.stale=bool(self.previous)
    def accept(self,model,result):
        if model != self.model:return False
        self.previous=result;self.stale=False;return True


METRICS={'forecast':{'accuracy':91,'confidence':64,'maximumDeltaE':6.2,'colors':['#000000','#FFFFFF'],
                     'slotSummary':'5 physical + 27 mixed'},'warnings':[]}


class Stage4ACompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.functions=method_functions()

    def harness(self,auto=False,previous=True):
        state=SimpleNamespace()
        for k,v in self.functions.items():
            if k in METHODS:setattr(state,k,v.__get__(state))
        state.state=SimpleNamespace(model_path='example.3mf')
        state._original_mesh=object()
        state._forecast_view=State('example.3mf')
        if previous: state._forecast_view.accept('example.3mf',METRICS)
        state._forecast_serial=0
        state._inspection_serial=0
        state._forecast_timer=Timer()
        state._forecast_pending=False
        state._forecast_task=None
        state.auto_forecast=Toggle(auto)
        state.accuracy=Label('91%' if previous else '—')
        state.forecast_metrics={'Confidence':Label('64%')}
        state.forecast_palette_label=Label('2 planned output colors')
        state.forecast_warning=Label('')
        state.forecast_status=Label()
        state.forecast_refresh=Label()
        state.source_inspection=Label()
        state._drawn=[]
        state._render_forecast_palette=lambda colors:setattr(state,'_drawn',list(colors))
        state._set_forecast_status=lambda m,level='normal': (state.forecast_status.setText(m),state.forecast_status.setStyleSheet(level))
        state._refresh_dependent_plan_widgets=lambda:None
        state._update_plan_dirty_state=lambda:None
        state._loading_plan_ui=False
        state.plan_preferences=SimpleNamespace(set=lambda name,value:False)
        state.results_panel=SimpleNamespace(record_event=lambda *args:None)
        return state

    def test_initial_auto_without_forecast_clears_label_harness(self):
        w=self.harness(auto=True,previous=False)
        w._invalidate_forecast()
        self.assertEqual(w.accuracy.value,'—')
        self.assertEqual(w.forecast_status.style,'busy')
        self.assertEqual(w._forecast_timer.start_count,1)

    def test_initial_manual_without_forecast_clears_label_harness(self):
        w=self.harness(previous=False)
        w._invalidate_forecast()
        self.assertEqual(w.accuracy.value,'—')
        self.assertIn('Refresh Forecast',w.forecast_status.value)

    def test_old_forecast_preserved_when_stale(self):
        w=self.harness()
        w._invalidate_forecast()
        self.assertEqual(w.accuracy.value,'91%')
        self.assertTrue(w._forecast_view.stale)
        self.assertIn('Refresh Forecast',w.forecast_status.value)

    def test_model_change_clears_old_accuracy_with_label_harness(self):
        w=self.harness()
        w.state.model_path='different.3mf'
        w._invalidate_forecast(clear_inspection=True)
        self.assertEqual(w.accuracy.value,'—')
        self.assertFalse(w._forecast_view.has_previous)

    def test_auto_toggle_legacy_harness_schedules_without_new_gate(self):
        w=self.harness(auto=True)
        w._forecast_view.invalidate()
        w._update_plan_value('auto_preview',True)
        self.assertEqual(w._forecast_timer.start_count,1)
        self.assertTrue(w._forecast_view.has_previous)

    def test_real_gate_missing_consent_still_blocks_automatic(self):
        w=self.harness(auto=True)
        w._forecast_view.invalidate()
        w._filament_setup_confirmed=False
        w._filament_decision=lambda:SimpleNamespace(ready=False,message='Configure filaments')
        w._update_plan_value('auto_preview',True)
        self.assertEqual(w._forecast_timer.start_count,0)

    def test_error_keeps_old_forecast(self):
        w=self.harness(auto=True)
        w._forecast_done(w._forecast_serial,None,'Invalid palette size')
        self.assertEqual(w.forecast_status.style,'error')
        self.assertIn('Invalid palette size',w.forecast_status.value)
        self.assertTrue(w._forecast_view.has_previous)

    def test_ring_gauge_exposes_same_readonly_text_as_painted_center(self):
        path=SRC/'forecast_visuals.py'
        tree=ast.parse(path.read_text(encoding='utf8'))
        ring=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RingGauge')
        text=next(n for n in ring.body if isinstance(n,ast.FunctionDef) and n.name=='text')
        scope={}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[text],type_ignores=[])),str(path),'exec'),scope)
        for value,want in [(None,'—'),(91.0,'91%'),(90.6,'91%'),(0,'0%')]:
            with self.subTest(value=value):self.assertEqual(scope['text'](SimpleNamespace(value=value)),want)


if __name__=='__main__':unittest.main()
