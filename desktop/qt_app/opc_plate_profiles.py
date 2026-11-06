"""Read OrcaSlicer's version-2 binary vendor cache for 3D build-plate previews.

Implements only its metadata prologue: header -> cache stamps -> dictionary ->
VendorMap -> VendorProfile/PrinterModel. Intentionally does NOT deserialize print
presets. This code does not run OrcaSlicer or modify its installed assets.

Format: OrcaSlicer src/libslic3r/{PresetCacheFormat.cpp,Preset.hpp,Semver.hpp}.
Unknown cache versions fail closed; no filename heuristics or silently bad plates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace, is_dataclass
from pathlib import Path
from typing import Iterable
import inspect
import os
import struct
import zlib

MAGIC = 0x4F52435A  # CacheFileHeader.magic, native little endian "ORCZ"
VERSION = 2
MAX_FILE = 128 * 1024 * 1024
MAX_STRING = 8192
MAX_ITEMS = 8192


class OpcFormatError(ValueError):
    """Unsupported, damaged or unsafe OPC vendor cache."""


@dataclass(frozen=True)
class CachedPlateModel:
    printer: str
    vendor: str
    bed_model: str
    bed_texture: str
    model_id: str = ""
    family: str = ""
    technology: int = 0


class _Reader:
    def __init__(self, body: bytes):
        self._body = memoryview(body)
        self.cursor = 0

    def take(self, count: int) -> bytes:
        if not 0 <= count <= len(self._body) - self.cursor:
            raise OpcFormatError("truncated cache metadata")
        result = self._body[self.cursor:self.cursor + count]
        self.cursor += count
        return result.tobytes()

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack('<H', self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack('<I', self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack('<i', self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack('<Q', self.take(8))[0]

    def sequence_count(self, limit: int = MAX_ITEMS) -> int:
        count = self.u64()  # cereal::size_type is uint64_t
        if count > limit:
            raise OpcFormatError(f"unreasonably large serialized collection: {count}")
        return count

    def text(self, limit: int = MAX_STRING) -> str:
        count = self.u64()
        if count > limit:
            raise OpcFormatError(f"serialized string exceeds limit: {count}")
        try:
            return self.take(count).decode('utf-8', errors='strict')
        except UnicodeDecodeError as exc:
            raise OpcFormatError('invalid UTF-8 in vendor cache') from exc

    def strings(self, limit: int = MAX_ITEMS) -> list[str]:
        return [self.text() for _ in range(self.sequence_count(limit))]


def read_opc_models(file: str | Path) -> tuple[CachedPlateModel, ...]:
    """Return model/bed references from a CRC-verified OrcaSlicer .opc file.

    Never returns unverified strings from an invalid header/cache. Does not read
    preset options, so an option-schema change cannot break plate discovery.
    """
    path = Path(file)
    try:
        size = path.stat().st_size
        if size < 24 or size > MAX_FILE:
            raise OpcFormatError(f"cache size unsupported: {size}")
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE + 1)
    except OSError as exc:
        raise OpcFormatError(f"cannot read {path.name}: {exc}") from exc
    if len(raw) != size:
        raise OpcFormatError('cache changed during read')
    magic, version, body_size, crc = struct.unpack('<IIQI', raw[:20])
    if magic != MAGIC:
        raise OpcFormatError('not an ORCZ vendor cache')
    if version != VERSION:
        raise OpcFormatError(f'unsupported header cache version {version}')
    if not body_size or body_size != size - 20:
        raise OpcFormatError('incorrect body size')
    body = raw[20:]
    if (zlib.crc32(body) & 0xffffffff) != crc:
        raise OpcFormatError('vendor cache failed CRC32 validation')

    reader = _Reader(body)
    if reader.u32() != VERSION:
        raise OpcFormatError('unsupported payload cache version')
    vendor_stamp = reader.text(1024)
    vendor_version = reader.text(1024)
    if not vendor_stamp or not vendor_version or vendor_stamp != path.stem:
        raise OpcFormatError('vendor name/version stamp mismatch')
    # CacheDictionary::save: m_keys, m_types (vector<uint16_t>), enum names.
    keys = reader.strings(65535)
    types = reader.sequence_count(65535)
    if types != len(keys):
        raise OpcFormatError('cache dictionary key/type lengths differ')
    reader.take(types * 2)
    enum_names = reader.strings(65535)
    if not enum_names or enum_names[0]:
        raise OpcFormatError('invalid enumeration dictionary')

    # VendorMap is std::map<std::string, VendorProfile>; cereal map writes
    # uint64 entry count followed by key/value pairs in declaration order.
    profiles = reader.sequence_count(256)
    models = []
    found_vendor = False
    for _ in range(profiles):
        key = reader.text()
        vendor_name = reader.text()
        vendor_id = reader.text()
        reader.text()  # Semver::save_minimal string, not three fixed ints
        reader.text()  # config_update_url
        reader.text()  # changelog_url
        count = reader.sequence_count(4096)
        if key == vendor_stamp and vendor_id == vendor_stamp:
            found_vendor = True
        for _ in range(count):
            model_id = reader.text()
            name = reader.text()
            reader.text()  # internal model_id (database ID)
            technology = reader.u8()  # C++ PrinterTechnology : unsigned char, 1 byte
            family = reader.text()
            variants = reader.sequence_count(256)
            for __ in range(variants):
                reader.text()  # PrinterVariant.name
            reader.strings(1024)  # default_materials
            reader.strings(128)  # unsupported_bed_types
            bed_model = reader.text()
            bed_texture = reader.text()
            # image_bed_type, bottom_texture_end_name, dual-extruder texture,
            # bottom_texture_rect, bottom_texture_rect_longer,
            # middle_texture_rect, hotend_model.
            for __ in range(7):
                reader.text()
            if key == vendor_stamp and vendor_id == vendor_stamp and name and bed_model:
                models.append(CachedPlateModel(name, vendor_id, bed_model,
                                               bed_texture, model_id, family, technology))
        reader.strings(2048)  # default_filaments (set<string>)
        reader.strings(2048)  # default_sla_materials (set<string>)
    if not found_vendor:
        raise OpcFormatError('cache does not contain matching VendorProfile')
    # Remaining bytes are process/filament/printer preset entries; intentionally
    # not parsed. Header size and CRC already authenticate the entire body.
    return tuple(models)


def checked_vendor_asset(root: Path, vendor: str, relative: str,
                         *, required: bool = True) -> Path | None:
    """Allow only actual files under root/vendor; never trust OPC asset paths."""
    if not relative:
        return None
    vendor_dir = (root / vendor).resolve()
    try:
        vendor_dir.relative_to(root.resolve())
    except ValueError:
        return None
    value = relative.replace('\\', '/')
    if '\x00' in value or ':' in value or value.startswith('/'):
        return None
    path = (vendor_dir / value).resolve()
    try:
        path.relative_to(vendor_dir)
    except ValueError:
        return None
    if not path.is_file():
        return None
    if required and path.suffix.lower() != '.stl':
        return None
    if not required and path.suffix.lower() not in ('.png', '.svg', '.jpg', '.jpeg', '.webp'):
        return None
    return path


def discover_opc_plate_assets(roots: Iterable[Path], plate_asset_class):
    """Read existing Orca vendor cache files; return (assets, diagnostics).

    PlateAsset positional order matches the established 6A2 catalog contract:
    printer, vendor, source, STL path, optional texture, profile source, root.
    """
    assets = []
    messages = []
    scanned = set()
    for item in roots:
        root = Path(item).expanduser()
        try:
            root = root.resolve()
            if root in scanned or not root.is_dir():
                continue
            scanned.add(root)
            caches = sorted(root.glob('*.opc'), key=lambda p: p.name.casefold())
            if not caches:
                continue
            for cache in caches:
                try:
                    models = read_opc_models(cache)
                except OpcFormatError as exc:
                    messages.append(f'OrcaSlicer {cache.name}: {exc}')
                    continue
                for model in models:
                    stl = checked_vendor_asset(root, model.vendor, model.bed_model)
                    if stl is None:
                        messages.append(f'OrcaSlicer {cache.name} / {model.printer}: bed STL missing or unsafe')
                        continue
                    texture = checked_vendor_asset(root, model.vendor, model.bed_texture, required=False)
                    assets.append(plate_asset_class(model.printer, model.vendor, 'OrcaSlicer',
                                                   stl, texture, cache, root))
        except OSError as exc:
            messages.append(f'Cannot scan OPC profile directory: {exc}')
    return assets, messages


def _possible_roots(original_discovery, args, kwargs, existing_catalog):
    roots = []
    # Access original API by name rather than assuming positional parameter order.
    try:
        arguments = inspect.signature(original_discovery).bind_partial(*args, **kwargs).arguments
    except (TypeError, ValueError):
        arguments = kwargs
    for key in ('resource_roots','roots'):
        for item in (arguments.get(key) or ()):
            roots.append(Path(item))
    for item in arguments.get('slicer_executables') or ():
        exe = Path(item)
        for base in (exe.parent,exe.parent.parent,exe.parent.parent.parent):
            roots.extend((base/'resources'/'profiles', base/'Resources'/'profiles'))
    for item in getattr(existing_catalog, 'sources', ()):
        for attribute in ('profile_root','root','path','directory'):
            value = getattr(item, attribute, None)
            if value is not None:
                roots.append(Path(value))
        if isinstance(item, (tuple,list)):
            for value in item:
                try:
                    path = Path(value)
                except (TypeError, ValueError):
                    continue
                if path.is_dir():
                    roots.append(path)
    # Nonempty explicit roots/executables and mocked discovery dependencies
    # define an isolated search universe.  Do not inject the host OrcaSlicer
    # installation in those calls; otherwise temporary unittest fixtures
    # unexpectedly contain hundreds of real printer models.
    # Important: the Qt UI forwards resource_roots=() and
    # slicer_executables=() during ordinary automatic discovery.  Empty
    # defaults therefore must NOT disable the installed-slicer fallback.
    custom_roots = any(bool(arguments.get(key) or kwargs.get(key))
                       for key in ('resource_roots', 'roots', 'slicer_executables'))
    simulated_host = any((arguments.get(key, kwargs.get(key)) is not None)
                         for key in ('registry_candidates', 'path_lookup', 'environ'))
    if custom_roots or simulated_host:
        return roots

    # Conventional installations, including the currently reported Windows path.
    for key in ('PROGRAMFILES','ProgramFiles','ProgramFiles(x86)','PROGRAMFILES(X86)',
                'LOCALAPPDATA'):
        base = os.environ.get(key)
        if base:
            roots.append(Path(base)/'OrcaSlicer'/'resources'/'profiles')
    if os.name == 'nt':
        roots.extend((Path('C:/Program Files/OrcaSlicer/resources/profiles'),
                      Path('C:/Program Files (x86)/OrcaSlicer/resources/profiles')))
    return roots


def extend_plate_catalog_with_opc(original_discovery, *args, **kwargs):
    """Extend original JSON catalog without changing its API or assets.

    Reuses PlateAsset and PlateCatalog from the original discovery function's
    module, preserving its sorted picker and all Bambu Studio profiles.
    """
    catalog = original_discovery(*args, **kwargs)
    namespace = inspect.getmodule(original_discovery)
    if namespace is None:
        return catalog
    asset_cls = getattr(namespace, 'PlateAsset', None)
    if asset_cls is None or not hasattr(catalog, 'plates'):
        return catalog
    roots = _possible_roots(original_discovery, args, kwargs, catalog)
    extras, diagnostics = discover_opc_plate_assets(roots, asset_cls)
    if not extras and not diagnostics:
        return catalog
    existing = list(catalog.plates)
    seen = {(p.source.casefold(), p.vendor.casefold(), p.printer.casefold()) for p in existing}
    for p in extras:
        key = (p.source.casefold(), p.vendor.casefold(), p.printer.casefold())
        if key not in seen:
            seen.add(key)
            existing.append(p)
    existing.sort(key=lambda p: (p.printer.casefold(), p.source.casefold(), p.vendor.casefold()))
    changes = {'plates':tuple(existing)}
    if diagnostics and hasattr(catalog, 'warnings'):
        changes['warnings'] = tuple(getattr(catalog, 'warnings') or ()) + tuple(diagnostics[:150])
    if is_dataclass(catalog):
        return replace(catalog, **changes)
    # NamedTuple compatibility, if the catalog changed its implementation.
    if hasattr(catalog, '_replace'):
        return catalog._replace(**changes)
    raise TypeError('Unsupported PlateCatalog type; cannot safely merge OPC profiles')


def cli():
    """Standalone read-only smoke check on an installed OrcaSlicer profile tree."""
    import argparse
    parser = argparse.ArgumentParser(description='Inspect OrcaSlicer v2 .opc build plates (read-only)')
    parser.add_argument('--root', type=Path, required=True,
                        help='Installed OrcaSlicer resources/profiles directory')
    parser.add_argument('--examples', type=int, default=12,
                        help='Show up to this many resolved printer names')
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error('profiles directory does not exist')
    class _TemporaryAsset:
        def __init__(self, printer, vendor, source, mesh, texture, profile, root):
            self.printer = printer
            self.vendor = vendor
            self.source = source
            self.mesh = mesh
            self.texture = texture
            self.profile = profile
            self.root = root

    caches = tuple(args.root.glob('*.opc'))
    models = 0
    bad = 0
    for file in sorted(caches):
        try:
            models += len(read_opc_models(file))
        except OpcFormatError:
            bad += 1
    assets, warnings = discover_opc_plate_assets((args.root,), _TemporaryAsset)
    print(f'PROFILE ROOT: {args.root}')
    print(f'OPC FILES: {len(caches)} | UNREADABLE/UNSUPPORTED CACHES: {bad}')
    print(f'CACHED PRINTER MODELS WITH BED REFERENCES: {models}')
    print(f'RESOLVED STL BUILD PLATES: {len(assets)}')
    print(f'WARNINGS: {len(warnings)}')
    for asset in assets[:max(0,min(args.examples,100))]:
        print(f'  {asset.vendor} / {asset.printer} | {asset.mesh.name}'
              f' | texture: {asset.texture.name if asset.texture else "(none)"}')
    for line in warnings[:15]:
        print('  WARNING:',line)
    return 0 if caches and models and assets else 1


if __name__ == '__main__':
    raise SystemExit(cli())
