"""One painted, edge-to-edge slicer selector backing two real Qt buttons.

The background and selected pill share a single QPainter canvas. Buttons are
transparent hit targets above it, so Qt style hover states cannot leave gaps
at the seam or cause two separate hover backgrounds.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QFrame


class ExportSlicerSegment(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_index = 0
        self._hovered = False
        self._tracked_buttons = []
        self.selected_color = QColor('#2183f5')
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def watch_button(self, button):
        self._tracked_buttons.append(button)
        button.installEventFilter(self)
        button.setMouseTracking(True)

    def set_selected(self, index):
        index = 1 if int(index) else 0
        if self._selected_index != index:
            self._selected_index = index
            self.update()

    def enterEvent(self, event):
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovered(False)
        super().leaveEvent(event)

    def _set_hovered(self, hovered):
        hovered = bool(hovered)
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()

    def eventFilter(self, watched, event):
        if watched in self._tracked_buttons:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                self._set_hovered(True)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                # Moving between halves should not flash the container idle.
                local = self.mapFromGlobal(QCursor.pos())
                self._set_hovered(self.rect().contains(local))
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        bounds = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if bounds.isEmpty():
            painter.end()
            return
        radius = bounds.height() / 2
        # Hover lightens the *whole* container; no per-button hover rectangle.
        painter.setBrush(QColor('#343b46' if self._hovered else '#282a30'))
        painter.drawRoundedRect(bounds, radius, radius)
        # Draw the selected pill right on the container's outer boundary.
        # The selected inner edge remains rounded, Mac-style. No layout gaps.
        half = bounds.width() / 2
        left = bounds.left() if self._selected_index == 0 else bounds.left() + half
        selected = QRectF(left, bounds.top(), half, bounds.height())
        painter.setBrush(self.selected_color)
        painter.drawRoundedRect(selected, radius, radius)
        painter.end()
