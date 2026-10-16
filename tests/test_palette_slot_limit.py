"""Regression tests for the explicit maximum output palette size."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('engine_color_limit', ROOT/'fullspectrum_engine.py')
ENGINE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)


class OutputColorLimitTests(unittest.TestCase):
    def setUp(self):
        self.anchors=[
            {'name':'Black','color':'#000000'},
            {'name':'White','color':'#FFFFFF'},
        ]
        self.targets=[f'#{i:02X}{i:02X}{i:02X}' for i in range(1,33)]
        # Deterministic mock isolates palette allocation from expensive color
        # optimization: 32 source shades have 32 distinct beneficial mixtures.
        def recipe(target, anchors, mix_model, allow_three=False, high_fidelity=False):
            n=int(target[1:3],16)
            return [1,2],[n/100,1-n/100],target,1.0
        self.recipe=recipe

    def palette(self, cap):
        with patch.object(ENGINE,'nearest_anchor_error',return_value=(20.0,1,'Black','#000000')):
            with patch.object(ENGINE,'best_mix_recipe',side_effect=self.recipe):
                return ENGINE.build_palette(self.targets,self.anchors,quality_bias=100,
                                            max_output_colors=cap)

    def test_explicit_count_never_exceeds_total_slot_cap(self):
        for cap in (2,4,8,16,24,32):
            with self.subTest(cap=cap):
                palette=self.palette(cap)
                self.assertEqual(len(palette[0]),cap)
                self.assertEqual(len(palette[1]),cap)
                self.assertTrue(all(s <= cap for s in palette[4].values()))

    def test_auto_retains_default_behavior(self):
        with patch.object(ENGINE,'nearest_anchor_error',return_value=(20.0,1,'Black','#000000')):
            with patch.object(ENGINE,'best_mix_recipe',side_effect=self.recipe):
                one=ENGINE.build_palette(self.targets,self.anchors,quality_bias=100)
                two=ENGINE.build_palette(self.targets,self.anchors,quality_bias=100,
                                         max_output_colors='auto')
        self.assertEqual(one,two)

    def test_bad_values_rejected(self):
        for cap in (0,1,33,'forty','',True):
            with self.subTest(cap=cap):
                with self.assertRaises(RuntimeError):
                    ENGINE.normalize_max_output_colors(cap)
        with self.assertRaisesRegex(RuntimeError,'physical slots'):
            ENGINE.build_palette(
                self.targets, self.anchors + [{'name':'Red','color':'#FF0000'}],
                max_output_colors=2
            )

if __name__=='__main__':
    unittest.main()
