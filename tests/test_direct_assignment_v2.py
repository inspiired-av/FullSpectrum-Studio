"""Phase 3 v2 global palette mapping, including protected-source invariants."""
import unittest
from direct_source_palette import globally_reassign_colors


def dist(a,b):
    # Synthetic signed integer-color metric makes regression deterministic.
    return abs(int(a[1:],16)-int(b[1:],16))


def name(a):
    return a['name']


def color(a):
    return a['color']


class GlobalDirectAssignmentTests(unittest.TestCase):
    def fixture(self):
        anchors=[{'name':'Grey','color':'#000064'},{'name':'Dark','color':'#000000'}]
        colors=['#000063','#00004F','#000017','#000001']
        # Source #00004F's first-choice recipe lost its allocation. Old code
        # left the nearest physical (#000064, distance 21) even though an
        # already-allocated mix (#000050, distance 1) was available.
        output=['#000064','#000000','#000050','#000018']
        flags=['0','0','1','1']
        comps=['','','1,2','1,2']
        ratios=['','','0.5000,0.5000','0.8000,0.2000']
        rows=[
            [1,1,colors[0],'SOLID','Grey','','',output[0],'1.00','1.00','0.00'],
            [2,1,colors[1],'ANCHOR','Grey','','',output[0],'21.00','21.00','0.00'],
            [3,4,colors[2],'MIX','',comps[3],ratios[3],output[3],'1.00','23.00','22.00'],
            [4,2,colors[3],'ANCHOR','Dark','','',output[1],'1.00','1.00','0.00'],
        ]
        return colors,(output,flags,comps,ratios,{1:1,2:1,3:4,4:2},rows),anchors

    def test_grey_protection_remains_solid_and_bad_fallback_recovers_mix(self):
        colors,palette,anchors=self.fixture()
        result,info=globally_reassign_colors(colors,palette,anchors,{1:'grey'},dist,name,color)
        self.assertEqual(result[4][1],1)
        self.assertEqual(result[5][0][3],'SOLID')
        self.assertEqual(result[4][2],3)
        self.assertEqual(result[5][1][3],'MIX')
        self.assertEqual(result[5][1][5],'1,2')
        self.assertEqual(result[5][1][6],'0.5000,0.5000')
        self.assertEqual(info['worstBefore'],21)
        self.assertEqual(info['worstAfter'],1)
        self.assertEqual(info['improved'],1)
        self.assertEqual(result[:4],palette[:4])

    def test_reassignment_is_deterministic_and_idempotent(self):
        colors,palette,anchors=self.fixture()
        first,_=globally_reassign_colors(colors,palette,anchors,{1:'grey'},dist,name,color)
        second,info=globally_reassign_colors(colors,first,anchors,{1:'grey'},dist,name,color)
        self.assertEqual(first,second)
        self.assertEqual(info['reassigned'],0)

    def test_does_not_assign_nonexistent_or_invalid_mixed_recipe(self):
        colors,palette,anchors=self.fixture()
        palette[2][2]=''
        with self.assertRaisesRegex(RuntimeError,'no valid mixed filament recipe'):
            globally_reassign_colors(colors,palette,anchors,{1:'grey'},dist,name,color)

    def test_rejects_inconsistent_source_row_indexing(self):
        colors,palette,anchors=self.fixture()
        palette[5][1][0]=99
        with self.assertRaisesRegex(RuntimeError,'not aligned'):
            globally_reassign_colors(colors,palette,anchors,{1:'grey'},dist,name,color)

    def test_rejects_broken_solid_protection(self):
        colors,palette,anchors=self.fixture()
        palette[5][0][3]='ANCHOR'
        with self.assertRaisesRegex(RuntimeError,'Protected exact'):
            globally_reassign_colors(colors,palette,anchors,{1:'grey'},dist,name,color)


if __name__=='__main__':
    unittest.main()
