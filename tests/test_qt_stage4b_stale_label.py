"""Stage 4B regression: first-run gating must not hide previous palette labeling.

AST testing avoids requiring PySide6 in CI, while preserving the runtime method.
"""
from __future__ import annotations
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'desktop/qt_app/main_window.py'


def extract(*names):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='MainWindow')
    functions = [n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(functions)==len(names)
    ns={}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(SOURCE),'exec'),ns)
    return {name: ns[name] for name in names}

class Label:
    def __init__(self, value=''):
        self.value=value
        self.style=''
    def setText(self,text):self.value=text
    def setStyleSheet(self,style):self.style=style

class ForecastState:
    def __init__(self,previous):self.previous=previous
    @property
    def has_previous(self):return self.previous is not None

class TestStaleLabel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.methods=extract('_present_forecast_pending','_show_previous_forecast')

    def harness(self, *, previous=True, ready=True, auto=False):
        w=SimpleNamespace()
        for name,fn in self.methods.items():
            setattr(w,name,fn.__get__(w))
        w._forecast_view=ForecastState({'forecast': {'colors':['#000000','#FFFFFF']}} if previous else None)
        w.forecast_palette_label=Label('2 planned output colors · Estimated before slicing')
        w._filament_setup_confirmed=False
        w._filament_decision=lambda:SimpleNamespace(ready=ready,message='Choose your available filaments.')
        w.auto_forecast=SimpleNamespace(isChecked=lambda:auto)
        w._set_forecast_status=lambda message,severity='normal':setattr(w,'status',(message,severity))
        w.state=SimpleNamespace(model_path='example.3mf')
        w._original_mesh=object()
        return w

    def test_unconfirmed_setup_still_labels_previous_palette(self):
        w=self.harness(ready=False)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'Previous forecast · 2 planned colors')
        self.assertIn('Choose your available filaments',w.status[0])

    def test_manual_changed_settings_show_previous_and_refresh_instruction(self):
        w=self.harness(ready=True,auto=False)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'Previous forecast · 2 planned colors')
        self.assertEqual(w.status[1],'stale')
        self.assertIn('Refresh Forecast',w.status[0])

    def test_auto_ready_shows_previous_then_auto_status(self):
        w=self.harness(ready=True,auto=True)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'Previous forecast · 2 planned colors')
        self.assertEqual(w.status[1],'busy')
        self.assertIn('automatically',w.status[0])

    def test_auto_not_ready_remains_blocked(self):
        w=self.harness(ready=False,auto=True)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'Previous forecast · 2 planned colors')
        self.assertNotIn('automatically',w.status[0])

    def test_no_previous_palette_is_not_misidentified_as_previous(self):
        w=self.harness(previous=False,ready=False)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'No forecast yet')
        self.assertEqual(w.forecast_palette_label.style,'')

    def test_empty_no_previous_with_ready_gate_no_stale_label(self):
        w=self.harness(previous=False,ready=True,auto=False)
        w._present_forecast_pending()
        self.assertEqual(w.forecast_palette_label.value,'No forecast yet')
        self.assertIn('Refresh Forecast',w.status[0])

if __name__=='__main__':unittest.main()
