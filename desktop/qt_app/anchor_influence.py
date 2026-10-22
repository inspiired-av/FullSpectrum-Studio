"""Stage 4D-A: exact recipe ratios and source-face GPU provenance (Qt-free).

No approximation from RGB: an analysis-only per-face slot map aligns the
engine's original source slots to the rendered OBJ face order. The optimizer
remains authoritative for mixtures, ratios and protected physical colors.
"""
from __future__ import annotations

from array import array
from pathlib import Path
import math
import re
import struct

MAX_SOURCE_SLOTS = 2047  # Conservative OpenGL 3.3 texture-height bound.
MAX_PREVIEW_FACES = 750_000
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
CATEGORIES = ('#28B8D5','#E86C8C','#EDC949','#4E79A7','#59A14F','#B07AA1')


def _ids(raw):
    if not isinstance(raw, str):
        raise ValueError('Component list is missing')
    return tuple(int(v.strip()) for v in raw.split(',') if v.strip())


def recipe_weights(recipes, source_count, anchors):
    """Compute true normalized per-source-slot physical component shares.

    Tie-breaking uses the smallest physical slot, not recipe component order.
    Missing/inconsistent recipes fail closed rather than inventing influence.
    """
    if (type(source_count) is not int or not 1 <= source_count <= MAX_SOURCE_SLOTS
            or not isinstance(anchors, (list, tuple)) or not 1 <= len(anchors) <= 8):
        raise ValueError('Unsupported source or anchor count')
    n = len(anchors)
    for index, anchor in enumerate(anchors, 1):
        if (not isinstance(anchor, dict) or anchor.get('slot') != index or
                not isinstance(anchor.get('color'), str) or
                not HEX.fullmatch(anchor['color'])):
            raise ValueError('Physical anchors are not aligned with output slots')
    if not isinstance(recipes, (list, tuple)):
        raise ValueError('Missing optimizer recipes')
    by_source = {}
    for row in recipes:
        if not isinstance(row, dict):
            raise ValueError('Invalid recipe')
        old = row.get('oldSlot')
        if type(old) is not int or not 1 <= old <= source_count or old in by_source:
            raise ValueError('Duplicate or invalid original source slot')
        kind = row.get('kind')
        if kind in ('ANCHOR', 'SOLID'):
            slot = row.get('newSlot')
            if type(slot) is not int or not 1 <= slot <= n:
                raise ValueError('Physical recipe references an invalid anchor')
            weights = [0.0] * n
            weights[slot-1] = 1.0
        elif kind == 'MIX':
            components = _ids(row.get('components'))
            try:
                values = tuple(float(v.strip()) for v in row['ratios'].split(',') if v.strip())
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('Invalid recipe ratios') from exc
            if (not 2 <= len(components) <= 3 or len(components) != len(values)
                    or len(set(components)) != len(components)
                    or any(type(x) is not int or x < 1 or x > n for x in components)
                    or any(not math.isfinite(v) or v <= 0 for v in values)
                    or abs(sum(values) - 1.0) > 0.002):
                raise ValueError('Invalid physical mixture components or ratios')
            weights = [0.0] * n
            total = sum(values)
            for slot, value in zip(components, values):
                weights[slot-1] = value / total
        else:
            raise ValueError('Unknown recipe kind')
        by_source[old] = tuple(weights)
    if set(by_source) != set(range(1, source_count+1)):
        raise ValueError('Optimizer omitted a source-slot recipe')
    result = tuple(by_source[k] for k in range(1, source_count+1))
    return result


def gpu_weight_texture(weights, anchor_count):
    """Encode GL_RGBA32F texture; X=physical slot, Y=source slot (0 sentinel).

    .r = contribution fraction; .g = dominant anchor slot.
    """
    packed = array('f', [0.0] * (8 * 4))
    for row in weights:
        if len(row) != anchor_count or anchor_count > 8:
            raise ValueError('Invalid GPU anchor weight shape')
        dominant = min(range(anchor_count), key=lambda i: (-row[i], i)) + 1
        for index in range(8):
            packed.extend((row[index] if index < anchor_count else 0.0,
                           float(dominant), 0.0, 0.0))
    return packed


def read_face_slots(asset, root, expected_count, source_count):
    path = Path(asset).resolve()
    path.relative_to(Path(root).resolve())
    if path.suffix.lower() != '.bin' or not path.is_file():
        raise ValueError('Missing engine source-face slot map')
    if type(expected_count) is not int or not 1 <= expected_count <= MAX_PREVIEW_FACES:
        raise ValueError('Unsupported influence mesh face count')
    if path.stat().st_size != expected_count * 4:
        raise ValueError('Source-face map does not match the analysis mesh')
    raw = path.read_bytes()
    slots = tuple(v[0] for v in struct.iter_unpack('<I', raw))
    if any(not 1 <= slot <= source_count for slot in slots):
        raise ValueError('Source-face map refers to an invalid source slot')
    return slots


def apply_face_slot_tags(mesh, slots):
    """Replace ONLY the influence overlay's GPU face tag, on worker thread.

    Each render vertex comprises twelve floats; offsets 9,21,33 are the
    first (red) channel of the flat source-tag attribute per triangle.
    Original/predicted/loss render buffers are never touched.
    """
    packed = mesh.render_buffer
    if (not isinstance(packed, array) or packed.typecode != 'f'
            or len(packed) != len(slots) * 36):
        raise ValueError('GPU buffer geometry does not align with source slots')
    for i, slot in enumerate(slots):
        for off in (9, 21, 33):
            packed[i * 36 + off] = float(slot)
    return mesh


def prepare_influence(assets, analysis_root, mesh, recipes, anchors, source_count):
    """Prepare permanent in-memory GPU metadata before temp analysis is removed."""
    if not isinstance(assets, dict) or not assets.get('sourceSlotMap'):
        raise ValueError('This engine forecast has no source-slot provenance')
    weights = recipe_weights(recipes, source_count, anchors)
    face_slots = read_face_slots(assets['sourceSlotMap'], analysis_root,
                                 len(mesh.triangles), source_count)
    packed = gpu_weight_texture(weights, len(anchors))
    apply_face_slot_tags(mesh, face_slots)
    return {
        'weights': packed,
        'sourceCount': source_count,
        'anchors': tuple((a['color'].upper(), CATEGORIES[i % len(CATEGORIES)])
                         for i,a in enumerate(anchors)),
        'faceCount': len(face_slots),
        'displayModes': ('physical', 'categorical', 'contribution'),
    }
