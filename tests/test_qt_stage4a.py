"""Stage 4A: preview must run through native engine and never export 3MF."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from desktop.qt_app.forecast_service import make_request, inspect_model, run_plan


DEFAULT = {
    'strategy': 'official', 'source': 'catalog', 'custom': '', 'real_slots': 'auto',
    'quality_bias': 55, 'smart_quality': False, 'catalog_region': 'global',
    'planner_mode': 'best', 'planning_sample': 'paint', 'max_output_colors': 'auto',
    'output_color_strategy': 'maximum_fidelity', 'native_project_template': '',
}


def fixture(tmp, **changes):
    path = Path(tmp) / 'sample.3mf'
    path.write_bytes(b'fake fixture; engine is mocked')
    settings = {**DEFAULT, **changes}
    return SimpleNamespace(model=str(path), reference=None, settings=settings,
                           disabled=frozenset(), pinned=frozenset(), protections=())


class FakeEngine:
    def __init__(self, standard=True):
        self.standard = standard
        self.args = None
        self.kw = None
    def is_standard_colored_3mf(self, path):
        return self.standard
    def inspect_project(self, path, **kw):
        self.kw = kw
        return {'sourceSlots': 5, 'sourceColors': ['#000000', '#FFFFFF']}
    def convert(self, *args, **kwargs):
        self.args, self.kw = args, kwargs
        assert kwargs['plan_only'] is True
        assert kwargs['reveal'] is False
        assert Path(kwargs['output_dir']).exists()
        return {'type': 'planPreview', 'quality': {'qualityScore': 91, 'confidenceScore': 70, 'maximumDeltaE': 3},
                'outputColors': ['#000000','#FFFFFF'], 'realSlots': 2, 'outputSlots': 2,
                'sourceSlots': 4, 'worstMatch': {}, 'warnings': [], 'plannerMode':'best'}


OPTIONS = lambda _engine, source, custom: [
    {'key': 'BLACK', 'color': '#000000'},
    {'key': 'WHITE', 'color': '#FFFFFF'},
    {'key': 'RED', 'color': '#FF0000'},
]


class PreviewContractTests(unittest.TestCase):
    def test_snapshots_unsaved_changes_and_protection(self):
        p = SimpleNamespace(get=lambda x: DEFAULT[x])
        f = SimpleNamespace(disabled={'RED'}, pinned={'BLACK'}, solid_assignments={'#FF0000':'BLACK'})
        r = make_request('a.3mf', '', p, f)
        self.assertIn('RED',r.disabled)
        self.assertEqual(dict(r.protections),{'#FF0000':'BLACK'})
        f.disabled.add('BLACK')
        self.assertNotIn('BLACK',r.disabled)

    def test_inspect_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            engine=FakeEngine()
            result=inspect_model(r.model, engine)
            self.assertEqual(result['sourceSlots'],5)
            self.assertEqual(engine.kw,{'metadata_only':True})

    def test_preview_is_native_plan_only_and_temp_removed(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            engine=FakeEngine()
            result=run_plan(r,engine=engine,options_loader=OPTIONS)
            self.assertEqual(result['forecast']['accuracy'],91)
            self.assertEqual(result['forecast']['slotSummary'],'2 physical + 0 mixed')
            self.assertTrue(engine.kw['direct_source_colors'])
            self.assertIsNone(engine.kw['analysis_dir'])
            self.assertFalse(Path(engine.kw['output_dir']).exists())
            self.assertFalse(list(Path(d).glob('*FullSpectrum*.3mf')))

    def test_saved_pins_and_disabled_are_forwarded(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            r.pinned=frozenset({'WHITE','RED'})
            r.disabled=frozenset({'RED'})
            engine=FakeEngine()
            run_plan(r,engine=engine,options_loader=OPTIONS)
            self.assertEqual(engine.kw['pinned_anchor_keys'],['WHITE'])
            self.assertEqual(engine.kw['allowed_anchor_keys'],['BLACK','WHITE'])

    def test_native_protections_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            r.protections=(('#123456','BLACK'),)
            with self.assertRaisesRegex(ValueError, 'only supports protected'):
                run_plan(r,engine=FakeEngine(standard=False),options_loader=OPTIONS)

    def test_too_few_enabled_colors_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            r.disabled=frozenset({'WHITE','RED'})
            with self.assertRaisesRegex(ValueError,'two distinct'):
                run_plan(r,engine=FakeEngine(),options_loader=OPTIONS)

    def test_error_does_not_leave_output_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            class BadEngine(FakeEngine):
                def convert(self,*args,**kw):
                    self.kw=kw
                    raise RuntimeError('optimizer failed')
            e=BadEngine()
            with self.assertRaisesRegex(RuntimeError,'optimizer failed'):
                run_plan(r,engine=e,options_loader=OPTIONS)
            self.assertFalse(Path(e.kw['output_dir']).exists())

    def test_window_keeps_forecast_on_main_thread_only(self):
        # Regression guard for real engine work crossing the Qt worker boundary.
        code = (Path(__file__).resolve().parents[1] / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        worker = (Path(__file__).resolve().parents[1] / 'desktop/qt_app/forecast_worker.py').read_text(encoding='utf-8')
        self.assertIn("ForecastWorker('forecast', request, self)",code)
        self.assertIn('if serial != self._forecast_serial:',code)
        self.assertIn("run_plan(self.argument, progress=report)",worker)
        self.assertIn("self._forecast_timer.setSingleShot(True)",code)

    def test_reject_wrong_engine_response(self):
        with tempfile.TemporaryDirectory() as d:
            r=fixture(d)
            class BadEngine(FakeEngine):
                def convert(self,*args,**kw):
                    return {'type':'conversion'}
            with self.assertRaisesRegex(RuntimeError,'instead of'):
                run_plan(r,engine=BadEngine(),options_loader=OPTIONS)


class OptionalQtStage4ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PySide6  # noqa
        except ImportError:
            raise unittest.SkipTest('PySide6 unavailable')

    def test_qt_window_shows_empty_state_without_forecast(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.qt_app.main_window import MainWindow
        app=QApplication.instance() or QApplication([])
        w=MainWindow()
        try:
            self.assertFalse(w.forecast_refresh.isEnabled())
            self.assertEqual(w.accuracy.text(),'—')
            self.assertFalse(w.compose_button.isEnabled())
        finally:
            w.close()


if __name__=='__main__': unittest.main()
