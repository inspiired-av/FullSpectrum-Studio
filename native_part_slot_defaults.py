"""Read-only source 3MF component-part physical extruder assignments.

This module is intentionally Qt-free and export-free. Its keys match the
component graph: (parent object id, component object id). It reads Bambu/Orca
Metadata/model_settings.config and returns explicit 1-based source slot IDs.
Missing assignments inherit their parent's slot in preview_world_geometry.

Note: a source part's slot number refers to the source project, *not* the
physical or mixed slots allocated by FullSpectrum's optimizer.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

MODEL_SETTINGS = 'Metadata/model_settings.config'
MAX_SETTINGS_BYTES = 8_000_000
MAX_PART_ASSIGNMENTS = 10_000


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def read_part_slot_defaults(archive, slot_count: int) -> dict[tuple[str, str], int]:
    """Return explicit inherited component defaults; fail closed on bad slots.

    This reader must not guess from the manufacturer's RGB color values; two
    source slots are allowed to share an RGB swatch. It must not silently
    change source material assignments when metadata is malformed.
    """
    if type(slot_count) is not int or not 1 <= slot_count <= 2047:
        raise ValueError('Invalid native 3MF source slot count')
    try:
        info = archive.getinfo(MODEL_SETTINGS)
    except KeyError:
        return {}
    if info.file_size > MAX_SETTINGS_BYTES:
        raise ValueError('Native 3MF part assignments exceed the safety budget')
    try:
        root = ET.fromstring(archive.read(info))
    except ET.ParseError as exc:
        raise ValueError('Native 3MF part assignments are malformed XML') from exc
    result: dict[tuple[str, str], int] = {}
    for obj in root:
        if _local(obj.tag) != 'object':
            continue
        parent_id = obj.get('id')
        if not parent_id:
            continue
        for part in obj:
            if _local(part.tag) != 'part':
                continue
            child_id = part.get('id')
            if not child_id:
                continue
            extruder_fields = [e.get('value') for e in part
                               if _local(e.tag) == 'metadata' and e.get('key') == 'extruder']
            if not extruder_fields:
                continue  # No explicit part assignment: inherit parent.
            if len(extruder_fields) != 1:
                raise ValueError('Ambiguous native 3MF part extruder assignment')
            try:
                slot = int(extruder_fields[0])
            except (ValueError, TypeError) as exc:
                raise ValueError('Invalid native 3MF part extruder assignment') from exc
            if not 1 <= slot <= slot_count:
                raise ValueError('Native 3MF part extruder is outside the source palette')
            key = (parent_id, child_id)
            if key in result:
                raise ValueError('Duplicate native 3MF part extruder assignment')
            result[key] = slot
            if len(result) > MAX_PART_ASSIGNMENTS:
                raise ValueError('Too many native 3MF part extruder assignments')
    return result
