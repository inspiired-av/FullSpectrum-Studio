"""Safe read-only Bambu/Orca native-object and single-state painted-face color scan.

An object's default extruder colors unpainted faces. A triangle carrying a
Bambu TriangleSelector *single leaf* paint state uses that painted slot instead.
Complex split-tree paint states cannot be accurately represented as one color
per face and are explicitly rejected; no guessing or mesh modification occurs.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET

HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
PAINT_CODE = re.compile(r'^[0-9A-Fa-f]+$')
MAX_CFG_BYTES = 12_000_000
MAX_XML_BYTES = 80_000_000
MAX_FACES = 5_000_000
MAX_PARTS = 512


class NativeColorCounts(dict):
    def __init__(self, counts, has_painted_faces=False):
        super().__init__(counts)
        self.has_painted_faces = has_painted_faces


def _read_member(archive, member, limit):
    try:
        info = archive.getinfo(member)
    except KeyError as exc:
        raise ValueError('Missing native-project member: ' + member) from exc
    if info.file_size > limit:
        raise ValueError('3MF member too large for protected-color inspection: ' + member)
    return archive.read(info)


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _metadata(object_node, name):
    for child in object_node:
        if _local(child.tag) == 'metadata' and child.get('key') == name:
            return child.get('value')
    return None


def _single_painted_slot(code, slots):
    """Decode exactly one Bambu TriangleSelector leaf, never a split tree.

    The nibble stream is serialized in reverse order. A normal state is
    state << 2 for states 0..2; higher states start with C, then extensions.
    Re-encoding precisely guards against ambiguous or truncated paint data.
    """
    if not isinstance(code, str) or len(code) > 128 or not PAINT_CODE.fullmatch(code):
        raise ValueError('Invalid native face paint state')
    nibbles = [int(x, 16) for x in reversed(code.upper())]
    head = nibbles[0]
    if head & 3:
        raise ValueError('Complex split-region face paint cannot be assigned a single color')
    if head == 12:
        if len(nibbles) < 2:
            raise ValueError('Truncated native face paint state')
        slot = 3
        pos = 1
        while True:
            if pos >= len(nibbles):
                raise ValueError('Truncated native face paint state')
            ext = nibbles[pos]
            pos += 1
            slot += ext
            if ext != 15:
                break
        if pos != len(nibbles):
            raise ValueError('Complex native face paint state has extra data')
        n = slot - 3
        encoded = [12]
        while n >= 15:
            encoded.append(15)
            n -= 15
        encoded.append(n)
    elif len(nibbles) == 1 and (head & 12) != 12:
        slot = head >> 2
        encoded = [head]
    else:
        raise ValueError('Complex native face paint state is unsupported')
    if ''.join(f'{v:X}' for v in reversed(encoded)) != code.upper():
        raise ValueError('Noncanonical native face paint state')
    if not 1 <= slot <= slots:
        raise ValueError(f'Native face paint references unavailable filament slot {slot}')
    return slot


def _main_object_parts(root):
    """Map top-level object id -> exact submodel paths (not filename guesses)."""
    mappings = {}
    resources = next((n for n in root if _local(n.tag) == 'resources'), None)
    if resources is None:
        return mappings
    for obj in resources:
        if _local(obj.tag) != 'object':
            continue
        oid = obj.get('id')
        if not oid or oid in mappings:
            raise ValueError('Duplicate or missing native object IDs')
        paths = []
        for cmp in obj.iter():
            if _local(cmp.tag) != 'component':
                continue
            raw = next((v for k, v in cmp.attrib.items() if _local(k) == 'path'), None)
            if raw is None:
                raise ValueError('Object has a component without an external mesh path')
            path = raw.lstrip('/')
            if (not path.startswith('3D/Objects/') or not path.endswith('.model')
                    or '..' in path.split('/') or '\\' in path):
                raise ValueError('Unsupported native object mesh path')
            paths.append(path)
        mappings[oid] = paths
    return mappings


def scan_native_object_colors(filename):
    """Count native object and unambiguously painted triangle colors.

    Requires complete object/mesh coverage and physical-only filament slots.
    Does not support mixed recipes, mesh paint split-trees, or implicit part
    colors with missing object mapping. No source project is ever modified.
    """
    with ZipFile(Path(filename)) as archive:
        names = archive.namelist()
        if 'Metadata/model_settings.config' not in names or 'Metadata/project_settings.config' not in names:
            raise ValueError('No native object-color assignments found')
        project = json.loads(_read_member(archive, 'Metadata/project_settings.config', MAX_CFG_BYTES))
        colors = project.get('filament_colour', [])
        mixed = project.get('filament_is_mixed', [])
        if not isinstance(colors, list) or not colors or not all(
                isinstance(c, str) and HEX.fullmatch(c) for c in colors):
            raise ValueError('Native project has no valid filament colors')
        if mixed and (not isinstance(mixed, list) or len(mixed) != len(colors) or '1' in mixed):
            raise ValueError('Mixed-filament project slots are not exact solid source colors')
        main_model = ET.fromstring(_read_member(archive, '3D/3dmodel.model', MAX_XML_BYTES))
        metadata = {n.get('name'): n.text or '' for n in main_model if _local(n.tag) == 'metadata'}
        if not (metadata.get('Application', '').startswith('BambuStudio-') or
                metadata.get('Application', '').startswith('OrcaSlicer-') or
                'OrcaSlicer' in metadata):
            raise ValueError('Not a recognized Bambu Studio / OrcaSlicer native project')
        root = ET.fromstring(_read_member(archive, 'Metadata/model_settings.config', MAX_XML_BYTES))
        submodel_paths = [n for n in names if n.startswith('3D/Objects/') and n.endswith('.model')]
        if not submodel_paths or len(submodel_paths) > MAX_PARTS:
            raise ValueError('No supported native mesh parts found')
        object_paths = _main_object_parts(main_model)
        mapping = Counter()
        assigned_faces = 0
        seen_paths = set()
        has_painted_faces = False
        summaries = []
        for obj in root:
            if _local(obj.tag) != 'object':
                continue
            extruder = _metadata(obj, 'extruder')
            face_count = next((c.get('face_count') for c in obj if
                               _local(c.tag) == 'metadata' and c.get('face_count') is not None), None)
            if extruder is None or face_count is None:
                raise ValueError('Some objects have no unambiguous filament assignment')
            try:
                index, expected = int(extruder), int(face_count)
            except (TypeError, ValueError) as exc:
                raise ValueError('Native object has an invalid extruder or face count') from exc
            if not 1 <= index <= len(colors) or expected < 0:
                raise ValueError('Object filament references an unavailable physical slot')
            summaries.append((obj.get('id'), index, expected))
        if not summaries:
            raise ValueError('No assigned native objects')
        # Older minimal native archives can omit main-model external component
        # links; fall back to their summaries ONLY if all meshes are unpainted.
        if not any(object_paths.get(oid) for oid,_,_ in summaries):
            for name in submodel_paths:
                mesh = ET.fromstring(_read_member(archive, name, MAX_XML_BYTES))
                tris = [e for e in mesh.iter() if _local(e.tag) == 'triangle']
                if any('paint_color' in t.attrib for t in tris):
                    raise ValueError('Face-painted native objects require explicit model-to-mesh relationships')
                assigned_faces += len(tris)
            expected = sum(count for _,_,count in summaries)
            if expected != assigned_faces:
                raise ValueError('Native object assignments do not cover every mesh face')
            for _, slot, count in summaries:
                mapping[colors[slot-1].upper()] += count
        else:
            for oid, default_slot, expected in summaries:
                paths = object_paths.get(oid, [])
                if not paths:
                    raise ValueError('Missing mesh-component mapping for an assigned object')
                count = 0
                for name in paths:
                    if name in seen_paths or name not in submodel_paths:
                        raise ValueError('Missing or duplicated native mesh reference')
                    seen_paths.add(name)
                    part = ET.fromstring(_read_member(archive, name, MAX_XML_BYTES))
                    for face in part.iter():
                        if _local(face.tag) != 'triangle':
                            continue
                        slot = default_slot
                        code = face.get('paint_color')
                        if code is not None:
                            slot = _single_painted_slot(code, len(colors))
                            has_painted_faces = True
                        mapping[colors[slot-1].upper()] += 1
                        count += 1
                        assigned_faces += 1
                        if assigned_faces > MAX_FACES:
                            raise ValueError('Native project exceeds source face scan limit')
                if count != expected:
                    raise ValueError(f'Native object {oid} face count differs from linked mesh geometry')
            if seen_paths != set(submodel_paths):
                raise ValueError('Native object mapping does not cover every mesh part')
        if assigned_faces <= 0 or assigned_faces > MAX_FACES:
            raise ValueError('No valid native source faces found')
        return NativeColorCounts(dict(sorted(mapping.items())), has_painted_faces)
