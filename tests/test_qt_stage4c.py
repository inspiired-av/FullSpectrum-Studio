"""Stage 4C: production forecast previews, bounds, and engine contract.

These tests intentionally never import patch/installer modules. They must
run from the installed Git checkout with `unittest discover -s tests`.
"""
from array import array
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop.qt_app.forecast_preview_assets import (
    MAX_PREVIEW_TRIANGLES, load_forecast_previews, recolor_buffer,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SampleMesh:
    vertices: tuple = ((0.,0.,0.),(1.,0.,0.),(0.,1.,0.))
    triangles: tuple = ((0, 1, 2),)
    face_colors: tuple = ('#123456',)
    render_buffer: object = None


def sample_buffer():
    # Position, normal, diffuse RGB and exact source tag; 12 floats per vertex.
    return array('f', sum((list(v)+[0,0,1,.1,.2,.3,.1,.2,.3] for v in SampleMesh().vertices),[]))


class AnalysisAssetTests(unittest.TestCase):
    def test_forecast_assets_are_consumed_in_memory(self):
        with TemporaryDirectory() as d:
            root=Path(d)/'analysis';root.mkdir()
            p=root/'predicted.obj'
            p.write_text('mock',encoding='utf-8')
            p.with_suffix('.mtl').write_text('mock',encoding='utf-8')
            meshes,note=load_forecast_previews(
                {'predictedMesh':str(p)},root,
                loader=lambda _:SampleMesh(),flattener=lambda _:sample_buffer())
            self.assertEqual(set(meshes),{'predicted'})
            self.assertEqual(meshes['predicted'].face_colors,('#123456',))
            self.assertFalse(note)
        self.assertEqual(len(meshes['predicted'].render_buffer),36)

    def test_rejects_outside_workspace_and_missing_mtl(self):
        with TemporaryDirectory() as d:
            root=Path(d)/'analysis';root.mkdir()
            p=Path(d)/'other.obj';p.write_text('mock',encoding='utf-8')
            p.with_suffix('.mtl').write_text('mock',encoding='utf-8')
            meshes,note=load_forecast_previews({'predictedMesh':str(p)},root,
                loader=lambda _:self.fail('outside workspace'),flattener=lambda _:())
            self.assertEqual(meshes,{})
            self.assertIn('unavailable',note)
            p=root/'inside.obj';p.write_text('mock',encoding='utf-8')
            meshes,note=load_forecast_previews({'predictedMesh':str(p)},root,
                loader=lambda _:self.fail('missing MTL'),flattener=lambda _:())
            self.assertEqual(meshes,{})
            self.assertIn('MTL',note)

    def test_geometry_reuse_colors_only(self):
        first=SampleMesh(render_buffer=sample_buffer())
        second=SampleMesh(face_colors=('#FF0000',))
        result=recolor_buffer(first,second)
        self.assertEqual(tuple(result[6:9]),(1.0,0.0,0.0))
        self.assertEqual(tuple(result[9:12]),(1.0,0.0,0.0))
        self.assertEqual(tuple(result[0:6]),tuple(first.render_buffer[0:6]))
        self.assertEqual(tuple(first.render_buffer[6:9]),tuple(sample_buffer()[6:9]))
        self.assertIsNone(recolor_buffer(first,SampleMesh(vertices=((1,1,1),)*3)))

    def test_three_modes_share_geometry_without_reflattening(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            paths={}
            for name in ('predicted','heatmap','influence'):
                p=root/(name+'.obj'); p.write_text('mock',encoding='utf-8')
                p.with_suffix('.mtl').write_text('mock',encoding='utf-8')
                paths[name]=str(p)
            colors={'predicted':'#FF0000','heatmap':'#37C977','influence':'#28B8D5'}
            prepared=[]
            def loader(path):
                return SampleMesh(face_colors=(colors[path.stem],))
            def flattener(mesh):
                prepared.append(mesh)
                return sample_buffer()
            meshes,note=load_forecast_previews(
                {'predictedMesh':paths['predicted'],'heatmapMesh':paths['heatmap'],
                 'anchorInfluenceMesh':paths['influence']},root,loader=loader,flattener=flattener)
            self.assertEqual(set(meshes),{'predicted','loss','influence'})
            self.assertEqual(len(prepared),1)
            self.assertFalse(note)
            for actual, expected in zip(meshes['loss'].render_buffer[6:9],
                                        (int('37C977'[i:i+2],16)/255 for i in (0,2,4))):
                self.assertAlmostEqual(actual,expected,places=6)

    def test_large_display_model_not_rejected_arbitrarily(self):
        self.assertGreaterEqual(MAX_PREVIEW_TRIANGLES,450_992)
        self.assertLessEqual(MAX_PREVIEW_TRIANGLES,750_000)

    def test_full_surface_cap_still_rejects_unbounded_geometry(self):
        with TemporaryDirectory() as d:
            root=Path(d);p=root/'large.obj'
            p.write_text('mock',encoding='utf-8')
            p.with_suffix('.mtl').write_text('mock',encoding='utf-8')
            meshes,note=load_forecast_previews({'predictedMesh':str(p)},root,
                loader=lambda _:SampleMesh(triangles=((0,1,2),)*(MAX_PREVIEW_TRIANGLES+1)),
                flattener=lambda _:self.fail('Oversized mesh should not flatten'))
            self.assertFalse(meshes)
            self.assertIn('triangle',note)

    def test_no_analysis_assets_is_explicit(self):
        with TemporaryDirectory() as d:
            meshes,note=load_forecast_previews(None,Path(d))
            self.assertFalse(meshes)
            self.assertIn('did not generate',note)


class RuntimeContractTests(unittest.TestCase):
    def test_engine_plan_only_direct_path_generates_all_three(self):
        engine=(ROOT/'fullspectrum_engine.py').read_text(encoding='utf-8')
        self.assertIn('if direct_source is not None and analysis_dir:',engine)
        self.assertIn('identity_slots={slot:slot for slot in range(1,len(old)+1)}',engine)
        self.assertIn('"heatmapMesh":str(heatmap)',engine)
        self.assertIn('"anchorInfluenceMesh":str(influence)',engine)
        self.assertIn('plan_only=True', (ROOT/'desktop/qt_app/forecast_service.py').read_text(encoding='utf-8'))

    def test_window_stage_version_and_gating(self):
        window=(ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8')
        self.assertIn('UI prototype · Stage 4D-A',window)
        self.assertIn('def _filament_decision(self):',window)
        self.assertIn('if not decision.ready:',window)
        self.assertIn('preserve_camera=True',window)
        self.assertIn('_mark_live_preview_stale',window)
        self.assertIn('Anchor Influence',window)


if __name__=='__main__': unittest.main()
