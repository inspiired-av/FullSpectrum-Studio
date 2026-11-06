"""Stage 6A3: preview-only grid mode, texture policy and persistence.

The real printer bed is never modified.  The stored settings are deliberately
separate from filament, forecast, export and build plate defaults.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

GRID_MODES = ('automatic', 'plate', 'perspective', 'off')
DEFAULT_GRID_SETTINGS = {'mode': 'automatic', 'last_mode': 'automatic', 'axes': True}


def settings_path(plate_workspace_path):
    return Path(plate_workspace_path).with_name('preview_grid.json')


def normalize_settings(data):
    if not isinstance(data, dict):
        return dict(DEFAULT_GRID_SETTINGS)
    mode = data.get('mode')
    if mode not in GRID_MODES:
        mode = 'automatic'
    last = data.get('last_mode')
    if last not in GRID_MODES or last == 'off':
        last = mode if mode != 'off' else 'automatic'
    axes = data.get('axes', True)
    return {'mode': mode, 'last_mode': last, 'axes': axes is not False}


def read_grid_settings(path):
    try:
        return normalize_settings(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError, UnicodeError, TypeError):
        return dict(DEFAULT_GRID_SETTINGS)


def write_grid_settings(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = normalize_settings(data)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='\n',
                                         dir=path.parent, prefix='.preview-grid-',
                                         suffix='.tmp', delete=False) as handle:
            tmp = Path(handle.name)
            json.dump(state, handle, indent=2)
            handle.write('\n')
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def choose_grid_layers(mode, *, plate_visible, plate_has_art):
    """Return (procedural plate grid, perspective floor grid).

    Automatic displays a measurable grid on *every* visible slicer bed; a
    bed_texture may contain just a logo, so texture presence is not evidence
    that grid lines are already present.  The grid is a shader overlay and
    leaves the underlying manufacturer image unchanged.  Users whose artwork
    already has its own grid can select Off to avoid duplicate markings.

    ``plate_has_art`` remains a compatibility argument for existing callers;
    it deliberately does not influence visibility.
    """
    if mode not in GRID_MODES:
        mode = 'automatic'
    if mode == 'off':
        return False, False
    if mode == 'perspective':
        return False, True
    if mode == 'plate':
        return bool(plate_visible), False
    if plate_visible:
        return True, False
    return False, True


def set_grid_mode(settings, mode):
    if mode not in GRID_MODES:
        raise ValueError('Unknown grid mode: ' + str(mode))
    result = normalize_settings(settings)
    result['mode'] = mode
    if mode != 'off':
        result['last_mode'] = mode
    return result


def toggle_grid(settings, checked):
    settings = normalize_settings(settings)
    return set_grid_mode(settings, settings['last_mode'] if checked else 'off')
