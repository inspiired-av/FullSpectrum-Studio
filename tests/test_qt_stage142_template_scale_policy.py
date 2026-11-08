"""Stage 1.4.2: native 3MF template UI policy and conservative size warnings."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from desktop.qt_app.export_template_policy import template_requirement
from desktop.qt_app.preview_scale_check import scale_warning


class SourceTemplatePolicyTests(unittest.TestCase):
    def fixture(self, root, name, settings=False):
        path = Path(root, name)
        with ZipFile(path, 'w') as z:
            z.writestr('3D/3dmodel.model', '<model/>')
            if settings:
                z.writestr('Metadata/project_settings.config', '{"printer_settings_id": "test"}')
        return path

    def test_native_slicer_project_needs_no_additional_template(self):
        with TemporaryDirectory() as temp:
            native = self.fixture(temp, 'native.3mf', settings=True)
            result = template_requirement(native)
            self.assertEqual((result.kind, result.required), ('native', False))
            self.assertIn('No additional template', result.description)

    def test_generic_3mf_and_external_formats_require_template(self):
        with TemporaryDirectory() as temp:
            generic = self.fixture(temp, 'generic.3mf')
            self.assertTrue(template_requirement(generic).required)
            self.assertEqual(template_requirement(generic).kind, 'generic')
        for name in ('sculpt.obj', 'sculpt.OBJ', 'sculpt.glb'):
            with self.subTest(name=name):
                self.assertTrue(template_requirement(name).required)

    def test_unreadable_archive_not_silently_called_generic(self):
        with TemporaryDirectory() as temp:
            p = Path(temp, 'broken.3mf')
            p.write_bytes(b'not-a-3mf')
            self.assertEqual(template_requirement(p).kind, 'unreadable')
            self.assertFalse(template_requirement(p).required)

    def test_no_model_is_not_actionable_missing_template(self):
        self.assertEqual(template_requirement(None).kind, 'none')
        self.assertFalse(template_requirement(None).required)


class ScaleAdvisoryTests(unittest.TestCase):
    def test_head_obj_warns_for_small_but_not_normalized_geometry(self):
        # ~6mm-ish OBJ is easy to mistake for a real bust-sized object.
        notice = scale_warning((0, 0, 0, 6.2, 9.1, 5.6), 'headMesh.obj')
        self.assertIn('Unusually small', notice)
        self.assertIn('9.1', notice)
        self.assertIn('has not changed', notice)

    def test_hair_and_normal_obj(self):
        self.assertIn('Unusually small',
                      scale_warning((0, 0, 0, .293, .479, .331), 'hair.OBJ'))
        self.assertEqual(scale_warning((0, 0, 0, 50, 60, 70), 'largeEnough.obj'), '')

    def test_glb_dimensions_are_not_mistaken_for_millimetres(self):
        text = scale_warning((0, 0, 0, .2, .4, .6), 'head.glb')
        self.assertIn('meters', text)
        self.assertIn('source units', text)


class UiIntegrationContracts(unittest.TestCase):
    def test_source_change_refreshes_template_advisory(self):
        src = (Path(__file__).resolve().parents[1] /
               'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        self.assertIn('template_requirement(self.state.model_path)', src)
        self.assertNotIn("'Template conflict'", src)
        self.assertIn("'native_project_template': ''", (
            Path(__file__).resolve().parents[1] /
            'desktop/qt_app/export_service.py').read_text(encoding='utf-8-sig'))
        self.assertIn("'Template required'", src)
        self.assertIn('self._refresh_template_status()\n        self._update_export_template_attention()', src)


if __name__ == '__main__':
    unittest.main()
