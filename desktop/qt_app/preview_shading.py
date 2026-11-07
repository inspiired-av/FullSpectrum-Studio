"""Crease-aware, color-preserving vertex expansion for the desktop preview.

Model geometry, source colors and indices are never modified.  Smooth vertices
are cached when incident face normals are guaranteed to fall within the crease
angle; sharp/nonmanifold vertices retain the exact per-face selection rule.
No Qt/OpenGL or NumPy dependency is required.
"""
from array import array
from functools import lru_cache
import math

_EPSILON = 1.e-12
_NEUTRAL_COLOR = (.56, .77, .84)
_MISSING_TAG = (-1., -1., -1.)


def _face_normals(mesh):
    """Return normalized face directions and area weights (read-only geometry)."""
    result = []
    v = mesh.vertices
    sqrt = math.sqrt
    for a, b, c in mesh.triangles:
        p, q, r = v[a], v[b], v[c]
        ux, uy, uz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        wx, wy, wz = r[0] - p[0], r[1] - p[1], r[2] - p[2]
        nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
        # Preserve the committed baseline's Python sum() arithmetic exactly.
        # Python 3.12+ uses compensated float summation; replacing this
        # expression with nx*nx + ny*ny + nz*nz changes some results by 1 ULP.
        size = sqrt(sum(x * x for x in (nx, ny, nz)))
        result.append(((nx / size, ny / size, nz / size)
                       if size > _EPSILON else (0., 0., 1.), size))
    return result


@lru_cache(maxsize=4096)
def _rgb(hex_color):
    """Cache repeated palette colors without changing per-corner interpolation."""
    return tuple(int(hex_color[j:j + 2], 16) / 255. for j in (1, 3, 5))


def _coherent_vertex_normals(normals, adjacency, cos_safe):
    """Compute one normal only where *all* crease comparisons must succeed.

    A deliberately narrower angular cone guarantees a substantial margin
    from the legacy crease predicate, including IEEE-754 roundoff.  Faces
    outside that cone use the exact legacy per-corner comparison.  This
    avoids expensive all-pairs verification on dense smooth meshes.
    """
    sqrt = math.sqrt
    result = [None] * len(adjacency)
    for idx, incident in enumerate(adjacency):
        if not incident:
            continue
        anchor = None
        sx = sy = sz = 0.
        safe = True
        for face_idx in incident:
            direction, weight = normals[face_idx]
            if weight <= _EPSILON:
                # A zero-area face has a synthetic +Z normal; it may select
                # a different subset than the valid faces at this vertex.
                safe = False
                break
            if anchor is None:
                anchor = direction
            elif (anchor[0] * direction[0] + anchor[1] * direction[1] +
                  anchor[2] * direction[2]) < cos_safe:
                safe = False
                break
            sx += direction[0] * weight
            sy += direction[1] * weight
            sz += direction[2] * weight
        if safe:
            magnitude = sqrt(sx * sx + sy * sy + sz * sz)
            if magnitude > _EPSILON:
                result[idx] = (sx / magnitude, sy / magnitude, sz / magnitude)
    return result


def flatten_faces(mesh, crease_angle=53):
    """Pack exactly 12 float32 attributes per corner, preserving original colors.

    A conservative vertex-level fast path avoids repeating identical weighted
    normal calculations for the many smooth triangles of typical printed
    models.  Sharp, non-manifold, and degenerate cases use the original
    per-face crease rule.  Output order and structure are unchanged.
    """
    vertices = mesh.vertices
    faces = mesh.triangles
    normals = _face_normals(mesh)
    # Sparse allocation: models may contain many unused vertices, so avoid
    # creating one Python list per vertex until actually referenced.
    adjacency = [None] * len(vertices)
    for i, tri in enumerate(faces):
        for idx in set(tri):
            if adjacency[idx] is None:
                adjacency[idx] = [i]
            else:
                adjacency[idx].append(i)

    cos_limit = math.cos(math.radians(crease_angle))
    # Keep a generous angular margin.  At 53°, pairs cached by this
    # 21.5° cap differ by <=43° (ten degrees short of the crease).
    safe_half = max(0.0, (crease_angle / 2.0) - min(5.0, crease_angle / 4.0))
    cos_safe = math.cos(math.radians(safe_half))
    # For crease angles outside [0, 180], use the complete legacy selection.
    if 0 < crease_angle < 180:
        cached = _coherent_vertex_normals(normals, adjacency, cos_safe)
    else:
        cached = [None] * len(vertices)

    palette = getattr(mesh, 'face_colors', ())
    corner_colors = getattr(mesh, 'corner_colors', ())
    use_palette = len(palette) == len(faces)
    use_corners = len(corner_colors) == len(faces)
    result = array('f')
    extend = result.extend
    sqrt = math.sqrt
    for i, tri in enumerate(faces):
        normal, _ = normals[i]
        src = palette[i] if use_palette else None
        color = _rgb(src) if src and len(src) == 7 else _NEUTRAL_COLOR
        tag = color if src else _MISSING_TAG
        for corner_idx, idx in enumerate(tri):
            vertex_color = color
            if use_corners:
                corner = corner_colors[i][corner_idx]
                if corner and len(corner) == 7:
                    vertex_color = _rgb(corner)
            smoothed = cached[idx]
            if smoothed is None:
                # Keep the original summation order in the crease predicate,
                # including Python's float sum behavior near the threshold.
                sx = sy = sz = 0.
                for j in adjacency[idx]:
                    direction, weight = normals[j]
                    if weight > _EPSILON and (
                        sum(normal[k] * direction[k] for k in range(3))) >= cos_limit:
                        sx += direction[0] * weight
                        sy += direction[1] * weight
                        sz += direction[2] * weight
                magnitude = sqrt(sx * sx + sy * sy + sz * sz)
                smoothed = (sx / magnitude, sy / magnitude, sz / magnitude) if magnitude > _EPSILON else normal
            extend((*vertices[idx], *smoothed, *vertex_color, *tag))
    return result
