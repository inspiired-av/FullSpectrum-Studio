"""Display-only preview LOD contracts: paint seams, topology, and persistence."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import math
import tempfile
import unittest

from desktop.qt_app.preview_quality import (
    QUALITY_MODES, build_quality_preview, choose_quality, normalize_quality,
    read_quality, write_quality,
)


@dataclass(frozen=True)
class Mesh:
    vertices: tuple
    triangles: tuple
    source_triangles: int
    bounds: tuple
    face_colors: tuple = ()
    corner_colors: tuple = ()
    palette_counts: tuple = ()
    color_status: str = ''
    render_buffer: object = None
    load_profile: object = None


def make_mesh(verts, triangles, colors=None, corners=None):
    verts = tuple(tuple(map(float, v)) for v in verts)
    triangles = tuple(tuple(map(int, f)) for f in triangles)
    bounds = tuple(min(v[i] for v in verts) for i in range(3)) + tuple(
        max(v[i] for v in verts) for i in range(3))
    return Mesh(verts, triangles, len(triangles), bounds,
                tuple(colors or ()), tuple(corners or ()),
                (('#AABBCC', len(triangles)),), 'original metadata')


def sphere(subdivisions=4):
    """Closed, consistently oriented octahedral sphere without trimesh dependency."""
    verts = [(1.,0.,0.), (-1.,0.,0.), (0.,1.,0.), (0.,-1.,0.), (0.,0.,1.), (0.,0.,-1.)]
    faces = [(0,2,4),(2,1,4),(1,3,4),(3,0,4),
             (2,0,5),(1,2,5),(3,1,5),(0,3,5)]
    for _ in range(subdivisions):
        cache = {}
        def midpoint(u, v):
            key = tuple(sorted((u, v)))
            if key not in cache:
                a, b = verts[u], verts[v]
                mid = tuple((a[i] + b[i]) / 2 for i in range(3))
                norm = math.sqrt(sum(x*x for x in mid))
                cache[key] = len(verts)
                verts.append(tuple(x/norm for x in mid))
            return cache[key]
        refined = []
        for a,b,c in faces:
            ab,bc,ca = midpoint(a,b),midpoint(b,c),midpoint(c,a)
            refined.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)))
        faces = refined
    return make_mesh(verts, faces)


def edge_counts(triangles):
    return Counter(tuple(sorted((a,b))) for x,y,z in triangles
                   for a,b in ((x,y),(y,z),(z,x)))


class PreviewQualityTests(unittest.TestCase):
    def test_auto_is_full_for_ordinary_models(self):
        self.assertEqual(choose_quality('auto', 450_992), 'full')
        self.assertEqual(choose_quality('auto', 500_001), 'balanced')
        self.assertEqual(normalize_quality('nonsense'), 'auto')
        self.assertEqual(len(QUALITY_MODES), 4)

    def test_full_preserves_original_object(self):
        model = sphere(3)
        result = build_quality_preview(model, 'full')
        self.assertIs(result.mesh, model)
        self.assertEqual(result.displayed_triangles, len(model.triangles))

    def test_balanced_reduces_closed_sphere_without_opening_holes(self):
        model = sphere(4)
        original_vertices, original_faces = model.vertices, model.triangles
        reduced = build_quality_preview(model, 'balanced', max_seconds=10)
        self.assertLess(reduced.displayed_triangles, len(model.triangles))
        self.assertGreater(reduced.displayed_triangles, len(model.triangles) * .45)
        self.assertEqual(reduced.mesh.source_triangles, model.source_triangles)
        self.assertEqual(reduced.mesh.bounds, model.bounds)
        self.assertEqual(reduced.mesh.palette_counts, model.palette_counts)
        self.assertEqual(reduced.mesh.color_status, model.color_status)
        self.assertEqual(model.vertices, original_vertices)
        self.assertEqual(model.triangles, original_faces)
        self.assertEqual(set(edge_counts(reduced.mesh.triangles).values()), {2})
        self.assertEqual(len(reduced.mesh.vertices) - len(edge_counts(reduced.mesh.triangles)) +
                         len(reduced.mesh.triangles), 2)

    def test_performance_reduces_more_than_balanced(self):
        model = sphere(4)
        balanced = build_quality_preview(model, 'balanced', max_seconds=10)
        performance = build_quality_preview(model, 'performance', max_seconds=10)
        self.assertLess(performance.displayed_triangles, balanced.displayed_triangles)
        self.assertEqual(set(edge_counts(performance.mesh.triangles).values()), {2})

    def test_uniform_color_patches_are_preserved(self):
        model = sphere(4)
        c = ('#AABBCC',) * len(model.triangles)
        gradients = (('#AABBCC',) * 3,) * len(model.triangles)
        colored = make_mesh(model.vertices, model.triangles, c, gradients)
        reduced = build_quality_preview(colored, 'balanced', max_seconds=10)
        self.assertLess(reduced.displayed_triangles, len(colored.triangles))
        self.assertEqual(reduced.mesh.face_colors,
                         ('#AABBCC',) * reduced.displayed_triangles)
        self.assertEqual(reduced.mesh.corner_colors,
                         (('#AABBCC',)*3,) * reduced.displayed_triangles)
        self.assertEqual(reduced.mesh.palette_counts, colored.palette_counts)

    def test_every_face_different_color_does_not_collapse(self):
        model = sphere(4)
        c = tuple(f'#{idx:06X}' for idx in range(len(model.triangles)))
        colored = make_mesh(model.vertices, model.triangles, c,
                            tuple((color,)*3 for color in c))
        reduced = build_quality_preview(colored, 'performance')
        self.assertIs(reduced.mesh, colored)

    def test_interpolated_corner_colors_remain_protected(self):
        model = sphere(3)
        gradients = (('#FF0000','#00FF00','#0000FF'),) * len(model.triangles)
        colored = make_mesh(model.vertices, model.triangles,
                            ('#555555',) * len(model.triangles), gradients)
        reduced = build_quality_preview(colored, 'performance')
        self.assertIs(reduced.mesh, colored)

    def test_open_boundary_is_preserved(self):
        width = 20
        vertices = [(float(x),float(y),0.) for y in range(width+1) for x in range(width+1)]
        faces=[]
        for y in range(width):
            for x in range(width):
                a=y*(width+1)+x
                faces.extend(((a,a+1,a+width+1),(a+1,a+width+2,a+width+1)))
        mesh=make_mesh(vertices, faces)
        before={tuple(sorted((a,b))) for (a,b),count in edge_counts(mesh.triangles).items() if count==1}
        reduced=build_quality_preview(mesh,'performance',max_seconds=10)
        after_edges=edge_counts(reduced.mesh.triangles)
        after={tuple(sorted((reduced.mesh.vertices[a],reduced.mesh.vertices[b])))
               for (a,b),count in after_edges.items() if count==1}
        original={tuple(sorted((mesh.vertices[a],mesh.vertices[b]))) for a,b in before}
        self.assertEqual(after, original)
        self.assertTrue(all(count in (1,2) for count in after_edges.values()))

    def test_repeatable_simplification(self):
        mesh = sphere(3)
        a = build_quality_preview(mesh, 'performance')
        b = build_quality_preview(mesh, 'performance')
        self.assertEqual(a.mesh.vertices, b.mesh.vertices)
        self.assertEqual(a.mesh.triangles, b.mesh.triangles)

    def test_quality_preference_roundtrip_and_invalid_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'settings'/'preview-quality.json'
            self.assertEqual(read_quality(path), 'auto')
            write_quality(path, 'performance')
            self.assertEqual(read_quality(path), 'performance')
            path.write_text('{invalid', encoding='utf-8')
            self.assertEqual(read_quality(path), 'auto')

    def test_integration_contract_does_not_touch_export_pipeline(self):
        root = Path(__file__).resolve().parents[1]
        worker=(root/'desktop/qt_app/preview_worker.py').read_text(encoding='utf-8-sig')
        main=(root/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        self.assertIn('build_quality_preview(', worker)
        self.assertIn('cancelled=self.isInterruptionRequested', worker)
        self.assertIn('resources = require_preview_budget(preview_resource_estimate(result))', worker)
        self.assertIn('render_buffer = flatten_faces(result)', worker)
        self.assertIn('quality="full"', worker)
        self.assertIn('self.preview_quality_menu = view.addMenu("Preview Quality")', main)
        self.assertIn('self._original_mesh = mesh', main)
        self.assertIn('preserve_camera=True', main)

if __name__=='__main__':
    unittest.main()
