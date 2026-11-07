"""Thread isolation for Stage 3A read-only model parsing."""
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.mesh_loader import load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces
from dataclasses import replace
from time import perf_counter
from desktop.qt_app.preview_quality import build_quality_preview, normalize_quality
from desktop.qt_app.preview_performance import (
    PreviewLoadProfile, preview_resource_estimate, require_preview_budget)


class ModelLoadWorker(QThread):
    completed = Signal(object, object, str)

    def __init__(self, path, parent=None, *, quality="full", source_mesh=None):
        super().__init__(parent)
        self.path = str(path)
        self.quality = normalize_quality(quality)
        self.source_mesh = source_mesh  # immutable parsed source, shared read-only

    def run(self):
        try:
            parse_start = perf_counter()
            if self.source_mesh is None:
                result = load_preview_mesh(self.path)
                self.source_mesh = result
                parse_ms = (perf_counter() - parse_start) * 1000.0
            else:
                result = self.source_mesh  # quality switch: no archive reparsing
                parse_ms = 0.0
            if self.isInterruptionRequested():
                return
            # Check predicted allocation size *before* expanding triangles.
            resources = require_preview_budget(preview_resource_estimate(result))
            quality = build_quality_preview(
                result, self.quality, cancelled=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                return
            result = quality.mesh
            resources = require_preview_budget(preview_resource_estimate(result))
            # CPU normal smoothing/vertex expansion is expensive on large models;
            # never run it in QOpenGLWidget.set_mesh() on the GUI thread.
            prepare_start = perf_counter()
            render_buffer = flatten_faces(result)
            if self.isInterruptionRequested():
                return
            prepare_ms = (perf_counter() - prepare_start) * 1000.0
            if len(render_buffer) * render_buffer.itemsize != resources.render_buffer_bytes:
                raise ValueError("Prepared vertex buffer size disagrees with preview budget")
            # Experimental indexing runs in this QThread, not in QOpenGLWidget.
            from desktop.qt_app.preview_indexed_mode import prepare_indexed_preview
            indexed_candidate = prepare_indexed_preview(
                render_buffer, cancelled=getattr(self, "isInterruptionRequested", None))
            if getattr(self, "isInterruptionRequested", lambda: False)():
                return
            result = replace(result, render_buffer=render_buffer,
                render_indexed=indexed_candidate,
                load_profile=PreviewLoadProfile(
                    resources, parse_ms, prepare_ms,
                    quality_ms=quality.duration_ms, quality_mode=quality.requested,
                    quality_effective=quality.effective,
                    quality_source_triangles=quality.original_triangles,
                    quality_reason=quality.reason))
            self.completed.emit(result, None, self.path)
        except Exception as exc:
            self.completed.emit(None, str(exc), self.path)
