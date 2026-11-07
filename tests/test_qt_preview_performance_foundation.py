"""Stage 6B-A: preview performance budget, no-copy GL path, integration contracts."""
from __future__ import annotations

import ast
from array import array
import ctypes
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace

from desktop.qt_app.preview_performance import (
    BYTES_PER_DISPLAY_TRIANGLE, MIB, PreviewLoadProfile,
    preview_resource_estimate, preview_performance_snapshot,
    require_preview_budget, require_upload_budget, format_preview_performance,
)

ROOT = Path(__file__).resolve().parents[1]


class SizedOnly:
    def __init__(self, length):
        self.length = length

    def __len__(self):
        return self.length


def fake_mesh(n=2, verts=4, *, source=None):
    return SimpleNamespace(
        vertices=SizedOnly(verts), triangles=SizedOnly(n),
        source_triangles=n if source is None else source,
        face_colors=SizedOnly(n), corner_colors=SizedOnly(n),
    )


class PreviewMemoryBudgetTests(unittest.TestCase):
    def test_gpu_byte_size_matches_actual_12_float_vertex_layout(self):
        mesh = fake_mesh(7)
        estimate = preview_resource_estimate(mesh)
        self.assertEqual(BYTES_PER_DISPLAY_TRIANGLE, 144)
        self.assertEqual(estimate.render_buffer_bytes, 7 * 144)
        self.assertEqual(estimate.gpu_buffer_bytes, 7 * 144)
        self.assertGreater(estimate.estimated_peak_bytes,
                           estimate.render_buffer_bytes * 3)

    def test_existing_full_detail_triangle_ceiling_remains_in_budget(self):
        estimate = preview_resource_estimate(fake_mesh(750_000, 1_500_000))
        self.assertIs(require_preview_budget(estimate), estimate)

    def test_large_future_vertex_buffer_fails_safely(self):
        estimate = preview_resource_estimate(fake_mesh(4_000_000, 1))
        with self.assertRaisesRegex(ValueError, 'Preview vertex buffer'):
            require_preview_budget(estimate)

    def test_preflight_peak_budget_is_independent(self):
        estimate = preview_resource_estimate(fake_mesh(100_000, 40_000))
        with self.assertRaisesRegex(ValueError, 'peak memory'):
            require_preview_budget(estimate, max_estimated_peak_bytes=1)

    def test_upload_budget_guards_invalid_or_oversized_allocation(self):
        self.assertEqual(require_upload_budget(0), 0)
        self.assertEqual(require_upload_budget(144), 144)
        for bad in (-1, None, 1.25):
            with self.assertRaises(ValueError):
                require_upload_budget(bad)
        with self.assertRaises(ValueError):
            require_upload_budget(513 * MIB)

    def test_diagnostics_is_explicit_about_estimates_and_timing(self):
        mesh = fake_mesh()
        mesh.load_profile = PreviewLoadProfile(preview_resource_estimate(mesh),
                                               parse_ms=12.5, prepare_ms=43.0)
        snapshot = preview_performance_snapshot(mesh, upload_submit_ms=4.1,
                                                upload_bytes=288)
        self.assertEqual(snapshot['parse_ms'], 12.5)
        self.assertEqual(snapshot['prepare_ms'], 43.0)
        self.assertEqual(snapshot['upload_submit_ms'], 4.1)
        info = format_preview_performance(snapshot)
        self.assertIn('12.5 ms', info)
        self.assertIn('GPU upload submission', info)
        self.assertIn('not GPU completion', info)
        self.assertIn('not process RSS or VRAM', info)
        self.assertIn('Open a model', format_preview_performance(None))

    def test_fallback_preparation_when_nonworker_mesh_used(self):
        snapshot = preview_performance_snapshot(fake_mesh(), fallback_prepare_ms=5.5)
        self.assertIsNone(snapshot['parse_ms'])
        self.assertEqual(snapshot['prepare_ms'], 5.5)
        self.assertIsNone(snapshot['upload_submit_ms'])

    def test_invalid_source_count_rejected(self):
        with self.assertRaises(ValueError):
            preview_resource_estimate(fake_mesh(10, source=2))


