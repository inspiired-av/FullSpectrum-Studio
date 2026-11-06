"""Discover locally installed OrcaSlicer/Bambu Studio 3D build-plate assets.

Read-only, Qt-independent discovery for Advanced 3D Preview 6A2-A.
Only trusted *references* to the user's installed assets are returned: this
module never copies vendor files, renders meshes, or modifies an import/export.

A printer-model profile under resources/profiles/<vendor>/machine/ typically
names ``bed_model`` (STL) and ``bed_texture`` (SVG or bitmap) stored alongside
that vendor's machine/ directory. The same keys are used for non-Bambu models.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Iterable

from desktop.slicer_launcher import SLICER_EXECUTABLES, windows_slicer_candidates

SLICERS = ('OrcaSlicer', 'Bambu Studio')
TEXTURE_SUFFIXES = frozenset({'.svg', '.png', '.jpg', '.jpeg', '.webp'})
MAX_PROFILE_BYTES = 1_000_000
MAX_MESH_BYTES = 64_000_000
MAX_TEXTURE_BYTES = 16_000_000


@dataclass(frozen=True)
class PlateAsset:
    """An installed, currently readable plate resource (not an imported model)."""

    printer: str
    vendor: str
    source: str
    model: Path
    texture: Path | None
    profile: Path
    profile_root: Path

    @property
    def label(self) -> str:
        return f'{self.printer} — {self.source}'


@dataclass(frozen=True)
class PlateCatalog:
    roots: tuple[tuple[str, Path], ...]
    plates: tuple[PlateAsset, ...]
    warnings: tuple[str, ...]


def _profile_root(candidate: Path) -> Path | None:
    """Locate resources/profiles near an installed or portable slicer.

    Account for executables in bin/, packaged programs and alternate share/
    layouts without recursively searching the entire system or reading config
    profiles as if they were STL assets. The returned directory must contain
    actual vendor directories.
    """
    path = Path(candidate).expanduser()
    if path.suffix.casefold() == '.exe':
        path = path.parent
    choices = [path]
    parents = (path, path.parent, path.parent.parent)
    for folder in parents:
        choices.extend((folder/'profiles', folder/'resources'/'profiles',
                        folder/'Resources'/'profiles',
                        folder/'share'/'OrcaSlicer'/'profiles',
                        folder/'share'/'orca-slicer'/'profiles',
                        folder/'app'/'resources'/'profiles'))
    for choice in choices:
        try:
            if (choice.name.casefold() == 'profiles' and choice.is_dir()
                    and any(p.is_dir() for p in choice.iterdir())):
                return choice.resolve()
        except (OSError, RuntimeError):
            continue
    return None

def _read_json_profile(path: Path) -> dict | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_PROFILE_BYTES:
            return None
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def _vendor_file(folder: Path, filename: object, extensions: frozenset[str],
                 limit: int) -> Path | None:
    """Resolve only relative vendor-owned asset paths (no traversal/symlinks out)."""
    if not isinstance(filename, str) or not filename or '\x00' in filename:
        return None
    normalized = filename.replace('\\', '/')
    relative = PurePosixPath(normalized)
    if (relative.is_absolute() or ':' in normalized or
            any(x in ('', '.', '..') for x in normalized.split('/')) or
            relative.suffix.lower() not in extensions):
        return None
    try:
        root = folder.resolve()
        candidate = (root / Path(*relative.parts)).resolve()
        candidate.relative_to(root)
        if not candidate.is_file() or candidate.stat().st_size > limit:
            return None
    except (OSError, ValueError):
        return None
    return candidate


def scan_profile_root(profile_root: Path, source: str) -> tuple[tuple[PlateAsset, ...], tuple[str, ...]]:
    """Read printer-*model* JSON, not nozzle/filament/process presets."""
    root = _profile_root(Path(profile_root))
    if root is None:
        return (), ('Not a slicer resources/profiles directory: ' + str(profile_root),)
    plates: list[PlateAsset] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    # Machine-model profiles live in vendor/machine; the vendor-level JSON
    # contains only the manufacturer profile index, not a specific bed mesh.
    for vendor_root in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.casefold()):
        try:
            vendor_root.resolve().relative_to(root)
            machine_dir = vendor_root / 'machine'
            if not machine_dir.is_dir():
                continue
            machine_dir.resolve().relative_to(vendor_root.resolve())
        except (OSError, ValueError, RuntimeError):
            continue  # No profile directory symlinks outside the slicer root.
        for profile in sorted(machine_dir.glob('*.json'), key=lambda p: p.name.casefold()):
            try:
                profile.resolve().relative_to(machine_dir.resolve())
            except (OSError, ValueError, RuntimeError):
                continue
            data = _read_json_profile(profile)
            if data is None or data.get('type') != 'machine_model':
                continue
            model_ref = data.get('bed_model')
            if not isinstance(model_ref, str) or not model_ref.strip():
                continue
            mesh = _vendor_file(vendor_root, model_ref, frozenset({'.stl'}), MAX_MESH_BYTES)
            if mesh is None:
                warnings.append(f'{source} / {vendor_root.name} / {profile.name}: bed mesh unavailable or unsafe')
                continue
            texture_ref = data.get('bed_texture')
            texture = (_vendor_file(vendor_root, texture_ref, TEXTURE_SUFFIXES, MAX_TEXTURE_BYTES)
                       if texture_ref else None)
            if texture_ref and texture is None:
                warnings.append(f'{source} / {vendor_root.name} / {profile.name}: optional texture unavailable')
            printer = data.get('name') or profile.stem
            if not isinstance(printer, str) or not printer.strip():
                printer = profile.stem
            printer = printer.strip()
            vendor = vendor_root.name
            key = (vendor.casefold(), printer.casefold())
            if key in seen:
                continue
            seen.add(key)
            plates.append(PlateAsset(printer, vendor, source, mesh, texture,
                                     profile.resolve(), root))
    return tuple(plates), tuple(warnings)


def _discover_installed_plates_json(*, environ=None, registry_candidates=None, path_lookup=None,
                              slicer_executables: Iterable[Path] = (),
                              resource_roots: Iterable[Path] = ()) -> PlateCatalog:
    """Find local slicer installs; accept explicit roots for portable installs.

    Registry and PATH-based discovery share existing slicer-launcher logic.
    Call this in a background worker when integrating with the Qt interface.
    """
    env = os.environ if environ is None else environ
    roots: list[tuple[str, Path]] = []
    seen: set[tuple[str, str]] = set()

    def add(source, path):
        root = _profile_root(Path(path))
        if root is None:
            return
        key = source, os.path.normcase(str(root)).casefold()
        if key not in seen:
            seen.add(key)
            roots.append((source, root))

    for source in SLICERS:
        candidates = windows_slicer_candidates(
            source, environ=env,
            registry_candidates=registry_candidates,
            path_lookup=path_lookup,
        )
        for exe in candidates:
            # No guessed install is trusted without the actual executable.
            if Path(exe).is_file():
                add(source, Path(exe))
    for exe in slicer_executables:
        exe = Path(exe)
        if exe.is_file() and exe.suffix.lower() == '.exe':
            name = exe.name.lower()
            source = next((s for s, names in SLICER_EXECUTABLES.items()
                           if name in (n.lower() for n in names)), 'Custom slicer')
            add(source, exe)
    for root in resource_roots:
        words = {part.casefold().replace(' ', '').replace('-', '') for part in Path(root).parts}
        source = ('OrcaSlicer' if 'orcaslicer' in words else
                  'Bambu Studio' if 'bambustudio' in words else 'Custom')
        add(source, root)

    plates: list[PlateAsset] = []
    warnings: list[str] = []
    for source, root in roots:
        found, notices = scan_profile_root(root, source)
        plates.extend(found)
        warnings.extend(notices)
    plates.sort(key=lambda a: (a.vendor.casefold(), a.printer.casefold(),
                               0 if a.source == 'OrcaSlicer' else 1, a.source.casefold()))
    return PlateCatalog(tuple(roots), tuple(plates), tuple(warnings))


# OrcaSlicer v2 .opc cache metadata support (preview assets only).
from desktop.qt_app.opc_plate_profiles import extend_plate_catalog_with_opc
from functools import wraps as _opc_wraps

@_opc_wraps(_discover_installed_plates_json)
def discover_installed_plates(*args, **kwargs):
    return extend_plate_catalog_with_opc(
        _discover_installed_plates_json, *args, **kwargs)



def preferred_plate(catalog: PlateCatalog, printer: str,
                    source: str = 'Automatic') -> PlateAsset | None:
    """Prefer Orca assets in Automatic mode, but preserve explicit source picks."""
    matches = [p for p in catalog.plates if p.printer.casefold() == printer.strip().casefold()]
    if source != 'Automatic':
        matches = [p for p in matches if p.source == source]
    return min(matches, key=lambda p: (0 if p.source == 'OrcaSlicer' else 1,
                                       p.source.casefold(), str(p.profile))) if matches else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='List installed 3D slicer build plate assets (read-only).')
    parser.add_argument('--slicer-exe', type=Path, action='append', default=[],
                        help='Optional portable slicer executable (repeatable)')
    parser.add_argument('--resource-root', type=Path, action='append', default=[],
                        help='Optional resources/profiles directory (repeatable)')
    parser.add_argument('--all', action='store_true', help='Print every discovered plate, not only summary')
    args = parser.parse_args(argv)
    result = discover_installed_plates(slicer_executables=args.slicer_exe,
                                       resource_roots=args.resource_root)
    print(f'Discovered {len(result.plates)} local printer plate profiles across {len(result.roots)} profile roots')
    for source, root in result.roots:
        print(f'  {source}: {root}')
    if args.all:
        for asset in result.plates:
            tex = asset.texture.name if asset.texture else '(none)'
            print(f'  {asset.label} | STL: {asset.model.name} | texture: {tex}')
    else:
        for asset in result.plates[:12]:
            print('  ' + asset.label)
        if len(result.plates) > 12:
            print(f'  ... {len(result.plates) - 12} more; add --all to list them')
    if result.warnings:
        print(f'Ignored {len(result.warnings)} unavailable/unsafe asset references', file=sys.stderr)
        for warning in result.warnings[:8]:
            print('  ' + warning, file=sys.stderr)
    if not result.roots:
        print('No slicer resources found. Pass --slicer-exe or --resource-root for portable installations.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
