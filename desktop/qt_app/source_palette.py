"""Interactive, responsive source-color swatches for Qt preview.

UI only: no changes to model geometry, painted states or filament planning.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QSizePolicy


def responsive_columns(width, swatch_count, min_cell=34, spacing=5, margins=8):
    """Fit swatches into the current width, without leaving arbitrary gaps.

    Does not depend on Qt widget geometry and is easy to regression test.
    """
    if swatch_count <= 0:
        return 0
    available = max(1, int(width) - margins)
    capacity = max(1, (available + spacing) // (min_cell + spacing))
    return min(swatch_count, capacity)


class PaletteSwatch(QLabel):
    """Mouse/keyboard accessible swatch with explicit hover feedback.

    Qt's native tooltips are supplementary; the parent shows color information
    visibly on hover/click so it also works when pop-up tooltips are unavailable.
    """
    hovered = Signal(str)
    left = Signal()
    chosen = Signal(str)

    def __init__(self, hex_color, face_count, parent=None):
        super().__init__('', parent)
        self.hex_color = str(hex_color).upper()
        self.face_count = int(face_count)
        self._selected = False
        self.setObjectName('sourcePaletteSwatch')
        self.setToolTip(f'{self.hex_color} · {self.face_count:,} faces')
        self.setAccessibleName(f'Source color {self.hex_color}, {self.face_count:,} faces')
        self.setFixedHeight(25)
        self.setMinimumWidth(27)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._refresh_style()

    def _refresh_style(self):
        border = '2px solid #e9f7ff' if self._selected else '1px solid #627484'
        self.setStyleSheet('QLabel#sourcePaletteSwatch {'
                           f'background-color: {self.hex_color}; border: {border}; '
                           'border-radius: 4px; }'
                           'QLabel#sourcePaletteSwatch:focus {border: 2px solid #d9efff;}')

    def set_selected(self, selected):
        self._selected = bool(selected)
        self._refresh_style()

    def enterEvent(self, event):
        self.hovered.emit(self.hex_color)
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        self.hovered.emit(self.hex_color)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self.hex_color)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.chosen.emit(self.hex_color)
            event.accept()
        else:
            super().keyPressEvent(event)
