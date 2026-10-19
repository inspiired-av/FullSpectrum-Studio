"""Stage 4D-C: reuse the existing exporter, publish only verified files."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zipfile import ZipFile
import os
import unittest

from desktop.qt_app.forecast_service import ForecastRequest
from desktop.qt_app.export_service import (
    ExportRequest, make_export_request, run_export, _exclusive_publish,
)

SETTINGS = {
    'strategy': 'official', 'source': 'catalog', 'custom': '',
    'real_slots': '4', 'quality_bias': 67, 'smart_quality': False,
    'catalog_region': 'global', 'planner_mode': 'best',
    'planning_sample': 'paint', 'max_output_colors': 'auto',
    'output_color_strategy': 'maximum_fidelity', 'native_project_template': '',
}


def options(_engine, _source, _custom):
    return [{'key': 'K1', 'color': '#000000'}, {'key': 'K2', 'color': '#FFFFFF'},
            {'key': 'K3', 'color': '#FF00FF'}]


def request(folder, *, native=True, ext='.3mf', **changes):
    source = Path(folder) / ('example' + ext)
    source.write_bytes(b'fake input, mocked converter handles it')
    plan = ForecastRequest(str(source), None, {**SETTINGS, **changes},
                           frozenset(), frozenset(), ())
    return ExportRequest(plan, str(folder), 'Bambu Studio')


class FakeEngine:
    def __init__(self, standard=False, fail=False, valid=True):
        self.standard = standard
        self.fail = fail
        self.valid = valid
        self.kw = None
        self.convert_calls = 0

    def is_standard_colored_3mf(self, path):
        return self.standard

    def convert(self, path, mode, **kw):
        self.convert_calls += 1
        self.kw = kw
        self.mode = mode
        assert kw['plan_only'] is False
        assert kw['reveal'] is False
        folder = Path(kw['output_dir'])
        assert folder.is_dir()
        if self.fail:
            raise RuntimeError('engine failure')
        name = f'{Path(path).stem}_FullSpectrum_OFFICIAL_BAMBU_DERIVED_v0.5.1'
        output = folder / f'{name}.3mf'
        with ZipFile(output, 'w') as z:
            z.writestr('3D/3dmodel.model', '<model/>')
        report = folder / f'{name}_report.txt'
        report.write_text('Validation: OK', encoding='utf-8')
        csv = folder / f'{name}_recipe.csv'
        csv.write_text('old,new\n1,2\n', encoding='utf-8')
        color = folder / f'{name}_COLOR_VALIDATION.md'
        color.write_text('Checked', encoding='utf-8')
        return {'output': str(output), 'report': str(report), 'csv': str(csv),
                'colorValidationReport': str(color), 'validation': 'OK' if self.valid else 'FAIL',
                'colorValidation': {'maximumDeltaE': 0.3},
                'realSlots': 4, 'outputSlots': 5, 'warnings': []}


class ExportTests(unittest.TestCase):
    def test_calls_original_engine_with_snapshot_and_validates_output(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            req = replace(req, plan=replace(req.plan,
                disabled=frozenset({'K3'}), pinned=frozenset({'K1', 'K3'})))
            engine = FakeEngine()
            result = run_export(req, engine=engine, options_loader=options)
            self.assertTrue(Path(result['output']).is_file())
            self.assertTrue(Path(result['csv']).is_file())
            self.assertTrue(Path(result['report']).is_file())
            self.assertEqual(result['validation'], 'OK')
            self.assertEqual(engine.kw['allowed_anchor_keys'], ['K1', 'K2'])
            self.assertEqual(engine.kw['pinned_anchor_keys'], ['K1'])
            self.assertEqual(engine.kw['quality_bias'], 67)
            self.assertEqual(engine.kw['analysis_dir'], None)
            self.assertFalse(any(Path(folder).glob('.fullspectrum_export_*')))

    def test_output_never_overwrites_previous_result(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            engine = FakeEngine()
            first = run_export(req, engine=engine, options_loader=options)
            original = Path(first['report']).read_bytes()
            with self.assertRaisesRegex(FileExistsError, 'already exist'):
                run_export(req, engine=engine, options_loader=options)
            self.assertEqual(Path(first['report']).read_bytes(), original)
            self.assertEqual(engine.convert_calls, 2)  # rerun is staged only

    def test_engine_error_does_not_publish_any_files(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            with self.assertRaisesRegex(RuntimeError, 'engine failure'):
                run_export(req, engine=FakeEngine(fail=True), options_loader=options)
            self.assertEqual(sorted(x.name for x in Path(folder).iterdir()), ['example.3mf'])

    def test_invalid_validation_never_publishes(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            with self.assertRaisesRegex(RuntimeError, 'validated 3MF'):
                run_export(req, engine=FakeEngine(valid=False), options_loader=options)
            self.assertEqual(sorted(x.name for x in Path(folder).iterdir()), ['example.3mf'])

    def test_cancel_at_publish_boundary_leaves_no_output(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            def cancel(fraction, message):
                if fraction >= .99:
                    raise InterruptedError('cancelled')
            with self.assertRaises(InterruptedError):
                run_export(req, engine=FakeEngine(), options_loader=options, progress=cancel)
            self.assertEqual(sorted(x.name for x in Path(folder).iterdir()), ['example.3mf'])

    def test_missing_template_rejected_for_generic_and_obj(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            with self.assertRaisesRegex(ValueError, 'Native Project Template'):
                run_export(req, engine=FakeEngine(standard=True), options_loader=options)
            req = request(folder, ext='.obj')
            with self.assertRaisesRegex(ValueError, 'Native Project Template'):
                run_export(req, engine=FakeEngine(), options_loader=options)

    def test_native_3mf_rejects_incompatible_template(self):
        with TemporaryDirectory() as folder:
            req = request(folder, native_project_template='unused.3mf')
            with self.assertRaisesRegex(ValueError, 'clear the template'):
                run_export(req, engine=FakeEngine(), options_loader=options)

    def test_existing_3mf_retained_if_report_name_collides(self):
        with TemporaryDirectory() as folder:
            req = request(folder)
            engine = FakeEngine()
            # Stage a preview once, then delete 3MF only; collision in reports
            result = run_export(req, engine=engine, options_loader=options)
            Path(result['output']).unlink()
            with self.assertRaises(FileExistsError):
                run_export(req, engine=engine, options_loader=options)
            self.assertFalse(Path(result['output']).exists())

    def test_publisher_rolls_back_when_copy_fails_after_first_file(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / 'source'; src.mkdir()
            dest = root / 'dest'; dest.mkdir()
            files = {key:src / f'stage_{key}.dat' for key in ('csv','report','colorValidationReport','output')}
            for file in files.values():file.write_text('file',encoding='utf-8')
            files['output'].unlink()  # fail after first three successfully published
            with self.assertRaises(OSError):
                _exclusive_publish(files, dest)
            self.assertEqual(list(dest.iterdir()), [])

    def test_snapshot_slicer_and_preferences(self):
        p = SimpleNamespace(get=lambda key: {
            **SETTINGS, 'output_application':'OrcaSlicer',
            'orcaslicer_executable':r'C:\Portable\orca-slicer.exe', 'auto_open':True
        }[key])
        f = SimpleNamespace(disabled={'K3'},pinned={'K1'},solid_assignments={})
        out = make_export_request('a.3mf', 'ref.png', p, f, 'folder')
        self.assertEqual(out.slicer,'OrcaSlicer')
        self.assertTrue(out.auto_open)
        self.assertEqual(out.slicer_executable,r'C:\Portable\orca-slicer.exe')
        f.pinned.add('K2')
        self.assertNotIn('K2',out.plan.pinned)


try:
    from PySide6.QtWidgets import QApplication
    from desktop.qt_app.main_window import MainWindow
except ImportError:
    QApplication = None

@unittest.skipUnless(QApplication is not None, 'PySide6 not installed')
class QtExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        cls.app=QApplication.instance() or QApplication([])

    def test_export_is_disabled_before_model_is_loaded(self):
        with TemporaryDirectory() as folder:
            w=MainWindow(settings_path=Path(folder)/'settings.json')
            try:
                self.assertFalse(w.compose_button.isEnabled())
                self.assertFalse(w.open_export_button.isEnabled())
                self.assertFalse(w.export_cancel_button.isEnabled())
                self.assertFalse(hasattr(w, 'object_plate_panel'))
            finally:
                w.close()

if __name__=='__main__':unittest.main()
