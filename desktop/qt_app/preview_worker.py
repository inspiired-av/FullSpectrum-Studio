"""Thread isolation for Stage 3A read-only model parsing."""
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.mesh_loader import load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces
from dataclasses import replace
from time import perf_counter
from desktop.qt_app.preview_performance import (
    PreviewLoadProfile, preview_resource_estimate, require_preview_budget)


class ModelLoadWorker(QThread):
    completed = Signal(object, object, str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = str(path)

    def run(self):
        try:
            parse_start = perf_counter()
            result = load_preview_mesh(self.path)
            parse_ms = (perf_counter() - parse_start) * 1000.0
            # Check predicted allocation size *before* expanding triangles.
            resources = require_preview_budget(preview_resource_estimate(result))
            # CPU normal smoothing/vertex expansion is expensive on large models;
            # never run it in QOpenGLWidget.set_mesh() on the GUI thread.
            prepare_start = perf_counter()
            render_buffer = flatten_faces(result)
            prepare_ms = (perf_counter() - prepare_start) * 1000.0
            if len(render_buffer) * render_buffer.itemsize != resources.render_buffer_bytes:
                raise ValueError("Prepared vertex buffer size disagrees with preview budget")
            result = replace(result, render_buffer=render_buffer,
                load_profile=PreviewLoadProfile(resources, parse_ms, prepare_ms))
            self.completed.emit(result, None, self.path)
        except Exception as exc:
            self.completed.emit(None, str(exc), self.path)