class FakeGL:
    GL_ARRAY_BUFFER = 34962
    GL_STATIC_DRAW = 35044
    GL_FLOAT = 5126
    GL_FALSE = 0

    def __init__(self):
        self.bytes_seen = None
        self.buffer_bytes = None

    def glBindVertexArray(self, *_): pass
    def glBindBuffer(self, *_): pass
    def glEnableVertexAttribArray(self, *_): pass
    def glVertexAttribPointer(self, *_): pass

    def glBufferData(self, target, size, pointer, usage):
        self.buffer_bytes = size
        if size:
            self.bytes_seen = bytes(pointer)
        else:
            self.bytes_seen = b''


class UploadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'desktop/qt_app/gl_viewport.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(source)
        main = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                    and node.name == 'ModelViewport')
        func = next(node for node in main.body if isinstance(node, ast.FunctionDef)
                    and node.name == '_upload')
        # Isolate only the OpenGL allocation logic: no Qt/OpenGL installation
        # is needed for this deterministic mock driver test.
        module = ast.Module(body=[func], type_ignores=[])
        ast.fix_missing_locations(module)
        ns = {'ctypes': ctypes, 'perf_counter': time.perf_counter,
              'require_upload_budget': require_upload_budget}
        exec(compile(module, '<isolated _upload>', 'exec'), ns)
        cls.upload = staticmethod(ns['_upload'])
        cls.upload_source = ast.get_source_segment(source, func)

    def test_borrowed_float_buffer_does_not_allocate_tobytes_copy(self):
        self.assertNotIn('.tobytes(', self.upload_source)
        gl = FakeGL()
        floatbuf = array('f', [i / 11 for i in range(36)])
        view = SimpleNamespace(_gl=gl, _vao=1, _vbo=2, _data=floatbuf,
                               _dirty=True, _preview_upload_ms=None,
                               _preview_upload_bytes=0)
        self.upload(view)
        self.assertEqual(gl.buffer_bytes, len(floatbuf) * 4)
        self.assertEqual(gl.bytes_seen, memoryview(floatbuf).cast('B').tobytes())
        self.assertFalse(view._dirty)
        self.assertEqual(view._preview_upload_bytes, len(floatbuf) * 4)
        self.assertGreaterEqual(view._preview_upload_ms, 0)

    def test_empty_buffer_supported(self):
        gl = FakeGL()
        view = SimpleNamespace(_gl=gl, _vao=1, _vbo=2, _data=None,
                               _dirty=True, _preview_upload_ms=None,
                               _preview_upload_bytes=1234)
        self.upload(view)
        self.assertEqual(gl.buffer_bytes, 0)
        self.assertEqual(view._preview_upload_bytes, 0)

    def test_preview_worker_and_menu_are_wired(self):
        worker = (ROOT / 'desktop/qt_app/preview_worker.py').read_text(encoding='utf-8-sig')
        main = (ROOT / 'desktop/qt_app/main_window.py').read_text(encoding='utf-8-sig')
        loader = (ROOT / 'desktop/qt_app/mesh_loader.py').read_text(encoding='utf-8-sig')
        self.assertIn('require_preview_budget(preview_resource_estimate(result))', worker)
        self.assertIn('parse_start = perf_counter()', worker)
        self.assertIn('prepare_start = perf_counter()', worker)
        self.assertIn('load_profile=PreviewLoadProfile(', worker)
        self.assertIn("'Preview Performance…'", main)
        self.assertIn('self.preview_surface.preview_performance_snapshot()', main)
        self.assertIn('load_profile: object = field(', loader)


if __name__ == '__main__':
    unittest.main()
