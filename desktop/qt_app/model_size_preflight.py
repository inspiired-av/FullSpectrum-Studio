"""Lightweight OBJ bounds preflight and explicit per-file dimension choices.

Preflight scans only position records; no face arrays, normals, render buffers,
OpenGL, or source rewrites. It precedes the ONE full preview preparation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

from desktop.qt_app.model_intended_dimensions import source_dimensions

STORE_VERSION = 1
MAX_CHOICES = 256


def scan_obj_bounds(path, *, cancelled=None):
    """Return XYZ min/max for an OBJ, or None for unusable positions.

    Iterate binary lines with O(1) retained mesh memory. Use only geometric
    `v` records (not `vt` or `vn`). Full validation remains the loader's job.
    """
    path = Path(path)
    if path.suffix.lower() != '.obj':
        return None
    low = [math.inf] * 3
    high = [-math.inf] * 3
    vertices = 0
    with path.open('rb') as stream:
        for index, line in enumerate(stream):
            if index % 4096 == 0 and cancelled is not None and cancelled():
                raise InterruptedError('OBJ dimension inspection cancelled')
            part = line.lstrip(b' \t')
            if not part.startswith((b'v ', b'v\t')):
                continue
            parts = part.split(maxsplit=4)
            if len(parts) < 4:
                return None
            try:
                xyz = [float(part) for part in parts[1:4]]
            except (ValueError, OverflowError):
                return None
            if not all(math.isfinite(v) for v in xyz):
                return None
            for axis in range(3):
                low[axis] = min(low[axis], xyz[axis])
                high[axis] = max(high[axis], xyz[axis])
            vertices += 1
    if cancelled is not None and cancelled():
        raise InterruptedError('OBJ dimension inspection cancelled')
    return (*low, *high) if vertices else None


def suspicious_obj_bounds(bounds):
    """Heuristic only; never infer real units or silently choose a scale."""
    if bounds is None:
        return False
    try:
        dims = source_dimensions(bounds)
    except (TypeError, ValueError, OverflowError):
        return False
    biggest = max(dims)
    return biggest > 0 and (biggest < 20.0 or biggest > 1000.0)


def model_fingerprint(path):
    """Hash path+file metadata. Moving/editing a model makes a new choice."""
    path = Path(path).resolve(strict=True)
    info = path.stat()
    if not path.is_file():
        raise ValueError('Not a model file')
    payload = json.dumps([os.path.normcase(str(path)), info.st_size, info.st_mtime_ns],
                         separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _read_store(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('version') == STORE_VERSION and isinstance(data.get('choices'), dict):
            return dict(data['choices'])
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


def read_dimension_choice(store, model):
    try:
        record = _read_store(store).get(model_fingerprint(model))
        if not isinstance(record, dict):
            return None
        if record.get('action') == 'skip':
            return {'action': 'skip'}
        if record.get('action') == 'apply':
            factor = float(record.get('factor'))
            if math.isfinite(factor) and factor > 0:
                return {'action': 'apply', 'factor': factor}
    except (OSError, ValueError, TypeError, OverflowError):
        pass
    return None


def save_dimension_choice(store, model, action, factor=None):
    """Only explicit opt-in calls this; atomic JSON replacement."""
    if action not in ('skip', 'apply'):
        raise ValueError('Unsupported dimension choice')
    if action == 'apply':
        factor = float(factor)
        if not (math.isfinite(factor) and factor > 0):
            raise ValueError('Invalid dimension choice scale')
    record = {'action': action, 'updated': time.time()}
    if action == 'apply':
        record['factor'] = factor
    key = model_fingerprint(model)
    existing = _read_store(store)
    existing[key] = record
    if len(existing) > MAX_CHOICES:
        existing = dict(sorted(existing.items(),
                               key=lambda item: item[1].get('updated', 0)
                               if isinstance(item[1], dict) else 0,
                               reverse=True)[:MAX_CHOICES])
    path = Path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.fs-dimchoice-',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': STORE_VERSION, 'choices': existing},
                      stream, indent=2, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def forget_dimension_choice(store, model):
    try:
        key = model_fingerprint(model)
        data = _read_store(store)
    except (OSError, ValueError, TypeError):
        return
    if key not in data:
        return
    data.pop(key)
    path = Path(store)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.fs-dimchoice-',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': STORE_VERSION, 'choices': data}, stream,
                      indent=2, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
