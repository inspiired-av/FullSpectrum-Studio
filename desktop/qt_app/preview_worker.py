"""Thread isolation for Stage 3A read-only model parsing."""
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.mesh_loader import load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces
from dataclasses import replace


class ModelLoadWorker(QThread):
    completed = Signal(object, object, str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = str(path)

    def run(self):
        try:
            result = load_preview_mesh(self.path)
            # CPU normal smoothing/vertex expansion is expensive on large models;
            # never run it in QOpenGLWidget.set_mesh() on the GUI thread.
            result = replace(result, render_buffer=flatten_faces(result))
            self.completed.emit(result, None, self.path)
        except Exception as exc:
            self.completed.emit(None, str(exc), self.path)
