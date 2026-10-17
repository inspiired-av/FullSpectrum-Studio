"""Stage 4D-A: dominant physical colors, true recipe shares and provenance tests."""
from __future__ import annotations
from array import array
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import ast
import unittest
from anchor_preview_map import write_face_slot_map
from desktop.qt_app.anchor_influence import (
    recipe_weights, gpu_weight_texture, read_face_slots, prepare_influence,
    CATEGORIES, apply_face_slot_tags,
)

ROOT=Path(__file__).resolve().parents[1]

def anchors():
    return [{'slot':i,'color':c,'name':f'PLA {i}'}
            for i,c in enumerate(('#111111','#EEEEEE','#FF0000'),1)]

def recipes():
    return [dict(oldSlot=1,newSlot=5,kind='MIX',components='1,2',ratios='0.2,0.8'),
            dict(oldSlot=2,newSlot=6,kind='MIX',components='3,2',ratios='0.4,0.6'),
            dict(oldSlot=3,newSlot=1,kind='ANCHOR',components='',ratios=''),
            dict(oldSlot=4,newSlot=7,kind='MIX',components='3,2,1',ratios='0.25,0.25,0.50')]

@dataclass(frozen=True)
class Mesh:
    triangles:tuple=((0,1,2),(0,2,3),(0,3,1),(1,2,3))
    render_buffer:object=None

class RecipeTests(unittest.TestCase):
    def test_largest_ratio_not_first_component(self):
        ws=recipe_weights(recipes(),4,anchors())
        self.assertAlmostEqual(ws[0][1],0.8)
        self.assertAlmostEqual(ws[1][1],0.6)
        self.assertEqual(ws[2],(1.0,0.0,0.0))
        # Three-way mixture includes secondary and tertiary components.
        self.assertEqual(ws[3],(0.5,0.25,0.25))
        texture=gpu_weight_texture(ws,3)
        # texel: each row has 8 RGBA pixels. In first source row dominant is 2.
        self.assertEqual(texture[32+1],2.0)
        self.assertAlmostEqual(texture[32+4],0.8)
        # Tie between physical 2 and 3 in source slot 4 -> physical 1 wins at 50%.
        self.assertEqual(texture[4*32+1],1.0)

    def test_tie_break_is_lowest_physical_slot_not_component_order(self):
        row=[dict(oldSlot=1,newSlot=4,kind='MIX',components='3,1',ratios='0.5,0.5')]
        out=gpu_weight_texture(recipe_weights(row,1,anchors()),3)
        self.assertEqual(out[32+1],1.0)
        self.assertAlmostEqual(out[32],0.5)
        self.assertAlmostEqual(out[32+8],0.5)

    def test_malformed_or_missing_ratios_fail_closed(self):
        invalid=[dict(oldSlot=1,newSlot=4,kind='MIX',components='1,2',ratios='0.1,0.1')]
        with self.assertRaisesRegex(ValueError,'Invalid physical mixture'):
            recipe_weights(invalid,1,anchors())
        with self.assertRaisesRegex(ValueError,'omitted'):
            recipe_weights(recipes()[:-1],4,anchors())
        with self.assertRaises(ValueError):
            recipe_weights(recipes()+[recipes()[0]],4,anchors())
        with self.assertRaises(ValueError):
            recipe_weights([dict(oldSlot=1,newSlot=2,kind='SOLID',components='',ratios='')],3,anchors())

class ProvenanceTests(unittest.TestCase):
    def test_native_obj_material_source_slots_and_order(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            model=root/'plan.obj'
            model.write_text('mtllib plan.mtl\nusemtl slot_2\nf 1 2 3\n'
                             'usemtl slot_1\nf 3 4 5\nf 5 6 7\n',encoding='utf-8')
            artifact=write_face_slot_map(root/'mapping.bin',source_mesh=model)
            self.assertEqual(read_face_slots(artifact,root,3,3),(2,1,1))
            with self.assertRaises(ValueError):
                read_face_slots(artifact,root,4,3)

    def test_direct_face_color_order_and_sandbox(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            artifact=write_face_slot_map(root/'mapping.bin',direct_source={
                'face_colors':['#00FF00','#FF0000','#00FF00'],
                'source_slots':{'#FF0000':1,'#00FF00':2},
            })
            self.assertEqual(read_face_slots(artifact,root,3,2),(2,1,2))
            with self.assertRaises(ValueError):
                read_face_slots(artifact,root/'elsewhere',3,2)

    def test_cpu_buffers_are_only_modified_for_influence(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            artifact=write_face_slot_map(root/'mapping.bin',direct_source={
                'face_colors':['#FF0000']*4, 'source_slots':{'#FF0000':1}})
            colors=array('f',[0.0]*144)
            mesh=Mesh(render_buffer=colors)
            meta=prepare_influence({'sourceSlotMap':str(artifact)},root,mesh,
                recipes(),anchors(),4)
            self.assertEqual(meta['sourceCount'],4)
            self.assertEqual(len(meta['weights']), (4+1)*8*4)
            self.assertEqual(meta['anchors'][0],('#111111',CATEGORIES[0]))
            for face in range(4):
                self.assertEqual(colors[face*36+9],1.0)
                self.assertEqual(colors[face*36+21],1.0)
                self.assertEqual(colors[face*36+33],1.0)
            self.assertEqual(colors[0],0.0)

class Contracts(unittest.TestCase):
    def test_source_uses_gpu_not_expensive_cpu_recolor_on_click(self):
        gl=(ROOT/'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8')
        main=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        service=(ROOT/'desktop/qt_app/forecast_service.py').read_text(encoding='utf-8')
        engine=(ROOT/'fullspectrum_engine.py').read_text(encoding='utf-8')
        for part in ('influenceWeights','texelFetch','influencePhysicalColors',
                     'influenceCategoricalColors','influenceSelectedSlot'):
            self.assertIn(part,gl)
        self.assertIn('self.preview_surface.set_influence_analysis(',main)
        self.assertIn('previewInfluence',service)
        self.assertIn('write_face_slot_map',engine)
        self.assertIn('plan_only=True',service)
        self.assertIn('preserve_camera=True',main)

try:
    import PySide6
except ImportError:
    PySide6=None

@unittest.skipUnless(PySide6 is not None,'PySide6 unavailable')
class QtAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_clickable_legend_physical_is_default_and_toggles_selection(self):
        from PySide6.QtWidgets import QWidget
        from desktop.qt_app.preview_legend import AnchorInfluenceLegend
        parent=QWidget();parent.resize(630,440)
        legend=AnchorInfluenceLegend(parent)
        rows=[dict(slot=i,name=f'PLA {i}',filament=anchor['color'],
                   overlay=CATEGORIES[i-1],pinned=False)
              for i,anchor in enumerate(anchors(),1)]
        selected=[]
        legend.anchor_selected.connect(selected.append)
        legend.set_rows(rows)
        try:
            parent.show();legend.show();self.app.processEvents()
            self.assertEqual(legend.color_mode,'physical')
            legend._choose(2)
            self.assertEqual(selected, [2])
            self.assertEqual(legend.selected_slot,2)
            self.assertTrue(legend._gradient.isVisible())
            legend._choose(2)
            self.assertEqual(selected,[2,0])
            self.assertEqual(legend.selected_slot,0)
            legend.display.setCurrentIndex(1)
            self.assertEqual(legend.color_mode,'categorical')
        finally:
            parent.close()

if __name__=='__main__':unittest.main()
