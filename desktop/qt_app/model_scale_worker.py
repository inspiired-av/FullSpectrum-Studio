"""Off-GUI-thread generation of a temporary uniformly scaled OBJ."""
from __future__ import annotations
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.model_intended_dimensions import write_scaled_obj


class ModelScaleWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, original, destination, factor, parent=None):
        super().__init__(parent)
        self.original = str(original)
        self.destination = str(destination)
        self.factor = float(factor)

    def run(self):
        try:
            output = write_scaled_obj(self.original, self.destination, self.factor,
                                      cancelled=self.isInterruptionRequested)
            self.completed.emit(output, None)
        except Exception as exc:
            self.completed.emit(None, str(exc))
