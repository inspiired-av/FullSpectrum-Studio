"""Bounded world-space XY reference lines, with pixel-independent spacing.

Pure math: no Qt, OpenGL, file IO or changes to model/plate geometry.
"""
from __future__ import annotations

from array import array
import math


def nice_step(value):
    """Choose a 1/2/5/10 * 10^N millimeter interval near *value*."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Grid step must be positive and finite')
    exponent = math.floor(math.log10(value))
    scale = 10.0 ** exponent
    mantissa = value / scale
    for base in (1.0, 2.0, 5.0, 10.0):
        if base >= mantissa:
            return base * scale
    return 10.0 * scale


def world_grid_vertices(bounds, floor_z, *, max_intervals=60):
    """Return interleaved XYZ + RGBA for GL_LINES, with bounded line counts.

    The grid is XY aligned in WORLD coordinates, centered around the visible
    model bounds and positioned just below the lowest displayed geometry.
    """
    x0, y0, z0, x1, y1, z1 = (float(n) for n in bounds)
    if not all(map(math.isfinite, (x0, y0, z0, x1, y1, z1, floor_z))):
        raise ValueError('Nonfinite preview bounds')
    if x1 < x0 or y1 < y0 or z1 < z0:
        raise ValueError('Invalid preview bounds')
    max_intervals = max(8, min(100, int(max_intervals)))
    center_x = (x0 + x1) / 2.0
    center_y = (y0 + y1) / 2.0
    # Scale to the model's full 3D envelope, not just its XY footprint.
    # Tall/narrow models need a broad enough ground reference, while tiny
    # models must not inherit an unrelated fixed 25 mm floor.
    reference_span = max(x1 - x0, y1 - y0, 0.80 * (z1 - z0), 0.001)
    half_extent = reference_span * 0.80
    # Around 14-20 useful grid cells across, in genuine millimeter units.
    step = nice_step((2.0 * half_extent) / 18.0)
    # Each direction is limited independently; bound buffer growth for
    # oddly shaped or extremely large models.
    half = min(max_intervals // 2, math.ceil(half_extent / step))
    cx_index = round(center_x / step)
    cy_index = round(center_y / step)
    ix0, ix1 = cx_index - half, cx_index + half
    iy0, iy1 = cy_index - half, cy_index + half
    a, b = ix0 * step, ix1 * step
    c, d = iy0 * step, iy1 * step
    vertices = array('f')

    def line(px, py, qx, qy, tint):
        vertices.extend((px, py, floor_z, *tint, qx, qy, floor_z, *tint))

    for xindex in range(ix0, ix1 + 1):
        x = xindex * step
        # World origin gets a muted red X-coordinate axis (X runs along Y=0,
        # so this is the GREEN Y-axis line at X=0).
        if xindex == 0:
            color = (0.26, 0.60, 0.35, 0.75)
        elif xindex % 5 == 0:
            color = (0.52, 0.60, 0.66, 0.35)
        else:
            color = (0.46, 0.54, 0.61, 0.16)
        line(x, c, x, d, color)
    for yindex in range(iy0, iy1 + 1):
        y = yindex * step
        if yindex == 0:
            color = (0.83, 0.32, 0.32, 0.75)
        elif yindex % 5 == 0:
            color = (0.52, 0.60, 0.66, 0.35)
        else:
            color = (0.46, 0.54, 0.61, 0.16)
        line(a, y, b, y, color)
    return vertices, step
