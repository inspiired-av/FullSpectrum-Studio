"""Preview-only plate preferences, never part of conversion or plan settings.

Keep a stable printer identity instead of absolute slicer asset paths. If slicers
update/move, the preferred printer is resolved against the fresh local catalog.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def workspace_path(settings_path=None, *, environ=None, home=None):
    if settings_path is not None:
        return Path(settings_path).expanduser().with_name('plate_workspace.json')
    env = os.environ if environ is None else environ
    if os.name == 'nt' or 'APPDATA' in env:
        root = Path(env.get('APPDATA') or env.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Roaming'))
        return root / 'FullSpectrum Studio' / 'plate_workspace.json'
    root = Path(env.get('XDG_CONFIG_HOME') or ((home or Path.home()) / '.config'))
    return root / 'FullSpectrum Studio' / 'plate_workspace.json'


def read_workspace(path):
    """Invalid settings are ignored; filesystem and renderer must still work."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {}
        result = {}
        candidate = data.get('default')
        if isinstance(candidate, dict) and all(isinstance(candidate.get(k), str)
                                               and 0 < len(candidate[k]) <= 256
                                               for k in ('printer','vendor','source')):
            result['default'] = {k:candidate[k] for k in ('printer','vendor','source')}
        result['visible'] = data.get('visible', True) is not False
        for key in ('slicer_executables', 'resource_roots'):
            values = data.get(key, [])
            result[key] = ([v for v in values if isinstance(v, str) and 0 < len(v) < 4096]
                           if isinstance(values, list) else [])[:12]
        return result
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}


def write_workspace(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2) + '\n'
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.plate-workspace-',
                                         suffix='.tmp', delete=False) as file:
            tmp = Path(file.name)
            file.write(payload)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def find_default_plate(catalog, default):
    if not isinstance(default, dict):
        return None
    matches = [p for p in catalog.plates
               if p.printer.casefold() == str(default.get('printer','')).casefold()
               and p.vendor.casefold() == str(default.get('vendor','')).casefold()]
    if not matches:
        return None
    source = str(default.get('source',''))
    return next((p for p in matches if p.source == source), None) or next(
        (p for p in matches if p.source == 'OrcaSlicer'), matches[0])
