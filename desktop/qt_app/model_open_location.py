"""UI-only model-open location preferences (independent of export settings).

A user-set default folder has priority; otherwise remember the most recent
successfully selected local model folder. No source files are modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def location_path(plate_workspace_path):
    return Path(plate_workspace_path).with_name('model_open_location.json')


def _clean_path(value):
    return value if isinstance(value, str) and len(value) <= 8192 and '\x00' not in value else ''


def normalize_location(data):
    if not isinstance(data, dict):
        data = {}
    return {'default_directory': _clean_path(data.get('default_directory')),
            'last_directory': _clean_path(data.get('last_directory'))}


def read_location(path):
    try:
        return normalize_location(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    except (OSError, UnicodeError, TypeError, ValueError):
        return normalize_location({})


def write_location(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                prefix='.model-location-', suffix='.tmp', delete=False) as handle:
            temp = Path(handle.name)
            json.dump(normalize_location(value), handle, indent=2)
            handle.write('\n')
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def initial_directory(location, home=None):
    """Prefer an existing user-set folder, last used folder, then Documents/home."""
    location = normalize_location(location)
    base = Path(home) if home is not None else Path.home()
    candidates = [location['default_directory'], location['last_directory'],
                  str(base / 'Documents'), str(base)]
    for candidate in candidates:
        if candidate:
            try:
                path = Path(candidate).expanduser()
                if path.is_dir():
                    return str(path.resolve())
            except (OSError, ValueError, RuntimeError):
                continue
    return str(base)


def with_default_folder(location, directory):
    state = normalize_location(location)
    folder = Path(directory).expanduser()
    if not folder.is_dir():
        raise ValueError('Model folder does not exist')
    state['default_directory'] = str(folder.resolve())
    return state


def with_last_opened_model(location, model_path):
    state = normalize_location(location)
    try:
        file = Path(model_path).expanduser()
        if file.is_file():
            state['last_directory'] = str(file.resolve().parent)
    except (OSError, RuntimeError, ValueError, TypeError):
        pass
    return state
