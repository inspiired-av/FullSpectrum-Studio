"""OPC v2 catalog isolation: host installations must never leak into fixtures."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch
import os
import tempfile
import unittest
import importlib.util

from desktop.qt_app import opc_plate_profiles as opc


@dataclass(frozen=True)
class PlateAsset:
    printer: str
    vendor: str
    source: str
    mesh: Path
    texture: Path | None
    profile: Path
    root: Path


@dataclass(frozen=True)
class FakeCatalog:
    plates: tuple[PlateAsset, ...]
    sources: tuple = ()
    warnings: tuple = ()


def _json_discovery(*, resource_roots=(), slicer_executables=(),
                    environ=None, registry_candidates=None, path_lookup=None):
    return FakeCatalog((PlateAsset('Bambu Lab H2C', 'BBL', 'Bambu Studio',
                                   Path('b.stl'), None, Path('b.json'), Path('.')),))


def _write_vendor(root: Path, *, printer: str) -> None:
    """Use the shared valid OPC v2 fixture: tiny binary vendor cache + STL."""
    # Existing OPC tests carry the same fixture that validated real Orca caches.
    from test_qt_opc_build_plate_profiles import make_opc
    root.mkdir(parents=True, exist_ok=True)
    (root / 'BBL').mkdir(exist_ok=True)
    (root / 'BBL' / 'h2c.stl').write_bytes(b'test-only geometry placeholder')
    make_opc(root / 'BBL.opc', model_name=printer)


class OpcDiscoveryIsolationTests(unittest.TestCase):
    def test_explicit_roots_never_append_real_host_installation(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            explicit = td / 'explicit'
            global_root = td / 'global' / 'OrcaSlicer' / 'resources' / 'profiles'
            _write_vendor(explicit, printer='Bambu Lab H2C')
            _write_vendor(global_root, printer='Unrelated Global Printer')
            with patch.dict(os.environ, {'PROGRAMFILES': str(td / 'global')}, clear=False):
                result = opc.extend_plate_catalog_with_opc(
                    _json_discovery, resource_roots=(explicit,))
            self.assertEqual(len(result.plates), 2)
            self.assertEqual({p.source for p in result.plates}, {'OrcaSlicer','Bambu Studio'})
            self.assertNotIn('Unrelated Global Printer', [p.printer for p in result.plates])

    def test_empty_forwarded_gui_defaults_keep_automatic_detection(self):
        # PlateCatalogWorker forwards empty tuples even for normal discovery.
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            root = td / 'global' / 'OrcaSlicer' / 'resources' / 'profiles'
            _write_vendor(root, printer='Default Orca GUI Printer')
            with patch.dict(os.environ, {'PROGRAMFILES': str(td / 'global')}, clear=False):
                result = opc.extend_plate_catalog_with_opc(
                    _json_discovery, resource_roots=(), slicer_executables=())
            self.assertGreaterEqual(len(result.plates), 2)
            self.assertIn('Default Orca GUI Printer', [p.printer for p in result.plates])

    def test_explicit_mock_environment_never_adds_host_roots(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            global_root = td / 'global' / 'OrcaSlicer' / 'resources' / 'profiles'
            _write_vendor(global_root, printer='Unrelated Global Printer')
            with patch.dict(os.environ, {'PROGRAMFILES': str(td / 'global')}, clear=False):
                result = opc.extend_plate_catalog_with_opc(_json_discovery,
                                                            environ={}, registry_candidates=[])
            self.assertEqual(len(result.plates), 1)

    def test_default_auto_discovery_still_scans_real_environment_paths(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            global_root = td / 'global' / 'OrcaSlicer' / 'resources' / 'profiles'
            _write_vendor(global_root, printer='Automatic Orca Printer')
            with patch.dict(os.environ, {'PROGRAMFILES': str(td / 'global')}, clear=False):
                result = opc.extend_plate_catalog_with_opc(_json_discovery)
            self.assertGreaterEqual(len(result.plates), 2)
            self.assertIn('Automatic Orca Printer', [p.printer for p in result.plates])

    def test_explicit_slicer_exe_never_appends_unrelated_host(self):
        with tempfile.TemporaryDirectory() as d:
            td = Path(d)
            local = td / 'local' / 'resources' / 'profiles'
            exe = td / 'local' / 'OrcaSlicer.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'MZ')
            _write_vendor(local, printer='Portable Orca Printer')
            global_root = td / 'global' / 'OrcaSlicer' / 'resources' / 'profiles'
            _write_vendor(global_root, printer='Unrelated Global Printer')
            with patch.dict(os.environ, {'PROGRAMFILES': str(td / 'global')}, clear=False):
                result = opc.extend_plate_catalog_with_opc(_json_discovery,
                                                            slicer_executables=(exe,))
            self.assertEqual(len(result.plates), 2)
            self.assertIn('Portable Orca Printer', [p.printer for p in result.plates])
            self.assertNotIn('Unrelated Global Printer', [p.printer for p in result.plates])


if __name__ == '__main__':
    unittest.main()
