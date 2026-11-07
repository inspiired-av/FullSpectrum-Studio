"""Precision preservation for optimized preview vertex packing (no Qt)."""
from __future__ import annotations
import importlib.util
import math
from array import array
from pathlib import Path
from random import Random
from types import SimpleNamespace
import unittest
from desktop.qt_app.preview_shading import flatten_faces, _coherent_vertex_normals

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'desktop/qt_app/preview_shading_baseline_precision_reference.py'

# The in-repo test keeps a small, independent copy of the committed a57daee
# formula rather than relying on git commands in CI.

def reference(mesh, crease_angle=53):
    from collections import defaultdict
    vertices=mesh.vertices;faces=mesh.triangles; normals=[]
    for a,b,c in faces:
        p,q,r=vertices[a],vertices[b],vertices[c]
        u=(q[0]-p[0],q[1]-p[1],q[2]-p[2]);w=(r[0]-p[0],r[1]-p[1],r[2]-p[2])
        n=(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0])
        size=math.sqrt(sum(x*x for x in n))
        normals.append((tuple(x/size for x in n) if size>1e-12 else (0.,0.,1.),size))
    adjacency=defaultdict(list)
    for face_i,tri in enumerate(faces):
        for idx in set(tri): adjacency[idx].append(face_i)
    cos_limit=math.cos(math.radians(crease_angle))
    palette=mesh.face_colors; corners=mesh.corner_colors
    use_corners=len(corners)==len(faces)
    result=array('f')
    for i,tri in enumerate(faces):
        normal,_=normals[i]
        src=palette[i] if len(palette)==len(faces) else None
        color=tuple(int(src[j:j+2],16)/255. for j in (1,3,5)) if src and len(src)==7 else (.56,.77,.84)
        tag=color if src else (-1.,-1.,-1.)
        for corner_idx,idx in enumerate(tri):
            vertex_color=color
            if use_corners:
                corner=corners[i][corner_idx]
                if corner and len(corner)==7:
                    vertex_color=tuple(int(corner[j:j+2],16)/255. for j in (1,3,5))
            sx=sy=sz=0.
            for j in adjacency[idx]:
                other,area=normals[j]
                if area>1.e-12 and sum(normal[k]*other[k] for k in range(3))>=cos_limit:
                    sx+=other[0]*area;sy+=other[1]*area;sz+=other[2]*area
            length=math.sqrt(sx*sx+sy*sy+sz*sz)
            smoothed=(sx/length,sy/length,sz/length) if length>1.e-12 else normal
            result.extend((*vertices[idx],*smoothed,*vertex_color,*tag))
    return result

def terrain(n, seed):
    rand=Random(seed)
    vertices=tuple((float(x),float(y),
                    5*math.sin(x/8)*math.cos(y/11)+rand.uniform(-.01,.01))
                   for y in range(n) for x in range(n))
    triangles=[]
    for y in range(n-1):
        for x in range(n-1):
            a=y*n+x
            triangles.extend(((a,a+1,a+n+1),(a,a+n+1,a+n)))
    colors=tuple(('#FFAA33' if i%11==0 else None) for i in range(len(triangles)))
    return SimpleNamespace(vertices=vertices, triangles=tuple(triangles),
                           face_colors=colors,corner_colors=())

class PrecisionTests(unittest.TestCase):
    def test_narrow_safe_cone_rejects_near_crease_threshold(self):
        # ±26.49 degrees fall within the earlier 26.5° cap, but not the
        # guarded cap.  The baseline per-corner math must be used instead.
        a=math.radians(26.49)
        normals=[((0.,0.,1.),1.),
                 ((math.sin(a),0.,math.cos(a)),1.),
                 ((-math.sin(a),0.,math.cos(a)),1.)]
        cosine=math.cos(math.radians(21.5))
        self.assertEqual(_coherent_vertex_normals(normals,[[0,1,2]],cosine),[None])

    def test_reference_matches_terrains(self):
        for n in (4, 19, 53):
            with self.subTest(n=n):
                m=terrain(n, n*13)
                self.assertEqual(reference(m).tobytes(),flatten_faces(m).tobytes())

    def test_reference_matches_sharp_corner_and_varied_angles(self):
        v=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(0.,-1.,0.))
        f=((0,1,2),(0,1,3),(0,3,4),(0,0,0))
        m=SimpleNamespace(vertices=v,triangles=f,face_colors=('#AA0033',None,None,None),
                          corner_colors=(('#FF0000',None,None),)*len(f))
        for a in (0,26.5,53,90,179,180):
            with self.subTest(angle=a):
                self.assertEqual(reference(m,a).tobytes(),flatten_faces(m,a).tobytes())

    def test_buffer_comparison_checks_bits(self):
        a=array('f',[float('nan'),1.,0.]); b=array('f',a)
        self.assertNotEqual(a,b)
        self.assertEqual(memoryview(a).cast('B'),memoryview(b).cast('B'))

if __name__=='__main__': unittest.main()
