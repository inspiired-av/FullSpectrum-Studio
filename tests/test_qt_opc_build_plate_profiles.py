"""OPC vendor-cache parser and discovery tests (runs without PySide6)."""
from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT/'desktop'/'qt_app'/'opc_plate_profiles.py'
spec = importlib.util.spec_from_file_location('plate_opc', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def u8(n): return struct.pack('<B', n)
def u16(n): return struct.pack('<H', n)
def u32(n): return struct.pack('<I', n)
def i32(n): return struct.pack('<i', n)
def u64(n): return struct.pack('<Q', n)
def st(s):
    b = s.encode('utf-8')
    return u64(len(b)) + b


def stlist(values):
    return u64(len(values)) + b''.join(st(s) for s in values)


def make_opc(path, *, vendor='BBL', model_name='Bambu Lab H2C',
             mesh='h2c.stl', texture='h2c.svg', header_version=2, payload_version=2,
             profile_vendor=None):
    # The same binary field order as the C++ cereal::BinaryOutputArchive
    # writer in PresetCacheFormat.cpp and VendorProfile::serialize.
    profile_vendor = profile_vendor or vendor
    model = (st('H2C') + st(model_name) + st('H2C-int') + u8(0) + st('H2')
             + u64(1) + st('0.4') + stlist(['PLA']) + stlist([])
             + st(mesh) + st(texture)
             + b''.join(st('') for _ in range(7)))
    profile = (st('Bambu Lab') + st(profile_vendor) + st('1.0.0') + st('') + st('')
               + u64(1) + model + stlist([]) + stlist([]))
    # stamps + dictionary + VendorMap + unused preset lists
    body = (u32(payload_version) + st(vendor) + st('1.0.0')
            + stlist(['layer_height']) + u64(1) + u16(2) + stlist([''])
            + u64(1) + st(vendor) + profile
            + u32(0)*3 + u64(0))
    path.write_bytes(struct.pack('<IIQI', mod.MAGIC, header_version,
                                 len(body), zlib.crc32(body) & 0xffffffff) + body)
    return path


@dataclasses.dataclass(frozen=True)
class Asset:
    printer: str
    vendor: str
    source: str
    mesh: Path
    texture: Path | None
    profile: Path
    root: Path


class OpcUnitTests(unittest.TestCase):
    def test_reads_cereal_vendor_model_and_version(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_opc(Path(td)/'BBL.opc')
            models = mod.read_opc_models(p)
            self.assertEqual(len(models), 1)
            m = models[0]
            self.assertEqual((m.printer,m.vendor,m.bed_model,m.bed_texture),
                             ('Bambu Lab H2C','BBL','h2c.stl','h2c.svg'))
            self.assertEqual((m.model_id,m.family,m.technology),('H2C','H2',0))

    def test_one_byte_technology_does_not_consume_family_string_length(self):
        # OrcaSlicer's PrinterTechnology is declared ': unsigned char' in Config.hpp.
        # A 4-byte read consumes three bytes of the next string's u64 length.
        with tempfile.TemporaryDirectory() as td:
            p = make_opc(Path(td)/'Anycubic.opc', vendor='Anycubic',
                         model_name='Anycubic Kobra 2', mesh='kobra2.stl')
            models = mod.read_opc_models(p)
            self.assertEqual(len(models), 1)
            self.assertEqual(models[0].family, 'H2')
            self.assertEqual(models[0].technology, 0)
            self.assertEqual(models[0].bed_model, 'kobra2.stl')

    def test_legacy_four_byte_fixture_is_not_accepted(self):
        # Prevent the old (incorrect) test fixture from masking this format bug.
        with tempfile.TemporaryDirectory() as td:
            p = make_opc(Path(td)/'BBL.opc')
            data = p.read_bytes()
            marker = st('H2C-int') + u8(0) + st('H2')
            self.assertEqual(data.count(marker), 1)
            altered = data.replace(marker, st('H2C-int') + i32(0) + st('H2'))
            # Adjust both declared size and CRC, so the parser reaches the model.
            body = altered[20:]
            altered = struct.pack('<IIQI',mod.MAGIC,mod.VERSION,len(body),
                                  zlib.crc32(body) & 0xffffffff) + body
            p.write_bytes(altered)
            with self.assertRaises(mod.OpcFormatError):
                mod.read_opc_models(p)

    def test_invalid_crc_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_opc(Path(td)/'BBL.opc')
            b = bytearray(p.read_bytes()); b[-1] ^= 0xFF; p.write_bytes(b)
            with self.assertRaisesRegex(mod.OpcFormatError,'CRC32'):
                mod.read_opc_models(p)

    def test_unknown_cache_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=make_opc(Path(td)/'BBL.opc',header_version=3)
            with self.assertRaisesRegex(mod.OpcFormatError,'version 3'):
                mod.read_opc_models(p)
            p=make_opc(p,payload_version=3)
            with self.assertRaisesRegex(mod.OpcFormatError,'payload'):
                mod.read_opc_models(p)

    def test_stamp_id_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=make_opc(Path(td)/'BBL.opc',profile_vendor='WrongVendor')
            with self.assertRaisesRegex(mod.OpcFormatError,'matching VendorProfile'):
                mod.read_opc_models(p)

    def test_rejects_symlink_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'BBL').mkdir()
            other=root/'outside.stl';other.write_bytes(b'0')
            (root/'BBL'/'fine.stl').write_bytes(b'ok')
            self.assertIsNone(mod.checked_vendor_asset(root,'BBL','../outside.stl'))
            self.assertIsNone(mod.checked_vendor_asset(root,'BBL','/tmp/outside.stl'))
            self.assertIsNone(mod.checked_vendor_asset(root,'../','fine.stl'))
            self.assertEqual(mod.checked_vendor_asset(root,'BBL','fine.stl'),root/'BBL'/'fine.stl')

    def test_valid_stl_keeps_missing_texture_optional(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'BBL').mkdir()
            (root/'BBL'/'h2c.stl').write_bytes(b'mesh')
            make_opc(root/'BBL.opc',texture='missing.svg')
            assets, warnings = mod.discover_opc_plate_assets([root],Asset)
            self.assertEqual(len(assets),1)
            self.assertEqual(assets[0].source,'OrcaSlicer')
            self.assertIsNone(assets[0].texture)
            self.assertEqual(warnings,[])

    def test_unavailable_mesh_and_bad_cache_are_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'BBL').mkdir()
            make_opc(root/'BBL.opc')
            (root/'Other.opc').write_bytes(b'not an OPC')
            assets, warnings = mod.discover_opc_plate_assets([root],Asset)
            self.assertEqual(assets,[])
            self.assertEqual(len(warnings),2)

    def test_merge_preserves_bambu_and_orca_same_printer(self):
        @dataclasses.dataclass(frozen=True)
        class Catalog:
            plates: tuple[Asset, ...]
            sources: tuple
            warnings: tuple = ()
        # Use a module-level function to ensure inspect.getmodule succeeds.
        global PlateAsset
        PlateAsset = Asset
        global _json_discovery
        def _json_discovery(*, resource_roots=()):
            return Catalog((Asset('Bambu Lab H2C','BBL','Bambu Studio',Path('b.stl'),None,
                                  Path('b.json'),Path('.')),),())
        _json_discovery.__module__ = __name__
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'BBL').mkdir()
            (root/'BBL'/'h2c.stl').write_bytes(b'fake mesh')
            make_opc(root/'BBL.opc')
            result = mod.extend_plate_catalog_with_opc(_json_discovery,
                                                       resource_roots=[root])
            self.assertEqual(len(result.plates),2)
            self.assertEqual({p.source for p in result.plates},
                             {'OrcaSlicer','Bambu Studio'})
            # Rerun does not double-append.
            result2=mod.extend_plate_catalog_with_opc(_json_discovery,
                                                       resource_roots=[root])
            self.assertEqual(len(result2.plates),2)


if __name__ == '__main__':
    unittest.main()
