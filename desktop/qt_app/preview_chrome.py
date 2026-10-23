"""Small non-intercepting viewport labels for model and forecast state.

These are QWidget overlays, not extra OpenGL draws and not export metadata.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtCore import QRectF



def _estimate_sparkle(size=14):
    """Filled four-point sparkle with hollow middle and upper-right satellite.

    Drawn from vector paths in Qt; no font glyphs, SVG plugins or asset files.
    Based on the reference icon supplied for the forecast estimate.
    """
    scale = 2  # sharp edges on high-DPI displays
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size * scale / 24.0, size * scale / 24.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#71d7dc'))
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.moveTo(11.4, 2.9)
    path.cubicTo(11.8, 7.8, 14.5, 10.7, 20.2, 11.6)
    path.cubicTo(14.5, 12.2, 11.8, 15.0, 11.4, 21.1)
    path.cubicTo(11.0, 15.0, 8.2, 12.2, 2.6, 11.6)
    path.cubicTo(8.2, 10.7, 11.0, 7.8, 11.4, 2.9)
    inner = QPainterPath()
    inner.moveTo(11.4, 7.3)
    inner.cubicTo(12.3, 9.3, 13.9, 10.8, 16.0, 11.6)
    inner.cubicTo(13.9, 12.4, 12.3, 14.0, 11.4, 16.2)
    inner.cubicTo(10.5, 14.0, 8.9, 12.4, 6.7, 11.6)
    inner.cubicTo(8.9, 10.8, 10.5, 9.3, 11.4, 7.3)
    path.addPath(inner)
    painter.drawPath(path)
    painter.drawEllipse(QRectF(17.3, 2.7, 4.7, 4.7))
    painter.end()
    return pix

class PreviewChrome(QObject):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self._metadata = ''
        self._accuracy = None
        self._outdated = False
        self.model_label = self._label('previewModelInfo')
        self.model_label.setToolTip('')
        self.estimate_label = self._label('previewEstimatedAccuracy')
        self.estimate_symbol = QLabel(self.estimate_label)
        self.estimate_symbol.setObjectName('previewEstimateSparkle')
        self.estimate_symbol.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.estimate_symbol.setPixmap(_estimate_sparkle())
        self.estimate_symbol.adjustSize()
        self.drop_label = self._label('previewDropFeedback')
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for label in (self.model_label, self.estimate_label, self.drop_label):
            label.hide()
        viewport.installEventFilter(self)
        self.reposition()

    def _label(self, name):
        label = QLabel('', self.viewport)
        label.setObjectName(name)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.setStyleSheet('QLabel#' + name + ' { color: #dcecf5; '
                            'background-color: rgba(17, 26, 34, 225); '
                            'border: 1px solid #354959; border-radius: 7px; '
                            'padding: 5px 9px; font-size: 11px; }')
        return label

    def set_model(self, name='', shown=0, source=0, sampled=False):
        """Keep filename/triangle details in the existing header and status line.

        Avoid duplicating the title or covering the 3D model with metadata.
        The forecast estimate now owns the upper-left viewport corner.
        """
        self._metadata = ''
        self.model_label.setText('')
        self.model_label.setToolTip('')
        self.model_label.hide()
        self.reposition()

    def set_estimate(self, value=None, *, outdated=False):
        self._accuracy = value
        self._outdated = bool(outdated)
        if value is None:
            self.estimate_label.hide()
        else:
            if outdated:
                text = 'Forecast outdated'
                tip = f'Last estimated accuracy: {float(value):.1f}%. Refresh Forecast to update.'
                color = '#e9b66c'
            else:
                text = f'{float(value):.1f}% estimated'
                tip = 'Read-only forecast estimate, not a measured print result.'
                color = '#8fdbd0'
            self.estimate_label.setText(text)
            self.estimate_label.setToolTip(tip)
            self.estimate_label.setStyleSheet(
                'QLabel#previewEstimatedAccuracy { color: ' + color + '; '
                'background-color: rgba(17, 33, 40, 235); border: 1px solid #44606a; '
                'border-radius: 7px; padding: 5px 9px 5px 29px; font-size: 11px; '
                'font-weight: 600; }')
            self.estimate_label.show()
            self.estimate_symbol.show()
        self.reposition()

    def mark_outdated(self):
        if self._accuracy is not None:
            self.set_estimate(self._accuracy, outdated=True)

    def set_drop_message(self, message):
        self.drop_label.setText(str(message))
        self.drop_label.setVisible(bool(message))
        self.reposition()
        if message:
            self.drop_label.raise_()

    def reposition(self, size=None):
        w = size.width() if size is not None else self.viewport.width()
        h = size.height() if size is not None else self.viewport.height()
        margin = 12
        if not self.estimate_label.isHidden():
            self.estimate_label.adjustSize()
            self.estimate_symbol.move(9,
                max(0, (self.estimate_label.height() - self.estimate_symbol.height()) // 2))
            # Top-left, without the duplicate model filename above the scene.
            self.estimate_label.move(margin, margin)
            self.estimate_label.raise_()
        if not self.drop_label.isHidden():
            self.drop_label.setFixedSize(max(100, min(360, w - 28)), 64)
            self.drop_label.move(max(0, (w - self.drop_label.width()) // 2),
                                 max(0, (h - self.drop_label.height()) // 2))
            self.drop_label.raise_()

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() == QEvent.Type.Resize:
            self.reposition(event.size())
        return super().eventFilter(watched, event)
