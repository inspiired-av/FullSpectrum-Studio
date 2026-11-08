"""Experimental multicolor LOD contracts; no Qt or OpenGL needed."""
from __future__ import annotations
from collections import Counter
from unittest import TestCase, mock
import os

from desktop.qt_app.preview_multicolor_lod import (
    build_cluster_lod, build_adaptive_multicolor_lod,
)
from desktop.qt_app.preview_quality import build_quality_preview
from test_qt_preview_quality import sphere, make_mesh, edge_counts


def painted_sphere():
    src=sphere(5)
    colors=tuple('#4422AA' if idx%3 else '#4466BB' for idx in range(len(src.triangles)))
    return make_mesh(src.vertices,src.triangles,colors,tuple((c,)*3 for c in colors))


class MulticolorLODTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh=painted_sphere()

    def test_balanced_removes_faces_preserving_source_palette(self):
        mesh=self.mesh
        original=(mesh.vertices,mesh.triangles,mesh.face_colors,
                  mesh.corner_colors,mesh.palette_counts)
        r=build_adaptive_multicolor_lod(mesh,'balanced',max_seconds=8)
        self.assertLess(r.draw_faces,len(mesh.triangles))
        self.assertGreater(r.draw_faces,0)
        self.assertIsNot(r.mesh,mesh)
        self.assertEqual(set(r.mesh.face_colors),set(mesh.face_colors))
        self.assertEqual(r.mesh.source_triangles,mesh.source_triangles)
        self.assertEqual(r.mesh.palette_counts,mesh.palette_counts)
        self.assertEqual((mesh.vertices,mesh.triangles,mesh.face_colors,
                          mesh.corner_colors,mesh.palette_counts),original)
        self.assertTrue(all(value==2 for value in edge_counts(r.mesh.triangles).values()))
        self.assertLess(r.worst_color_area_error,.075)

    def test_performance_simplifies_more(self):
        balanced=build_adaptive_multicolor_lod(self.mesh,'balanced',max_seconds=8)
        faster=build_adaptive_multicolor_lod(self.mesh,'performance',max_seconds=8)
        self.assertLess(faster.draw_faces,balanced.draw_faces)
        self.assertEqual(set(edge_counts(faster.mesh.triangles).values()),{2})

    def test_every_surviving_color_is_original_per_face(self):
        r=build_cluster_lod(self.mesh,'balanced',cells=30,max_seconds=8)
        self.assertLess(r.draw_faces,len(self.mesh.triangles))
        self.assertEqual(len(r.mesh.corner_colors),r.draw_faces)
        for face_color, triple in zip(r.mesh.face_colors,r.mesh.corner_colors):
            self.assertEqual(triple,(face_color,)*3)
        self.assertEqual(Counter(r.mesh.face_colors).keys(),Counter(self.mesh.face_colors).keys())

    def test_interpolated_gradients_are_not_collapsed(self):
        source=sphere(4)
        grad=(('#FF0000','#00FF00','#0000FF'),)*len(source.triangles)
        m=make_mesh(source.vertices,source.triangles,
                    ('#888888',)*len(source.triangles),grad)
        r=build_adaptive_multicolor_lod(m,'performance',max_seconds=8)
        self.assertIs(r.mesh,m)

    def test_non_manifold_source_is_rejected(self):
        src=self.mesh
        # Add the first face a second time: every edge would become non-manifold.
        faces=src.triangles+(src.triangles[0],)
        colors=src.face_colors+(src.face_colors[0],)
        corners=src.corner_colors+(src.corner_colors[0],)
        m=make_mesh(src.vertices,faces,colors,corners)
        r=build_cluster_lod(m,'performance',cells=25,max_seconds=8)
        self.assertIs(r.mesh,m)
        self.assertIn('Non-manifold',r.reason)

    def test_cancellation_keeps_source_intact(self):
        r=build_adaptive_multicolor_lod(self.mesh,'balanced',
                                        cancelled=lambda: True)
        self.assertIs(r.mesh,self.mesh)

    def test_missing_face_colors_uses_full_detail(self):
        src=sphere(4)
        r=build_adaptive_multicolor_lod(src,'performance',max_seconds=8)
        self.assertIs(r.mesh,src)

    def test_opt_in_preserves_default_renderer_and_auto_quality(self):
        with mock.patch.dict(os.environ, {'FULLSPECTRUM_MULTICOLOR_LOD':'connected'}):
            result=build_quality_preview(self.mesh,'performance',max_seconds=8)
            self.assertLess(result.displayed_triangles,len(self.mesh.triangles))
            self.assertIn('Experimental multicolor LOD',result.reason)
            full=build_quality_preview(self.mesh,'full')
            self.assertIs(full.mesh,self.mesh)
        with mock.patch.dict(os.environ, {'FULLSPECTRUM_MULTICOLOR_LOD':''}):
            baseline=build_quality_preview(self.mesh,'full')
            self.assertIs(baseline.mesh,self.mesh)

    def test_repeatability(self):
        x=build_cluster_lod(self.mesh,'balanced',cells=30,max_seconds=8)
        y=build_cluster_lod(self.mesh,'balanced',cells=30,max_seconds=8)
        self.assertEqual(x.mesh.triangles,y.mesh.triangles)
        self.assertEqual(x.mesh.face_colors,y.mesh.face_colors)
        self.assertEqual(x.mesh.vertices,y.mesh.vertices)
