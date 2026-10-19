"""Single-purpose Qt worker for Stage 4D-C native export."""
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.export_service import run_export


class ExportWorker(QThread):
    progress_changed = Signal(float, str)
    completed = Signal(object, object)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request

    def run(self):
        try:
            def report(fraction, message):
                if self.isInterruptionRequested():
                    raise InterruptedError('Export cancelled before publishing output.')
                self.progress_changed.emit(float(fraction), str(message))
            result = run_export(self.request, progress=report)
            self.completed.emit(result, None)
        except InterruptedError as exc:
            self.completed.emit(None, exc)
        except Exception as exc:
            self.completed.emit(None, exc)
