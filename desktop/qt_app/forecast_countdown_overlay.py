"""Nonmodal six-second auto-forecast notice, anchored inside the 3D viewport.

The forecast itself is scheduled ONLY by ForecastCountdownTimer.  The overlay's
100 ms timer reads its remaining time for display; it never initiates engine work.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)


class ForecastCountdownTimer(QTimer):
    """Drop-in QTimer that announces every automatic start/restart and stop.

    Existing callers continue to use .start() and .stop(); there is no second
    engine scheduler and a new start resets the countdown atomically.
    """

    armed = Signal()
    disarmed = Signal()

    def start(self, interval_ms=None):
        if interval_ms is None:
            super().start()
        else:
            super().start(int(interval_ms))
        if self.isActive():
            self.armed.emit()

    def stop(self):
        super().stop()
        self.disarmed.emit()


class ForecastCountdownOverlay(QFrame):
    """Interactive toast in the viewport's lower-right corner."""

    cancel_requested = Signal()
    run_now_requested = Signal()

    def __init__(self, viewport):
        super().__init__(viewport)
        self.setObjectName('forecastCountdownOverlay')
        self.setAccessibleName('Automatic forecast countdown')
        self._source_timer = None
        # A heavy model may delay this widget's first visible paint.
        self._reset_on_first_paint = False
        self._display_tick = QTimer(self)
        self._display_tick.setInterval(100)
        self._display_tick.timeout.connect(self._refresh)
        self.setStyleSheet('''
            QFrame#forecastCountdownOverlay {
                background-color: rgba(18, 26, 34, 238);
                border: 1px solid #536473;
                border-radius: 10px;
            }
            QLabel#forecastCountdownTitle {
                background: transparent; border: none;
                color: #e8f2f6; font-size: 12px; font-weight: 700;
            }
            QLabel#forecastCountdownSeconds {
                background: transparent; border: none;
                color: #b9d3dd; font-size: 11px;
            }
            QProgressBar#forecastCountdownProgress {
                border: none; background-color: #354451;
                border-radius: 3px; height: 5px;
            }
            QProgressBar#forecastCountdownProgress::chunk {
                background-color: #69bbcb; border-radius: 3px;
            }
            QPushButton { min-height: 25px; padding: 3px 8px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        self.title = QLabel('◷  FORECAST STARTING SOON', self)
        self.title.setObjectName('forecastCountdownTitle')
        layout.addWidget(self.title)
        self.seconds = QLabel('Starting in 6 seconds', self)
        self.seconds.setObjectName('forecastCountdownSeconds')
        layout.addWidget(self.seconds)
        self.progress = QProgressBar(self)
        self.progress.setObjectName('forecastCountdownProgress')
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 6000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(5)
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.cancel_button = QPushButton('Cancel', self)
        self.cancel_button.setObjectName('cancelScheduledForecast')
        self.cancel_button.setToolTip('Skip this automatic forecast; Automatic Forecast stays enabled.')
        self.cancel_button.clicked.connect(lambda _checked=False: self.cancel_requested.emit())
        buttons.addWidget(self.cancel_button, 1)
        self.run_button = QPushButton('Run Now', self)
        self.run_button.setObjectName('runScheduledForecastNow')
        self.run_button.setToolTip('Run the scheduled forecast immediately.')
        self.run_button.clicked.connect(lambda _checked=False: self.run_now_requested.emit())
        buttons.addWidget(self.run_button, 1)
        layout.addLayout(buttons)
        self.setFixedSize(268, 123)
        viewport.installEventFilter(self)
        self.position_over_viewport()
        self.hide()

    def begin(self, timer):
        self._source_timer = timer
        # The cancel window begins only after the actual popup is painted.
        # The original QTimer remains the only forecast scheduler.
        self._reset_on_first_paint = True
        self._refresh()
        if timer.isActive():
            self.position_over_viewport()
            self.show()
            self.raise_()
            self._display_tick.start()
            self.update()  # Schedule first paint even on timer restarts.

    def dismiss(self):
        self._reset_on_first_paint = False
        self._display_tick.stop()
        self._source_timer = None
        self.hide()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._reset_on_first_paint:
            return
        self._reset_on_first_paint = False
        timer = self._source_timer
        if timer is not None and timer.isActive() and self.isVisible():
            # The timer was armed by MainWindow before the popup had a chance
            # to paint. Reset *that same timer* to its full interval now. Call
            # the native QTimer method so ForecastCountdownTimer.start() does
            # not emit `armed` again and create a second overlay cycle.
            QTimer.start(timer)
            self._refresh()

    def _refresh(self):
        timer = self._source_timer
        if timer is None or not timer.isActive():
            self.dismiss()
            return
        remaining = max(0, timer.remainingTime())
        total = max(1, timer.interval())
        seconds = max(1, math.ceil(remaining / 1000))
        self.seconds.setText(f'Starting in {seconds} second' + ('' if seconds == 1 else 's'))
        self.progress.setRange(0, total)
        self.progress.setValue(max(0, total - remaining))

    def position_over_viewport(self, size=None):
        viewport = self.parentWidget()
        if viewport is None:
            return
        width = size.width() if size is not None else viewport.width()
        height = size.height() if size is not None else viewport.height()
        self.setFixedWidth(max(190, min(268, width - 24)))
        self.move(max(8, width - self.width() - 16), max(8, height - self.height() - 16))
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.position_over_viewport(event.size())
        return super().eventFilter(watched, event)
