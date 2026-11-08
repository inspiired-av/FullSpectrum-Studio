"""Stage 1.4.1: scale warning, source encoding, and pending export options."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop.qt_app.preview_scale_check import dimensions, scale_warning
from desktop.qt_app.export_pending_settings import summarize_pending


class ScaleWarningTests(unittest.TestCase):
    def test_hair_obj_normalized_coordinates_warn_without_mutation(self):
        bounds = (-0.14921619, 1.32443523, -0.17856130,
                   0.14379239, 1.80389154, 0.15270701)
        copy = tuple(bounds)
        notice = scale_warning(bounds, 'hair.OBJ')
        self.assertIn('Unusually small', notice)
        self.assertIn('0.479', notice)
        self.assertIn('Verify physical dimensions', notice)
        self.assertEqual(tuple(bounds), copy)
    def test_normal_obj_and_native_3mf_not_flagged(self):
        self.assertEqual(scale_warning((0, 0, 0, 80, 90, 100), 'normal.obj'), '')
        self.assertEqual(scale_warning((0, 0, 0, .1, .2, .3), 'frog.3mf'), '')
    def test_large_and_invalid(self):
        self.assertIn('large', scale_warning((0, 0, 0, 1200, 0, 0), 'giant.obj').lower())
        self.assertIsNone(dimensions((1, 2, 3)))
        self.assertEqual(scale_warning((0, 0, 0, float('nan'), 1, 1), 'nan.obj'), '')
    def test_glb_units_not_assumed_to_be_mm(self):
        self.assertIn('meters', scale_warning((0, 0, 0, 0.3, 0.3, 0.6), 'a.glb'))


class PendingSettingsTests(unittest.TestCase):
    def test_reports_and_value_are_shown(self):
        class P:
            dirty_keys = {'export_report_txt', 'export_validation_md'}
            def get(self, k): return False
        summary = summarize_pending(P())
        self.assertIn('Conversion TXT: Off', summary)
        self.assertIn('Validation MD: Off', summary)
    def test_paths_not_disclosed_in_summary(self):
        class P:
            dirty_keys = {'native_project_template'}
            def get(self, k): return r'C:\private\project\template.3mf'
        self.assertEqual(summarize_pending(P()), 'Pending: Native template: Selected')
    def test_more_and_empty(self):
        class P:
            dirty_keys = {'source', 'real_slots', 'auto_open', 'strategy'}
            def get(self, k): return 'foo'
        self.assertIn('+1 more', summarize_pending(P()))
        P.dirty_keys = set()
        self.assertEqual(summarize_pending(P()), '')


class UnicodeReportEncodingTests(unittest.TestCase):
    def test_renamed_reports_accept_unicode_written_by_engine(self):
        from types import SimpleNamespace
        import fullspectrum_engine as engine
        from desktop.qt_app.export_service import _renamed_staged_assets
        with TemporaryDirectory() as folder:
            root = Path(folder)
            files = {
                'output': root/'source.3mf',
                'csv': root/'source_recipes.csv',
                'report': root/'source_report.txt',
                'colorValidationReport': root/'source_color-validation.md',
            }
            for key, path in files.items():
                if key in ('report', 'colorValidationReport'):
                    engine._write_utf8_report(path, 'Area: mm²; file: source.3mf')
                else:
                    path.write_bytes(b'placeholder')
            request = SimpleNamespace(
                slicer='Bambu Studio',
                plan=SimpleNamespace(model=str(root/'frog.3mf'),
                                     settings={'strategy':'official'}),
            )
            renamed = _renamed_staged_assets(files,request)
            for key in ('report','colorValidationReport'):
                text = renamed[key].read_text(encoding='utf-8')
                self.assertIn('mm²', text)
                self.assertIn(renamed['output'].name, text)

    def test_windows_default_cp1252_is_not_utf8_but_helper_is(self):
        # Exercise the exact report-writing helper used by the converter.
        import fullspectrum_engine as engine
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'report.txt'
            payload = 'Native colors weighted by surface area (mm²).'
            path.write_text(payload, encoding='cp1252')
            with self.assertRaises(UnicodeDecodeError):
                path.read_text(encoding='utf-8')
            engine._write_utf8_report(path, payload)
            self.assertEqual(path.read_text(encoding='utf-8'), payload)
            self.assertIn(b'\xc2\xb2', path.read_bytes())


if __name__ == '__main__':
    unittest.main()
