"""Mouse-transparent viewport badge for perspective-grid cell dimensions.

Numeric X/Y rulers are rendered separately by WorldGridRulerRenderer using the
OpenGL depth buffer. This QWidget deliberately paints **no** coordinate labels.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from desktop.qt_app.preview_grid_measurements import (
    choose_badge_rect, grid_spacing_label,
)


class PerspectiveGridMeasurementOverlay(QWidget):
    """Passive grid-cell badge; forecast and other overlays take priority."""

    BLOCKING_WIDGET_NAMES = (
        'forecastCountdownOverlay', 'previewEstimatedAccuracy',
        'previewDropFeedback', 'previewAxisIndicator',
        'colorLossLegend', 'anchorInfluenceLegend',
    )

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.setObjectName('perspectiveGridMeasurementOverlay')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._step = None
        self._enabled = True
        self._watched_obstacles = set()
        self.setGeometry(viewport.rect())
        viewport.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event):
        viewport = getattr(self, 'viewport', None)
        if viewport is None:
            return False
        if watched is viewport and event.type() == QEvent.Type.Resize:
            self.setGeometry(viewport.rect())
        if watched in getattr(self, '_watched_obstacles', ()) and event.type() in (
                QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Move,
                QEvent.Type.Resize):
            self.update()
        return super().eventFilter(watched, event)

    def set_enabled(self, value):
        self._enabled = bool(value)
        if not self._enabled:
            self.clear_scene()

    def clear_scene(self):
        self._step = None
        self.hide()

    def set_scene(self, matrix, step, limits, floor_z):
        """Retain the existing viewport API; only the actual grid step is needed."""
        if not self._enabled or step is None or limits is None:
            self.clear_scene()
            return
        try:
            step = float(step)
            finite = (step, float(floor_z), *(float(v) for v in limits))
            if len(finite) != 6 or step <= 0 or not all(map(math.isfinite, finite)):
                self.clear_scene()
                return
        except (ValueError, TypeError, OverflowError):
            self.clear_scene()
            return
        self._step = step
        if not self.isVisible():
            self.show()
        self.update()

    def _occupied_rects(self):
        viewport = getattr(self, 'viewport', None)
        if viewport is None:
            return []
        blocked = []
        for name in self.BLOCKING_WIDGET_NAMES:
            item = viewport.findChild(QWidget, name)
            if item is None or item is self:
                continue
            if item not in self._watched_obstacles:
                item.installEventFilter(self)
                self._watched_obstacles.add(item)
            if item.isVisible():
                rect = item.geometry()
                blocked.append((rect.x(), rect.y(), rect.width(), rect.height()))
        return blocked

    def paintEvent(self, event):
        if not self._enabled or self._step is None:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setFont(QFont('Arial', 10, QFont.Weight.Medium))
            text = grid_spacing_label(self._step)
            metrics = painter.fontMetrics()
            w = metrics.horizontalAdvance(text) + 24
            h = metrics.height() + 12
            rect = choose_badge_rect(self.width(), self.height(), w, h,
                                     self._occupied_rects())
            if rect is not None:
                x, y, rw, rh = rect
                painter.setPen(QColor('#476272'))
                painter.setBrush(QColor(23, 36, 45, 230))
                painter.drawRoundedRect(QRectF(x, y, rw, rh), 6, 6)
                painter.setPen(QColor('#c0dbe6'))
                painter.drawText(QRectF(x+8, y+2, rw-16, rh-4),
                                 Qt.AlignmentFlag.AlignCenter, text)
        finally:
            painter.end()
