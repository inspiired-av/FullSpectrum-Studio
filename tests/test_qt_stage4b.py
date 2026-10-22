"""Stage 4B: existing engine's physical/mixed palette details, no fake metrics."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from desktop.qt_app.planning_details import _components, build_details
from desktop.qt_app.forecast_service import run_plan


BASE = dict(strategy='official',source='catalog',custom='',real_slots='auto',quality_bias=80,
            smart_quality=False,catalog_region='global',planner_mode='best',
            planning_sample='paint',max_output_colors='12',output_color_strategy='maximum_fidelity',
            native_project_template='')


class Stage4BParsingTests(unittest.TestCase):
    def payload(self):
        return {
            'realSlots': 2, 'outputSlots': 3, 'sourceSlots': 19,
            'maxOutputColors': '5', 'plannerMode': 'best', 'qualityBias': 85,
            'qualityBiasMode': 'auto', 'printability': {'difficulty': 'High'},
            'pinnedAnchorKeys': ['PLA Basic|#000000'],
            'anchors': [
                {'slot': 1, 'key': 'PLA Basic|#000000', 'name': 'PLA Basic - Black',
                 'color': '#000000', 'preset': 'PLA Basic @base', 'remainingGrams': 100},
                {'slot': 2, 'key': 'PLA Basic|#FFFFFF', 'name': 'PLA Basic - White',
                 'color': '#ffffff', 'remainingGrams': None}],
            'recipes': [
                {'kind': 'MIX', 'oldSlot': 1, 'newSlot': 3, 'preview': '#999999',
                 'components': '1,2', 'ratios': '0.35,0.65', 'deltaE': 2.2},
                {'kind': 'MIX', 'oldSlot': 2, 'newSlot': 3, 'preview': '#999999',
                 'components': '1,2', 'ratios': '0.35,0.65', 'deltaE': 3.5},
                {'kind': 'SOLID', 'oldSlot': 3, 'newSlot': 1, 'preview': '#000000',
                 'components': '', 'ratios': '', 'deltaE': 0.0},
            ],
        }

    def test_unique_output_slot_not_source_recipe_count(self):
        d = build_details(self.payload())
        self.assertEqual(len(d.physical), 2)
        self.assertEqual(len(d.mixed), 1)
        self.assertEqual(d.mixed[0]['states'], 2)
        self.assertAlmostEqual(d.mixed[0]['maxDeltaE'], 3.5)
        self.assertEqual(d.mixed[0]['components'], '1 (35%) + 2 (65%)')

    def test_pin_and_source_metrics_are_truthful(self):
        d = build_details(self.payload())
        self.assertEqual(d.pin_count, 1)
        self.assertEqual(d.physical[0]['remainingGrams'], 100.0)
        self.assertEqual(d.source_slots, 19)
        self.assertEqual(d.slot_summary, '3 / 5 allowed · 2 physical + 1 mixed')
        self.assertEqual(d.quality_bias, 'Smart (85/100)')
        self.assertEqual(d.printability, 'High')

    def test_no_fabrication_when_missing_data(self):
        d = build_details({'realSlots': 4, 'outputSlots': 8, 'maxOutputColors': 'auto'})
        self.assertFalse(d.physical)
        self.assertFalse(d.mixed)
        self.assertEqual(d.printability, 'Not estimated')
        self.assertEqual(d.quality_bias, '—')
        self.assertIn('Auto cap', d.slot_summary)

    def test_invalid_components_or_ratios_are_not_guessed(self):
        self.assertEqual(_components('1,2', 'garbage'), '')
        self.assertEqual(_components('1,2', '0.5'), '')
        self.assertEqual(_components('1,2', 'nan,0.5'), '')

    def test_out_of_range_slots_rejected(self):
        data = self.payload()
        data['recipes'].append({'kind': 'MIX', 'newSlot': 90, 'preview': '#FF00FF'})
        data['anchors'].append({'slot': 90, 'color': '#abc123'})
        d = build_details(data)
        self.assertEqual(len(d.mixed), 1)
        self.assertEqual(len(d.physical), 2)


class Stage4BEngineContractTests(unittest.TestCase):
    def test_optimizer_payload_is_forwarded_without_second_optimization(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / 'source.3mf'
            model.write_bytes(b'test only')
            req = SimpleNamespace(model=str(model),reference=None,settings=dict(BASE),
                                  disabled=frozenset(),pinned=frozenset({'B'}),protections=())
            class FakeEngine:
                calls = 0
                def is_standard_colored_3mf(self,path):return True
                def convert(self,*args,**kwargs):
                    self.calls += 1
                    self.kw=kwargs
                    assert kwargs['plan_only'] and not kwargs['reveal']
                    return {'type': 'planPreview','quality': {'qualityScore': 85},
                            'realSlots':2,'outputSlots':3,'sourceSlots':7,
                            'outputColors':['#000000','#FFFFFF','#888888'],
                            'anchors':[{'slot':1,'key':'B','color':'#000000','name':'Black'}],
                            'recipes':[{'oldSlot':1,'newSlot':3,'kind':'MIX','components':'1,2',
                                        'ratios':'0.5,0.5','preview':'#888888'}],
                            'pinnedAnchorKeys':['B'],'qualityBiasMode':'auto','qualityBias':75,
                            'printability': {'difficulty':'Low'},'warnings':[]}
            engine=FakeEngine()
            options=lambda _eng,_src,_custom:[{'key':'B','color':'#000000'},
                                               {'key':'W','color':'#FFFFFF'}]
            got=run_plan(req,engine=engine,options_loader=options)
            self.assertEqual(engine.calls,1)
            self.assertEqual(got['planningDetails']['anchors'][0]['key'],'B')
            self.assertEqual(got['planningDetails']['recipes'][0]['newSlot'],3)
            self.assertEqual(got['planningDetails']['maxOutputColors'],'12')
            self.assertEqual(got['planningDetails']['pinnedAnchorKeys'],['B'])
            self.assertFalse(Path(engine.kw['output_dir']).exists())

    def test_core_qt_contract_preserves_last_forecast_as_stale(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('self.planning_details_panel.set_stale(True)',source)
        self.assertIn('self.planning_details_panel.clear_result()',source)
        self.assertIn("self.planning_details_panel.set_result(result.get('planningDetails') or {})",source)
        self.assertIn('self.planning_details_panel.review_filament.connect',source)
        self.assertIn('self.filaments_panel.search.setText',source)
        self.assertIn('self.details_toggle.setChecked(False)',source)


class QtPlanningDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try: import PySide6
        except ImportError: raise unittest.SkipTest('PySide6 not installed here')
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_counts_and_review_does_not_mutate_settings(self):
        from desktop.qt_app.planning_details_panel import PlanningDetailsPanel
        p=PlanningDetailsPanel()
        data=Stage4BParsingTests().payload()
        try:
            p.set_result(data)
            self.assertEqual(p.physical.rowCount(),2)
            self.assertEqual(p.mixed.rowCount(),1)
            selected=[]
            p.review_filament.connect(selected.append)
            p.physical.selectRow(0)
            p._review()
            self.assertEqual(selected,['PLA Basic|#000000'])
            p.set_stale(True)
            self.assertIn('OUTDATED FORECAST', p.stale_notice.text())
            self.assertFalse(p.stale_notice.isHidden())
            p.clear_result()
            self.assertEqual(p.physical.rowCount(),0)
        finally:p.close()


if __name__=='__main__':unittest.main()
