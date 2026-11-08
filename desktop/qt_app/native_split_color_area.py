"""Read-only, source-area-based color verification for Bambu/Orca split paint.

This is ONLY a diagnostic/color-swatch representation. It does not measure
filament volume, produce mixing recipes, protect native source colors, or
change source geometry. Each displayed subdivision contributes its geometric
surface area in mm^2, never one whole original triangle per subregion.

Use only for cases where the legacy native scan refuses a complex paint state.
The authoritative 3MF reader must have successfully reconstructed ALL colored
regions, including every part/default assignment, with no unresolved faces.
"""
from __future__ import annotations

from collections import defaultdict
from math import hypot, isfinite
import re

_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _area_mm2(a, b, c):
    ax, ay, az = (float(b[i]) - float(a[i]) for i in range(3))
    bx, by, bz = (float(c[i]) - float(a[i]) for i in range(3))
    return 0.5 * hypot(ay * bz - az * by,
                       az * bx - ax * bz,
                       ax * by - ay * bx)


def split_source_surface_areas(path):
    """Return actual displayed source color area (mm^2) for a split-painted 3MF.

    Fail closed if original paint assignments could not all be reproduced.
    The preview has an existing 750k display-face guard and archive bounds;
    this function cannot enlarge them. Caller runs it off the UI thread.
    """
    from desktop.qt_app.mesh_loader import load_3mf
    mesh = load_3mf(path)
    faces = mesh.triangles
    colors = mesh.face_colors
    if (getattr(mesh, 'split_painted_faces', 0) <= 0 or
            getattr(mesh, 'split_paint_regions', 0) <= 0 or
            mesh.source_triangles >= len(faces)):
        raise ValueError('No decoded native split-paint regions found')
    if ('unsupported/unknown faces' in mesh.color_status.lower() or
            len(colors) != len(faces)):
        raise ValueError('Native paint coverage is incomplete; cannot verify colors')
    areas = defaultdict(float)
    for face, color in zip(faces, colors):
        if not isinstance(color, str) or not _COLOR.fullmatch(color):
            raise ValueError('Unassigned or unsupported source paint; cannot verify colors')
        try:
            triangle = tuple(mesh.vertices[int(index)] for index in face)
            area = _area_mm2(*triangle)
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError('Invalid native paint facet geometry') from exc
        if not isfinite(area) or area <= 0:
            raise ValueError('Degenerate or non-finite native paint facet geometry')
        areas[color.upper()] += area
    if not areas or any(not isfinite(v) or v <= 0 for v in areas.values()):
        raise ValueError('No verified native paint surface area')
    return dict(sorted(areas.items()))
