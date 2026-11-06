"""Custom painted model-view combobox and modern Qt popup list.

This is only a presentation subclass of WheelSafeComboBox: existing model,
selection, keyboard, and disabled-item semantics remain standard QComboBox.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QListView, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem)
from desktop.qt_app.wheel_safe_combo import WheelSafeComboBox


class _ViewModeDelegate(QStyledItemDelegate):
    """A legible 36px menu row, rather than Windows' compact classic list."""

    def __init__(self, combo):
        super().__init__(combo)
        self._combo = combo

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(max(200, size.width() + 36), 36)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = option.rect.adjusted(4, 2, -4, -2)
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        active = index.row() == self._combo.currentIndex()
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if enabled and (hovered or selected):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#2b5264'))
            painter.drawRoundedRect(QRectF(area), 6, 6)
        painter.setPen(QColor('#eff8fc' if active else
                              '#d0dde6' if enabled else '#748491'))
        fm = option.fontMetrics
        label = fm.elidedText(str(index.data(Qt.ItemDataRole.DisplayRole) or ''),
                              Qt.TextElideMode.ElideRight, max(40, area.width() - 34))
        painter.drawText(area.adjusted(12, 0, -24, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        if active:
            check = QPen(QColor('#7bd3e1'), 1.9)
            check.setCapStyle(Qt.PenCapStyle.RoundCap)
            check.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check)
            x, y = area.right() - 22, area.center().y()
            painter.drawLine(x, y, x + 4, y + 4)
            painter.drawLine(x + 4, y + 4, x + 11, y - 4)
        painter.restore()


class ModernPreviewComboBox(WheelSafeComboBox):
    """Rounded model-view selector with an owner-painted dropdown arrow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('previewMode')
        self.setMinimumHeight(32)
        self.setMinimumWidth(145)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(15)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        view = QListView(self)
        view.setMouseTracking(True)
        view.setUniformItemSizes(True)
        view.setMinimumWidth(208)
        view.setSpacing(0)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setItemDelegate(_ViewModeDelegate(self))
        view.setStyleSheet('''
            QListView {
                background-color: #1a2630;
                color: #e3eef6;
                border: 1px solid #456071;
                border-radius: 8px;
                padding: 5px;
                outline: none;
            }
            QListView::item { background: transparent; border: none; }
            QScrollBar:vertical { background: #1a2630; width: 8px; }
            QScrollBar::handle:vertical { background: #4b6373; border-radius: 4px; }
        ''')
        self.setView(view)
        self.setStyleSheet('''
            QComboBox#previewMode { border: none; background: transparent; }
            QComboBox#previewMode::drop-down { border: none; width: 24px; }
            QComboBox#previewMode::down-arrow { image: none; width: 0px; height: 0px; }
        ''')

    def paintEvent(self, event):
        # Drawing the closed selector ourselves avoids the platform's old
        # beveled Windows combo chrome, while QComboBox still owns interaction.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        hover = self.underMouse() and enabled
        opened = self.view().isVisible() if self.view() is not None else False
        bg = '#2b4050' if (hover or opened) else '#202d38'
        border = '#6aabb9' if opened else '#476071' if hover else '#344a59'
        painter.setPen(QPen(QColor(border), 1.0))
        painter.setBrush(QColor(bg if enabled else '#1c252c'))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 7, 7)

        painter.setPen(QColor('#dbe9f1' if enabled else '#7e8e9a'))
        text_area = self.rect().adjusted(11, 0, -30, 0)
        text = painter.fontMetrics().elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, text_area.width())
        painter.drawText(text_area, Qt.AlignmentFlag.AlignVCenter |
                         Qt.AlignmentFlag.AlignLeft, text)
        # Crisp hand-drawn chevron; no OS-provided 1990s-style arrow asset.
        c = self.width() - 17
        y = self.height() / 2
        pen = QPen(QColor('#8cd4e2' if hover or opened else '#a3b6c5'), 1.65)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(c - 4, int(y) - 2, c, int(y) + 2)
        painter.drawLine(c, int(y) + 2, c + 4, int(y) - 2)
        painter.end()

    def showPopup(self):
        # Qt's own popup, not a detached native fullscreen presentation path.
        # Keep the full model names legible and the five options on screen.
        self.view().setMinimumWidth(max(208, self.width()))
        super().showPopup()
