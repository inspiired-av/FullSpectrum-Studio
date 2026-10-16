"""Pure Python GPU vertex preparation: crease-aware smoothing and exact face colors.

No Qt/OpenGL, geometry writes or filament prediction.
"""
from array import array
from collections import defaultdict
import math

def _face_normals(mesh):
    """Return normalized face directions and area weights (read-only geometry)."""
    result=[]
    v=mesh.vertices
    for a,b,c in mesh.triangles:
        p,q,r=v[a],v[b],v[c]
        u=(q[0]-p[0],q[1]-p[1],q[2]-p[2]);w=(r[0]-p[0],r[1]-p[1],r[2]-p[2])
        n=(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0])
        size=math.sqrt(sum(x*x for x in n))
        result.append((tuple(x/size for x in n) if size>1e-12 else (0.,0.,1.),size))
    return result


def flatten_faces(mesh, crease_angle=53):
    """Pack position, crease-aware normals and face colors for GPU upload.

    Area-weighted smoothing blends faceted curved surfaces, but only across
    incident faces within `crease_angle` of each triangle. Sharp edges and
    independent objects remain intact. No vertices, source faces or colors change.
    """
    vertices=mesh.vertices
    faces=mesh.triangles
    normals=_face_normals(mesh)
    adjacency=defaultdict(list)
    for face_i,tri in enumerate(faces):
        for idx in set(tri):adja=adjacency[idx];adja.append(face_i)
    cos_limit=math.cos(math.radians(crease_angle))
    palette=getattr(mesh,'face_colors',())
    result=array('f')
    for i,tri in enumerate(faces):
        normal,_=normals[i]
        src=palette[i] if len(palette)==len(faces) else None
        if src and len(src)==7:
            color=tuple(int(src[j:j+2],16)/255. for j in (1,3,5))
        else:color=(.56,.77,.84)
        for idx in tri:
            sx=sy=sz=0.
            for j in adjacency[idx]:
                other,area=normals[j]
                if area>1.e-12 and sum(normal[k]*other[k] for k in range(3))>=cos_limit:
                    sx+=other[0]*area;sy+=other[1]*area;sz+=other[2]*area
            length=math.sqrt(sx*sx+sy*sy+sz*sz)
            smoothed=(sx/length,sy/length,sz/length) if length>1.e-12 else normal
            result.extend((*vertices[idx],*smoothed,*color))
    return result

