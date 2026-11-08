"""Read-only native Bambu/Orca part-to-filament assignments for the Qt preview.

The standard 3MF colorgroup/basematerials properties and native per-face paint
are resolved by mesh_loader, not here. This module only supplies an inherited
part default when model_settings.config explicitly assigns an extruder to a
component part under a parent object. No archive writes, color inference,
or on-disk caching.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

MAX_MODEL_SETTINGS_BYTES = 12_000_000
MAX_PART_ASSIGNMENTS = 10_000


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def read_native_part_defaults(archive, native_colors):
    """Return {(parent object id, component part id): RGB hex or None}.

    A missing per-part ``extruder`` is intentionally omitted: the caller
    inherits the parent object's established color. An *explicitly present*
    but invalid extruder yields None, so it does not silently render with
    the wrong parent material. This is a display-only hint, not print data.

    native_colors are already decoded/validated by mesh_loader._native_defaults.
    """
    if not native_colors:
        return {}
    try:
        info = archive.getinfo('Metadata/model_settings.config')
    except KeyError:
        return {}
    if info.file_size > MAX_MODEL_SETTINGS_BYTES:
        raise ValueError('Native 3MF part assignments exceed the preview size limit')
    root = ET.fromstring(archive.read(info))
    assignments = {}
    for obj in root:
        if _local(obj.tag) != 'object':
            continue
        parent_id = obj.get('id')
        if not parent_id:
            continue
        for part in obj:
            if _local(part.tag) != 'part' or not part.get('id'):
                continue
            slot_text = next((element.get('value') for element in part
                              if _local(element.tag) == 'metadata'
                              and element.get('key') == 'extruder'), None)
            if slot_text is None:
                continue
            key = (parent_id, part.get('id'))
            if key in assignments:
                raise ValueError('Duplicate 3MF native part assignment')
            try:
                slot = int(slot_text)
            except (TypeError, ValueError):
                slot = 0
            assignments[key] = (native_colors[slot - 1]
                                if 1 <= slot <= len(native_colors) else None)
            if len(assignments) > MAX_PART_ASSIGNMENTS:
                raise ValueError('Too many native 3MF part assignments')
    return assignments
