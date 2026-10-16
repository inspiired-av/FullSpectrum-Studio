"""Stage 3A: bounded, read-only model geometry loader (no Qt, no engine writes).

3MF build/component transforms use the 3MF column-vector convention; world axes
remain X right, Y back, Z up. Display-only triangle sampling is reported.
Color and paint metadata are intentionally deferred to Stage 3B.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
import re
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
import math
import json
import struct
import posixpath

MAX_ARCHIVE_MEMBERS = 700
MAX_MODEL_MEMBER = 90_000_000
MAX_SOURCE_VERTICES = 1_500_000
MAX_SOURCE_TRIANGLES = 1_500_000
MAX_DRAW_TRIANGLES = 750_000  # full-surface display; never drop isolated faces
MAX_GLB_BYTES = 160_000_000
IDENTITY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)
PROD_PATH = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path'


@dataclass(frozen=True)
class PreviewMesh:
    vertices: tuple
    triangles: tuple
    source_triangles: int
    bounds: tuple  # (minx,miny,minz,maxx,maxy,maxz)
    name: str
    face_colors: tuple = ()  # one RGB hex string or None per DISPLAY triangle
    palette_counts: tuple = ()  # (HEX, faces) from the COMPLETE source, not the sampled view
    color_status: str = "No explicit source colors detected"
    render_buffer: object = field(default=None, compare=False, repr=False)  # prepared off the UI thread
    corner_colors: tuple = ()  # exact (color1,color2,color3) per triangle, for GPU interpolation

    @property
    def sampled(self):
        return len(self.triangles) < self.source_triangles


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _matrix(raw):
    if not raw:
        return IDENTITY
    numbers = tuple(float(v) for v in raw.split())
    if len(numbers) != 12 or not all(map(math.isfinite, numbers)):
        raise ValueError('Invalid 3MF object transformation')
    return numbers


def _apply(m, v):
    x, y, z = v
    return (m[0]*x + m[3]*y + m[6]*z + m[9],
            m[1]*x + m[4]*y + m[7]*z + m[10],
            m[2]*x + m[5]*y + m[8]*z + m[11])


def _compose(a, b):
    """Apply b locally, then a in world coordinates (3MF's 3x4 layout)."""
    rows = []
    for col in range(3):
        bx, by, bz = b[3*col:3*col+3]
        rows.extend((a[0]*bx+a[3]*by+a[6]*bz,
                     a[1]*bx+a[4]*by+a[7]*bz,
                     a[2]*bx+a[5]*by+a[8]*bz))
    x, y, z = _apply(a, (b[9], b[10], b[11]))
    return tuple(rows) + (x,y,z)


def _safe_member(z, name, limit=MAX_MODEL_MEMBER):
    info = z.getinfo(name)
    if info.file_size > limit:
        raise ValueError('3MF model member exceeds the preview safety limit')
    return z.read(info)


def _safe_path(name):
    name = str(name).replace('\\','/').lstrip('/')
    result = posixpath.normpath(name)
    if result == '..' or result.startswith('../') or result.startswith('/'):
        raise ValueError('Unsafe 3MF member path')
    return result


def _objects(xml):
    root = ET.fromstring(xml)
    objects = {}
    for obj in root.iter():
        if _local(obj.tag) != 'object':
            continue
        identifier = obj.attrib.get('id')
        if identifier:
            objects[identifier] = obj
    return root, objects


def _mesh_parts(obj, palette=None, default_color=None, native_colors=(), stats=None):
    meshes = [child for child in obj if _local(child.tag) == 'mesh']
    for mesh in meshes:
        vertices=[]; triangles=[]; face_colors=[]; corner_colors=[]
        for elem in mesh.iter():
            what=_local(elem.tag)
            if what == 'vertex':
                try:
                    xyz=tuple(float(elem.get(k)) for k in ('x','y','z'))
                except (ValueError,TypeError) as exc:
                    raise ValueError('Invalid 3MF mesh vertex') from exc
                if not all(math.isfinite(v) for v in xyz):
                    raise ValueError('3MF contains non-finite geometry')
                vertices.append(xyz)
                if len(vertices)>MAX_SOURCE_VERTICES:
                    raise ValueError('3MF mesh vertex limit exceeded')
            elif what=='triangle':
                try:
                    t=tuple(int(elem.get(k)) for k in ('v1','v2','v3'))
                except (ValueError,TypeError) as exc:
                    raise ValueError('Invalid 3MF triangle index') from exc
                hex_color=None
                corners=None
                pid=elem.get('pid') or obj.get('pid')
                base=elem.get('p1',obj.get('pindex','0'))
                if pid and palette and pid in palette:
                    table=palette[pid]
                    try:
                        indexes=[int(elem.get(k,base)) for k in ('p1','p2','p3')]
                        values=[table[index] for index in indexes]
                        if all(v is not None for v in values):
                            corners=tuple(values)
                            if len(set(values))==1:hex_color=values[0]
                            else:
                                rgb=[tuple(int(c[j:j+2],16) for j in (1,3,5)) for c in values]
                                hex_color='#'+''.join(f'{round(sum(v[n] for v in rgb)/3):02X}' for n in range(3))
                                if stats is not None:stats['blended']+=1
                    except (ValueError,IndexError):
                        if stats is not None:stats['unresolved']+=1
                elif native_colors:
                    code=elem.get('paint_color')
                    if code is None:hex_color=default_color
                    else:
                        try:
                            from desktop.qt_app.native_object_colors import _single_painted_slot
                            slot=_single_painted_slot(code,len(native_colors))
                            hex_color=native_colors[slot-1]
                        except ValueError:
                            if stats is not None:stats['unresolved']+=1
                else:hex_color=default_color
                triangles.append(t)
                face_colors.append(hex_color)
                corner_colors.append(corners if corners else (hex_color,)*3)
                if len(triangles)>MAX_SOURCE_TRIANGLES:
                    raise ValueError('3MF mesh triangle limit exceeded')
        if not vertices or not triangles:
            continue
        if any(any(i<0 or i>=len(vertices) for i in t) for t in triangles):
            raise ValueError('3MF references an invalid mesh vertex')
        yield vertices, triangles, face_colors, corner_colors


HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?$')


def _color(value):
    if not isinstance(value,str) or not HEX_COLOR.fullmatch(value):return None
    if len(value)==9 and value[-2:].upper()!='FF':return None  # no unsupported transparency guessing
    return value[:7].upper()


def _model_palettes(root):
    colors={}
    for resources in root:
        if _local(resources.tag)!='resources':continue
        for group in resources:
            kind=_local(group.tag)
            if kind not in ('colorgroup','basematerials'):continue
            items=[]
            for item in group:
                if kind=='colorgroup' and _local(item.tag)=='color':
                    items.append(_color(item.get('color')))
                elif kind=='basematerials' and _local(item.tag)=='base':
                    items.append(_color(item.get('displaycolor')))
            colors[group.get('id')]=items
    return colors


def _native_defaults(z,root):
    if 'Metadata/project_settings.config' not in z.namelist() or 'Metadata/model_settings.config' not in z.namelist():
        return {},()
    # Read-only native assignment hints. Never invent mixed-slot or split-face colors.
    try:
        project=json.loads(_safe_member(z,'Metadata/project_settings.config'))
        colors=tuple(_color(c) for c in project.get('filament_colour',[]))
        mixed=project.get('filament_is_mixed',[])
        if not colors or any(c is None for c in colors):return {},()
        settings=ET.fromstring(_safe_member(z,'Metadata/model_settings.config'))
        slots={}
        for obj in settings:
            if _local(obj.tag)!='object':continue
            meta={c.get('key'):c.get('value') for c in obj if _local(c.tag)=='metadata'}
            index=int(meta.get('extruder','0'))-1
            if 0<=index<len(colors):
                # Mixed-slot display color is a saved slicer swatch, not a physical material.
                slots[obj.get('id')]=colors[index]
        return slots,colors
    except (KeyError,ValueError,TypeError,ET.ParseError):return {},()


def _unit_scale(root):
    return {'millimeter':1., 'centimeter':10., 'meter':1000., 'inch':25.4,
            'foot':304.8, 'micron':0.001}.get(root.attrib.get('unit','millimeter').lower(),1.)


def _build_mesh(vertices, triangles, name, face_colors=None, stats=None, corner_colors=None):
    if not triangles or not vertices:
        raise ValueError('No renderable triangles found in the model')
    minx=min(v[0] for v in vertices);miny=min(v[1] for v in vertices);minz=min(v[2] for v in vertices)
    maxx=max(v[0] for v in vertices);maxy=max(v[1] for v in vertices);maxz=max(v[2] for v in vertices)
    count=len(triangles)
    if face_colors is not None and len(face_colors)!=count:
        raise ValueError('Source colors are not aligned with preview geometry')
    if corner_colors is not None and len(corner_colors)!=count:
        raise ValueError('Vertex source colors are not aligned with preview geometry')
    palette=Counter(c for c in (face_colors or ()) if c)
    palette_counts=tuple(sorted(palette.items(),key=lambda x:(-x[1],x[0])))
    if count>MAX_DRAW_TRIANGLES:
        # Slicing triangles[::step] punctures every watertight object and makes
        # interiors visible as disconnected fans. Never pretend this is a valid
        # surface-preserving LOD. A real mesh simplifier belongs in Stage 3C.
        raise ValueError(
            f'This model contains {count:,} triangles, exceeding the safe full-surface '
            f'preview limit ({MAX_DRAW_TRIANGLES:,}). Triangle skipping has been disabled '
            'because it corrupts closed surfaces. Use a reduced preview mesh until '
            'topology-preserving decimation is available.'
        )
    stats=stats or {}
    parts=[]
    if palette_counts:parts.append(f'{len(palette_counts)} source colors')
    else:parts.append('No explicit source colors detected')
    if stats.get('unresolved'):parts.append(f"{stats['unresolved']:,} unsupported/unknown faces rendered neutral")
    if stats.get('blended'):parts.append(f"{stats['blended']:,} interpolated vertex-color faces")
    return PreviewMesh(tuple(vertices),tuple(triangles),count,
                       (minx,miny,minz,maxx,maxy,maxz),name,
                       tuple(face_colors or ()),palette_counts,' · '.join(parts),
                       corner_colors=tuple(corner_colors or ()))


def load_3mf(path):
    vertices=[]; triangles=[]; face_colors=[]; corner_colors=[]; stats=Counter()
    try:
        with ZipFile(path) as z:
            entries=z.infolist()
            if len(entries)>MAX_ARCHIVE_MEMBERS:
                raise ValueError('3MF has too many archive members')
            for item in entries:
                if _safe_path(item.filename)!=item.filename.rstrip('/'):
                    raise ValueError('Unsafe 3MF member path')
            root,objects=_objects(_safe_member(z,'3D/3dmodel.model'))
            scale=_unit_scale(root)
            native_defaults,native_colors=_native_defaults(z,root)
            cache={'3D/3dmodel.model':(root,objects)}
            active=set()
            total_v=0;total_t=0

            def walk(member,obj_id,transform,depth=0,default_color=None):
                nonlocal total_v,total_t
                if depth>18:
                    raise ValueError('3MF component nesting limit exceeded')
                reference=(member,obj_id)
                if reference in active:
                    raise ValueError('Cyclic 3MF component graph')
                active.add(reference)
                try:
                    if member not in cache:
                        cache[member]=_objects(_safe_member(z,member))
                    node=cache[member][1].get(obj_id)
                    if node is None:
                        raise ValueError('Missing 3MF component object '+obj_id)
                    if member=='3D/3dmodel.model':
                        default_color=native_defaults.get(obj_id,default_color)
                    local_palette=_model_palettes(cache[member][0])
                    for points,faces,colors,corners in _mesh_parts(node,local_palette,default_color,native_colors,stats):
                        if total_v+len(points)>MAX_SOURCE_VERTICES or total_t+len(faces)>MAX_SOURCE_TRIANGLES:
                            raise ValueError('Model exceeds preview geometry limits')
                        offset=len(vertices)
                        vertices.extend(_apply(transform,(x*scale,y*scale,z*scale)) for x,y,z in points)
                        triangles.extend(tuple(offset+i for i in t) for t in faces)
                        face_colors.extend(colors)
                        corner_colors.extend(corners)
                        total_v+=len(points);total_t+=len(faces)
                    for comp_container in node:
                        if _local(comp_container.tag)!='components':continue
                        for comp in comp_container:
                            if _local(comp.tag)!='component':continue
                            raw=comp.get(PROD_PATH) or comp.get('path')
                            child_member=_safe_path(raw) if raw else member
                            # Relative paths are interpreted against the parent .model.
                            if raw and not raw.startswith('/'):
                                child_member=_safe_path(posixpath.join(posixpath.dirname(member),raw))
                            walk(child_member,comp.attrib['objectid'],
                                 _compose(transform,_matrix(comp.get('transform'))),depth+1,default_color)
                finally:
                    active.remove(reference)

            build=next((node for node in root if _local(node.tag)=='build'),None)
            if build is None or not list(build):
                raise ValueError('3MF has an empty build plate')
            for item in build:
                if _local(item.tag)=='item':
                    walk('3D/3dmodel.model',item.attrib['objectid'],_matrix(item.get('transform')))
    except (BadZipFile,KeyError,ET.ParseError) as exc:
        raise ValueError('3MF model structure is unreadable') from exc
    return _build_mesh(vertices,triangles,Path(path).name,face_colors,stats,corner_colors)


def _obj_materials(path):
    # Explicit local MTL only. No texture/image fetches or remote file access.
    materials={};name=None
    mtl=Path(path).with_suffix('.mtl')
    if not mtl.is_file() or mtl.stat().st_size>4_000_000:return materials
    for line in mtl.read_text(encoding='utf-8',errors='replace').splitlines():
        words=line.split()
        if not words:continue
        if words[0]=='newmtl' and len(words)>1:name=' '.join(words[1:])
        elif words[0]=='Kd' and name and len(words)>=4:
            try:
                rgb=[int(round(max(0,min(1,float(v)))*255)) for v in words[1:4]]
                materials[name]='#'+''.join(f'{n:02X}' for n in rgb)
            except ValueError:pass
    return materials


def load_obj(path):
    vertices=[];faces=[];colors=[];materials=_obj_materials(path);current=None
    with open(path,'r',encoding='utf-8',errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                bits=line.split()
                if len(bits)<4:continue
                xyz=tuple(float(x) for x in bits[1:4])
                if not all(math.isfinite(x) for x in xyz):raise ValueError('Invalid OBJ vertex')
                vertices.append(xyz)
                if len(vertices)>MAX_SOURCE_VERTICES:raise ValueError('OBJ vertex limit exceeded')
            elif line.startswith('usemtl '):
                current=materials.get(line[7:].strip())
            elif line.startswith('f '):
                raw=[x.split('/')[0] for x in line.split()[1:]]
                inds=[int(v)-1 if int(v)>0 else len(vertices)+int(v) for v in raw]
                if not all(0<=i<len(vertices) for i in inds):raise ValueError('Invalid OBJ face index')
                for k in range(1,len(inds)-1):
                    faces.append((inds[0],inds[k],inds[k+1]))
                    colors.append(current)
                if len(faces)>MAX_SOURCE_TRIANGLES:raise ValueError('OBJ face limit exceeded')
    return _build_mesh(vertices,faces,Path(path).name,colors)


def _gltf_compose_translation_rotation_scale(node):
    if 'matrix' in node:
        m=node['matrix']
        if len(m)!=16:raise ValueError('Invalid glTF transform matrix')
        return (m[0],m[1],m[2],m[4],m[5],m[6],m[8],m[9],m[10],m[12],m[13],m[14])
    tx,ty,tz=node.get('translation',[0,0,0]); sx,sy,sz=node.get('scale',[1,1,1])
    x,y,z,w=node.get('rotation',[0,0,0,1]); norm=math.sqrt(x*x+y*y+z*z+w*w)
    if norm<=1e-12:raise ValueError('Invalid glTF rotation')
    x/=norm;y/=norm;z/=norm;w/=norm
    r=(1-2*(y*y+z*z),2*(x*y+z*w),2*(x*z-y*w),
       2*(x*y-z*w),1-2*(x*x+z*z),2*(y*z+x*w),
       2*(x*z+y*w),2*(y*z-x*w),1-2*(x*x+y*y))
    return (r[0]*sx,r[1]*sx,r[2]*sx,r[3]*sy,r[4]*sy,r[5]*sy,
            r[6]*sz,r[7]*sz,r[8]*sz,float(tx),float(ty),float(tz))


def load_glb(path):
    data=Path(path).read_bytes()
    if len(data)>MAX_GLB_BYTES:raise ValueError('GLB exceeds the preview size limit')
    if len(data)<20 or data[:4]!=b'glTF' or struct.unpack_from('<I',data,4)[0]!=2:
        raise ValueError('Not a supported glTF 2.0 GLB')
    if struct.unpack_from('<I',data,8)[0]!=len(data):raise ValueError('GLB length does not match header')
    at=12; chunks={}
    while at<len(data):
        length,kind=struct.unpack_from('<II',data,at);at+=8
        if at+length>len(data):raise ValueError('Truncated GLB chunk')
        chunks[kind]=memoryview(data)[at:at+length];at+=length
    if 0x4e4f534a not in chunks or 0x004e4942 not in chunks:
        raise ValueError('GLB requires embedded JSON and binary geometry')
    doc=json.loads(bytes(chunks[0x4e4f534a]))
    buffer=chunks[0x004e4942]; accessors=doc.get('accessors',[]); views=doc.get('bufferViews',[])
    def get_accessor(idx, kind):
        a=accessors[idx]
        if 'sparse' in a or 'bufferView' not in a:raise ValueError('Sparse GLB geometry is not supported in Stage 3A')
        v=views[a['bufferView']]
        if v.get('buffer',0)!=0:raise ValueError('External GLB geometry is not supported')
        count=a['count'];ctype=a['componentType'];typ=a['type']
        if count>MAX_SOURCE_VERTICES:raise ValueError('GLB accessor exceeds preview limits')
        if kind=='vertex' and (ctype!=5126 or typ!='VEC3'):
            raise ValueError('GLB positions must be float VEC3')
        if kind=='index' and (ctype not in (5121,5123,5125) or typ!='SCALAR'):
            raise ValueError('GLB indices must use unsigned integers')
        formatc={5126:'f',5121:'B',5123:'H',5125:'I'}[ctype]
        size=struct.calcsize('<'+formatc); components=3 if kind=='vertex' else 1
        stride=v.get('byteStride',size*components)
        begin=v.get('byteOffset',0)+a.get('byteOffset',0)
        limit=v.get('byteOffset',0)+v['byteLength']
        if stride<size*components or begin+(count-1)*stride+size*components>limit:
            raise ValueError('GLB accessor exceeds its buffer view')
        result=[]
        fmt='<'+formatc*components
        for i in range(count):result.append(struct.unpack_from(fmt,buffer,begin+i*stride))
        return result
    verts=[];tri=[];matrices=[]
    def walk_node(idx,m,stack):
        if idx in stack:raise ValueError('Cyclic GLB scene graph')
        node=doc['nodes'][idx];local=_gltf_compose_translation_rotation_scale(node)
        transform=_compose(m,local)
        if 'mesh' in node:
            mesh=doc['meshes'][node['mesh']]
            for prim in mesh.get('primitives',[]):
                if prim.get('mode',4)!=4:raise ValueError('Only GLB triangle primitives are supported')
                arr=get_accessor(prim['attributes']['POSITION'],'vertex')
                inds=[int(x[0]) for x in get_accessor(prim['indices'],'index')] if 'indices' in prim else list(range(len(arr)))
                if len(inds)%3:raise ValueError('Invalid GLB triangle index count')
                if len(verts)+len(arr)>MAX_SOURCE_VERTICES or len(tri)+len(inds)//3>MAX_SOURCE_TRIANGLES:
                    raise ValueError('GLB preview geometry limit exceeded')
                base=len(verts)
                # glTF is Y-up: rotate +90° around X to preserve handedness in Z-up view.
                verts.extend((lambda v: (v[0],-v[2],v[1]))(_apply(transform,p)) for p in arr)
                if any(k<0 or k>=len(arr) for k in inds):raise ValueError('Invalid GLB triangle index')
                tri.extend((base+inds[k],base+inds[k+1],base+inds[k+2]) for k in range(0,len(inds),3))
        for child in node.get('children',[]):walk_node(child,transform,stack|{idx})
    scene=doc['scenes'][doc.get('scene',0)] if doc.get('scenes') else {'nodes':list(range(len(doc.get('nodes',[]))))}
    for idx in scene.get('nodes',[]):walk_node(idx,IDENTITY,set())
    return _build_mesh(verts,tri,Path(path).name)


def load_preview_mesh(filename):
    p=Path(filename)
    if not p.is_file():raise ValueError('Model file does not exist')
    fmt=p.suffix.lower()
    if fmt=='.3mf':return load_3mf(p)
    if fmt=='.obj':return load_obj(p)
    if fmt=='.glb':return load_glb(p)
    raise ValueError('Stage 3A supports 3MF, OBJ and embedded GLB models')
