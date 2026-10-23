"""Small theme-matched, DPI-aware Qt vector icons for the compact Export tab.

No platform-dependent font glyphs, image assets or extra dependencies.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def export_icon(name: str, color='#bcd0dd', size=20) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size/24.0, size/24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    def stroke(*coords):
        line = QPainterPath()
        line.moveTo(*coords[0])
        for x, y in coords[1:]:
            line.lineTo(x, y)
        p.drawPath(line)
    if name == 'folder':
        path.moveTo(2.5, 7); path.lineTo(9.5, 7); path.lineTo(12, 9.5)
        path.lineTo(21, 9.5); path.lineTo(21, 19)
        path.quadTo(21, 21, 19, 21); path.lineTo(5, 21)
        path.quadTo(3, 21, 2.5, 19); path.closeSubpath()
        p.drawPath(path)
        stroke((2.5, 7), (2.5, 5.5), (4, 4), (9, 4), (11, 7))
    elif name == 'x':
        stroke((6, 6), (18, 18)); stroke((18, 6), (6, 18))
    elif name == 'info':
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(11, 6.4, 2, 2))
        p.drawRoundedRect(QRectF(11.15, 10.4, 1.7, 7), .7, .7)
    elif name in ('alert', 'alert-circle'):
        if name == 'alert':
            stroke((12, 3), (22, 20), (2, 20), (12, 3))
        else:
            p.drawEllipse(QRectF(3, 3, 18, 18))
        stroke((12, 9), (12, 13.5))
        p.setBrush(QColor(color));p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(11, 16, 2, 2))
    elif name == 'copy':
        p.drawRoundedRect(QRectF(8, 8, 12, 13), 1.2, 1.2)
        stroke((5.5, 16), (4, 16), (4, 3.5), (16, 3.5), (16, 5.5))
    elif name == 'trash':
        stroke((4, 7), (20, 7)); stroke((9, 4.5), (15, 4.5));
        stroke((6.5, 7), (7.5, 20), (16.5, 20), (17.5, 7))
        stroke((10, 10), (10.5, 17));stroke((14, 10), (13.5, 17))
    elif name in ('right', 'down'):
        if name == 'right': stroke((9, 5), (16, 12), (9, 19))
        else: stroke((5, 9), (12, 16), (19, 9))
    elif name == 'file':
        stroke((6, 2.5), (14.5, 2.5), (19, 7), (19, 21), (6, 21), (6, 2.5))
        stroke((14.5, 2.5), (14.5, 7), (19, 7))
        stroke((9, 12), (16, 12));stroke((9, 16), (16, 16))
    elif name == 'fullscreen':
        # Four diagonal arrows POINTING OUT toward viewport corners.
        stroke((10, 10), (3.5, 3.5))
        stroke((3.5, 9), (3.5, 3.5), (9, 3.5))
        stroke((14, 10), (20.5, 3.5))
        stroke((15, 3.5), (20.5, 3.5), (20.5, 9))
        stroke((10, 14), (3.5, 20.5))
        stroke((3.5, 15), (3.5, 20.5), (9, 20.5))
        stroke((14, 14), (20.5, 20.5))
        stroke((15, 20.5), (20.5, 20.5), (20.5, 15))
    elif name == 'fullscreen-exit':
        # Four arrows POINTING IN; visible exit-state distinction.
        stroke((3, 3), (10, 10))
        stroke((10, 5), (10, 10), (5, 10))
        stroke((21, 3), (14, 10))
        stroke((19, 10), (14, 10), (14, 5))
        stroke((3, 21), (10, 14))
        stroke((5, 14), (10, 14), (10, 19))
        stroke((21, 21), (14, 14))
        stroke((14, 19), (14, 14), (19, 14))
    elif name == 'sidebar':
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
        stroke((10, 4), (10, 20))
    elif name == 'open':
        stroke((15, 3), (21, 3), (21, 9));stroke((21, 3), (11, 13))
        stroke((19, 13), (19, 20), (4, 20), (4, 5), (11, 5))
    elif name == 'check':
        p.drawEllipse(QRectF(3, 3, 18, 18));stroke((7, 12), (10.5, 15.5), (17.5, 8.5))
    elif name == 'save':
        stroke((4, 3), (17, 3), (21, 7), (21, 21), (3, 21), (3, 3), (4, 3))
        stroke((7, 3), (7, 10), (17, 10), (17, 3))
        stroke((7, 20), (7, 14), (17, 14), (17, 20))
    elif name == 'reset':
        stroke((4, 10), (4, 4), (10, 4))
        p.drawArc(QRectF(4, 5, 16, 16), 160*16, 300*16)
    elif name == 'settings':
        stroke((3, 6), (21, 6))
        stroke((3, 17), (21, 17))
        p.drawEllipse(QRectF(7, 3, 6, 6))
        p.drawEllipse(QRectF(13, 14, 6, 6))
    elif name == 'export':
        stroke((12, 3), (12, 15));stroke((7, 10), (12, 15), (17, 10))
        stroke((4, 16), (4, 21), (20, 21), (20, 16))
    else:
        p.end()
        raise ValueError('Unknown Export icon: ' + str(name))
    p.end()
    return QIcon(pix)


def compact_icon_button(button, icon_name, description, *, side=28, color='#bcd0dd'):
    """Give existing signal-connected QPushButton/QToolButton a consistent shape."""
    button.setText('')
    button.setIcon(export_icon(icon_name, color))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(side, side)
    button.setToolTip(description)
    button.setAccessibleName(description)
    button.setStyleSheet(
        'QPushButton, QToolButton { background-color: #222b35; '
        'border: 1px solid #3a4c5a; border-radius: 5px; padding: 2px; }'
        'QPushButton:hover, QToolButton:hover { border-color: #72bed1; background-color: #293b49; }'
        'QPushButton:disabled, QToolButton:disabled { border-color: #2d3842; }'
    )
    return button
