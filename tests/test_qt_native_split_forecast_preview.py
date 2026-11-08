"""Lossless native split-paint forecast overlay tests (no GUI or engine required)."""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import json
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from zipfile import ZipFile

from desktop.qt_app.native_split_forecast_preview import (
    _flat_slots, _paint_rgb, _read_unique_native_swatches,
    _recipe_rows, build_overlays, enabled, has_native_split_paint,
)

SWATCHES=['#68724D','#FFFFFF','#61C680','#000000',
          '#FF0000','#0000FF','#008040','#008000']


@dataclass(frozen=True)
class StubMesh:
    vertices: tuple
    triangles: tuple
    face_colors: tuple
    corner_colors: tuple
    source_triangles: int = 2
    split_painted_faces: int = 1
    split_paint_regions: int = 2
    color_status: str = 'Native split-paint source'
    render_buffer: object = None
    render_indexed: object = None
    load_profile: object = None


def fake_mesh(colors=('#61C680','#FFFFFF','#000000')):
    return StubMesh(
        ((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),
        ((0,1,2),(0,2,3),(0,1,3)),
        tuple(colors), tuple((c,c,c) for c in colors))


def fake_flatten(mesh):
    result=array('f')
    for face,color in zip(mesh.triangles,mesh.face_colors):
        rgb=tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
        for idx in face:
            result.extend((*mesh.vertices[idx],0.,0.,1.,*rgb,*rgb))
    return result


def fake_output():
    return {'type':'planPreview','sourceSlots':8,'realSlots':5,
            'recipes':[{'oldSlot':n,'newSlot':min(5,n),'targetColor':c,
                        'kind':'ANCHOR','label':'source','components':'',
                        'ratios':'','preview':c,'deltaE':0.0,
                        'directDeltaE':0.0,'visualGain':0.0}
                       for n,c in enumerate(SWATCHES,1)]}


def fake_plan(swatches, rows, real_count):
    assert len(rows)==8 and len(swatches)==8 and real_count==5
    return ([f'#{n:06X}' for n in range(1,9)],
            ['#F00000']*8,
            ['#00FFFF']*8)


def write_fixture(path, colors=SWATCHES, paint='481', mixed=None):
    doc={'filament_colour':colors}
    if mixed is not None:doc['filament_is_mixed']=mixed
    with ZipFile(path,'w') as archive:
        archive.writestr('Metadata/project_settings.config',json.dumps(doc))
        archive.writestr('3D/Objects/object_1.model',
                        '<triangle v1="0" v2="1" v3="2" paint_color="'+paint+'"/>')


class NativeSplitForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.model=self.root/'frog.3mf'
        write_fixture(self.model)

    def test_opt_in_defaults_off_and_accepts_explicit_flag(self):
        value=os.environ.get('FULLSPECTRUM_NATIVE_SPLIT_FORECAST')
        try:
            os.environ.pop('FULLSPECTRUM_NATIVE_SPLIT_FORECAST',None)
            self.assertFalse(enabled())
            os.environ['FULLSPECTRUM_NATIVE_SPLIT_FORECAST']='1'
            self.assertTrue(enabled())
        finally:
            if value is None:os.environ.pop('FULLSPECTRUM_NATIVE_SPLIT_FORECAST',None)
            else:os.environ['FULLSPECTRUM_NATIVE_SPLIT_FORECAST']=value

    def test_probe_recognizes_native_split_not_single_slot_leaf(self):
        self.assertTrue(has_native_split_paint(self.model))
        write_fixture(self.model,paint='0C')
        self.assertFalse(has_native_split_paint(self.model))

    def test_rebuilds_all_facets_and_source_slot_provenance(self):
        source=fake_mesh()
        indexed=[]
        def indexer(packed):
            indexed.append(len(packed))
            return None
        overlays,slotmap=build_overlays(
            self.model,fake_output(),self.root,
            loader=lambda _:source,flattener=fake_flatten,
            indexer=indexer,color_plan=fake_plan)
        self.assertEqual(set(overlays),{'predicted','loss','influence'})
        for mesh in overlays.values():
            self.assertEqual(mesh.triangles,source.triangles)
            self.assertEqual(mesh.source_triangles,2)
            self.assertEqual(mesh.split_painted_faces,1)
            self.assertEqual(len(mesh.render_buffer),len(mesh.triangles)*36)
        self.assertEqual(overlays['predicted'].face_colors,('#000003','#000002','#000004'))
        self.assertEqual(overlays['loss'].face_colors,('#F00000',)*3)
        self.assertEqual(overlays['influence'].face_colors,('#00FFFF',)*3)
        self.assertEqual(len(indexed),2)
        self.assertIsNone(overlays['influence'].render_indexed)
        self.assertEqual(struct.unpack('<3I',Path(slotmap).read_bytes()),(3,2,4))
        # Original source color tag is preserved in Predicted, even as RGB changes.
        source_packed=fake_flatten(source)
        pred=overlays['predicted'].render_buffer
        self.assertEqual(pred[9:12],source_packed[9:12])
        self.assertNotEqual(pred[6:9],source_packed[6:9])
        self.assertEqual(source.face_colors,('#61C680','#FFFFFF','#000000'))

    def test_ambiguous_duplicate_swatch_fails_closed(self):
        colors=SWATCHES.copy();colors[5]=colors[2]
        write_fixture(self.model,colors=colors)
        with self.assertRaisesRegex(ValueError,'share an RGB swatch'):
            _read_unique_native_swatches(self.model,8)

    def test_mixed_source_slots_do_not_fake_unchanged_provenance(self):
        write_fixture(self.model,mixed=['1']+['0']*7)
        with self.assertRaisesRegex(ValueError,'mixed-filament'):
            _read_unique_native_swatches(self.model,8)

    def test_unknown_face_color_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'does not uniquely identify'):
            _flat_slots(fake_mesh(('#61C680','#FFFFFF','#DD00DD')),SWATCHES)

    def test_interpolated_vertex_colors_fail_closed(self):
        source=fake_mesh()
        source=StubMesh(source.vertices,source.triangles,source.face_colors,
                        (('#FFFFFF','#61C680','#FFFFFF'),)+source.corner_colors[1:])
        with self.assertRaisesRegex(ValueError,'gradients'):
            _flat_slots(source,SWATCHES)

    def test_missing_recipe_fails_closed(self):
        model=fake_output()
        model['recipes']=model['recipes'][:-1]
        with self.assertRaisesRegex(ValueError,'omitted'):
            _recipe_rows(model,8)

    def test_direct_vertex_color_replacement_preserves_original_paint_tags(self):
        original=fake_flatten(fake_mesh())
        slots=[3,2,4]
        colors=['#A1B2C3']*8
        updated=_paint_rgb(original,colors,slots)
        self.assertEqual(updated[6:9],array('f',(161/255,178/255,195/255)))
        self.assertEqual(updated[9:12],original[9:12])
        self.assertEqual(original[6:9],array('f',(97/255,198/255,128/255)))
        self.assertIsNot(original,updated)

    @unittest.skipUnless(os.environ.get('FULLSPECTRUM_PAINT_FIXTURE'),
                         'Set FULLSPECTRUM_PAINT_FIXTURE to a real multicolor 3MF')
    def test_real_frog_uses_the_same_split_presence_probe(self):
        path=Path(os.environ['FULLSPECTRUM_PAINT_FIXTURE'])
        self.assertTrue(has_native_split_paint(path))
        self.assertEqual(len(_read_unique_native_swatches(path,8)),8)
        if importlib.util.find_spec('desktop.qt_app.mesh_loader') is None:
            return  # Real decoded geometry requires the full Qt application repository.
        overlays, slotmap = build_overlays(
            path, fake_output(), self.root, indexer=lambda _: None,
            color_plan=fake_plan)
        self.assertEqual(len(overlays['predicted'].triangles),13033)
        self.assertEqual(overlays['predicted'].source_triangles,424)
        self.assertEqual(overlays['predicted'].split_painted_faces,2)
        self.assertEqual(len(Path(slotmap).read_bytes()),13033*4)
        # Verify all source region IDs survived, not just the palette summary.
        values=struct.unpack('<13033I',Path(slotmap).read_bytes())
        self.assertIn(2,values)
        self.assertIn(3,values)
        self.assertIn(4,values)


if __name__=='__main__':unittest.main()
