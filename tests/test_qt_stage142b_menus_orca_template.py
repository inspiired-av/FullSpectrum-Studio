"""Stage 1.4.2b: menus, actual Orca template versions and native template snapshots."""
from __future__ import annotations

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile

from orca_profile_warning import orca_h2c_warning
from desktop.qt_app.export_template_policy import template_requirement

ROOT = Path(__file__).resolve().parents[1]


class OrcaReleaseWarningTests(TestCase):
    def info(self, version, printer='Bambu Lab H2C 0.4 nozzle', slicer='OrcaSlicer'):
        return dict(slicer=slicer, slicerVersion=version, printerPreset=printer)

    def test_current_h2c_versions_do_not_warn(self):
        for version in ('2.5.0', '2.5.1', '2.6.0', '2.5.0-alpha', '2.5.0-rc'):
            with self.subTest(version=version):
                self.assertEqual(orca_h2c_warning(self.info(version), 'OrcaSlicer'), '')

    def test_older_h2c_template_warns_specifically(self):
        warning = orca_h2c_warning(self.info('2.4.2'), 'OrcaSlicer')
        self.assertIn('2.4.2', warning)
        self.assertIn('older than 2.5.0', warning)
        self.assertIn('H2C', warning)

    def test_other_printers_do_not_get_h2c_warning(self):
        for name in ('Bambu Lab P1S 0.4 nozzle', 'Bambu Lab H2D 0.4 nozzle'):
            with self.subTest(printer=name):
                self.assertEqual(orca_h2c_warning(self.info('2.4.0', name), 'OrcaSlicer'), '')

    def test_no_inferred_installed_slicer_version(self):
        self.assertEqual(orca_h2c_warning(self.info('unknown'), 'OrcaSlicer'), '')
        self.assertIn('Template was saved by OrcaSlicer',
                      orca_h2c_warning(self.info('2.5.0'), 'Bambu Studio'))


class NativeSnapshotPolicyTests(TestCase):
    def fixture(self, folder, name, native):
        dest = Path(folder, name)
        with ZipFile(dest, 'w') as z:
            z.writestr('3D/3dmodel.model', '<model/>')
            if native:
                z.writestr('Metadata/project_settings.config', '{}')
        return dest

    def test_native_export_ignores_only_snapshot_template(self):
        from desktop.qt_app.export_service import make_export_request
        from desktop.qt_app.forecast_service import ForecastRequest
        with TemporaryDirectory() as folder:
            native = self.fixture(folder, 'native.3mf', True)
            settings = {'native_project_template': 'saved_blank_template.3mf',
                        'strategy': 'official'}
            request = ForecastRequest(str(native), None, settings, frozenset(),
                                      frozenset(), ())
            class Prefs:
                def get(self, key):
                    return dict(output_application='OrcaSlicer',
                                orcaslicer_executable='',auto_open=False,
                                export_recipe_csv=True,export_report_txt=True,
                                export_validation_md=True).get(key)
            with patch('desktop.qt_app.forecast_service.make_request', return_value=request):
                snapshot = make_export_request(native, None, Prefs(), None, folder)
            self.assertEqual(snapshot.plan.settings['native_project_template'], '')
            self.assertEqual(settings['native_project_template'], 'saved_blank_template.3mf')
            self.assertEqual(snapshot.plan.model, str(native))

    def test_generic_input_keeps_saved_template(self):
        from desktop.qt_app.export_service import make_export_request
        from desktop.qt_app.forecast_service import ForecastRequest
        with TemporaryDirectory() as folder:
            generic = self.fixture(folder, 'generic.3mf', False)
            req = ForecastRequest(str(generic), None,
                                  {'native_project_template':'blank.3mf'},
                                  frozenset(), frozenset(), ())
            class Prefs:
                def get(self, key):
                    return dict(output_application='Bambu Studio',
                                bambu_studio_executable='',auto_open=False,
                                export_recipe_csv=False,export_report_txt=False,
                                export_validation_md=False).get(key)
            with patch('desktop.qt_app.forecast_service.make_request', return_value=req):
                output = make_export_request(generic, None, Prefs(), None, folder)
            self.assertEqual(output.plan.settings['native_project_template'], 'blank.3mf')
            self.assertTrue(template_requirement(generic).required)


class MenuLocationContracts(TestCase):
    def test_navigate_view_settings_are_separate(self):
        text = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        node = ast.parse(text)
        window = next(n for n in node.body if isinstance(n,ast.ClassDef)
                      and n.name == 'MainWindow')
        menu = next(n for n in window.body if isinstance(n,ast.FunctionDef)
                    and n.name == '_build_menus')
        source = ast.get_source_segment(text,menu)
        self.assertIn('addMenu("&Navigate")', source)
        self.assertIn('navigate.addAction(nav)', source)
        self.assertIn('addMenu("&View")', source)
        self.assertIn('addMenu("&Settings")', source)
        self.assertIn('settings.addAction(folder)', source)
        self.assertIn('settings.addAction(save)', source)
        self.assertIn('settings.addAction(export_options)', source)
        self.assertIn('settings.addAction(revert)', source)
        self.assertNotIn('view.addAction(nav)', source)
        self.assertNotIn('\n        menu.addAction(save)', source)
        self.assertIn('Ctrl+{idx+1}', source)

    def test_ui_does_not_call_external_template_a_conflict(self):
        text = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        self.assertNotIn('Template conflict', text)
        self.assertIn("requirement.kind == 'native'", text)
        self.assertIn('The saved template is ignored for this export.', text)


if __name__=='__main__':
    import unittest
    unittest.main()
