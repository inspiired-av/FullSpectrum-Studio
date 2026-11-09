"""Small-memory OBJ size probe, run before full mesh/GL preparation."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from desktop.qt_app.model_size_preflight import scan_obj_bounds


class ModelSizePreflightWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = str(source)

    def run(self):
        try:
            bounds = scan_obj_bounds(self.source, cancelled=self.isInterruptionRequested)
            if not self.isInterruptionRequested():
                self.completed.emit(bounds, None)
        except InterruptedError:
            pass
        except (OSError, ValueError, OverflowError) as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))
