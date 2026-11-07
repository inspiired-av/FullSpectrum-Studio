"""Non-interactive XYZ orientation legend inside the Qt model viewport."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

from desktop.qt_app.preview_axis_layout import axis_marker_position


class ViewAxisIndicator(QWidget):
    """Camera-relative axis triad; no OpenGL and no change to model coordinates."""

    OBSTACLES = (
        'colorLossLegend', 'anchorInfluenceLegend',
        'forecastCountdownOverlay', 'previewEstimatedAccuracy',
        'previewDropFeedback',
    )

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self._watched_obstacles = set()
        self.setObjectName('previewAxisIndicator')
        self.setFixedSize(104, 104)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        viewport.installEventFilter(self)
        self._position()
        self.hide()
        # The main window calls refresh_obstacles() after constructing its
        # viewport legends and forecast popup; there are no delayed callbacks.

    def refresh_obstacles(self):
        viewport = getattr(self, 'viewport', None)
        if viewport is None:
            return
        for name in self.OBSTACLES:
            item = viewport.findChild(QWidget, name)
            if item is not None and item not in self._watched_obstacles:
                item.installEventFilter(self)
                self._watched_obstacles.add(item)
        self._position()

    def _position(self, changing=None):
        viewport = getattr(self, 'viewport', None)
        if viewport is None:
            return
        occupied = []
        for widget in tuple(self._watched_obstacles):
            try:
                visible = (changing[1] if changing is not None and widget is changing[0]
                           else widget.isVisible())
                if visible:
                    rect = widget.geometry()
                    occupied.append((rect.x(), rect.y(), rect.width(), rect.height()))
            except RuntimeError:
                # A Qt C++ child may be deleted during window teardown.
                self._watched_obstacles.discard(widget)
        pos = axis_marker_position(viewport.width(), viewport.height(),
                                   self.width(), self.height(), occupied)
        if pos is None:
            # A small viewport may have no unobstructed corner. Keep the
            # marker disabled until space returns rather than cover controls.
            self.hide()
        else:
            self.move(*pos)
            if viewport.mesh is not None and getattr(viewport, '_grid_show_axes', True):
                self.show()

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Type.Resize:
            self.refresh_obstacles()
        elif watched in self._watched_obstacles and event.type() in (
                QEvent.Type.Show, QEvent.Type.Hide,
                QEvent.Type.Move, QEvent.Type.Resize):
            # The Show/Hide event can arrive before isVisible() changes.
            kind = event.type()
            forced = ((watched, kind == QEvent.Type.Show)
                      if kind in (QEvent.Type.Show, QEvent.Type.Hide) else None)
            self._position(forced)
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        if self.viewport.mesh is None:
            return
        yaw = float(self.viewport.yaw)
        pitch = float(self.viewport.pitch)
        sy, cy = math.sin(yaw), math.cos(yaw)
        sp, cp = math.sin(pitch), math.cos(pitch)
        right = (-sy, cy, 0.0)
        up = (-sp * cy, -sp * sy, cp)
        toward_camera = (cp * cy, cp * sy, sp)
        center = QPointF(50.0, 53.0)
        colors = {'X': '#ee6468', 'Y': '#6bd484', 'Z': '#6d9df5'}
        axes = {'X': (1., 0., 0.), 'Y': (0., 1., 0.), 'Z': (0., 0., 1.)}
        items = []
        for name, axis in axes.items():
            dx = sum(axis[i] * right[i] for i in range(3))
            dy = sum(axis[i] * up[i] for i in range(3))
            depth = sum(axis[i] * toward_camera[i] for i in range(3))
            tip = QPointF(center.x() + dx * 32.0, center.y() - dy * 32.0)
            items.append((depth, name, tip))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(16, 24, 31, 205))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 10, 10)
        painter.setFont(QFont('Arial', 9, QFont.Weight.Bold))
        # Far axes first: near-facing axes remain readable when projections overlap.
        for _depth, name, tip in sorted(items):
            color = QColor(colors[name])
            painter.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(center, tip)
            painter.setPen(QPen(QColor(17, 25, 32), 1.0))
            painter.setBrush(color)
            painter.drawEllipse(tip, 10, 10)
            painter.setPen(QColor(17, 24, 31))
            painter.drawText(int(tip.x()-8), int(tip.y()-8), 16, 16,
                             Qt.AlignmentFlag.AlignCenter, name)
        painter.setBrush(QColor('#c6d2dc'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, 3.0, 3.0)
        painter.end()
