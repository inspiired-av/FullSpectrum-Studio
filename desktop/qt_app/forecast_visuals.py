"""Read-only, Mac-inspired live forecast presentation for Qt. No engine calls."""
from __future__ import annotations
import math
import re
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy, QFrame

HEX_PAIR = re.compile(r'Worst target\s+(#[0-9a-fA-F]{6})\s+becomes\s+(#[0-9a-fA-F]{6})', re.I)


def worst_pair(forecast):
    """Extract actual, engine-provided worst target/prediction; never infer one."""
    match = HEX_PAIR.search(str(forecast.get('gapMessage') or ''))
    if match:
        return tuple(x.upper() for x in match.groups())
    return None


class RingGauge(QWidget):
    def __init__(self, caption, accent='#65C690', parent=None):
        super().__init__(parent)
        self.caption = caption
        self.accent = accent
        self.value = None
        self.setMinimumSize(86, 101)
        self.setMaximumHeight(125)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(caption + ': unavailable')

    def set_value(self, value):
        try:
            v = float(value)
            self.value = max(0, min(100, v)) if math.isfinite(v) else None
        except (TypeError, ValueError):
            self.value = None
        self.setAccessibleName(f'{self.caption}: {self.value:.0f}%' if self.value is not None else self.caption + ': unavailable')
        self.update()

    def text(self):
        """Return the displayed center value for accessibility and legacy Qt tests.

        The RingGauge is a painted QWidget, not a QLabel; this read-only
        accessor preserves the previous accuracy-label inspection API.
        """
        return '—' if self.value is None else f'{self.value:.0f}%'

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        diameter = max(8, min(72, width - 16, height - 29))
        x, y = (width-diameter)/2, max(7, (height-diameter-24)/2)
        rect = QRectF(x,y,diameter,diameter)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#38434c'), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect,0,360*16)
        if self.value is not None:
            painter.setPen(QPen(QColor(self.accent), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect,90*16,-round(self.value/100*360*16))
        painter.setPen(QColor('#e5edf4'))
        font=QFont('Segoe UI',15, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect,Qt.AlignmentFlag.AlignCenter, self.text())
        font=QFont('Segoe UI',9)
        painter.setFont(font)
        painter.setPen(QColor('#a8b7c5'))
        painter.drawText(QRectF(0,y+diameter+7,width,17),Qt.AlignmentFlag.AlignCenter,self.caption)
        painter.end()


class WorstMatchPanel(QFrame):
    """Mac-style compact target → predicted swatches with the real worst ΔE."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('worstMatchPanel')
        self.setStyleSheet('QFrame#worstMatchPanel {border-top: 1px solid #3a4048; '
                           'border-bottom: 1px solid #3a4048; border-left: none; '
                           'border-right: none; background: transparent;}')
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 8, 3, 8)
        row.setSpacing(8)
        self.source = self._swatch('Target')
        self.predicted = self._swatch('Predicted')
        row.addWidget(self.source[1])
        arrow = QLabel('→')
        arrow.setStyleSheet('color: #9aa9b7; font-weight: 700; font-size: 14px; border: none;')
        row.addWidget(arrow)
        row.addWidget(self.predicted[1])
        copy = QVBoxLayout()
        copy.setSpacing(3)
        headline = QHBoxLayout()
        headline.setSpacing(6)
        title = QLabel('Worst visible match')
        title.setObjectName('worstMatchTitle')
        title.setStyleSheet('font-size: 11px; color: #e7bc7c; font-weight: 700; border: none;')
        headline.addWidget(title)
        headline.addStretch()
        self.delta = QLabel('ΔE —')
        self.delta.setStyleSheet('font-size: 11px; color: #e7bc7c; border: none;')
        headline.addWidget(self.delta)
        copy.addLayout(headline)
        self.details = QLabel('Available after forecasting')
        self.details.setObjectName('worstMatchDescription')
        self.details.setStyleSheet('font-size: 10px; color: #9baabb; border: none;')
        self.details.setWordWrap(True)
        copy.addWidget(self.details)
        row.addLayout(copy, 1)
        self.set_forecast(None)

    @staticmethod
    def _swatch(caption):
        block = QFrame()
        block.setFixedSize(24, 24)
        block.setStyleSheet('background: #26313b; border: 1px solid #55616d; border-radius: 5px;')
        return caption, block

    def set_forecast(self, forecast):
        match = worst_pair(forecast) if forecast else None
        for part, color in zip((self.source, self.predicted), match or (None, None)):
            block = part[1]
            block.setStyleSheet(f'background: {color or "#26313b"}; '
                                'border: 1px solid #5f6875; border-radius: 5px;')
            block.setToolTip(f'{part[0]}: {color or "unavailable"}')
        self.details.setText(
            f'Target {match[0]}  →  Predicted {match[1]}'
            if match else 'Color comparison unavailable'
        )
        delta = forecast.get('maximumDeltaE') if forecast else None
        try:
            value = float(delta)
            self.delta.setText(f'ΔE {value:.1f}' if math.isfinite(value) else 'ΔE —')
        except (ValueError, TypeError):
            self.delta.setText('ΔE —')
