"""Bounded, read-only provenance map for Stage 4D-A plan-only analysis OBJ meshes.

A uint32-per-triangle sidecar preserves the ORIGINAL source slot, not the
predicted output slot. The sidecar is temporary and never written to a 3MF.
"""
from __future__ import annotations

from pathlib import Path
import re
import struct

MAX_MAP_FACES = 750_000
SLOT_MATERIAL = re.compile(r'^usemtl slot_(\d+)$')


def write_face_slot_map(destination, source_mesh=None, direct_source=None):
    """Write face-ordered little-endian source slots; return path or None.

    Exactly one of source_mesh (native preview OBJ, `usemtl slot_N`) or
    direct_source (original material-colored 3MF face colors) is required.
    """
    if (source_mesh is None) == (direct_source is None):
        raise ValueError('Select exactly one original source-slot representation')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    count = 0
    try:
        with temporary.open('wb') as target:
            if direct_source is not None:
                colors = direct_source['face_colors']
                slots = direct_source['source_slots']
                if len(colors) > MAX_MAP_FACES:
                    raise ValueError('Preview has too many triangles for an interactive influence map')
                for color in colors:
                    slot = slots[color]
                    if type(slot) is not int or not 1 <= slot <= 2_047:
                        raise ValueError('Invalid source slot in direct-source influence map')
                    target.write(struct.pack('<I', slot))
                    count += 1
            else:
                active = None
                with Path(source_mesh).open('r', encoding='utf-8', errors='replace') as source:
                    for raw in source:
                        line = raw.strip()
                        match = SLOT_MATERIAL.fullmatch(line)
                        if match:
                            active = int(match.group(1))
                        elif line.startswith('f '):
                            vertices = line.split()[1:]
                            if len(vertices) != 3 or active is None or not 1 <= active <= 2_047:
                                raise ValueError('Preview must have triangles with original slot materials')
                            count += 1
                            if count > MAX_MAP_FACES:
                                raise ValueError('Preview has too many triangles for an interactive influence map')
                            target.write(struct.pack('<I', active))
        if count == 0:
            raise ValueError('No source faces available for influence map')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
