"""Offline deterministic tests for Phase 3 global recipe allocation."""
import unittest
from global_recipe_optimizer import optimize_direct_palette


def d(a,b):
    return abs(int(a[1:],16)-int(b[1:],16))


def n(anchor):
    return anchor['name']


class GlobalRecipeOptimizerTests(unittest.TestCase):
    def fixture(self):
        anchors=[{'name':'Black','color':'#000000'},{'name':'White','color':'#000064'}]
        # Greedy per-target old recipes [#30,#60] are suboptimal for a global
        # weight distribution in which the near-#40 colors dominate.
        old=['#000000','#000064','#000030','#000060']
        sources=['#000032','#000034','#000036','#00003A','#000064']
        flags=['0','0','1','1']
        comps=['','','1,2','1,2']
        ratios=['','','0.5000,0.5000','0.1000,0.9000']
        mapping={1:3,2:3,3:3,4:4,5:2}
        rows=[]
        for i,c in enumerate(sources,1):
            slot=mapping[i]
            rows.append([i,slot,c,'MIX' if slot>2 else 'SOLID' if i==5 else 'ANCHOR',
                         '' if slot>2 else 'White',
                         comps[slot-1],ratios[slot-1],old[slot-1],
                         str(d(c,old[slot-1])),str(min(d(c,x) for x in old[:2])),'0.00'])
        recipes=[((1,2),(.4,.6),'#00003C'),((1,2),(.5,.5),'#000032'),((1,2),(.7,.3),'#000046')]
        return sources,anchors,(old,flags,comps,ratios,mapping,rows),recipes

    def run_opt(self, usage=None, budget=4):
        sources,anchors,palette,recipes=self.fixture()
        result,info=optimize_direct_palette(
            sources, usage or {1:20,2:20,3:20,4:20,5:10},palette,anchors,{5:'grey'},d,n,
            recipes,budget
        )
        return result,info

    def test_global_selection_improves_weighted_source_error_without_more_slots(self):
        result,info=self.run_opt()
        self.assertTrue(info['accepted'],info)
        self.assertLess(info['meanAfter'],info['meanBefore'])
        self.assertLessEqual(info['worstAfter'],info['worstBefore'])
        self.assertLessEqual(len(result[0]),4)
        self.assertEqual(result[0][:2],['#000000','#000064'])

    def test_protected_physical_slot_unchanged(self):
        result,info=self.run_opt()
        self.assertEqual(result[4][5],2)
        self.assertEqual(result[5][4][3],'SOLID')
        self.assertEqual(result[5][4][7],'#000064')

    def test_lower_budget_respected(self):
        result,info=self.run_opt(budget=3)
        self.assertLessEqual(len(result[0]),3)
        self.assertEqual(len(result[0]),len(result[1]))
        self.assertEqual(len(result[0]),len(result[2]))
        self.assertEqual(len(result[0]),len(result[3]))

    def test_reject_invalid_nonphysical_components(self):
        sources,anchors,palette,recipes=self.fixture()
        recipes=[((1,3),(.5,.5),'#000052')]
        with self.assertRaisesRegex(ValueError,'nonphysical'):
            optimize_direct_palette(sources,{i:1 for i in range(1,6)},palette,anchors,{5:'grey'},d,n,recipes,4)

    def test_repeated_result_is_deterministic(self):
        a,info_a=self.run_opt()
        b,info_b=self.run_opt()
        self.assertEqual(a,b)
        self.assertEqual(info_a,info_b)

    def test_no_gain_keeps_existing_palette(self):
        sources,anchors,palette,recipes=self.fixture()
        unchanged,info=optimize_direct_palette(sources,{i:1 for i in range(1,6)},palette,anchors,{5:'grey'},d,n,[],4)
        self.assertIs(unchanged,palette) if not info['accepted'] else self.assertTrue(info['meanAfter']<info['meanBefore'])

    def test_empty_nonprotected_weights_are_handled(self):
        result,info=self.run_opt(usage={5:10})
        self.assertTrue(isinstance(info['accepted'],bool))
        self.assertEqual(result[4][5],2)

if __name__=='__main__':
    unittest.main()
