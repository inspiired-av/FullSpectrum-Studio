"""Display-only dimension precision helpers.

None of these functions is used to compute or quantize mesh transformations.
The dialog keeps Qt's numeric value, and uniform_scale receives that value
without passing through a formatted label.
"""
from __future__ import annotations

import math

INPUT_DECIMALS = 8


def _compact_display(value, places):
    """Show standard fixed precision, but never hide tiny nonzero sizes as zero."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('A dimension must be finite')
    if number != 0.0 and abs(number) < 0.5 * (10 ** (-places)):
        return format(number, '.8g')
    return format(number, f'.{places}f')


def display_source_extent(value):
    """Original OBJ coordinate span: ordinarily four decimal places."""
    return _compact_display(value, 4)


def display_result_mm(value):
    """Converted dimension: ordinarily two decimal places, label only."""
    return _compact_display(value, 2)


def display_scale_factor(value):
    """Scale multiplier: ordinarily two decimal places, label only."""
    return _compact_display(value, 2)


def compact_input_value(value, decimal_point='.', decimals=INPUT_DECIMALS):
    """QDoubleSpinBox display text without needless trailing decimal zeros.

    The Qt spin box retains the configured numeric precision; this helper is
    only used by textFromValue and never rounds mesh or export coordinates.
    """
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('A physical dimension must be finite')
    if not isinstance(decimals, int) or not 0 <= decimals <= 16:
        raise ValueError('Unsupported number of decimals')
    if decimal_point not in ('.', ','):
        raise ValueError('Unsupported decimal separator')
    rendered = format(number, f'.{decimals}f')
    whole, sep, fraction = rendered.partition('.')
    fraction = fraction.rstrip('0')
    return whole + (decimal_point + fraction if fraction else '')
