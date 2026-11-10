"""App-owned custom PLA filament library, compatible with engine.custom_palette().

The user-managed JSON is separate from Bambu inventory/catalog files and other
user-supplied custom libraries. All saves are atomic and validated. The editor
can save one entry as a draft; the optimizer requires >=2 distinct colors.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

from desktop.settings_store import settings_path

FAMILIES = (
    'PLA Basic', 'PLA Matte', 'PLA Silk', 'PLA Silk+', 'PLA Marble',
    'PLA Sparkle', 'PLA Tough', 'PLA Tough+', 'PLA Aero', 'PLA Glow',
    'PLA Dynamic', 'PLA Galaxy', 'PLA Wood', 'PLA Translucent',
    'PLA Lite', 'PLA Pure', 'PLA-CF', 'PLA Metal',
)
MAX_FILAMENTS = 512
MAX_LIBRARY_BYTES = 512_000
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def personal_library_path(path=None):
    """Local per-user personal palette; never alter another selected JSON file."""
    return Path(path) if path is not None else settings_path().parent / 'my_filaments.json'


def normalize_filament(entry):
    """Reject invalid/ambiguous names, colors or unsupported material profiles."""
    if not isinstance(entry, dict):
        raise ValueError('Each filament must be an object with name, brand, series and color')
    result = {}
    for field, maximum, fallback in (
        ('name', 100, None), ('brand', 80, 'Custom'), ('series', 40, 'PLA Basic'),
    ):
        value = entry.get(field, fallback)
        if not isinstance(value, str):
            raise ValueError(f'{field.capitalize()} must be text')
        value = value.strip()
        if not value or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise ValueError(f'Enter a valid {field} (maximum {maximum} characters)')
        result[field] = value
    if result['series'] not in FAMILIES:
        raise ValueError('Select a supported PLA material profile')
    color = entry.get('color')
    if not isinstance(color, str) or not HEX.fullmatch(color):
        raise ValueError('Enter a six-digit HEX color, e.g. #61C680')
    result['color'] = color.upper()
    return result


def filament_key(entry):
    """Same unique identity as engine.anchor_key: material family + HEX."""
    f = normalize_filament(entry)
    return f["series"] + '|' + f['color']


def validate_library(filaments):
    if not isinstance(filaments, list) or len(filaments) > MAX_FILAMENTS:
        raise ValueError(f'Personal library supports up to {MAX_FILAMENTS} filaments')
    clean = [normalize_filament(item) for item in filaments]
    keys = [f['series']+'|'+f['color'] for f in clean]
    if len(keys) != len(set(keys)):
        raise ValueError('Only one filament per material profile and HEX color is supported')
    return clean


def ready_for_planning(filaments):
    return len({item['color'] for item in validate_library(filaments)}) >= 2


def load_personal_library(path=None):
    destination = personal_library_path(path)
    if not destination.exists():
        return []
    if not destination.is_file() or destination.is_symlink():
        raise ValueError('Personal filament library is not a regular file')
    if destination.stat().st_size > MAX_LIBRARY_BYTES:
        raise ValueError('Personal filament library exceeds its safety limit')
    try:
        payload = json.loads(destination.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Personal filament JSON is malformed; it was not modified') from exc
    if not isinstance(payload, dict) or set(payload) != {'filaments'}:
        raise ValueError('Unexpected personal library format; refusing to overwrite')
    return validate_library(payload['filaments'])


def save_personal_library(filaments, path=None):
    destination = personal_library_path(path)
    clean = validate_library(filaments)
    if destination.exists():
        # Do not clobber an edited or malformed file created elsewhere.
        load_personal_library(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({'filaments': clean}, ensure_ascii=False, indent=2) + '\n'
    if len(data.encode('utf-8')) > MAX_LIBRARY_BYTES:
        raise ValueError('Personal filament library exceeds its safety limit')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         prefix='.my-filaments-', suffix='.tmp',
                                         dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
