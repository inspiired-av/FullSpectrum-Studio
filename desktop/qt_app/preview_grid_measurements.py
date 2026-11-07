"""Pure, display-only measurement formatting and label-placement helpers.

The values supplied here come from the actual WorldGridRenderer's generated
vertices and minor grid step. Never infer or modify a build plate's own grid.
"""
from __future__ import annotations

import math


def format_millimeters(value):
    """Compact human-readable millimeters without float residue or negative zero."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Measurement must be finite')
    if abs(value) < 1.e-12:
        return '0'
    return format(value, '.6g')


def grid_spacing_label(step):
    if not math.isfinite(step) or step <= 0:
        raise ValueError('Perspective grid spacing must be positive')
    cell = format_millimeters(step)
    return f'Grid cell: {cell} × {cell} mm'


def project_grid_point(row_major, x, y, z, width, height):
    """Project a world-space coordinate to viewport pixels without PySide6.

    QMatrix4x4.copyDataTo() returns 16 row-major floats. Manual homogeneous
    multiplication avoids PySide6's QMatrix4x4 * QVector4D binding failure.
    Reject behind-camera, clipped, invalid, or zero-sized projections.
    """
    if row_major is None or len(row_major) != 16 or width <= 0 or height <= 0:
        return None
    try:
        px, py, pz = float(x), float(y), float(z)
        v = (px, py, pz, 1.0)
        clip = tuple(sum(float(row_major[4*i+j]) * v[j] for j in range(4))
                     for i in range(4))
        w = clip[3]
        if not math.isfinite(w) or w <= 1.e-8:
            return None
        nx, ny, nz = (clip[i] / w for i in range(3))
        if not all(math.isfinite(q) and -1.0 <= q <= 1.0 for q in (nx, ny, nz)):
            return None
        return ((nx + 1.0) * 0.5 * width,
                (1.0 - ny) * 0.5 * height)
    except (ValueError, TypeError, OverflowError):
        return None


def projected_model_bounds(row_major, bounds, width, height, *, margin=10):
    """Conservative screen-space AABB of the authoritative model's bounds.

    Qt paints labels *over* OpenGL, so text cannot use the model depth buffer.
    Excluding this model silhouette prevents coordinate values appearing through
    geometry without expensive glReadPixels or per-frame ray/triangle tests.

    Corners may project off-screen; keep their unclipped pixel coordinates so
    partial model overlap is still detected.  If a corner is behind the camera
    or the near/far clip planes, hide model-overlapping labels conservatively.
    None means no valid model bounds to exclude.
    """
    if bounds is None:
        return None
    if (row_major is None or len(row_major) != 16 or len(bounds) != 6
            or width <= 0 or height <= 0):
        return (0, 0, width, height) if width > 0 and height > 0 else None
    try:
        coords = tuple(float(v) for v in bounds)
        x0, y0, z0, x1, y1, z1 = coords
        if (not all(math.isfinite(v) for v in coords)
                or x0 > x1 or y0 > y1 or z0 > z1):
            return (0, 0, width, height)
        m = tuple(float(v) for v in row_major)
        if not all(math.isfinite(v) for v in m):
            return (0, 0, width, height)
        xs, ys = [], []
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    v = (x, y, z, 1.0)
                    clip = [sum(m[4*i+j] * v[j] for j in range(4))
                            for i in range(4)]
                    w = clip[3]
                    if not math.isfinite(w) or w <= 1e-8:
                        return (0, 0, width, height)
                    nz = clip[2] / w
                    if not math.isfinite(nz) or not -1.0 <= nz <= 1.0:
                        return (0, 0, width, height)
                    nx, ny = clip[0]/w, clip[1]/w
                    if not math.isfinite(nx) or not math.isfinite(ny):
                        return (0, 0, width, height)
                    xs.append((nx + 1.0) * width * .5)
                    ys.append((1.0 - ny) * height * .5)
        pad = max(0.0, float(margin))
        return (min(xs)-pad, min(ys)-pad,
                max(xs)-min(xs)+2*pad, max(ys)-min(ys)+2*pad)
    except (ValueError, TypeError, OverflowError):
        return (0, 0, width, height)


def major_ticks(lower, upper, step, *, major=5, limit=24):
    """World-coordinate major ticks. Labels use actual 5x minor-grid lines."""
    if (not all(math.isfinite(v) for v in (lower, upper, step))
            or step <= 0 or upper < lower):
        raise ValueError('Invalid grid limits')
    major = max(1, int(major))
    limit = max(1, min(48, int(limit)))
    spacing = step * major
    # GL vertex coordinates are float32. Recover their integer minor-grid
    # indices before finding major ticks: otherwise rounding can skip the
    # first line (e.g. 0.40000000596 instead of 0.4), so the ruler and
    # highlighted axes disagree about the shared zero.
    def major_index(value, *, ceiling):
        minor_index = round(value / step)
        if abs(value - minor_index * step) <= abs(step) * 1.e-5:
            return (-(-minor_index // major) if ceiling
                    else minor_index // major)
        ratio = value / spacing
        return math.ceil(ratio - 1.e-10) if ceiling else math.floor(ratio + 1.e-10)

    first = major_index(lower, ceiling=True)
    last = major_index(upper, ceiling=False)
    if last < first:
        return ()
    count = last - first + 1
    stride = max(1, math.ceil(count / limit))
    return tuple(k * spacing for k in range(first, last + 1, stride))


def intersects(left, right, gap=0):
    """Collision of two (x, y, width, height) rectangles with padding."""
    x, y, w, h = left
    a, b, u, v = right
    return (x < a + u + gap and x + w + gap > a
            and y < b + v + gap and y + h + gap > b)


def choose_badge_rect(width, height, badge_width, badge_height, occupied=()):
    """Prefer upper-right; never cover another visible viewport overlay.

    Used by the actual Qt widget and unit-tested independently of PySide6.
    Return None instead of crowding very small viewports.
    """
    width, height = int(width), int(height)
    bw, bh = int(badge_width), int(badge_height)
    margin = 12
    if min(width, height, bw, bh) <= 0 or bw + margin * 2 > width or bh + margin * 2 > height:
        return None
    places = [
        (width - margin - bw, margin),
        ((width - bw) // 2, margin),
        (margin, margin),
        (margin, height - margin - bh),
        (width - margin - bw, height - margin - bh),
    ]
    for x, y in places:
        rect = (x, y, bw, bh)
        if not any(intersects(rect, other, gap=7) for other in occupied):
            return rect
    return None


def grid_xy_limits(vertices):
    """Recover exact XY extents from the same bounded GL line vertices.

    All line vertices are packed as XYZ/RGBA, in float32, by world_grid_vertices.
    """
    if len(vertices) < 14 or len(vertices) % 14:
        raise ValueError('Invalid grid vertex buffer')
    x = vertices[0::7]
    y = vertices[1::7]
    return (float(min(x)), float(max(x)), float(min(y)), float(max(y)))

def grid_ruler_ticks(lower, upper, step, *, major=5, limit=24):
    """World tick locations paired with distances from the first major line.

    The grid can be centered far from world (0, 0). Showing those absolute
    positions as bare numbers is confusing: e.g. 200 beside a 10 mm cell.
    Distances remain physical millimeters, but start at the first visible
    bold grid line. This is a preview ruler, not a printer-origin coordinate.
    """
    ticks = major_ticks(lower, upper, step, major=major, limit=limit)
    if not ticks:
        return ()
    return tuple((value, value - ticks[0]) for value in ticks)


def layout_grid_ruler_labels(step, limits, floor_z, width, height, project,
                             measure, blocked=(), *, model_rect=None,
                             max_per_axis=12):
    """Lay out X/Y ruler ticks on whichever grid edge actually has room.

    ``project(x,y,z)`` projects with the *same* 3D view/projection matrix as
    the drawn grid. ``measure(text)`` returns pixel text dimensions. Labels
    never cover the projected model, overlays, each other or viewport edges.
    Both boundaries are considered separately for *each* major line, so a
    camera turn cannot discard an entire axis just because one edge clipped.
    This is pure Python: it can be tested without a Qt/OpenGL context.
    """
    x0, x1, y0, y1 = (float(v) for v in limits)
    if not all(math.isfinite(v) for v in (x0, x1, y0, y1, floor_z, step)):
        return ()
    if x1 < x0 or y1 < y0 or step <= 0 or width <= 0 or height <= 0:
        return ()
    used = list(blocked)
    if model_rect is not None:
        used.append(model_rect)
    center = project((x0+x1)*.5, (y0+y1)*.5, floor_z)
    if center is None:
        center = (width*.5, height*.5)

    tasks = []
    for axis in ('X', 'Y'):
        lo, hi = ((x0, x1) if axis == 'X' else (y0, y1))
        ticks = grid_ruler_ticks(lo, hi, step, limit=24)
        for value, distance in ticks:
            label = axis + ' ' + format_millimeters(distance)
            tw, th = measure(label)
            w, h = max(1.0, float(tw) + 10.0), max(1.0, float(th) + 4.0)
            options = []
            # A particular major line may meet the edge at a clipped or
            # obstructed point. Evaluate both ends before dropping its label.
            for edge in ((y0, y1) if axis == 'X' else (x0, x1)):
                point = (project(value, edge, floor_z) if axis == 'X'
                         else project(edge, value, floor_z))
                if point is None:
                    continue
                sx, sy = point
                dx, dy = sx-center[0], sy-center[1]
                length = math.hypot(dx, dy)
                # Radial outward placement is more stable under orbiting
                # than a hardcoded top/bottom/left/right offset.
                nx, ny = ((dx/length, dy/length) if length > 1e-6
                          else (0.0, 1.0))
                # Try small outward offsets first; if they collide, allow a
                # more distant position, or the other visible grid edge.
                for pad in (11.0, 21.0, 32.0):
                    rect = (sx+nx*pad-w*.5, sy+ny*pad-h*.5, w, h)
                    rx, ry, rw, rh = rect
                    if (rx < 7 or ry < 7 or rx+rw > width-7 or
                            ry+rh > height-7 or
                            any(intersects(rect, other, gap=5) for other in used)):
                        continue
                    options.append((pad, rect))
            if options:
                tasks.append((axis, label, options))
    # Consider scarce placements first, using X/Y interleaving on ties. This
    # maximizes readability instead of allowing the first edge to consume all
    # the viewport's free space. No extra 53-pixel suppression is needed:
    # actual rendered label rectangles already enforce spacing.
    tasks.sort(key=lambda item: (len(item[2]),
                                 0 if item[0] == 'X' else 1,
                                 float(item[1].split(' ')[1])))
    chosen = []
    counts = {'X': 0, 'Y': 0}
    for axis, text, options in tasks:
        if counts[axis] >= max_per_axis:
            continue
        for _distance, rect in options:
            if not any(intersects(rect, other, gap=5) for other in used):
                chosen.append((axis, text, rect))
                used.append(rect)
                counts[axis] += 1
                break
    return tuple(chosen)

