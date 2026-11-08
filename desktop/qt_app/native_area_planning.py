"""Strict, default-on geometry-area weights for native Bambu/Orca 3MF planning.

Reuses the authoritative read-only Qt 3MF decoder. Unlike TriangleSelector
leaf-reference counts, each painted display facet contributes its actual world-
space surface area in square millimeters. These are COLOR weights, NEVER sliced
filament volume/grams and NEVER modifications to the source or export paint tree.

This deliberately supports the same unambiguous physical-source-slot subset
as the validated native split-paint forecast overlay. Oversized, hybrid,
source-mixed, or incomplete paint cases fail closed to the legacy planner.
"""
from __future__ import annotations

from collections import Counter
import math
import os
import re

_RGB = re.compile(r'^#[0-9A-Fa-f]{6}$')
MAX_FACETS = 750_000  # aligned with desktop.qt_app.mesh_loader safety guard


def enabled() -> bool:
    """Verified native 3MF weights default on; 0/off restores legacy weights."""
    choice = os.environ.get('FULLSPECTRUM_NATIVE_AREA_WEIGHTS', 'auto').strip().lower()
    return choice in ('', 'auto', '1', 'true', 'yes', 'on')


def triangle_area_mm2(a, b, c):
    """Numerically stable area of an arbitrary 3D triangle in mm²."""
    u = tuple(float(b[i]) - float(a[i]) for i in range(3))
    v = tuple(float(c[i]) - float(a[i]) for i in range(3))
    x = u[1] * v[2] - u[2] * v[1]
    y = u[2] * v[0] - u[0] * v[2]
    z = u[0] * v[1] - u[1] * v[0]
    area = 0.5 * math.hypot(x, y, z)
    if not math.isfinite(area) or area <= 0:
        raise ValueError('Invalid or degenerate 3MF display facet area')
    return area


def facet_slot_areas(mesh, swatches):
    """Area by 1-based native physical slot, preserving every painted subfacet.

    RGB can stand in for slot identity ONLY after a separate reader has verified
    all native source swatches are distinct, solid, and have no hybrid material
    properties. This helper also rejects missing/gradient colors and malformed
    facet indices so a partial rendering never becomes an authoritative weight.
    """
    colors = tuple(str(c).upper() for c in swatches)
    if (not colors or any(not _RGB.fullmatch(c) for c in colors) or
            len(set(colors)) != len(colors)):
        raise ValueError('Source slots require distinct, valid physical RGB swatches')
    faces = mesh.triangles
    paint = mesh.face_colors
    corners = mesh.corner_colors
    if not faces or len(faces) > MAX_FACETS or len(paint) != len(faces):
        raise ValueError('Native paint display geometry is empty, incomplete or too large')
    if len(corners) != len(faces):
        raise ValueError('Missing per-corner paint provenance')
    if 'unsupported/unknown faces' in str(mesh.color_status).lower():
        raise ValueError('3MF has undecodable or unknown native paint faces')
    slots = {c: i for i, c in enumerate(colors, 1)}
    result = Counter()
    vertices = mesh.vertices
    for face, color, triple in zip(faces, paint, corners):
        if not isinstance(color, str) or color.upper() not in slots:
            raise ValueError('A display face does not match a distinct native filament slot')
        if tuple(triple) != (color, color, color):
            raise ValueError('Interpolated corner colors need explicit source-slot attribution')
        if len(face) != 3:
            raise ValueError('Invalid native facet indices')
        try:
            indices = tuple(int(i) for i in face)
            if any(i < 0 or i >= len(vertices) for i in indices) or len(set(indices)) != 3:
                raise ValueError('Invalid native facet indices')
            area = triangle_area_mm2(*(vertices[i] for i in indices))
        except (TypeError, IndexError, OverflowError) as exc:
            raise ValueError('Invalid native facet coordinates') from exc
        result[slots[color.upper()]] += area
    if (not result or any(not math.isfinite(a) or a <= 0 for a in result.values())
            or not math.isfinite(sum(result.values()))):
        raise ValueError('Invalid total native painted surface area')
    return Counter(dict(sorted(result.items())))


def native_surface_slot_weights(path, source_colors, *, loader=None,
                                validated_swatches=None):
    """Return optimizer Counter[physical source slot] = verified area in mm².

    Neither the mesh loader nor the native-project reader writes anything.
    Keep bounds and hybrid-material/mixed-slot guards identical to Stage 1.2's
    known-good live forecast overlay. The original slicer files remain intact.
    """
    if validated_swatches is None:
        from desktop.qt_app.native_split_forecast_preview import _read_unique_native_swatches
        validated_swatches = _read_unique_native_swatches
    if loader is None:
        from desktop.qt_app.mesh_loader import load_3mf
        loader = load_3mf
    source_colors = tuple(str(color).upper() for color in source_colors)
    verified = tuple(validated_swatches(path, len(source_colors)))
    if verified != source_colors:
        raise ValueError('Native source swatches differ from the engine palette')
    mesh = loader(path)
    return facet_slot_areas(mesh, verified)
