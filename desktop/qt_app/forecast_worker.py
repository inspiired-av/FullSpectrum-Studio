"""Stage 4A: Qt background task for FullSpectrum read-only engine operations."""
from PySide6.QtCore import QThread, Signal
from desktop.qt_app.forecast_service import inspect_model, run_plan


class ForecastWorker(QThread):
    completed = Signal(object, object)
    progress_changed = Signal(float, str)

    def __init__(self, kind, argument, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.argument = argument

    def run(self):
        try:
            if self.kind == 'inspection':
                result = inspect_model(self.argument)
            else:
                def report(fraction, message):
                    if self.isInterruptionRequested():
                        raise InterruptedError('Forecast cancelled.')
                    self.progress_changed.emit(float(fraction), str(message))
                result = run_plan(self.argument, progress=report)
            self.completed.emit(result, None)
        except Exception as exc:
            self.completed.emit(None, str(exc) or type(exc).__name__)
