"""Stage 1.4: optional output publication must never bypass 3MF validation."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from desktop.qt_app.export_artifacts import (
    OPTIONAL_ARTIFACTS, chosen_diagnostics, publication_keys)
from desktop.qt_app.export_service import ExportRequest, run_export
from desktop.qt_app.forecast_service import ForecastRequest
from desktop.qt_app.plan_preferences import PlanPreferences
from desktop.settings_store import save_settings, load_settings


class ArtifactSelectionTests(unittest.TestCase):
    def test_defaults_and_3mf_mandatory(self):
        self.assertEqual(publication_keys(), ('csv', 'report', 'colorValidationReport', 'output'))
        self.assertEqual(publication_keys(()), ('output',))
        self.assertEqual(publication_keys(('report',)), ('report', 'output'))

    def test_invalid_selection_is_rejected(self):
        for values in (('csv', 'csv'), ('output',), ('bogus',)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                publication_keys(values)

    def test_old_preferences_default_to_reports(self):
        class PreviousPreferences:
            def get(self, key):
                raise KeyError(key)
        self.assertEqual(chosen_diagnostics(PreviousPreferences()), OPTIONAL_ARTIFACTS)

    def test_settings_roundtrip_and_explicit_revert(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'settings.json'
            prefs=PlanPreferences(path)
            for key in ('export_recipe_csv','export_report_txt','export_validation_md'):
                self.assertTrue(prefs.get(key))
            prefs.set('export_recipe_csv',False)
            prefs.set('export_validation_md',False)
            self.assertTrue(prefs.is_dirty)
            prefs.save()
            saved=load_settings(path)
            self.assertEqual(saved['export_recipe_csv'],False)
            self.assertEqual(saved['export_validation_md'],False)
            prefs.set('export_recipe_csv',True)
            prefs.revert()
            self.assertFalse(prefs.get('export_recipe_csv'))
            self.assertEqual(chosen_diagnostics(prefs), ('report',))
            self.assertTrue(prefs.get('export_report_txt'))


class FakeConverter:
    def __init__(self):
        self.output_count=0
    def is_standard_colored_3mf(self,path):
        return False
    def convert(self, path, strategy, *, output_dir, progress, **kwargs):
        self.output_count += 1
        root=Path(output_dir)
        paths={key:root/name for key,name in {
            'csv':'project_recipes.csv','report':'project_report.txt',
            'colorValidationReport':'project_validation.md',
            'output':'project.3mf'}.items()}
        with ZipFile(paths['output'],'w') as z:
            z.writestr('3D/3dmodel.model','<model/>')
        for key in ('csv','report','colorValidationReport'):
            paths[key].write_text('Report concerning project.3mf',encoding='utf-8')
        return {'type':'conversion','validation':'OK',
                'colorValidation':{'maximumDeltaE':2.5},
                **{key:str(value) for key,value in paths.items()}}


def options(*unused):
    return [{'key':'a','color':'#000000'},{'key':'b','color':'#FFFFFF'}]


class TransactionalSelectionTests(unittest.TestCase):
    def _request(self, source, dest, diagnostics):
        settings={'source':'catalog','custom':'','strategy':'official',
                  'native_project_template':'','smart_quality':True,
                  'quality_bias':60,'real_slots':'auto',
                  'max_output_colors':'32','output_color_strategy':'maximum_fidelity',
                  'catalog_region':'global','planner_mode':'best','planning_sample':'paint'}
        plan=ForecastRequest(model=str(source),reference=None,settings=settings,
                             disabled=frozenset(),pinned=frozenset(),
                             protections=())
        return ExportRequest(plan,str(dest),'Bambu Studio',
                             diagnostic_artifacts=diagnostics)

    def test_3mf_only_still_requires_full_engine_validation(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source.3mf';source.write_bytes(b'fake source')
            converter=FakeConverter()
            request=self._request(source,root,())
            out=run_export(request,engine=converter,options_loader=options)
            self.assertEqual(converter.output_count,1)
            self.assertEqual({p.suffix for p in root.iterdir() if p.name.startswith('source_FS-')}, {'.3mf'})
            with ZipFile(out['output']) as z:
                self.assertIn('3D/3dmodel.model',z.namelist())
            self.assertTrue(all(out[key] is None for key in OPTIONAL_ARTIFACTS))
            self.assertEqual(out['validation'],'OK')

    def test_selected_csv_only_and_ignored_collision(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source.3mf';source.write_bytes(b'fake source')
            # An unselected report is allowed to pre-exist without blocking export.
            from desktop.app_support import APP_VERSION
            report=root/f'source_FS-Optimized_v{APP_VERSION}_report.txt'
            report.write_text('existing file',encoding='utf-8')
            out=run_export(self._request(source,root,('csv',)),
                           engine=FakeConverter(),options_loader=options)
            self.assertTrue(Path(out['csv']).exists())
            self.assertEqual(report.read_text(), 'existing file')
            self.assertIsNone(out['report'])
            self.assertIsNone(out['colorValidationReport'])

    def test_full_default_publication(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source.3mf';source.write_bytes(b'fake source')
            out=run_export(self._request(source,root,OPTIONAL_ARTIFACTS),
                           engine=FakeConverter(),options_loader=options)
            self.assertTrue(all(Path(out[k]).is_file() for k in (*OPTIONAL_ARTIFACTS,'output')))

    def test_rejects_unknown_artifact_before_conversion(self):
        with TemporaryDirectory() as d:
            root=Path(d);source=root/'source.3mf';source.write_bytes(b'fake source')
            fake=FakeConverter()
            with self.assertRaisesRegex(ValueError,'Unknown'):
                run_export(self._request(source,root,('output',)),
                           engine=fake,options_loader=options)
            self.assertEqual(fake.output_count,0)


if __name__=='__main__':
    unittest.main()
