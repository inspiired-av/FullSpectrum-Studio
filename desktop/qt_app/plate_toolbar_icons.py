"""Small antialiased visibility icons for the existing Qt model preview toolbar."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def plate_eye_icon(visible: bool) -> QIcon:
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor('#a7c8dc'))
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(2.5, 12)
    path.cubicTo(7, 4.7, 17, 4.7, 21.5, 12)
    path.cubicTo(17, 19.3, 7, 19.3, 2.5, 12)
    painter.drawPath(path)
    painter.drawEllipse(QRectF(9.3, 9.3, 5.4, 5.4))
    if not visible:
        pen.setColor(QColor('#f09c9c'))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawLine(4, 20, 20, 4)
    painter.end()
    return QIcon(pix)
