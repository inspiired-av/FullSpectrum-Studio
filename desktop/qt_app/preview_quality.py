"""Conservative, display-only triangle LOD for the Qt model preview.

This is not a print/export mesh simplifier. Closed manifold neighborhoods may
be collapsed within solid-color regions, or along safe two-material boundaries.
Multicolor junctions and interpolated corner gradients are protected. Original
color metadata and print/export geometry remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
import math
import os
import tempfile
from time import perf_counter

QUALITY_MODES = ('auto', 'full', 'balanced', 'performance')
SETTINGS_FILENAME = 'preview-quality.json'


@dataclass(frozen=True)
class QualityResult:
    mesh: object
    requested: str
    effective: str
    original_triangles: int
    displayed_triangles: int
    duration_ms: float
    reason: str


def normalize_quality(mode):
    return mode if mode in QUALITY_MODES else 'auto'


def choose_quality(mode, triangles):
    mode = normalize_quality(mode)
    if mode != 'auto':
        return mode
    # Never trade away source detail on ordinary models by default.
    return 'full' if triangles <= 500_000 else 'balanced'


def read_quality(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return normalize_quality(data['preview_quality'])
    except (OSError, ValueError, TypeError, KeyError):
        return 'auto'


def write_quality(path, mode):
    mode = normalize_quality(mode)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not leave a half-written preference after a crash.
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.preview-quality-', suffix='.tmp',
                                     delete=False) as f:
        temp = Path(f.name)
        try:
            json.dump({'preview_quality': mode}, f, indent=2)
            f.write('\n')
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _color_signature(mesh, n):
    """A face may be collapsed only if all three corner colors agree.

    We never assume that a face's average RGB represents its three corners.
    Distinct source-slot tags are protected as separate material regions.
    """
    colors = mesh.face_colors
    corners = mesh.corner_colors
    has_faces = len(colors) == n
    has_corners = len(corners) == n
    keys = []
    for i in range(n):
        base = colors[i] if has_faces else None
        if has_corners:
            triple = corners[i]
            if len(triple) != 3 or triple[0] != triple[1] or triple[1] != triple[2]:
                keys.append(('gradient', i))
                continue
            if base is not None and triple[0] != base:
                keys.append(('gradient', i))
                continue
        keys.append(('material', base, triple[0] if has_corners else base))
    return keys


@lru_cache(maxsize=4096)
def _material_rgb(signature):
    """Decode a valid flat material signature; unsupported paint stays protected."""
    if len(signature) != 3 or signature[0] != 'material':
        return None
    color = signature[1]
    if (color != signature[2] or not isinstance(color, str) or
            len(color) != 7 or not color.startswith('#')):
        return None
    try:
        return tuple(bytes.fromhex(color[1:]))
    except ValueError:
        return None


def _links_for(vertex, vertex_faces, triangles):
    """Vertex neighbor/ring graph; return None for boundary/nonmanifold fans."""
    incidence = vertex_faces[vertex]
    if len(incidence) < 3:
        return None
    degrees = {}
    ring = {}
    for fi in incidence:
        tri = triangles[fi]
        if tri is None:
            return None
        others = [int(v) for v in tri if v != vertex]
        if len(others) != 2 or others[0] == others[1]:
            return None
        a, b = others
        degrees[a] = degrees.get(a, 0) + 1
        degrees[b] = degrees.get(b, 0) + 1
        ring.setdefault(a, set()).add(b)
        ring.setdefault(b, set()).add(a)
    if len(degrees) != len(incidence) or any(value != 2 for value in degrees.values()):
        return None
    start = next(iter(degrees))
    seen = {start}
    pending = [start]
    while pending:
        for neighbor in ring[pending.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return set(degrees) if len(seen) == len(degrees) else None


def _eligible_collapse(u, v, points, faces, vertex_faces, materials,
                       max_length2, angle_cos, max_displacement, color_tolerance):
    import numpy as np
    if not vertex_faces[u] or not vertex_faces[v]:
        return None
    delta = points[u] - points[v]
    if float(np.dot(delta, delta)) > max_length2:
        return None
    # Check paint eligibility BEFORE expensive topological fan walks. On dense
    # color-painted models, most candidate edges are unsafe and can be rejected
    # using only local face signatures.
    shared = vertex_faces[u] & vertex_faces[v]
    if len(shared) != 2:
        return None
    adjacent_u = vertex_faces[u]
    adjacent_v = vertex_faces[v]
    impacted = adjacent_u | adjacent_v
    palette_u = {materials[fi] for fi in adjacent_u}
    palette_v = {materials[fi] for fi in adjacent_v}
    if any(signature[0] != 'material' for signature in palette_u | palette_v):
        return None  # Per-corner gradients need color interpolation/texture LOD.
    if len(palette_u | palette_v) == 1:
        pass  # Interior edge of a single-color island.
    elif (len(palette_u) == len(palette_v) == 2 and
          palette_u == palette_v and
          {materials[fi] for fi in shared} == palette_u):
        # Seam edge, bordered by the SAME two painted regions at both ends.
        # Keep color-junction vertices (>2 regions) and short one-face regions
        # intact. Each side must survive deletion of its incident edge face.
        if any(sum(materials[fi] == mat for fi in adjacent_u) < 3 or
               sum(materials[fi] == mat for fi in adjacent_v) < 3
               for mat in palette_u):
            return None
        # High-contrast boundaries are visually important even if their topology
        # could remain manifold: do not move them to a collapsed midpoint.
        rgbs = [_material_rgb(m) for m in palette_u]
        if any(rgb is None for rgb in rgbs):
            return None
        if any(max(rgb[k] for rgb in rgbs) - min(rgb[k] for rgb in rgbs)
               > color_tolerance for k in range(3)):
            return None
        # Smaller movement budget at paint boundaries than inside a region.
        if float(np.dot(delta, delta)) > max_length2 * .36:
            return None
    elif (color_tolerance and len(palette_u | palette_v) <= 8 and
          all(_material_rgb(m) is not None for m in palette_u | palette_v)):
        # Small, explicitly display-only paint approximation. Keep all source
        # material IDs and exact metadata; only low-contrast neighboring faces
        # may be removed. Strong color seams remain untouched.
        # Keep distinct source-color identities represented by a single face:
        # each locally present color must survive removal of the edge faces.
        if any(sum(materials[fi] == mat for fi in impacted) < 2
               for mat in palette_u | palette_v):
            return None
        rgbs = [_material_rgb(m) for m in palette_u | palette_v]
        if any(max(rgb[k] for rgb in rgbs) - min(rgb[k] for rgb in rgbs)
               > color_tolerance for k in range(3)):
            return None
    else:
        return None
    ring_u = _links_for(u, vertex_faces, faces)
    ring_v = _links_for(v, vertex_faces, faces)
    if ring_u is None or ring_v is None:
        return None
    # The link condition protects manifoldness under an edge collapse.
    opposite = set()
    for fi in shared:
        opposite.update(int(x) for x in faces[fi] if int(x) not in (u, v))
    if len(opposite) != 2 or ring_u & ring_v != opposite:
        return None
    midpoint = (points[u] + points[v]) * .5
    if not np.isfinite(midpoint).all():
        return None
    for fi in impacted - shared:
        tri = faces[fi]
        orig = points[list(tri)]
        new = orig.copy()
        for k, idx in enumerate(tri):
            if idx == u or idx == v:
                new[k] = midpoint
        old_n = np.cross(orig[1] - orig[0], orig[2] - orig[0])
        new_n = np.cross(new[1] - new[0], new[2] - new[0])
        old_len = np.linalg.norm(old_n)
        new_len = np.linalg.norm(new_n)
        if old_len <= 1e-15 or new_len <= old_len * .07:
            return None
        if float(np.dot(old_n, new_n)) < angle_cos * old_len * new_len:
            return None
        # Limit projected displacement relative to the original plane.
        shift = midpoint - points[u if u in tri else v]
        if abs(float(np.dot(shift, old_n))) > max_displacement * old_len:
            return None
    return midpoint, shared


def _collapse_pass(points, faces, materials, target_faces, *, max_length2,
                   cos_allowed, max_displacement, color_tolerance, operation_budget, deadline,
                   cancelled=None):
    """Greedily collapse shortest valid edges; never skip unrelated triangles."""
    import numpy as np
    live_faces = np.asarray([f for f in faces if f is not None], dtype=np.int32)
    if len(live_faces) <= target_faces:
        return 0
    edge_pairs = np.concatenate((live_faces[:, [0, 1]], live_faces[:, [1, 2]],
                                 live_faces[:, [2, 0]]), axis=0)
    edge_pairs.sort(axis=1)
    edge_pairs = np.unique(edge_pairs, axis=0)
    lens = ((points[edge_pairs[:, 0]] - points[edge_pairs[:, 1]]) ** 2).sum(axis=1)
    # Stable ordering makes output deterministic for equal-length edges.
    ordering = np.argsort(lens, kind='stable')
    vertex_faces = [set() for _ in range(len(points))]
    for fi, face in enumerate(faces):
        if face is not None:
            for v in face:
                vertex_faces[v].add(fi)
    removed = 0
    attempts = 0
    for candidate in ordering:
        if len(live_faces) - removed <= target_faces or attempts >= operation_budget:
            break
        u, v = map(int, edge_pairs[candidate])
        if lens[candidate] > max_length2:
            break
        attempts += 1
        if (attempts & 2047) == 0:
            if cancelled is not None and cancelled():
                break
            if perf_counter() >= deadline:
                break
        decision = _eligible_collapse(u, v, points, faces, vertex_faces, materials,
                                      max_length2, cos_allowed, max_displacement,
                                      color_tolerance)
        if decision is None:
            continue
        midpoint, shared = decision
        neighbors = vertex_faces[u] | vertex_faces[v]
        # Remove exactly the two faces formerly incident to the edge.
        for fi in shared:
            for idx in faces[fi]:
                vertex_faces[idx].discard(fi)
            faces[fi] = None
        for fi in list(vertex_faces[v]):
            if faces[fi] is None:
                continue
            tri = faces[fi]
            faces[fi] = tuple(u if idx == v else idx for idx in tri)
            vertex_faces[u].add(fi)
        vertex_faces[v].clear()
        points[u] = midpoint
        removed += 2
    return removed


def build_quality_preview(mesh, mode='auto', *, max_seconds=8.0, cancelled=None):
    """Make a display-only LOD. Return the original if safe reduction is unavailable.

    Source colors/counts, original file and forecast/export data remain untouched.
    This first iteration intentionally handles only <=750k-face imported meshes.
    """
    start = perf_counter()
    original = len(mesh.triangles)
    if cancelled is not None and cancelled():
        return QualityResult(mesh, normalize_quality(mode), 'full', original,
                             original, 0., 'Cancelled before LOD preparation')
    resolved = choose_quality(mode, original)
    if resolved == 'full' or original < 150:
        return QualityResult(mesh, normalize_quality(mode), resolved, original,
                             original, 0., 'Full source geometry')
    ratio = .70 if resolved == 'balanced' else .45
    target = max(1, round(original * ratio))
    import numpy as np
    points = np.asarray(mesh.vertices, dtype=np.float64).copy()
    faces = [tuple(map(int, tri)) for tri in mesh.triangles]
    materials = _color_signature(mesh, original)
    # Do not reject an entire colored model based on seam prevalence.
    # Candidate edges are now screened locally for interior OR two-material
    # seam collapses; complex paint junctions and gradients stay protected.
    bounds = tuple(float(v) for v in mesh.bounds)
    diagonal = math.dist(bounds[:3], bounds[3:])
    if not math.isfinite(diagonal) or diagonal < 1e-10:
        return QualityResult(mesh, normalize_quality(mode), 'full', original,
                             original, 0., 'Degenerate source bounds')
    tris = np.asarray(mesh.triangles, dtype=np.int32)
    sample = tris[::max(1, len(tris) // 18000)]
    sample_edges = np.concatenate((sample[:, [0, 1]], sample[:, [1, 2]],
                                   sample[:, [2, 0]]), axis=0)
    sample_lengths = np.linalg.norm(points[sample_edges[:, 0]] -
                                    points[sample_edges[:, 1]], axis=1)
    typical_edge = float(np.median(sample_lengths))
    max_edge = min(diagonal * (.04 if resolved == 'balanced' else .08),
                   typical_edge * (1.25 if resolved == 'balanced' else 2.25))
    max_dev = min(diagonal * (.002 if resolved == 'balanced' else .006),
                  typical_edge * (.35 if resolved == 'balanced' else .85))
    max_angle = math.cos(math.radians(24 if resolved == 'balanced' else 38))
    # Hard operation cap; 6B-C will introduce cooperative cancellation.
    # A single deterministic pass avoids prolonged CPU work on ineligible meshes.
    removed = _collapse_pass(points, faces, materials, target,
                             max_length2=max_edge * max_edge,
                             cos_allowed=max_angle, max_displacement=max_dev,
                             color_tolerance=(8 if resolved == 'balanced' else 24),
                             operation_budget=min(original * 2, 180_000),
                             deadline=start + max(1.0, float(max_seconds)),
                             cancelled=cancelled)
    if cancelled is not None and cancelled():
        return QualityResult(mesh, normalize_quality(mode), 'full', original,
                             original, (perf_counter() - start) * 1000.,
                             'Cancelled LOD preparation')
    if not removed:
        return QualityResult(mesh, normalize_quality(mode), 'full', original,
                             original, (perf_counter() - start) * 1000.,
                             'No safe color-aware manifold collapses; full detail retained')
    # Compact only retained faces; preserve 3MF source IDs/color order exactly.
    kept = [i for i, face in enumerate(faces) if face is not None]
    used = sorted({i for fi in kept for i in faces[fi]})
    mapping = {value: i for i, value in enumerate(used)}
    tris = tuple(tuple(mapping[v] for v in faces[i]) for i in kept)
    vertices = tuple(tuple(map(float, points[idx])) for idx in used)
    color_faces = tuple(mesh.face_colors[i] for i in kept) if len(mesh.face_colors) == original else ()
    corner_faces = tuple(mesh.corner_colors[i] for i in kept) if len(mesh.corner_colors) == original else ()
    lod = replace(mesh, vertices=vertices, triangles=tris, face_colors=color_faces,
                  corner_colors=corner_faces, render_buffer=None, load_profile=None)
    return QualityResult(lod, normalize_quality(mode), resolved, original,
                         len(tris), (perf_counter() - start) * 1000.,
                         'Low-contrast color-aware preview approximation; original paint unchanged')
