"""Transform-aware native 3MF analysis viewport geometry (engine-only; no Qt).

The original model viewer honors 3MF build/component transforms and native
per-object extruders. The older optimized OBJ exporter did neither, stacking
objects at the origin and mapping all unpainted parts to slot 1.

This module generates only transient, read-only analysis geometry. It doesn't
modify source projects, saved filament settings, or export remapping.
"""
from __future__ import annotations

from collections import Counter
import math
import posixpath
import xml.etree.ElementTree as ET
from xml.sax import make_parser, handler

IDENTITY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
UNIT_SCALES = {'millimeter': 1., 'centimeter': 10., 'meter': 1000.,
               'inch': 25.4, 'foot': 304.8, 'micron': .001}
MAX_INSTANCES = 4096
MAX_DEPTH = 18


def _tag(name):
    return name.rsplit(':', 1)[-1].rsplit('}', 1)[-1]


def _matrix(raw):
    if not raw:
        return IDENTITY
    values = tuple(float(v) for v in raw.split())
    if len(values) != 12 or not all(math.isfinite(v) for v in values):
        raise ValueError('Invalid preview 3MF transform')
    return values


def _apply(m, p):
    x, y, z = p
    return (m[0]*x + m[3]*y + m[6]*z + m[9],
            m[1]*x + m[4]*y + m[7]*z + m[10],
            m[2]*x + m[5]*y + m[8]*z + m[11])


def _compose(a, b):
    result = []
    for i in range(0, 9, 3):
        x, y, z = b[i:i+3]
        result.extend((a[0]*x + a[3]*y + a[6]*z,
                       a[1]*x + a[4]*y + a[7]*z,
                       a[2]*x + a[5]*y + a[8]*z))
    return tuple(result) + _apply(a, b[9:12])


def _path(member, raw):
    if not raw:
        return member
    candidate = raw.replace('\\', '/')
    if candidate.startswith('/'):
        candidate = candidate.lstrip('/')
    else:
        candidate = posixpath.join(posixpath.dirname(member), candidate)
    normalized = posixpath.normpath(candidate)
    if not normalized.startswith('3D/') or not normalized.lower().endswith('.model'):
        raise ValueError('Invalid external 3MF model component path')
    return normalized


def _component_path(attrs):
    for key in attrs.keys():
        if _tag(key) == 'path':
            return attrs.get(key)
    return None


class _Graph(handler.ContentHandler):
    def __init__(self):
        super().__init__()
        self.objects = {}
        self.items = []
        self.unit = 'millimeter'
        self.current = None

    def startElement(self, name, attrs):
        tag = _tag(name)
        if tag == 'model':
            self.unit = attrs.get('unit', 'millimeter').lower()
        elif tag == 'object':
            key = attrs.get('id')
            if key:
                self.current = key
                self.objects[key] = {'mesh': False, 'components': []}
        elif tag == 'mesh' and self.current:
            self.objects[self.current]['mesh'] = True
        elif tag == 'component' and self.current:
            self.objects[self.current]['components'].append(
                (attrs.get('objectid'), _component_path(attrs), attrs.get('transform')))
        elif tag == 'item':
            self.items.append((attrs.get('objectid'), attrs.get('transform')))

    def endElement(self, name):
        if _tag(name) == 'object':
            self.current = None


def _parse_graph(archive, member):
    parser = make_parser()
    parser.setFeature(handler.feature_namespaces, False)
    parser.setFeature(handler.feature_external_ges, False)
    graph = _Graph()
    parser.setContentHandler(graph)
    with archive.open(member) as source:
        parser.parse(source)
    return graph


def _object_extruders(archive, slot_count):
    name = 'Metadata/model_settings.config'
    if name not in archive.namelist() or archive.getinfo(name).file_size > 8_000_000:
        return {}
    root = ET.fromstring(archive.read(name))
    selected = {}
    for element in root:
        if _tag(element.tag) != 'object':
            continue
        key = element.get('id')
        for child in element:
            if _tag(child.tag) == 'metadata' and child.get('key') == 'extruder':
                try:
                    slot = int(child.get('value'))
                except (TypeError, ValueError):
                    break
                if 1 <= slot <= slot_count:
                    selected[key] = slot
                break
    return selected


