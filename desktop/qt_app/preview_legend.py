"""Compact Qt overlay for the engine's *estimated* color-loss heatmap.

Presentation only. The engine defines the thresholds and heatmap colors;
this widget never calculates ΔE, modifies meshes, or writes files.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy, QPushButton, QComboBox, QGridLayout, QScrollArea


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
    """Interactive lower-left GPU influence legend: dominant physical-color default.

    Categorical overlay colors are optional. Clicking a physical anchor shows
    its recipe share (0–100%) in ALL regions, even when a minority component.
    """
    anchor_selected = Signal(int)
    palette_mode_changed = Signal(str)

    def __init__(self, viewport):
        super().__init__(viewport)
        self.setObjectName('anchorInfluenceLegend')
        self.setStyleSheet(
            'QFrame#anchorInfluenceLegend {background: rgba(15,21,29,238); '
            'border: 1px solid #465361; border-radius: 9px;}'
            'QLabel#anchorLegendTitle {color: #eef4f8; font-size: 11px; font-weight: 700; border: none;}'
            'QLabel#anchorLegendNote {color: #a5bac7; font-size: 9px; border: none;}'
            'QPushButton#anchorLegendChoice {background: transparent; border: 1px solid transparent; '
            'text-align: left; padding: 2px; color: #e2eaf0; font-size: 10px;}'
            'QPushButton#anchorLegendChoice:checked {border: 1px solid #72d8ed; '
            'background: #244752; border-radius: 4px;}'
        )
        self.rows=()
        self._labels=[]
        self._columns=1
        self.selected_slot=0
        self.color_mode='physical'
        layout=QVBoxLayout(self)
        layout.setContentsMargins(11,8,11,8)
        layout.setSpacing(4)
        heading=QHBoxLayout()
        title=QLabel('ANCHOR INFLUENCE  ·  PHYSICAL SLOTS')
        title.setObjectName('anchorLegendTitle')
        title.setMinimumWidth(0)
        self._title=title
        heading.addWidget(title,1)
        self.display=QComboBox(self)
        self.display.setObjectName('anchorDisplayMode')
        self.display.addItem('Physical colors', 'physical')
        self.display.addItem('Distinct colors', 'categorical')
        self.display.setToolTip('Physical colors are the actual dominant filaments. Distinct colors provide contrast.')
        self.display.setFixedWidth(124)
        self.display.currentIndexChanged.connect(self._display_changed)
        heading.addWidget(self.display)
        layout.addLayout(heading)
        # The legend must fit a short viewport while still allowing access to
        # every anchor, including when the contribution gradient is expanded.
        self._grid_scroll=QScrollArea(self)
        self._grid_scroll.setObjectName('anchorLegendScroll')
        self._grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setMinimumHeight(0)
        self._grid_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._grid_scroll.setStyleSheet(
            'QScrollArea#anchorLegendScroll {background: transparent; border: none;}'
            'QScrollArea#anchorLegendScroll > QWidget > QWidget {background: transparent;}')
        self._grid_content=QWidget(self._grid_scroll)
        self._grid=QGridLayout(self._grid_content)
        self._grid.setContentsMargins(0,0,0,0)
        self._grid.setHorizontalSpacing(9)
        self._grid.setVerticalSpacing(3)
        self._grid_scroll.setWidget(self._grid_content)
        self._grid_scroll.viewport().setAutoFillBackground(False)
        self._grid_content.setAutoFillBackground(False)
        layout.addWidget(self._grid_scroll,1)
        self._note=QLabel('Click a filament for its contribution (0–100%)')
        self._note.setObjectName('anchorLegendNote')
        layout.addWidget(self._note)
        self._gradient=QWidget(self)
        gradient=QVBoxLayout(self._gradient)
        gradient.setContentsMargins(0,0,0,0)
        gradient.setSpacing(3)
        bar=QFrame(self._gradient)
        bar.setFixedHeight(9)
        bar.setStyleSheet('QFrame {background: qlineargradient(x1:0,y1:0,x2:1,y2:0, '
                          'stop:0 #1C2938, stop:0.5 #27818F, stop:1 #30DDF5); '
                          'border: none; border-radius: 3px;}')
        gradient.addWidget(bar)
        ticks=QHBoxLayout()
        for index,text in enumerate(('0%','50%','100%')):
            tick=QLabel(text)
            tick.setObjectName('anchorLegendNote')
            ticks.addWidget(tick,1)
            tick.setAlignment((Qt.AlignmentFlag.AlignLeft if index==0 else
                               Qt.AlignmentFlag.AlignRight if index==2 else
                               Qt.AlignmentFlag.AlignCenter))
        gradient.addLayout(ticks)
        layout.addWidget(self._gradient)
        self._gradient.hide()
        self.setFixedSize(390,60)
        viewport.installEventFilter(self)
        self.position_over_viewport()

    @property
    def has_rows(self):
        return bool(self.rows)

    def _display_changed(self,index):
        mode=self.display.itemData(index)
        if mode not in ('physical','categorical') or mode==self.color_mode:
            return
        self.color_mode=mode
        self._restyle_chips()
        self.palette_mode_changed.emit(mode)

    def _restyle_chips(self):
        for chip, row in self._chips:
            color=row['filament'] if self.color_mode=='physical' else row['overlay']
            chip.setStyleSheet(f'QFrame#anchorLegendSwatch {{background-color: {color}; '
                               f'border: 1px solid #8b9aa8; border-radius: 3px;}}')
            chip.setToolTip('Physical filament' if self.color_mode=='physical' else 'High-contrast category')

    def _choose(self,slot):
        self.selected_slot = 0 if self.selected_slot==slot else slot
        for button,record in self._buttons:
            button.setChecked(record['slot']==self.selected_slot)
        self._gradient.setVisible(self.selected_slot > 0)
        if self.selected_slot:
            name=next(row['name'] for row in self.rows if row['slot']==self.selected_slot)
            self._note.setText(f'Slot {self.selected_slot} · recipe share, not filament consumption')
        else:
            self._note.setText('Click a filament for its contribution (0–100%)')
        self._update_size()
        self.position_over_viewport()
        self.anchor_selected.emit(self.selected_slot)

    def set_rows(self, rows):
        self.rows=tuple(rows or ())
        self.selected_slot=0
        self._gradient.hide()
        self._note.setText('Click a filament for its contribution (0–100%)')
        self._build_rows()
        self.position_over_viewport()

    def _columns_needed(self):
        parent=self.parentWidget()
        # Prefer two columns before the legend would exceed its viewport.
        # Include the optional contribution scale in that decision.
        natural_height=72+len(self.rows)*26+(32 if self.selected_slot else 0)
        return 2 if (parent and len(self.rows)>2 and parent.width()>=380 and
                     natural_height > parent.height()-24) else 1

    def _build_rows(self):
        while self._grid.count():
            item=self._grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._buttons=[]
        self._chips=[]
        self._columns=self._columns_needed()
        nrows=(len(self.rows)+self._columns-1)//self._columns
        for index,record in enumerate(self.rows):
            cell=QWidget(self)
            contents=QHBoxLayout(cell)
            contents.setContentsMargins(0,0,0,0)
            contents.setSpacing(5)
            chip=QFrame(cell)
            chip.setObjectName('anchorLegendSwatch')
            chip.setFixedSize(13,13)
            contents.addWidget(chip)
            self._chips.append((chip,record))
            button=QPushButton(cell)
            button.setObjectName('anchorLegendChoice')
            button.setCheckable(True)
            button.setChecked(record['slot']==self.selected_slot)
            full=f"{record['slot']} · {record['name']}"+('  (Pinned)' if record['pinned'] else '')
            button.setText(full)
            button.setToolTip(full+' · click to show percentage contribution')
            button.setAccessibleName(full)
            button.clicked.connect(lambda checked=False,slot=record['slot']:self._choose(slot))
            contents.addWidget(button,1)
            self._buttons.append((button,record))
            self._grid.addWidget(cell,index%nrows if nrows else 0,index//nrows if nrows else 0)
        self._restyle_chips()
        self._update_size()

    def _update_size(self):
        parent=self.parentWidget()
        if parent is None:return
        width=min(max(1,parent.width()-24),460 if self._columns==1 else 590)
        natural_height=72+((len(self.rows)+self._columns-1)//self._columns)*26
        if self.selected_slot: natural_height+=32
        # Never extend beyond the viewport. The scroll area keeps omitted
        # rows accessible rather than cropping them behind the model.
        height=min(natural_height,max(1,parent.height()-24))
        self.setFixedSize(width,height)
        self._title.setText('ANCHOR INFLUENCE' if width<380 else
                            'ANCHOR INFLUENCE  ·  PHYSICAL SLOTS')
        text_width=max(45,(width-38)//self._columns-42)
        for button,record in self._buttons:
            full=f"{record['slot']} · {record['name']}"+('  (Pinned)' if record['pinned'] else '')
            button.setText(button.fontMetrics().elidedText(full,Qt.TextElideMode.ElideRight,text_width))

    def position_over_viewport(self,size=None):
        parent=self.parentWidget()
        if parent is None:return
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
