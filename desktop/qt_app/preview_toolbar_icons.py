"""Outlined preview icons with consistent 24-unit geometry and HiDPI painting.

Expand points to the TOP-RIGHT and BOTTOM-LEFT. Restore reverses the arrows.
Reset matches a rounded counterclockwise 9-unit rotation glyph.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_VALID = frozenset({'expand', 'restore', 'reset', 'more'})


def preview_toolbar_icon(name: str, color: str = '#d1dfe8') -> QIcon:
    if name not in _VALID:
        raise ValueError(f'Unknown preview toolbar icon: {name!r}')
    pixmap = QPixmap(60, 60)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(3.0)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(20.0 / 24.0, 20.0 / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == 'expand':
        # NE + SW diagonal expansion, rather than the previous NW + SE pair.
        painter.drawLine(QPointF(10, 14), QPointF(19, 5))
        painter.drawLine(QPointF(13, 5), QPointF(19, 5))
        painter.drawLine(QPointF(19, 5), QPointF(19, 11))
        painter.drawLine(QPointF(14, 10), QPointF(5, 19))
        painter.drawLine(QPointF(5, 13), QPointF(5, 19))
        painter.drawLine(QPointF(5, 19), QPointF(11, 19))
    elif name == 'restore':
        # Paired inward arrows along the same NE/SW diagonal.
        painter.drawLine(QPointF(19, 5), QPointF(14, 10))
        painter.drawLine(QPointF(14, 6), QPointF(14, 10))
        painter.drawLine(QPointF(14, 10), QPointF(18, 10))
        painter.drawLine(QPointF(5, 19), QPointF(10, 14))
        painter.drawLine(QPointF(6, 14), QPointF(10, 14))
        painter.drawLine(QPointF(10, 14), QPointF(10, 18))
    elif name == 'reset':
        # Lucide-like rotate-ccw: one near-complete circular sweep, with a
        # separate square corner arrowhead. No stuttering arc/zigzag joint.
        curve = QPainterPath()
        curve.moveTo(3.2, 10.7)
        curve.cubicTo(3.8, 6.5, 7.5, 3.4, 12.0, 3.4)
        curve.cubicTo(16.9, 3.4, 20.6, 7.1, 20.6, 12.0)
        curve.cubicTo(20.6, 16.9, 16.9, 20.6, 12.0, 20.6)
        curve.cubicTo(9.8, 20.6, 7.8, 19.7, 6.1, 18.0)
        painter.drawPath(curve)
        painter.drawLine(QPointF(3.2, 4.6), QPointF(3.2, 10.7))
        painter.drawLine(QPointF(3.2, 10.7), QPointF(9.3, 10.7))
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        for x in (5, 12, 19):
            painter.drawEllipse(QPointF(x, 12), 1.4, 1.4)

    painter.end()
    return QIcon(pixmap)