def model_instances(archive, slot_count):
    """Return world-space instances as (member, mesh ID, transform, base slot)."""
    root_name = '3D/3dmodel.model'
    if root_name not in archive.namelist():
        return None  # Minimal legacy synthetic fixture without a build graph.
    root = _parse_graph(archive, root_name)
    if not root.items:
        raise ValueError('3MF analysis preview has no build items')
    scale = UNIT_SCALES.get(root.unit, 1.)
    extruders = _object_extruders(archive, slot_count)
    cache = {root_name: root}
    instances = []

    def visit(member, object_id, transform, slot, active, depth):
        if depth > MAX_DEPTH or (member, object_id) in active:
            raise ValueError('Cyclic or overly deep 3MF preview components')
        graph = cache.get(member)
        if graph is None:
            if member not in archive.namelist():
                raise ValueError('Missing 3MF preview component: ' + member)
            graph = cache[member] = _parse_graph(archive, member)
        obj = graph.objects.get(object_id)
        if obj is None:
            raise ValueError('Missing 3MF preview object: ' + str(object_id))
        if obj['mesh']:
            instances.append((member, object_id, transform, slot))
            if len(instances) > MAX_INSTANCES:
                raise ValueError('Too many 3MF preview instances')
        for child_id, raw_path, raw_transform in obj['components']:
            visit(_path(member, raw_path), child_id,
                  _compose(transform, _matrix(raw_transform)), slot,
                  active | {(member, object_id)}, depth + 1)

    for oid, transform in root.items:
        visit(root_name, oid, _matrix(transform), extruders.get(oid, 1), set(), 0)
    if not instances:
        raise ValueError('3MF analysis preview has no component meshes')
    return instances, scale


class _Mesh(handler.ContentHandler):
    def __init__(self, wanted, vertices=None, face=None):
        super().__init__()
        self.wanted = wanted
        self.current = None
        self.vertices = vertices
        self.face = face

    def startElement(self, name, attrs):
        tag = _tag(name)
        if tag == 'object':
            self.current = attrs.get('id')
        elif self.current == self.wanted and tag == 'vertex' and self.vertices is not None:
            xyz = tuple(float(attrs.get(k)) for k in ('x', 'y', 'z'))
            if not all(math.isfinite(v) for v in xyz):
                raise ValueError('Non-finite 3MF preview vertex')
            self.vertices.append(xyz)
        elif self.current == self.wanted and tag == 'triangle' and self.face is not None:
            self.face((int(attrs.get('v1')), int(attrs.get('v2')), int(attrs.get('v3'))),
                      attrs.get('paint_color'))

    def endElement(self, name):
        if _tag(name) == 'object':
            self.current = None


def _parse_mesh(archive, member, object_id, vertices=None, face=None):
    parser = make_parser()
    parser.setFeature(handler.feature_namespaces, False)
    parser.setFeature(handler.feature_external_ges, False)
    parser.setContentHandler(_Mesh(object_id, vertices, face))
    with archive.open(member) as stream:
        parser.parse(stream)


def preview_geometry(archive, slot_count, grid_resolution=None, slot_lookup=None):
    """Generate placed faces; grid mode welds ONLY within each mesh instance.

    Preserves source face slots for anchor-influence provenance. The caller
    supplies the native paint codec's existing preview_face_slot callable.
    """
    if slot_lookup is None:
        raise ValueError('A native paint-slot decoder is required')
    graph = model_instances(archive, slot_count)
    if graph is None:
        return None
    instances, unit_scale = graph
    all_vertices = []
    counts = []
    for member, object_id, transform, default_slot in instances:
        points = []
        _parse_mesh(archive, member, object_id, vertices=points)
        counts.append(len(points))
        # Apply 3MF placement BEFORE reduction and bounding-box estimation.
        all_vertices.extend(tuple(v*unit_scale for v in _apply(transform, p)) for p in points)
    if not all_vertices:
        return [], {}
    if grid_resolution is None:
        display_vertices = all_vertices
        display_faces = {}
        offset = 0
        for member, object_id, transform, default_slot in instances:
            size = counts.pop(0)
            def insert(indices, code):
                if any(i < 0 or i >= size for i in indices):
                    return
                if len(set(indices)) < 3:
                    return
                display_faces[len(display_faces)] = (
                    tuple(offset + i + 1 for i in indices),
                    slot_lookup(code, slot_count) if code else default_slot)
            _parse_mesh(archive, member, object_id, face=insert)
            offset += size
        return display_vertices, display_faces
    low = [min(v[j] for v in all_vertices) for j in range(3)]
    high = [max(v[j] for v in all_vertices) for j in range(3)]
    max_extent = max(high[j] - low[j] for j in range(3)) or 1.
    cell = max_extent / max(8, int(grid_resolution))
    clustered = {}
    display_vertices = []
    display_faces = {}
    offset = 0
    for instance_id, (member, object_id, transform, default_slot) in enumerate(instances):
        size = counts[instance_id]
        def display_index(index):
            p = all_vertices[offset+index]
            key = (instance_id,) + tuple(int(math.floor((p[j]-low[j])/cell)) for j in range(3))
            vertex_id = clustered.get(key)
            if vertex_id is None:
                vertex_id = len(display_vertices) + 1
                clustered[key] = vertex_id
                display_vertices.append(p)
            return vertex_id
        def insert(indices, code):
            if any(i < 0 or i >= size for i in indices):
                return
            mapped = tuple(display_index(i) for i in indices)
            if len(set(mapped)) < 3:
                return
            # Never weld or deduplicate faces belonging to different objects.
            key = (instance_id,) + tuple(sorted(mapped))
            if key not in display_faces:
                display_faces[key] = (mapped, slot_lookup(code, slot_count) if code else default_slot)
        _parse_mesh(archive, member, object_id, face=insert)
        offset += size
    return display_vertices, display_faces
