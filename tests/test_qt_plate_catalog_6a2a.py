"""6A2-A slicer asset discovery; runs without PySide6 or an installed slicer."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from desktop.qt_app.plate_catalog import (
    discover_installed_plates, preferred_plate, scan_profile_root, _vendor_file,
)


def add_printer(root: Path, vendor: str, printer: str, *, mesh=True,
                texture=True, type='machine_model', model_ref=None,
                texture_ref=None):
    assets = root / vendor
    machine = assets / 'machine'
    machine.mkdir(parents=True, exist_ok=True)
    name = printer.replace('/', '_')
    model_file = model_ref or name + '.stl'
    texture_file = texture_ref or name + '.svg'
    record = {'type': type, 'name': printer,
              'bed_model': model_file, 'bed_texture': texture_file}
    (machine / (name + '.json')).write_text(json.dumps(record), encoding='utf-8')
    if mesh and model_ref is None:
        (assets / model_file).write_bytes(b'STL placeholder')
    if texture and texture_ref is None:
        (assets / texture_file).write_text('<svg></svg>', encoding='utf-8')
    return assets, machine / (name + '.json')


class PlateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_orca_non_bambu_printer_bed_model_and_texture(self):
        root = self.base / 'OrcaSlicer' / 'resources' / 'profiles'
        add_printer(root, 'Creality', 'Creality K1 Max')
        entries, warnings = scan_profile_root(root, 'OrcaSlicer')
        self.assertEqual(len(entries), 1)
        self.assertFalse(warnings)
        self.assertEqual(entries[0].printer, 'Creality K1 Max')
        self.assertEqual(entries[0].model.name, 'Creality K1 Max.stl')
        self.assertEqual(entries[0].texture.name, 'Creality K1 Max.svg')
        self.assertEqual(entries[0].source, 'OrcaSlicer')

    def test_bambu_h2c_mesh_works_without_svg(self):
        root = self.base / 'Bambu Studio' / 'resources' / 'profiles'
        add_printer(root, 'BBL', 'Bambu Lab H2C', texture=False)
        entries, warnings = scan_profile_root(root, 'Bambu Studio')
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0].texture)
        self.assertTrue(any('optional texture' in x for x in warnings))

    def test_missing_mesh_does_not_create_broken_catalog_entry(self):
        root = self.base / 'resources' / 'profiles'
        add_printer(root, 'Qidi', 'Qidi X-Max 3', mesh=False)
        entries, warnings = scan_profile_root(root, 'OrcaSlicer')
        self.assertEqual(entries, ())
        self.assertTrue(any('mesh unavailable' in x for x in warnings))

    def test_discovery_finds_two_installed_slicers_from_executables(self):
        orca = self.base / 'Program Files' / 'OrcaSlicer'
        bambu = self.base / 'Program Files' / 'Bambu Studio'
        orca.mkdir(parents=True)
        bambu.mkdir(parents=True)
        (orca / 'orca-slicer.exe').write_bytes(b'MZ')
        (bambu / 'bambu-studio.exe').write_bytes(b'MZ')
        add_printer(orca / 'resources' / 'profiles', 'Creality', 'Creality K1 Max')
        add_printer(bambu / 'resources' / 'profiles', 'BBL', 'Bambu Lab H2D')
        data = discover_installed_plates(
            environ={'ProgramFiles': str(self.base / 'Program Files')},
            registry_candidates=[], path_lookup=lambda _: None,
        )
        self.assertEqual(len(data.roots), 2)
        self.assertEqual({a.printer for a in data.plates}, {'Creality K1 Max', 'Bambu Lab H2D'})
        self.assertEqual({a.source for a in data.plates}, {'OrcaSlicer', 'Bambu Studio'})

    def test_executable_custom_folder_for_portable_install(self):
        install = self.base / 'Custom Location' / 'OrcaSlicer'
        install.mkdir(parents=True)
        exe = install / 'orca-slicer.exe'
        exe.write_bytes(b'MZ')
        add_printer(install / 'resources' / 'profiles', 'Anycubic', 'Anycubic Kobra 3')
        data = discover_installed_plates(
            environ={}, registry_candidates=[], path_lookup=lambda _: None,
            slicer_executables=[exe])
        self.assertEqual(len(data.plates), 1)
        self.assertEqual(data.plates[0].printer, 'Anycubic Kobra 3')

    def test_custom_resource_root_without_executable(self):
        root = self.base / 'Custom' / 'resources' / 'profiles'
        add_printer(root, 'Creality', 'K1C')
        data = discover_installed_plates(
            environ={}, registry_candidates=[], path_lookup=lambda _: None,
            resource_roots=[root])
        self.assertEqual(len(data.plates), 1)
        self.assertEqual(data.plates[0].source, 'Custom')

    def test_automatic_prefers_orca_and_explicit_source_chooses_bambu(self):
        roots = []
        for name in ('OrcaSlicer', 'Bambu Studio'):
            root = self.base / name / 'resources' / 'profiles'
            add_printer(root, 'BBL', 'Bambu Lab H2D')
            roots.append(root)
        a, _ = scan_profile_root(roots[0], 'OrcaSlicer')
        b, _ = scan_profile_root(roots[1], 'Bambu Studio')
        from desktop.qt_app.plate_catalog import PlateCatalog
        catalog = PlateCatalog((), b+a, ())
        self.assertEqual(preferred_plate(catalog, 'bambu lab h2d').source, 'OrcaSlicer')
        self.assertEqual(preferred_plate(catalog, 'Bambu Lab H2D', 'Bambu Studio').source,
                         'Bambu Studio')
        self.assertIsNone(preferred_plate(catalog, 'missing'))

    def test_skips_corrupt_and_no_bed_model_machine_profiles(self):
        root = self.base / 'resources' / 'profiles'
        folder = root / 'Vendor' / 'machine'
        folder.mkdir(parents=True)
        (folder / 'bad.json').write_text('{bad json', encoding='utf-8')
        (folder / 'filament.json').write_text(json.dumps({'type':'filament', 'bed_model':'x.stl'}))
        (folder / 'regular.json').write_text(json.dumps({'type':'machine_model', 'name':'None'}))
        self.assertEqual(scan_profile_root(root, 'OrcaSlicer')[0], ())

    def test_refuses_parent_path_and_absolute_and_symlink_escape(self):
        folder = self.base / 'SafeVendor'
        folder.mkdir()
        outside = self.base / 'secret.stl'
        outside.write_bytes(b'not a build plate')
        self.assertIsNone(_vendor_file(folder, '../secret.stl', frozenset({'.stl'}), 10_000))
        self.assertIsNone(_vendor_file(folder, str(outside), frozenset({'.stl'}), 10_000))
        self.assertIsNone(_vendor_file(folder, 'C:\\other\\secret.stl', frozenset({'.stl'}), 10_000))
        try:
            (folder / 'linked.stl').symlink_to(outside)
        except (OSError, NotImplementedError):
            return  # Some Windows accounts don't have symlink privileges.
        self.assertIsNone(_vendor_file(folder, 'linked.stl', frozenset({'.stl'}), 10_000))

    def test_discovery_is_read_only_and_never_uses_engine_or_qt(self):
        path = Path(__file__).resolve().parents[1] / 'desktop/qt_app/plate_catalog.py'
        source = path.read_text(encoding='utf-8')
        self.assertNotIn('import PySide6', source)
        self.assertNotIn('fullspectrum_engine', source)
        self.assertNotIn('.write_bytes(', source)
        self.assertNotIn('.write_text(', source)


if __name__ == '__main__':
    unittest.main()
