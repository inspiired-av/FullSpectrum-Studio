"""Render source-face-color plate thumbnails for native-template exports.

This preview is illustrative, not a slicing/simulation output. The real 3MF
geometry/painting is untouched. Requires Pillow, already used by desktop UI.
"""

from __future__ import annotations

import io
import math
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

CORE = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'


def _single_paint_slot(code):
    """Decode a single Bambu TriangleSelector leaf, no split-tree approximation."""
    if not code:
        return 1
    try:
        data = [int(c, 16) for c in reversed(code.strip())]
        marker = data.pop(0)
        if marker & 3:   # subdivided triangle; its preview uses fallback color
            return None
        if marker & 12 == 12:
            slot = 3
            while data:
                digit = data.pop(0)
                if digit == 15:
                    slot += 15
                else:
                    slot += digit
                    return slot if not data else None
            return None
        return marker >> 2 if not data else None
    except (ValueError, IndexError):
        return None


def render_plate_preview(model_xml, palette, size=512, max_faces=25000):
    """Produce a simple projected, source-painted PNG, never mutate the mesh."""
    tree = ET.fromstring(model_xml)
    vertices = []
    mesh = tree.find(f'.//{{{CORE}}}mesh')
    if mesh is None:
        raise ValueError('No mesh available for preview')
    for vertex in mesh.findall(f'{{{CORE}}}vertices/{{{CORE}}}vertex'):
        xyz = tuple(float(vertex.get(k)) for k in ('x', 'y', 'z'))
        if not all(math.isfinite(v) for v in xyz):
            raise ValueError('Non-finite coordinate in preview mesh')
        vertices.append(xyz)
    if not vertices:
        raise ValueError('Mesh has no preview vertices')
    extents = [max(v[i] for v in vertices)-min(v[i] for v in vertices) for i in range(3)]
    # Project thin upright objects along their narrowest horizontal axis;
    # fall back to a conventional isometric view for volumetric meshes.
    flat = min(extents) < max(extents)*0.52
    thin_axis = min(range(3), key=lambda i: extents[i]) if flat else -1
    face_nodes=mesh.findall(f'{{{CORE}}}triangles/{{{CORE}}}triangle')
    # A thin sign may be painted on its lower- or higher-coordinate side.
    # Face the decorated side instead of viewing the unpainted backing sheet.
    side=1
    if thin_axis in (0,1):
        positions_with_paint=[]
        for triangle in face_nodes[::max(1,len(face_nodes)//3000)]:
            if not triangle.get('paint_color'):
                continue
            try:
                indices=[int(triangle.get(k)) for k in ('v1','v2','v3')]
                positions_with_paint.append(sum(vertices[i][thin_axis] for i in indices)/3)
            except (ValueError,IndexError,TypeError):
                continue
        if positions_with_paint:
            midpoint=(min(v[thin_axis] for v in vertices)+max(v[thin_axis] for v in vertices))/2
            side=1 if sorted(positions_with_paint)[len(positions_with_paint)//2]>=midpoint else -1
    def project(v):
        x,y,z=v
        if thin_axis == 0:
            return (-y + x*0.12, -z + x*0.15, side*x)
        if thin_axis == 1:
            return (x + y*0.12, -z + y*0.15, side*y)
        return (x*0.78-y*0.78, -z + (x+y)*0.32, x+y+z*0.08)
    positions = [project(v) for v in vertices]
    x0=min(v[0] for v in positions); x1=max(v[0] for v in positions)
    y0=min(v[1] for v in positions); y1=max(v[1] for v in positions)
    factor=(size*0.76)/max(x1-x0,y1-y0,1.e-6)
    def screen(p):
        return (int(size/2+(p[0]-(x0+x1)/2)*factor),
                int(size/2+(p[1]-(y0+y1)/2)*factor))
    projected=[screen(p) for p in positions]
    img=Image.new('RGB',(size,size),(35,40,46))
    draw=ImageDraw.Draw(img)
    # Add an unobtrusive floor so small/dark geometry is visible.
    draw.ellipse((size*.12,size*.82,size*.88,size*.91),fill=(40,46,50))
    triangles=[]
    step=max(1,math.ceil(len(face_nodes)/max_faces))
    for tri in face_nodes[::step]:
        try:
            indices=[int(tri.get(k)) for k in ('v1','v2','v3')]
            if any(i<0 or i>=len(vertices) for i in indices):
                continue
            points=[projected[i] for i in indices]
            depth=sum(positions[i][2] for i in indices)/3
            slot=_single_paint_slot(tri.get('paint_color'))
            color=palette[slot-1] if slot and slot<=len(palette) else '#B6BCC5'
            rgb=tuple(int(color[k:k+2],16) for k in (1,3,5))
            a,b,c=(vertices[i] for i in indices)
            ab=[b[j]-a[j] for j in range(3)]
            ac=[c[j]-a[j] for j in range(3)]
            normal=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
            magnitude=max(1.e-9,math.sqrt(sum(x*x for x in normal)))
            lighting=.70+.28*abs(sum(normal[j]*([.72,.25,.65][j]) for j in range(3))/magnitude)
            shaded=tuple(min(255,max(0,int(x*lighting))) for x in rgb)
            triangles.append((depth,points,shaded))
        except (ValueError,TypeError):
            continue
    # Painter sorting is adequate for thumbnail display, not an occlusion contract.
    for _,points,color in sorted(triangles,key=lambda item:item[0]):
        draw.polygon(points,fill=color)
    data=io.BytesIO()
    img.save(data,format='PNG',optimize=True)
    large=data.getvalue()
    thumb=img.resize((128,128),Image.Resampling.LANCZOS)
    data=io.BytesIO()
    thumb.save(data,format='PNG',optimize=True)
    return large,data.getvalue()


def add_native_thumbnails(payload, child_bytes, planned):
    """Replace *blank template* plate images only in the new archive payload."""
    colors=planned.get('filament_colour', [])
    if not colors:
        return
    large,small=render_plate_preview(child_bytes,colors)
    for name in ('Metadata/plate_1.png', 'Metadata/plate_no_light_1.png',
                 'Metadata/top_1.png', 'Metadata/pick_1.png'):
        if name in payload:
            payload[name]=large
    if 'Metadata/plate_1_small.png' in payload:
        payload['Metadata/plate_1_small.png']=small
