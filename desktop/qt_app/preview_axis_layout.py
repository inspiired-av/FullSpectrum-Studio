"""Pure geometry for locating the XYZ marker clear of other viewport overlays.

There is no dependence on Qt, GL, export, or preview model coordinates here.
"""
from __future__ import annotations


def _intersects(a, b, gap):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax < bx + bw + gap and ax + aw + gap > bx
            and ay < by + bh + gap and ay + ah + gap > by)


def axis_marker_position(width, height, marker_width, marker_height,
                         occupied=(), *, margin=9, gap=8):
    """Find a free corner, favoring bottom-left then bottom-right.

    The marker remains world-orientation-only, not part of the model scene.
    Rectangles are in viewport-local logical pixels (x, y, width, height).
    Return None if no complete corner fits, rather than obscure controls.
    """
    w, h, mw, mh = (int(v) for v in
                    (width, height, marker_width, marker_height))
    if min(w, h, mw, mh) <= 0 or w < mw + 2 * margin or h < mh + 2 * margin:
        return None
    candidates = (
        (margin, h - mh - margin),
        (w - mw - margin, h - mh - margin),
        (w - mw - margin, margin),
        (margin, margin),
    )
    for x, y in candidates:
        rect = (x, y, mw, mh)
        if not any(_intersects(rect, obstacle, gap) for obstacle in occupied):
            return x, y
    return None
