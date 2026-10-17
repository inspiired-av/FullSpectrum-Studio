"""Compact Qt overlay for the engine's *estimated* color-loss heatmap.

Presentation only. The engine defines the thresholds and heatmap colors;
this widget never calculates ΔE, modifies meshes, or writes files.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy


class ColorLossLegend(QFrame):
    """Anchored in the model viewport's lower-left corner, above geometry."""

    def __init__(self, viewport):
        super().__init__(viewport)
        self.setObjectName('colorLossLegend')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setToolTip('Engine color-loss estimate before slicing or physical calibration; '
                        'lower ΔE means closer perceived color.')
        self.setStyleSheet(
            'QFrame#colorLossLegend {background: rgba(15, 21, 29, 228); '
            'border: 1px solid #465361; border-radius: 9px;}'
            'QFrame#legendSegment {border: 0; border-radius: 3px;}'
            'QLabel#legendCaption {color: #cbd8e3; font-size: 10px;}'
            'QLabel#legendHeading {color: #eef4f8; font-size: 11px; font-weight: 700;}'
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(7)
        title = QLabel('COLOR LOSS  ·  ESTIMATED ΔE')
        title.setObjectName('legendHeading')
        layout.addWidget(title)
        bars = QHBoxLayout()
        bars.setSpacing(9)
        self.segments = []
        for label, name, color in (
                ('ΔE ≤ 2', 'Low', '#37C977'),
                ('ΔE 2–6', 'Moderate', '#F5D725'),
                ('ΔE > 6', 'Higher', '#F54A1F')):
            segment = QWidget(self)
            column = QVBoxLayout(segment)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(4)
            swatch = QFrame(segment)
            swatch.setObjectName('legendSegment')
            swatch.setFixedHeight(10)
            # One complete f-string: the CSS braces must be escaped as {{ / }}
            # in Python source, producing exactly one { / } for Qt's parser.
            swatch.setStyleSheet(
                f'QFrame#legendSegment {{ background-color: {color}; '
                f'border: none; border-radius: 3px; }}'
            )
            column.addWidget(swatch)
            caption = QLabel(f'{label} · {name}')
            caption.setObjectName('legendCaption')
            caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            column.addWidget(caption)
            bars.addWidget(segment, 1)
            self.segments.append((label, color))
        layout.addLayout(bars)
        self.setFixedSize(382, 79)
        viewport.installEventFilter(self)
        self.position_over_viewport()

    def position_over_viewport(self, size=None):
        parent = self.parentWidget()
        if parent is None:
            return
        w = size.width() if size is not None else parent.width()
        h = size.height() if size is not None else parent.height()
        # Don't intercept orbit/zoom: the whole overlay is mouse-transparent.
        width = max(230, min(382, w - 24))
        self.setFixedWidth(width)
        self.move(12, max(9, h - self.height() - 12))
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.position_over_viewport(event.size())
        return super().eventFilter(watched, event)


class AnchorInfluenceLegend(QFrame):
    """Compact, noninteractive lower-left 3D viewport legend."""

    def __init__(self, viewport):
        super().__init__(viewport)
        from PySide6.QtWidgets import QGridLayout
        self.setObjectName('anchorInfluenceLegend')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            'QFrame#anchorInfluenceLegend {background: rgba(15,21,29,238); '
            'border: 1px solid #465361; border-radius: 9px;}'
            'QLabel#anchorLegendTitle {color: #eef4f8; font-size: 11px; font-weight: 700; border: none;}'
            'QLabel#anchorLegendName {color: #e2eaf0; font-size: 10px; border: none;}'
            'QLabel#anchorLegendNote {color: #a5bac7; font-size: 9px; border: none;}'
        )
        self.rows = ()
        self._columns = 1
        self._labels = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11,8,11,8)
        layout.setSpacing(5)
        title=QLabel('ANCHOR INFLUENCE  ·  PHYSICAL SLOTS')
        title.setObjectName('anchorLegendTitle')
        layout.addWidget(title)
        self._grid=QGridLayout()
        self._grid.setContentsMargins(0,0,0,0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(3)
        layout.addLayout(self._grid)
        self._note=QLabel('Overlay → filament  ·  MIX uses first recipe component')
        self._note.setObjectName('anchorLegendNote')
        layout.addWidget(self._note)
        self.setFixedSize(390,60)
        viewport.installEventFilter(self)
        self.position_over_viewport()

    @property
    def has_rows(self):
        return bool(self.rows)

    def set_rows(self, rows):
        self.rows = tuple(rows or ())
        self._build_rows()
        self.position_over_viewport()

    def _columns_needed(self):
        parent=self.parentWidget()
        return (2 if parent and len(self.rows)>2 and parent.width()>=380 and
                62+len(self.rows)*23 > parent.height()-24 else 1)

    def _build_rows(self):
        while self._grid.count():
            item=self._grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._labels=[]
        self._columns=self._columns_needed()
        nrows=(len(self.rows)+self._columns-1)//self._columns
        for index,row in enumerate(self.rows):
            cell=QWidget(self)
            contents=QHBoxLayout(cell)
            contents.setContentsMargins(0,0,0,0)
            contents.setSpacing(5)
            for kind,color in (('Overlay',row['overlay']),('Filament',row['filament'])):
                chip=QFrame(cell)
                chip.setObjectName('anchorLegendSwatch')
                chip.setFixedSize(14,14)
                chip.setStyleSheet('QFrame#anchorLegendSwatch {background-color: '+color+
                                   '; border: 1px solid #8b9aa8; border-radius: 3px;}')
                chip.setAccessibleName(f"{kind} color for slot {row['slot']}: {color}")
                contents.addWidget(chip)
            label=QLabel(cell)
            label.setObjectName('anchorLegendName')
            full=f"{row['slot']} · {row['name']}"+('  (Pinned)' if row['pinned'] else '')
            label.setToolTip(full)
            label.setAccessibleName(full)
            contents.addWidget(label,1)
            self._labels.append((label,full))
            column=index//nrows if nrows else 0
            line=index%nrows if nrows else 0
            self._grid.addWidget(cell,line,column)
        self._note.setText('Overlay colors repeat after six anchors  ·  First MIX component'
                           if len(self.rows)>6 else
                           'Overlay → actual filament  ·  MIX uses first recipe component')
        self._update_size()

    def _update_size(self):
        parent=self.parentWidget()
        if not parent:return
        width=min(max(230,parent.width()-24),440 if self._columns==1 else 530)
        height=59+((len(self.rows)+self._columns-1)//self._columns)*23
        self.setFixedSize(width,height)
        name_width=max(20,(width-40)//self._columns-42)
        for label,full in self._labels:
            label.setText(label.fontMetrics().elidedText(full,Qt.TextElideMode.ElideRight,name_width))

    def position_over_viewport(self,size=None):
        parent=self.parentWidget()
        if not parent:return
        if self.rows:
            if self._columns_needed()!=self._columns:
                self._build_rows()
            else:
                self._update_size()
        self.move(12,max(9,parent.height()-self.height()-12))
        self.raise_()

    def eventFilter(self,watched,event):
        if watched is self.parentWidget() and event.type()==QEvent.Type.Resize:
            self.position_over_viewport(event.size())
        return super().eventFilter(watched,event)
