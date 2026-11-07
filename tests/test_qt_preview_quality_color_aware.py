"""Color-aware preview LOD and responsive switching regression contracts."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import unittest
from test_qt_preview_quality import sphere, make_mesh, edge_counts
from desktop.qt_app.preview_quality import build_quality_preview

ROOT = Path(__file__).resolve().parents[1]


class ColorAwarePreviewTests(unittest.TestCase):
    def test_smooth_multicolor_model_can_reduce_without_modifying_source(self):
        src = sphere(4)
        colors = tuple('#4488AA' if sum(src.vertices[v][2] for v in face) >= 0
                       else '#488CAC' for face in src.triangles)
        mesh = make_mesh(src.vertices, src.triangles, colors,
                         tuple((c, c, c) for c in colors))
        before = (mesh.vertices, mesh.triangles, mesh.face_colors,
                  mesh.corner_colors, mesh.palette_counts)
        result = build_quality_preview(mesh, 'performance', max_seconds=10)
        self.assertLess(result.displayed_triangles, len(mesh.triangles))
        self.assertGreater(result.displayed_triangles, 0)
        self.assertEqual(result.mesh.source_triangles, mesh.source_triangles)
        self.assertTrue(set(result.mesh.face_colors) <= set(mesh.face_colors))
        self.assertEqual(set(edge_counts(result.mesh.triangles).values()), {2})
        self.assertEqual((mesh.vertices, mesh.triangles, mesh.face_colors,
                          mesh.corner_colors, mesh.palette_counts), before)

    def test_high_contrast_color_seams_do_not_move(self):
        src = sphere(4)
        colors = tuple('#FF0000' if sum(src.vertices[v][2] for v in face) >= 0
                       else '#0000FF' for face in src.triangles)
        mesh = make_mesh(src.vertices, src.triangles, colors,
                         tuple((c, c, c) for c in colors))
        seam = set()
        first = {}
        for face, color in zip(mesh.triangles, mesh.face_colors):
            for vertex in face:
                if vertex in first and first[vertex] != color:
                    seam.add(vertex)
                else:
                    first[vertex] = color
        result = build_quality_preview(mesh, 'performance', max_seconds=10)
        self.assertTrue(set(mesh.vertices[v] for v in seam).issubset(
                        set(result.mesh.vertices)))
        self.assertEqual(set(edge_counts(result.mesh.triangles).values()), {2})

    def test_real_gradients_stay_protected(self):
        src = sphere(3)
        faces = ('#808080',) * len(src.triangles)
        corner = (('#FF0000', '#00FF00', '#0000FF'),) * len(src.triangles)
        mesh = make_mesh(src.vertices, src.triangles, faces, corner)
        result = build_quality_preview(mesh, 'performance')
        self.assertIs(result.mesh, mesh)

    def test_cancellation_returns_source_object(self):
        mesh = sphere(3)
        cancelled = build_quality_preview(mesh, 'balanced', cancelled=lambda: True)
        self.assertIs(cancelled.mesh, mesh)
        self.assertIn('Cancelled', cancelled.reason)

    def test_original_preview_pipeline_not_touched_by_export(self):
        module = (ROOT/'desktop/qt_app/preview_worker.py').read_text(encoding='utf-8-sig')
        self.assertIn('source_mesh=None', module)
        self.assertIn('self.source_mesh = result', module)
        self.assertIn('cancelled=self.isInterruptionRequested', module)
        self.assertIn('render_buffer = flatten_faces(result)', module)
        self.assertIn('self.completed.emit(result, None, self.path)', module)

    def test_quality_switch_is_single_flight_with_visible_busy_state(self):
        module = (ROOT/'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(module)
        main = next(c for c in tree.body if isinstance(c, ast.ClassDef)
                    and c.name == 'MainWindow')
        methods = {m.name for m in main.body if isinstance(m, ast.FunctionDef)}
        self.assertTrue({'_start_preview_quality_if_idle', '_preview_quality_finished',
                         '_set_preview_quality_busy'} <= methods)
        self.assertIn('self._preview_quality_task.requestInterruption()', module)
        self.assertIn('source_mesh=self._preview_quality_source_mesh', module)
        self.assertIn('self.preview_quality_activity_bar.setRange(0, 0)', module)
        self.assertIn("self._preview_quality_cache.clear()", module)


if __name__ == '__main__':
    unittest.main()
