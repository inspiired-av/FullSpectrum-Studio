"""Non-interactive XYZ orientation legend inside the Qt model viewport."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget


class ViewAxisIndicator(QWidget):
    """Camera-relative axis triad; no OpenGL and no change to model coordinates."""

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.setObjectName('previewAxisIndicator')
        self.setFixedSize(104, 104)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        viewport.installEventFilter(self)
        self._position()
        self.hide()

    def _position(self):
        self.move(9, max(0, self.viewport.height() - self.height() - 9))

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Type.Resize:
            self._position()
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
