"""Read-only perspective-grid camera helpers (Stage 6A3-D).

The grid has its own extents, distinct from the model and build plate. These
helpers make the GL clipping volume include the full reference plane without
resizing the model or altering its geometry, transforms, forecasts, or exports.
"""
from __future__ import annotations

from functools import lru_cache
import math

from desktop.qt_app.preview_grid_geometry import world_grid_vertices


@lru_cache(maxsize=32)
def world_grid_footprint(model_bounds):
    """XY limits of the exact generated grid, including major-aligned edges.

    Cached on immutable model bounds: orbiting never rebuilds the world grid to
    compute its camera clip volume. Reflects the same float32 coordinates as GL.
    Returns (min_x, max_x, min_y, max_y).
    """
    model_bounds = tuple(float(v) for v in model_bounds)
    if len(model_bounds) != 6:
        raise ValueError('Expected six model bounds')
    data, _step = world_grid_vertices(model_bounds, 0.0)
    if not data:
        raise ValueError('Perspective grid has no geometry')
    return (float(min(data[0::7])), float(max(data[0::7])),
            float(min(data[1::7])), float(max(data[1::7])))


def expand_clip_for_grid(eye, target, near_far, xy_limits, floor_z):
    """Expand near/far to contain the four world-grid corner depths.

    Depths are measured along the actual camera view direction; a bounding
    sphere would needlessly lower depth precision on oblique views. This does
    NOT guarantee screen-edge visibility under manual zoom (which is expected).
    """
    near, far = map(float, near_far)
    eye = tuple(map(float, eye))
    target = tuple(map(float, target))
    min_x, max_x, min_y, max_y = map(float, xy_limits)
    z = float(floor_z)
    if (len(eye) != 3 or len(target) != 3 or
        not all(map(math.isfinite, (near, far, *eye, *target,
                                    min_x, max_x, min_y, max_y, z))) or
        near <= 0 or far <= near or min_x > max_x or min_y > max_y):
        raise ValueError('Invalid camera or grid bounds')
    forward = tuple(target[i] - eye[i] for i in range(3))
    length = math.sqrt(sum(c*c for c in forward))
    if length < 1e-9:
        return near, far
    forward = tuple(c / length for c in forward)
    depths = [sum((corner[i] - eye[i]) * forward[i] for i in range(3))
              for corner in ((x, y, z) for x in (min_x, max_x)
                                   for y in (min_y, max_y))]
    positive = [depth for depth in depths if depth > 0]
    if not positive:
        return near, far  # A plane wholly behind the camera cannot be shown.
    # Do not drag the near plane toward zero if the camera is inside/crossing
    # the grid; clipping behind the viewer is a normal perspective limitation.
    if len(positive) == len(depths):
        near = max(0.001, min(near, min(positive) * 0.80))
    far = max(far, max(positive) * 1.08, near * 1.01)
    return near, far


def scene_grid_bounds(model_bounds, floor_z):
    """3D AABB enclosing model AND grid (only for explicit Fit Grid)."""
    x0, y0, z0, x1, y1, z1 = (float(v) for v in model_bounds)
    a, b, c, d = world_grid_footprint(tuple(model_bounds))
    z = float(floor_z)
    return (min(x0, a), min(y0, c), min(z0, z),
            max(x1, b), max(y1, d), max(z1, z))


def fit_grid_zoom(viewport_width, viewport_height):
    """Conservative zoom that fits a bounding sphere for a 45-degree camera."""
    aspect = max(0.05, float(viewport_width) / max(1.0, float(viewport_height)))
    half_angle = math.atan(math.tan(math.radians(22.5)) * min(1.0, aspect))
    return max(0.2, min(1.0, 3.2 * math.sin(half_angle) / 1.15))
