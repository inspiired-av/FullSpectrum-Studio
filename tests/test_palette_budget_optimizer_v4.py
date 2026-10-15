import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from palette_budget_optimizer import allocate_palette,normalize_output_color_strategy


def distance(a,b):
    return abs(int(a[1:3],16)-int(b[1:3],16)) / 10.0


def anchor_name(a):
    return a['name']


class PaletteBudgetStrategyTests(unittest.TestCase):
    def setUp(self):
        self.sources=['#000000','#101010','#808080','#D0D0D0','#EFEFEF']
        self.anchors=[{'name':'Black'},{'name':'White'}]
        # Black & White have unique physical color previews.
        self.palette=(
            ['#000000','#FFFFFF','#707070'], ['0','0','1'],
            ['','','1,2'],['','','0.5000,0.5000'],
            {1:1,2:1,3:3,4:2,5:2},
            [[1,1,self.sources[0],'SOLID','Black','','','#000000','0.00','0.00','0.00'],
             [2,1,self.sources[1],'ANCHOR','Black','','','#000000','1.60','1.60','0.00'],
             [3,3,self.sources[2],'MIX','','1,2','0.5000,0.5000','#707070','1.60','12.80','11.20'],
             [4,2,self.sources[3],'ANCHOR','White','','','#FFFFFF','4.70','4.70','0.00'],
             [5,2,self.sources[4],'ANCHOR','White','','','#FFFFFF','1.60','1.60','0.00']]
        )
        self.recipes=[((1,2),(.4,.6),'#888888'),
                      ((1,2),(.2,.8),'#D0D0D0'),
                      ((1,2),(.1,.9),'#EFEFEF'),
                      ((1,2),(.3,.7),'#A0A0A0'),
                      ((1,2),(.6,.4),'#555555')]
        self.weights={i:1 for i in range(1,6)}

    def run_strategy(self,strategy,count=5,recipes=None):
        return allocate_palette(
            self.sources,self.weights,self.palette,self.anchors,{1:'black'},
            distance,anchor_name,self.recipes if recipes is None else recipes,
            count,strategy)

    def test_normalize(self):
        for s in ['balanced','maximum_fidelity','fill_palette']:
            self.assertEqual(normalize_output_color_strategy(s),s)
        with self.assertRaises(ValueError):
            normalize_output_color_strategy('unknown')

    def test_balanced_can_prune_low_value_mixtures(self):
        palette,info=self.run_strategy('balanced')
        self.assertTrue(info['accepted'])
        self.assertLessEqual(info['outputSlots'],5)
        self.assertEqual(palette[4][1],1)

    def test_maximum_fidelity_uses_better_mix(self):
        palette,info=self.run_strategy('maximum_fidelity')
        self.assertTrue(info['accepted'])
        self.assertLess(info['meanAfter'],info['meanBefore'])
        self.assertLessEqual(info['worstAfter'],info['worstBefore'])
        self.assertLessEqual(len(palette[0]),5)
        self.assertEqual(palette[4][1],1)
        self.assertEqual(palette[5][0][3],'SOLID')
        self.assertEqual(palette[5][0][1],1)

    def test_maximum_fidelity_does_not_fill_no_gain(self):
        # A perfect physical representation of all targets cannot benefit from
        # extra mixes. Force sources equal to physical only.
        colors=['#000000','#FFFFFF']
        p=(self.palette[0][:2],['0','0'],['',''],['',''],{1:1,2:2},
           [[1,1,colors[0],'SOLID','Black','','',colors[0],'0','0','0'],
            [2,2,colors[1],'ANCHOR','White','','',colors[1],'0','0','0']])
        result,info=allocate_palette(colors,{1:1,2:1},p,self.anchors,{1:'black'},
            distance,anchor_name,self.recipes,5,'maximum_fidelity')
        self.assertEqual(len(result[0]),2)
        self.assertFalse(info['accepted'])

    def test_fill_palette_reaches_requested_cap(self):
        palette,info=self.run_strategy('fill_palette',5)
        self.assertTrue(info['accepted'])
        self.assertEqual(len(palette[0]),5)
        self.assertEqual(len(set(palette[0])),5)
        self.assertTrue(all(slot <= 5 for slot in palette[4].values()))
        self.assertEqual(palette[4][1],1)

    def test_fill_palette_distinct_pool_limit(self):
        palette,info=self.run_strategy('fill_palette',5,recipes=[((1,2),(.4,.6),'#888888')])
        self.assertTrue(info['accepted'])
        self.assertEqual(len(palette[0]),4)
        self.assertIn('only 4',info['reason'])

    def test_refuse_too_small_budget(self):
        with self.assertRaises(ValueError):
            self.run_strategy('fill_palette',1)
        with self.assertRaises(ValueError):
            self.run_strategy('maximum_fidelity',33)

    def test_reject_malformed_mix(self):
        with self.assertRaises(ValueError):
            self.run_strategy('fill_palette',5,[((1,3),(.5,.5),'#222222')])


if __name__=='__main__':unittest.main()
