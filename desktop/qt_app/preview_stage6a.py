"""Small, Qt-independent helpers for the interactive 3D preview.

A dropped source model uses the *same* application loading path as Open Model.
Never interpret a remote URL, directory, or archive other than a known model type.
"""
from __future__ import annotations

from pathlib import Path

SUPPORTED_MODEL_SUFFIXES = frozenset({'.3mf', '.obj', '.glb'})


def classify_model_drop(paths):
    """Return (local_path, explanation). Accept exactly one existing model file."""
    paths = tuple(paths or ())
    if len(paths) != 1:
        return None, 'Drop one model file at a time.'
    item = paths[0]
    if not isinstance(item, (str, Path)):
        return None, 'Only local model files can be opened.'
    raw = str(item)
    if not raw or '\x00' in raw:
        return None, 'Invalid model file path.'
    path = Path(raw)
    if path.suffix.lower() not in SUPPORTED_MODEL_SUFFIXES:
        return None, 'Supported models: .3mf, .obj, .glb.'
    if not path.is_file():
        return None, 'Model file not found or not a regular file.'
    return str(path), ''
