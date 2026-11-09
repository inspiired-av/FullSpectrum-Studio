"""Explicit, non-destructive *uniform* physical scaling for unitless OBJ inputs.

The derived OBJ is a temporary engine input shared by preview/forecast/export.
Original bytes, face indices, normals, UVs, materials, and vertex RGB stay intact.
No scaling is inferred from coordinate size. 3MF and GLB are not rewritten here.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import shlex
from pathlib import Path

AXES = ('X', 'Y', 'Z')
MAX_COORDINATE = 1.0e9


def source_dimensions(bounds):
    """Finite XYZ extents from the original, unscaled source mesh."""
    if len(bounds) != 6:
        raise ValueError('Invalid source bounds')
    numbers = tuple(float(number) for number in bounds)
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError('Source bounds contain non-finite values')
    result = tuple(numbers[n + 3] - numbers[n] for n in range(3))
    if any(value < 0 for value in result):
        raise ValueError('Source bounds are inverted')
    return result


def uniform_scale(bounds, axis, intended_mm):
    """Scale factor making the selected axis equal the stated physical size."""
    axis = str(axis).upper()
    if axis not in AXES:
        raise ValueError('Choose X, Y, or Z')
    target = float(intended_mm)
    if not math.isfinite(target) or not 0.001 <= target <= 1_000_000.0:
        raise ValueError('Intended dimension must be between 0.001 and 1,000,000 mm')
    dims = source_dimensions(bounds)
    original = dims[AXES.index(axis)]
    if original <= 1e-12:
        raise ValueError(f'The model has no measurable {axis} dimension')
    factor = target / original
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('The requested scale is not finite and positive')
    if any(abs(value) * factor > MAX_COORDINATE for value in bounds):
        raise ValueError('Scaled coordinates are too large')
    return factor


def scaled_dimensions(bounds, factor):
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('Invalid scale factor')
    return tuple(d * factor for d in source_dimensions(bounds))


def _relative_asset(raw):
    """Reject absolute/traversing paths; never follow links outside the model root."""
    if not raw or '\x00' in raw or re.match(r'^[A-Za-z]:', raw):
        return None
    normalized = raw.replace('\\', '/')
    path = Path(normalized)
    if path.is_absolute() or any(bit in ('', '..') for bit in path.parts):
        return None
    return path


def _copy_asset(source_root, target_root, name):
    relative = _relative_asset(name)
    if relative is None:
        return
    source_root = Path(source_root).resolve()
    source = (source_root / relative).resolve()
    if not source.is_relative_to(source_root) or not source.is_file():
        return
    target = Path(target_root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)  # avoids duplicate large texture files
    except OSError:
        shutil.copy2(source, target)


def _stage_materials(source, target):
    """Stage local OBJ sidecars, including conventional MTL texture references."""
    source = Path(source)
    src_root = source.parent
    dest_root = Path(target).parent
    materials = {source.with_suffix('.mtl').name}
    # mtllib can name an alternate MTL; supports common paths with spaces.
    with source.open('r', encoding='utf-8-sig', errors='replace') as stream:
        for line in stream:
            stripped = line.lstrip()
            if stripped.lower().startswith('mtllib '):
                materials.add(stripped[7:].strip().strip('"'))
    for name in sorted(materials):
        mtl_rel = _relative_asset(name)
        if mtl_rel is None:
            raise ValueError('OBJ references an external material path that cannot be staged safely')
        mtl = (src_root / mtl_rel).resolve()
        if not mtl.is_relative_to(src_root.resolve()):
            raise ValueError('OBJ material escapes the source directory')
        if not mtl.is_file():
            continue  # Missing even for the unchanged source; do not invent data.
        _copy_asset(src_root, dest_root, name)
        if mtl.stat().st_size > 4_000_000:
            continue
        for line in mtl.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            text = line.strip()
            if not text or text.startswith('#'):
                continue
            words = text.split(maxsplit=1)
            if len(words) != 2:
                continue
            directive = words[0].lower()
            if directive.startswith('map_') or directive in ('bump', 'disp', 'decal', 'refl'):
                # Preserve local MTL map paths. Reject unknown option forms
                # rather than silently dropping texture input during export.
                expression = words[1].strip()
                if expression.startswith('-'):
                    tokens = shlex.split(expression)
                    i = 0
                    counts = {'-s': 3, '-o': 3, '-t': 3, '-mm': 2,
                              '-bm': 1, '-clamp': 1, '-blendu': 1,
                              '-blendv': 1, '-imfchan': 1, '-texres': 1,
                              '-type': 1, '-boost': 1}
                    while i < len(tokens) and tokens[i].startswith('-'):
                        if tokens[i] not in counts or i + counts[tokens[i]] >= len(tokens):
                            raise ValueError('MTL has an unsupported texture option')
                        i += 1 + counts[tokens[i]]
                    path = ' '.join(tokens[i:])
                else:
                    path = expression.strip('"')
                if _relative_asset(path) is None:
                    raise ValueError('MTL references an external texture path')
                _copy_asset(src_root, dest_root, path)


def write_scaled_obj(source, destination, factor, *, cancelled=None):
    """Stage a derived OBJ; only positions on `v` records are changed.

    The destination must be on a different path. A partial file is never
    presented to a worker as a usable input. Existing targets are rejected.
    """
    original = Path(source).resolve()
    target = Path(destination).resolve()
    if original == target or original.suffix.lower() != '.obj' or target.suffix.lower() != '.obj':
        raise ValueError('Scaling requires a separate .obj destination')
    if not original.is_file() or target.exists():
        raise FileExistsError('Source missing or target already exists')
    factor = float(factor)
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError('Invalid scale factor')
    if cancelled and cancelled():
        raise InterruptedError('Scaling cancelled')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.obj.partial')
    if partial.exists():
        raise FileExistsError('Partial scaled OBJ already exists')
    changed = 0
    try:
        _stage_materials(original, target)
        with original.open('r', encoding='utf-8-sig', errors='replace', newline='') as inp, \
                partial.open('x', encoding='utf-8', newline='') as out:
            for i, line in enumerate(inp):
                if i % 4096 == 0 and cancelled and cancelled():
                    raise InterruptedError('Scaling cancelled')
                prefix = line[:len(line)-len(line.lstrip())]
                content = line[len(prefix):]
                if content.startswith('v ') or content.startswith('v\t'):
                    fields = content.split()
                    if len(fields) < 4:
                        raise ValueError('Invalid OBJ vertex record')
                    try:
                        xyz = tuple(float(v) * factor for v in fields[1:4])
                    except ValueError as exc:
                        raise ValueError('Invalid OBJ vertex coordinate') from exc
                    if any(not math.isfinite(v) or abs(v) > MAX_COORDINATE for v in xyz):
                        raise ValueError('Scaled OBJ vertex outside safe coordinate range')
                    remainder = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                    # Preserve all extra vertex fields (w and vertex colors), UVs,
                    # normal lines, and face indexing; normals need no rotation.
                    out.write(prefix + 'v ' + ' '.join(format(v, '.17g') for v in xyz)
                              + ((' ' + ' '.join(fields[4:])) if len(fields) > 4 else '')
                              + remainder)
                    changed += 1
                else:
                    out.write(line)
        if not changed:
            raise ValueError('OBJ has no vertices to scale')
        if cancelled and cancelled():
            raise InterruptedError('Scaling cancelled')
        partial.replace(target)
        return str(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
