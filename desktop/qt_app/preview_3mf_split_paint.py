"""Bounded, read-only tessellation of Bambu/Orca 3MF TriangleSelector paint.

A native paint_color string is a serialized tree of split triangles, not an RGB
value. Leaves are 1-based filament slots (zero means inherit part assignment).
The generated geometry is exclusively for the Qt display. The original 3MF,
its triangle paint strings, and all native project/forecast/export data remain
unchanged. No other libraries or external codecs are required.

The split geometry is derived from the public bitstream and triangle-subdivision
rules. This is an independent implementation, not copied slicer source code.
"""
from __future__ import annotations

from math import isfinite
from typing import NamedTuple

MAX_PAINT_CODE_NIBBLES = 100_000
MAX_PAINT_REGIONS_PER_FACE = 120_000
MAX_PAINT_TREE_DEPTH = 64
_HEX = frozenset('0123456789abcdefABCDEF')


class PaintDecodeError(ValueError):
    """Malformed, unsupported or resource-intensive native paint encoding."""


class PaintRegion(NamedTuple):
    points: tuple  # three XYZ triples (the planar preview sub-triangle)
    slot: int  # 0 = inherit part extruder; positive = 1-based filament slot


def _middle(a, b):
    return tuple((x + y) * 0.5 for x, y in zip(a, b))


def _children(triangle, count, special):
    """Partition a CCW triangle into 2, 3 or 4 CCW facets.

    The special-side token cyclically rotates the starting vertex. No new
    vertex lies off the original triangular plane; the children tile it.
    """
    if special > 2:
        raise PaintDecodeError('Invalid split-side rotation')
    a, b, c = (triangle[(special + k) % 3] for k in range(3))
    if count == 1:
        m = _middle(b, c)
        return ((a, b, m), (m, c, a))
    ab = _middle(a, b)
    ac = _middle(a, c)
    if count == 2:
        return ((a, ab, ac), (ab, b, ac), (b, c, ac))
    if count == 3:
        bc = _middle(b, c)
        return ((a, ab, ac), (ab, b, bc), (bc, c, ac), (ab, bc, ac))
    raise PaintDecodeError('Invalid split count')


def decode_paint_regions(triangle, encoded, slot_count, *,
                         max_regions=MAX_PAINT_REGIONS_PER_FACE):
    """Return the exact display sub-triangles for one slicer paint_color.

    The slicer's data stream is consumed right-to-left, one hex nibble at a
    time. For internal nodes, children are visited in reverse facet order.
    A valid leaf never invents a filament: slot 0 inherits the parent color.
    Complexity limits defend against untrusted 3MF archives.
    """
    if (not isinstance(encoded, str) or not encoded or
            len(encoded) > MAX_PAINT_CODE_NIBBLES or
            any(char not in _HEX for char in encoded)):
        raise PaintDecodeError('Invalid or oversized native paint encoding')
    if not isinstance(slot_count, int) or not 1 <= slot_count <= 256:
        raise PaintDecodeError('Invalid number of project filament slots')
    if (len(triangle) != 3 or any(len(point) != 3 or
            not all(isfinite(float(x)) for x in point) for point in triangle)):
        raise PaintDecodeError('Invalid triangle coordinates')
    if max_regions < 1 or max_regions > MAX_PAINT_REGIONS_PER_FACE:
        raise PaintDecodeError('Invalid paint region budget')
    # Stack order matches the slicer's reverse-child depth-first serialization.
    stack = [(tuple(tuple(float(x) for x in p) for p in triangle), 0)]
    regions = []
    consumed = 0
    length = len(encoded)

    def next_nibble():
        nonlocal consumed
        if consumed == length:
            raise PaintDecodeError('Truncated native paint tree')
        digit = int(encoded[length - consumed - 1], 16)
        consumed += 1
        return digit

    while stack:
        tri, depth = stack.pop()
        code = next_nibble()
        split = code & 3
        if split:
            if depth >= MAX_PAINT_TREE_DEPTH:
                raise PaintDecodeError('Native paint tree exceeds nesting budget')
            facets = _children(tri, split, code >> 2)
            # Appending in normal order makes LIFO visit the last child first.
            stack.extend((facet, depth + 1) for facet in facets)
        else:
            state = code >> 2
            if state == 3:
                state = 3
                while True:
                    nibble = next_nibble()
                    state += nibble
                    if nibble != 15:
                        break
                    if state > slot_count:
                        raise PaintDecodeError('Native paint slot exceeds project palette')
            if state > slot_count:
                raise PaintDecodeError('Native paint slot exceeds project palette')
            regions.append(PaintRegion(tri, state))
            if len(regions) > max_regions:
                raise PaintDecodeError('Native painted triangle exceeds preview region budget')
        # Every pending tree node must produce at least one final facet.
        if len(regions) + len(stack) > max_regions:
            raise PaintDecodeError('Native painted triangle exceeds preview region budget')
    if consumed < length:
        # The bitstream is nibble-aligned. Some slicers leave zero padding.
        if any(char != '0' for char in encoded[:length - consumed]):
            raise PaintDecodeError('Unexpected trailing native paint instructions')
    return tuple(regions)
