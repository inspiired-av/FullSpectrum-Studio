"""Regression checks for the optimized preview-only normal and color packer.

The test oracle intentionally retains the legacy per-corner crease rule to
catch seam/normal regressions.  No Qt or OpenGL context is needed.
"""
from __future__ import annotations

from array import array
from collections import defaultdict
import math
import random
import unittest
from types import SimpleNamespace

from desktop.qt_app.preview_shading import _face_normals, flatten_faces


def _reference_flatten(mesh, crease_angle=53):
    """Original full per-corner computation (independent oracle)."""
    vertices, faces = mesh.vertices, mesh.triangles
    normals = []
    for a, b, c in faces:
        p, q, r = vertices[a], vertices[b], vertices[c]
        u = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
        w = (r[0] - p[0], r[1] - p[1], r[2] - p[2])
        n = (u[1] * w[2] - u[2] * w[1],
             u[2] * w[0] - u[0] * w[2],
             u[0] * w[1] - u[1] * w[0])
        area = math.sqrt(sum(x * x for x in n))
        normals.append((tuple(x / area for x in n) if area > 1.e-12
                        else (0., 0., 1.), area))
    adjacency = defaultdict(list)
    for i, tri in enumerate(faces):
        for vertex in set(tri):
            adjacency[vertex].append(i)
    cosine = math.cos(math.radians(crease_angle))
    palette = getattr(mesh, 'face_colors', ())
    corners = getattr(mesh, 'corner_colors', ())
    use_corners = len(corners) == len(faces)
    result = array('f')
    for i, tri in enumerate(faces):
        normal, _ = normals[i]
        src = palette[i] if len(palette) == len(faces) else None
        color = tuple(int(src[j:j + 2], 16) / 255. for j in (1, 3, 5)) if src and len(src) == 7 else (.56, .77, .84)
        tag = color if src else (-1., -1., -1.)
        for corner_idx, idx in enumerate(tri):
            vertex_color = color
            if use_corners:
                corner = corners[i][corner_idx]
                if corner and len(corner) == 7:
                    vertex_color = tuple(int(corner[j:j + 2], 16) / 255. for j in (1, 3, 5))
            sx = sy = sz = 0.
            for j in adjacency[idx]:
                other, area = normals[j]
                if area > 1.e-12 and sum(normal[k] * other[k] for k in range(3)) >= cosine:
                    sx += other[0] * area
                    sy += other[1] * area
                    sz += other[2] * area
            magnitude = math.sqrt(sx * sx + sy * sy + sz * sz)
            smoothed = (sx / magnitude, sy / magnitude, sz / magnitude) if magnitude > 1.e-12 else normal
            result.extend((*vertices[idx], *smoothed, *vertex_color, *tag))
    return result


def mesh(vertices, faces, palette=(), corners=()):
    return SimpleNamespace(vertices=tuple(vertices), triangles=tuple(faces),
                           face_colors=tuple(palette), corner_colors=tuple(corners))


class GeometryPackingTests(unittest.TestCase):
    def assertMatchesOriginal(self, source, angles=(0, 25, 53, 90, 179)):
        original = (source.vertices, source.triangles,
                    source.face_colors, source.corner_colors)
        for angle in angles:
            with self.subTest(angle=angle):
                expected = _reference_flatten(source, angle)
                actual = flatten_faces(source, angle)
                self.assertIsInstance(actual, array)
                self.assertEqual(actual.typecode, 'f')
                self.assertEqual(actual.tobytes(), expected.tobytes())
                self.assertEqual(len(actual), len(source.triangles) * 36)
        self.assertEqual(original, (source.vertices, source.triangles,
                                    source.face_colors, source.corner_colors))

    def test_planar_shared_vertex_grid(self):
        vertices = [(float(x), float(y), 0.) for y in range(7) for x in range(7)]
        tris = []
        for y in range(6):
            for x in range(6):
                a = y * 7 + x
                tris.extend(((a, a + 1, a + 8), (a, a + 8, a + 7)))
        self.assertMatchesOriginal(mesh(vertices, tris))

    def test_curved_surface_shared_vertices(self):
        vertices = [(float(x), float(y), 3 * math.sin(x / 5) * math.cos(y / 5))
                    for y in range(7) for x in range(7)]
        tris = []
        for y in range(6):
            for x in range(6):
                a = y * 7 + x
                tris.extend(((a, a + 1, a + 8), (a, a + 8, a + 7)))
        self.assertMatchesOriginal(mesh(vertices, tris))

    def test_right_angle_crease_and_nonmanifold_fan(self):
        vertices = ((0, 0, 0), (1, 0, 0), (0, 1, 0),
                    (0, 0, 1), (0, -1, 0), (-1, 0, 0))
        tris = ((0, 1, 2), (0, 1, 3), (0, 3, 4), (0, 5, 2))
        self.assertMatchesOriginal(mesh(vertices, tris))

    def test_degenerate_and_duplicate_corner_indices(self):
        vertices = ((0, 0, 0), (1, 0, 0), (0, 1, 0), (3, 3, 3))
        tris = ((0, 1, 2), (0, 0, 0), (0, 1, 1), (0, 3, 3))
        self.assertMatchesOriginal(mesh(vertices, tris))

    def test_disconnected_faces_and_unused_vertices(self):
        vertices = ((0, 0, 0), (1, 0, 0), (0, 1, 0),
                    (0, 0, 1), (1, 0, 1), (0, 1, 1), (4, 5, 6))
        tris = ((0, 1, 2), (3, 4, 5))
        self.assertMatchesOriginal(mesh(vertices, tris))

    def test_per_face_source_and_mixed_corner_colors(self):
        vertices = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))
        tris = ((0, 1, 2), (0, 2, 3))
        self.assertMatchesOriginal(mesh(vertices, tris,
            ('#FF0000', '#00FF00'),
            (('#00FF00', '#0000FF', '#FFFFFF'), (None, '#112233', '#FF00FF'))))

    def test_palette_missing_corner_colors_and_invalid_length(self):
        vertices = ((0, 0, 0), (1, 0, 0), (0, 1, 0))
        tris = ((0, 1, 2),)
        for source in (mesh(vertices, tris), mesh(vertices, tris, ('#ABCD12',)),
                       mesh(vertices, tris, ('#00FF00', '#000000')),
                       mesh(vertices, tris, ('#ABCDEF00',))):
            self.assertMatchesOriginal(source, (53,))

    def test_seeded_random_topology_and_colors(self):
        rng = random.Random(20261106)
        for iteration in range(20):
            count = 16 + iteration
            vertices = [(rng.uniform(-2, 2), rng.uniform(-2, 2),
                         rng.uniform(-2, 2)) for _ in range(count)]
            faces = [tuple(rng.randrange(count) for _ in range(3))
                     for _ in range(25 + iteration)]
            palette = [rng.choice((None, '#AB00FF', '#00FF00', '#222222'))
                       for _ in faces]
            corners = [tuple(rng.choice((None, '#FFAA00', '#33FF44'))
                             for _ in range(3)) for _ in faces]
            self.assertMatchesOriginal(mesh(vertices, faces, palette, corners), (15, 53, 90))

    def test_length_of_face_normals_and_empty_mesh(self):
        source = mesh((), ())
        self.assertEqual(_face_normals(source), [])
        self.assertEqual(flatten_faces(source), array('f'))


if __name__ == '__main__':
    unittest.main()
