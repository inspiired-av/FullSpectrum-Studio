"""Read-only, bounded STL loader for *visual* installed-slicer bed models.

No model geometry, forecasts, native 3MF files, or slicer settings are touched.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
from pathlib import Path
import struct

MAX_STL_BYTES = 64_000_000
MAX_FACES = 400_000


@dataclass(frozen=True)
class PlateMesh:
    # Interleaved position(3), normal(3), planar UV(2); no printable geometry.
    vertices: array
    faces: int
    bounds: tuple[float, float, float, float, float, float]


def _unit_normal(p, q, r):
    u = tuple(q[i] - p[i] for i in range(3))
    v = tuple(r[i] - p[i] for i in range(3))
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    length = math.sqrt(sum(x*x for x in n))
    return tuple(x/length for x in n) if length > 1e-18 else (0., 0., 1.)


def _parse_binary(data):
    faces = struct.unpack_from('<I', data, 80)[0]
    if faces <= 0 or faces > MAX_FACES or 84 + faces*50 != len(data):
        raise ValueError('STL binary facet count or size is invalid')
    triangles = []
    offset = 84
    for _ in range(faces):
        # Ignore provided STL normals: recompute from actual vertex positions.
        numbers = struct.unpack_from('<12f', data, offset)
        p, q, r = (tuple(numbers[n:n+3]) for n in (3, 6, 9))
        triangles.append((p, q, r))
        offset += 50
    return triangles


def _parse_ascii(data):
    # Accept standard 'facet normal ... outer loop vertex ... endloop endfacet'
    # plus slicer ASCII STLs that omit the normal. Never execute STL content.
    triangles, current = [], []
    try:
        lines = data.decode('utf-8-sig').splitlines()
    except UnicodeError as exc:
        raise ValueError('Unsupported STL encoding') from exc
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0].lower() == 'vertex' and len(parts) == 4:
            try:
                xyz = tuple(float(x) for x in parts[1:])
            except ValueError as exc:
                raise ValueError('Invalid STL vertex coordinates') from exc
            current.append(xyz)
            if len(current) > 3:
                raise ValueError('Invalid ASCII STL facet with more than three vertices')
        elif parts[0].lower() == 'endfacet':
            if len(current) != 3:
                raise ValueError('Invalid ASCII STL facet')
            triangles.append(tuple(current))
            current = []
            if len(triangles) > MAX_FACES:
                raise ValueError('Build plate STL exceeds preview face limit')
    if current or not triangles:
        raise ValueError('No complete triangular facets in STL')
    return triangles


def load_plate_mesh(path: str | Path) -> PlateMesh:
    path = Path(path)
    if path.suffix.casefold() != '.stl':
        raise ValueError('Build plate mesh must be an STL')
    size = path.stat().st_size
    if size < 84 or size > MAX_STL_BYTES:
        raise ValueError('Build plate STL is empty or exceeds safe size limit')
    data = path.read_bytes()
    binary = (len(data) >= 84 and
              0 < struct.unpack_from('<I', data, 80)[0] <= MAX_FACES and
              84 + struct.unpack_from('<I', data, 80)[0] * 50 == len(data))
    faces = _parse_binary(data) if binary else _parse_ascii(data)
    mins = [float('inf')]*3
    maxs = [float('-inf')]*3
    for triangle in faces:
        for p in triangle:
            if not all(math.isfinite(x) and abs(x) < 1_000_000 for x in p):
                raise ValueError('Nonfinite or implausible STL coordinate')
            for axis in range(3):
                mins[axis] = min(mins[axis], p[axis]); maxs[axis] = max(maxs[axis], p[axis])
    w = max(maxs[0]-mins[0], 1e-6)
    h = max(maxs[1]-mins[1], 1e-6)
    output = array('f')
    for p, q, r in faces:
        normal = _unit_normal(p, q, r)
        for x, y, z in (p, q, r):
            output.extend((x, y, z, *normal, (x-mins[0])/w, 1.-(y-mins[1])/h))
    return PlateMesh(output, len(faces), (mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2]))


def plate_offset(mesh_bounds, plate_bounds, gap=0.5):
    """Place visual plate under the model without translating *the model*."""
    x0,y0,z0,x1,y1,_ = mesh_bounds
    a,b,_,c,d,f = plate_bounds
    return ((x0+x1-a-c)/2, (y0+y1-b-d)/2, z0-f-gap)



def combined_scene_bounds(model_bounds, plate_bounds):
    """World-space scene AABB, without scaling or changing model positions."""
    if plate_bounds is None:
        return tuple(model_bounds)
    offset = plate_offset(model_bounds, plate_bounds)
    x0,y0,z0,x1,y1,z1 = model_bounds
    a,b,c,d,e,f = plate_bounds
    ox,oy,oz = offset
    return (min(x0,a+ox),min(y0,b+oy),min(z0,c+oz),
            max(x1,d+ox),max(y1,e+oy),max(z1,f+oz))


def scene_clip_planes(eye, model_bounds, plate_bounds, base_planes, target=None):
    """Expand near/far to fit model+plate in camera depth without changing zoom.

    Use scene bounding corners projected onto the actual camera view direction,
    not a giant bounding sphere: that keeps the near plane farther away and
    reduces z-fighting when the plate is much larger than the model.
    """
    near, far = base_planes
    if plate_bounds is None:
        return near, far
    bounds = combined_scene_bounds(model_bounds,plate_bounds)
    x0,y0,z0,x1,y1,z1 = bounds
    eye = tuple(float(x) for x in eye)
    if target is None:
        target = ((x0+x1)*.5,(y0+y1)*.5,(z0+z1)*.5)
    vector = tuple(float(target[i])-eye[i] for i in range(3))
    length = math.sqrt(sum(v*v for v in vector))
    if length < 1e-9:
        return near, far
    direction = tuple(v/length for v in vector)
    depths = [sum((corner[i]-eye[i])*direction[i] for i in range(3))
              for corner in ((x,y,z) for x in (x0,x1)
                                     for y in (y0,y1) for z in (z0,z1))]
    front = [d for d in depths if d > 0]
    if not front:
        return near, far
    return max(.01,min(near,min(front)*.5)), max(far,max(front)*1.2)
