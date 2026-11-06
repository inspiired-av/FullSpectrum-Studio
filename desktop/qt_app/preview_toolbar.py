"""Small adaptive preview toolbar, with independent View, Plate and Camera groups.

Never reparents or rebuilds the OpenGL viewport: only normal toolbar widgets
move from the primary row to the secondary row at a width breakpoint.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLayout,
                               QSizePolicy, QVBoxLayout, QWidget)
from desktop.qt_app.preview_toolbar_breakpoint import compact_preview_rows

GROUP_STYLE = '''
QFrame#previewToolbarGroup {
    background-color: #1b252f;
    border: 1px solid #374a5a;
    border-radius: 8px;
}
QFrame#previewToolbarGroup QPushButton,
QFrame#previewToolbarGroup QToolButton {
    border: 0;
    border-radius: 5px;
    background-color: transparent;
    color: #cfdee7;
    padding: 3px 6px;
}
QFrame#previewToolbarGroup QPushButton:hover,
QFrame#previewToolbarGroup QToolButton:hover {
    background-color: #304350;
    color: #f5fbff;
}
QFrame#previewToolbarGroup QPushButton:pressed,
QFrame#previewToolbarGroup QToolButton:pressed {
    background-color: #3a5567;
}
QFrame#previewToolbarGroup QPushButton:disabled,
QFrame#previewToolbarGroup QToolButton:disabled {
    color: #798d9a;
}
QFrame#previewToolbarGroup QComboBox#previewMode { border: none; background: transparent; }
'''


def make_preview_group(*widgets, name: str) -> QFrame:
    group = QFrame()
    group.setObjectName('previewToolbarGroup')
    group.setProperty('group', name)
    group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    group.setStyleSheet(GROUP_STYLE)
    lay = QHBoxLayout(group)
    lay.setContentsMargins(3, 2, 3, 2)
    lay.setSpacing(2)
    for widget in widgets:
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    return group


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName('previewToolbarDivider')
    line.setFixedSize(1, 18)
    line.setStyleSheet('background-color: #425566; border: none;')
    return line


class AdaptivePreviewToolbar(QWidget):
    """Responsive toolbar. The wide breakpoint is measured from all groups.

    A QWidget can otherwise refuse a programmatic shrink because the wide
    row's minimumSizeHint is larger than the target width. We override that
    hint and measure the original groups, *not* the changing row contents.
    """

    def __init__(self, heading: QWidget, view: QWidget,
                 plate: QWidget, camera: QWidget, parent=None):
        super().__init__(parent)
        self._groups = (heading, view, plate, camera)
        self._narrow = None
        self._wide_minimum = 0
        self.setObjectName('adaptivePreviewToolbar')
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        col = QVBoxLayout(self)
        col.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(5)
        self._wide_row = QHBoxLayout()
        self._wide_row.setContentsMargins(0, 0, 0, 0)
        self._wide_row.setSpacing(7)
        col.addLayout(self._wide_row)
        self._compact_box = QWidget(self)
        self._compact_row = QHBoxLayout(self._compact_box)
        self._compact_row.setContentsMargins(0, 0, 0, 0)
        self._compact_row.setSpacing(7)
        col.addWidget(self._compact_box)
        self._set_narrow(False)
        self._wide_minimum = self._measure_wide_width()

    def minimumSizeHint(self) -> QSize:
        # Crucial: do not inherit the 1-row layout's minimum width. Without
        # this, resize(410, ...) can silently clamp to the wide row's width.
        return QSize(0, max(38, self._groups[1].minimumSizeHint().height()))

    def _measure_wide_width(self) -> int:
        # Fixed-height heading and groups have stable content measurements
        # regardless of whether the Plate and Camera live in a secondary row.
        widths = [max(g.sizeHint().width(), g.minimumSizeHint().width(),
                      g.minimumWidth()) for g in self._groups]
        return sum(widths) + 3 * self._wide_row.spacing() + 16

    @staticmethod
    def _clear(layout):
        while layout.count():
            layout.takeAt(0)

    def _set_narrow(self, narrow: bool):
        if self._narrow == bool(narrow):
            return
        self._clear(self._wide_row)
        self._clear(self._compact_row)
        heading, view, plate, camera = self._groups
        self._wide_row.addWidget(heading)
        self._wide_row.addStretch(1)
        self._wide_row.addWidget(view)
        if narrow:
            self._compact_row.addWidget(plate)
            self._compact_row.addStretch(1)
            self._compact_row.addWidget(camera)
            self._compact_box.setVisible(True)
        else:
            self._wide_row.addWidget(plate)
            self._wide_row.addWidget(camera)
            self._compact_box.setVisible(False)
        self._narrow = bool(narrow)
        self.layout().invalidate()
        self.updateGeometry()

    def refresh(self, available_width=None):
        # Always calculate from the FULL (wide) set of groups. If measured from
        # the compact row, this could flip wide/narrow on successive events.
        self._wide_minimum = max(self._wide_minimum, self._measure_wide_width())
        width = int(available_width) if available_width is not None else self.width()
        should_wrap = compact_preview_rows(width, self._wide_minimum,
                                           was_compact=bool(self._narrow))
        self._set_narrow(should_wrap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh(event.size().width())
