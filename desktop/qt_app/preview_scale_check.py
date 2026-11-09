"""Non-destructive, unit-aware geometry size warnings for source preview.

OBJ coordinates are unitless; glTF conventionally uses metres. The current
Qt preview and native importer do not normalize either format to millimetres.
Never silently scale geometry, modify the source or claim an inferred unit.
"""
from __future__ import annotations

import math
from pathlib import Path


def dimensions(bounds):
    """Return bounding dimensions in source coordinate units, or None."""
    try:
        values = tuple(float(v) for v in bounds)
        if len(values) != 6 or not all(math.isfinite(v) for v in values):
            return None
        result = tuple(values[i + 3] - values[i] for i in range(3))
        return result if all(v >= 0 for v in result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def scale_warning(bounds, filename):
    """Surface a warning only on unusually sized OBJ/GLB inputs.

    It is intentionally impossible to guess a correct physical print scale
    from OBJ coordinates alone. Explicit native 3MF units are out of scope.
    """
    extension = Path(str(filename)).suffix.lower()
    if extension not in ('.obj', '.glb'):
        return ''
    extents = dimensions(bounds)
    if extents is None:
        return ''  # Loader owns invalid-geometry errors.
    biggest = max(extents)
    if biggest >= 20.0 and biggest <= 1000.0:
        return ''
    shown = ' × '.join(f'{value:.3g}' for value in extents)
    if biggest < 20.0:
        flag = 'Unusually small model'
    else:
        flag = 'Unusually large model'
    if extension == '.obj':
        unit = 'OBJ has no defined units. Coordinates may not be millimeters.'
    else:
        unit = ('GLB/glTF coordinates are conventionally in meters; this '
                'Qt preview does not currently convert them to millimeters.')
    instruction = (
        ' To set intended OBJ dimensions: open File → Set Intended Dimensions…, '
        'choose X, Y, or Z, enter the intended size in millimeters, '
        'then select Apply Dimensions. The original OBJ stays unchanged.'
        if extension == '.obj' else '')
    return (f'{flag}: {shown} source units (X × Y × Z). {unit} '
            'Verify physical dimensions in the slicer before printing; '
            'FullSpectrum has not changed the model scale.' + instruction)
