"""Exact float32 equivalence regression for the preview geometry packer.

The eight vertices below were minimized from a user-provided 450,992-triangle
3MF. They cover the single seven-face shared vertex that exposed a Python
float-summation difference. No external model fixture or Qt is required.
"""
from __future__ import annotations

from array import array
from collections import defaultdict
import math
import unittest
from types import SimpleNamespace

from desktop.qt_app.preview_shading import _face_normals, flatten_faces


VERTICES = (
    (126.49200439453125, 186.73788452148438, 0.0),
    (127.29161834716797, 186.7844696044922, 0.8000001907348633),
    (126.51652526855469, 186.30120849609375, 0.0),
    (127.3165283203125, 186.30120849609375, 0.8000001907348633),
    (127.29161834716797, 185.8179473876953, 0.8000001907348633),
    (126.49200439453125, 185.86456298828125, 0.0),
    (124.49598693847656, 185.36663818359375, 0.0),
    (124.39598846435547, 187.36663818359375, 0.0),
)
TRIANGLES = (
    (0, 1, 2), (2, 1, 3), (2, 3, 4), (4, 5, 2),
    (5, 6, 2), (2, 6, 7), (2, 7, 0),
)


def fixture_mesh(*, colors=False):
    if colors:
        palette = ('#C00040', '#B80048', '#B00050', '#A80058',
                   '#A00060', '#980068', '#900070')
        corners = tuple((palette[i], palette[(i + 1) % 7], palette[(i + 2) % 7])
                        for i in range(7))
    else:
        palette, corners = (), ()
    return SimpleNamespace(vertices=VERTICES, triangles=TRIANGLES,
                           face_colors=palette, corner_colors=corners)


def legacy_normals(mesh):
    """The committed baseline's exact arithmetic, kept independent of optimized code."""
    result = []
    for a, b, c in mesh.triangles:
        p, q, r = mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]
        u = (q[0]-p[0], q[1]-p[1], q[2]-p[2])
        w = (r[0]-p[0], r[1]-p[1], r[2]-p[2])
        n = (u[1]*w[2]-u[2]*w[1],
             u[2]*w[0]-u[0]*w[2],
             u[0]*w[1]-u[1]*w[0])
        size = math.sqrt(sum(x*x for x in n))
        result.append((tuple(x/size for x in n) if size > 1e-12
                       else (0., 0., 1.), size))
    return result


def legacy_packed(mesh, crease_angle=53):
    normals = legacy_normals(mesh)
    adjacency = defaultdict(list)
    for face_i, tri in enumerate(mesh.triangles):
        for idx in set(tri):
            adjacency[idx].append(face_i)
    cos_limit = math.cos(math.radians(crease_angle))
    result = array('f')
    for i, tri in enumerate(mesh.triangles):
        normal, _ = normals[i]
        src = mesh.face_colors[i] if len(mesh.face_colors)==len(mesh.triangles) else None
        color = tuple(int(src[j:j+2], 16)/255. for j in (1,3,5)) if src and len(src)==7 else (.56,.77,.84)
        tag = color if src else (-1.,-1.,-1.)
        for corner_i, idx in enumerate(tri):
            vertex_color = color
            if len(mesh.corner_colors)==len(mesh.triangles):
                corner = mesh.corner_colors[i][corner_i]
                if corner and len(corner)==7:
                    vertex_color = tuple(int(corner[j:j+2],16)/255. for j in (1,3,5))
            sx = sy = sz = 0.
            for j in adjacency[idx]:
                other, area = normals[j]
                if area > 1.e-12 and sum(normal[k]*other[k] for k in range(3)) >= cos_limit:
                    sx += other[0]*area
                    sy += other[1]*area
                    sz += other[2]*area
            magnitude = math.sqrt(sx*sx+sy*sy+sz*sz)
            smoothed = ((sx/magnitude,sy/magnitude,sz/magnitude)
                        if magnitude > 1.e-12 else normal)
            result.extend((*mesh.vertices[idx], *smoothed, *vertex_color, *tag))
    return result


class ExactNormalArithmeticTests(unittest.TestCase):
    def test_compensated_face_normal_arithmetic_matches_baseline(self):
        mesh = fixture_mesh()
        self.assertEqual(_face_normals(mesh), legacy_normals(mesh))
        # This face caused an ULP disagreement with ordinary chained addition.
        self.assertEqual(_face_normals(mesh)[1][1], 0.5471116876000829)

    def test_minimized_user_model_vertex_preserves_exact_bytes(self):
        mesh = fixture_mesh()
        expected = legacy_packed(mesh)
        actual = flatten_faces(mesh)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        # Original mismatch: global triangle 6902, corner 2, normal.y.
        self.assertEqual(actual[2*12 + 4], 0.0)

    def test_exact_colors_and_corner_interpolation(self):
        mesh = fixture_mesh(colors=True)
        self.assertEqual(flatten_faces(mesh).tobytes(), legacy_packed(mesh).tobytes())

    def test_crease_angles_preserve_baseline(self):
        mesh = fixture_mesh(colors=True)
        for angle in (1, 35, 53, 70, 110, 180):
            with self.subTest(angle=angle):
                self.assertEqual(flatten_faces(mesh, angle).tobytes(),
                                 legacy_packed(mesh, angle).tobytes())


if __name__ == '__main__':
    unittest.main()
