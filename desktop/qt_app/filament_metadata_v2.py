"""Strict, backward-compatible optional metadata for schema-v1 filament records.

Schema-v1 personal and palette JSON remain the canonical editable documents for
now. Extra *recognized* metadata fields are kept losslessly by normalize(),
including native preset references that must not be mistaken for verified data.
No I/O and no implicit catalog or slicer updates occur here.
"""
from __future__ import annotations

from datetime import date
import json
import math
import re
from urllib.parse import urlsplit

IDENTITY = re.compile(r'^[A-Za-z0-9_.:+-]{1,160}$')
PRESET_KEYS = ('slicer', 'preset_name', 'filament_id', 'setting_id',
               'printer_model', 'nozzle_mm', 'source_id', 'inherits', 'verification')
SUPPORTED_SLICERS = ('bambu_studio', 'orcaslicer', 'unknown')


def _short(value, field, limit=300):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{field} must be nonempty text (up to {limit} characters)')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{field} contains control characters')
    return value.strip()


def _url(value):
    value = _short(value, 'manufacturer_url', 1024)
    parts = urlsplit(value)
    if (parts.scheme not in ('https', 'http') or not parts.hostname or
            parts.username is not None or parts.password is not None or
            any(c.isspace() for c in value)):
        raise ValueError('manufacturer_url must be a valid HTTP(S) URL without credentials')
    return value


def _finite(value, field, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{field} must be a finite number')
    if not lo <= value <= hi:
        raise ValueError(f'{field} is outside supported range')
    return value


def _measured_lab(value):
    if not isinstance(value, dict) or set(value) != {'L', 'a', 'b'}:
        raise ValueError('measured_lab must contain L, a, and b measurements')
    return {'L': _finite(value['L'], 'L', 0, 100),
            'a': _finite(value['a'], 'a', -160, 160),
            'b': _finite(value['b'], 'b', -160, 160)}


def _optical_calibration(value):
    if not isinstance(value, dict):
        raise ValueError('optical_calibration must be an object')
    try:
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError('optical_calibration must contain finite JSON values') from exc
    if len(payload.encode('utf-8')) > 4096:
        raise ValueError('optical_calibration exceeds the 4 KiB limit')
    return value


def _preset_refs(value):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError('preset_refs must be a list of no more than 32 references')
    clean = []
    for ref in value:
        if not isinstance(ref, dict) or set(ref) - set(PRESET_KEYS):
            raise ValueError('Unknown native preset reference fields')
        slicer = ref.get('slicer', 'unknown')
        if slicer not in SUPPORTED_SLICERS:
            raise ValueError('Invalid preset slicer')
        result = {'slicer': slicer}
        for key in PRESET_KEYS:
            if key == 'slicer':
                continue
            if ref.get(key) is not None:
                result[key] = _short(ref[key], key)
        if not any(result.get(key) for key in ('preset_name', 'filament_id', 'setting_id')):
            raise ValueError('Preset reference requires a native identifier or name')
        clean.append(result)
    return clean


def retain_optional_metadata(original, normalized):
    """Add only explicitly supported metadata, retaining other normalized fields.

    Called *after* v1 normalize() validates the core filament data, so the
    optimizer's existing name/series/HEX representation remains unchanged.
    """
    if 'product_id' in original and original['product_id'] is not None:
        value = _short(original['product_id'], 'product_id', 160)
        if not IDENTITY.fullmatch(value):
            raise ValueError('Invalid explicit product_id')
        normalized['product_id'] = value
    if 'manufacturer_url' in original and original['manufacturer_url'] is not None:
        normalized['manufacturer_url'] = _url(original['manufacturer_url'])
    if 'last_verified' in original and original['last_verified'] is not None:
        raw = _short(original['last_verified'], 'last_verified', 10)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            raise ValueError('last_verified must be YYYY-MM-DD')
        try:
            date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError('last_verified must be YYYY-MM-DD') from exc
        normalized['last_verified'] = raw
    if 'measured_lab' in original and original['measured_lab'] is not None:
        normalized['measured_lab'] = _measured_lab(original['measured_lab'])
    if 'transmission_distance_mm' in original and original['transmission_distance_mm'] is not None:
        normalized['transmission_distance_mm'] = _finite(
            original['transmission_distance_mm'], 'transmission_distance_mm', 0.000001, 10000)
    if 'optical_calibration' in original and original['optical_calibration'] is not None:
        normalized['optical_calibration'] = _optical_calibration(original['optical_calibration'])
    if 'preset_refs' in original and original['preset_refs'] is not None:
        normalized['preset_refs'] = _preset_refs(original['preset_refs'])
    return normalized
