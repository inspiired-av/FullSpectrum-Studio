"""Compact, read-only Qt presentation of the native optimizer's chosen palette."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QSizePolicy, QWidget,
)
from desktop.qt_app.planning_details import build_details


class PlanningDetailsPanel(QFrame):
    review_filament = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('planningDetailsPanel')
        self._details = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)
        self.summary = QLabel('Run a forecast to view its physical filaments and mixed recipes.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.stale_notice = QLabel('OUTDATED FORECAST · Previous optimization results')
        self.stale_notice.setObjectName('planningDetailsStale')
        self.stale_notice.setWordWrap(True)
        self.stale_notice.setStyleSheet(
            'color: #ffce80; background: #342715; border: 1px solid #7b5d32; '
            'border-radius: 5px; padding: 7px 9px; font-weight: 700;'
        )
        self.stale_notice.setVisible(False)
        layout.addWidget(self.stale_notice)
        self.constraints = QLabel('')
        self.constraints.setWordWrap(True)
        layout.addWidget(self.constraints)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('planningDetailsTabs')
        self.physical = self._table(['Slot', 'Color', 'Chosen physical filament', 'Status'])
        self.mixed = self._table(['Slot', 'Color', 'Physical components', 'Source states', 'Worst dE'])
        self.tabs.addTab(self.physical, 'Physical Filaments')
        self.tabs.addTab(self.mixed, 'Mixed Recipes')
        layout.addWidget(self.tabs)
        bottom = QHBoxLayout()
        self.hint = QLabel('Read-only optimizer results · Nothing is pinned or exported by viewing this table.')
        self.hint.setWordWrap(True)
        bottom.addWidget(self.hint, 1)
        self.review = QPushButton('Find in Filaments…')
        self.review.setObjectName('findPlannedFilament')
        self.review.setEnabled(False)
        self.review.setToolTip('Locate the selected physical filament in your available filament choices.')
        self.review.clicked.connect(self._review)
        bottom.addWidget(self.review)
        layout.addLayout(bottom)
        self.physical.itemSelectionChanged.connect(self._sync_review)
        self.tabs.currentChanged.connect(self._sync_review)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def _table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(165)
        table.setMaximumHeight(240)
        return table

    def _cell(self, text, color=None, tooltip=''):
        item = QTableWidgetItem(str(text))
        if color and QColor(color).isValid():
            item.setBackground(QBrush(QColor(color)))
            item.setForeground(QBrush(QColor('#111820') if QColor(color).lightness() > 118 else QColor('#f4f8fb')))
        if tooltip:
            item.setToolTip(tooltip)
        return item

    def set_result(self, result):
        details = build_details(result)
        self._details = details
        self.set_stale(False)
        self.summary.setText(details.slot_summary)
        self.constraints.setText(
            f'Planner: {details.planner.title()} · Quality vs waste: {details.quality_bias} · '
            f'{details.pin_count} pinned physical · Printability: {details.printability} (pre-slice estimate)')
        self.physical.setRowCount(len(details.physical))
        for row, anchor in enumerate(details.physical):
            self.physical.setItem(row, 0, self._cell(anchor['slot']))
            self.physical.setItem(row, 1, self._cell(anchor['color'], anchor['color'], anchor['color']))
            note = anchor['name']
            if anchor['remainingGrams'] is not None:
                note += f" · {anchor['remainingGrams']:.0f} g listed"
            self.physical.setItem(row, 2, self._cell(note, tooltip=anchor['preset']))
            self.physical.setItem(row, 3, self._cell('Pinned' if anchor['pinned'] else 'Optimized'))
        self.physical.clearSelection()
        self.mixed.setRowCount(len(details.mixed))
        for row, mix in enumerate(details.mixed):
            self.mixed.setItem(row, 0, self._cell(mix['slot']))
            self.mixed.setItem(row, 1, self._cell(mix['color'], mix['color'], mix['color']))
            self.mixed.setItem(row, 2, self._cell(mix['components'] or 'Recipe unavailable'))
            self.mixed.setItem(row, 3, self._cell(mix['states']))
            self.mixed.setItem(row, 4, self._cell(f"{mix['maxDeltaE']:.2f}" if mix['maxDeltaE'] is not None else '—'))
        self.mixed.clearSelection()
        self.tabs.setTabText(0, f'Physical Filaments ({len(details.physical)})')
        self.tabs.setTabText(1, f'Mixed Recipes ({len(details.mixed)})')
        self._sync_review()

    def set_stale(self, stale, updating=False):
        self.setProperty('outdated', bool(stale))
        self.stale_notice.setText(
            'UPDATING FORECAST · Showing previous optimization results'
            if updating else 'OUTDATED FORECAST · Previous optimization results')
        self.stale_notice.setStyleSheet(
            ('color: #a7e4ff; background: #142532; border: 1px solid #35647c; '
             if updating else
             'color: #ffce80; background: #342715; border: 1px solid #7b5d32; ')
            + 'border-radius: 5px; padding: 7px 9px; font-weight: 700;'
        )
        self.stale_notice.setVisible(bool(stale) and self._details is not None)
        self._sync_review()

    def clear_result(self):
        self._details = None
        self.physical.setRowCount(0)
        self.mixed.setRowCount(0)
        self.summary.setText('Run a forecast to view its physical filaments and mixed recipes.')
        self.constraints.setText('')
        self.tabs.setTabText(0, 'Physical Filaments')
        self.tabs.setTabText(1, 'Mixed Recipes')
        self.set_stale(False)
        self._sync_review()

    def _sync_review(self, *_):
        physical_tab = self.tabs.currentWidget() is self.physical
        row = self.physical.currentRow()
        available = bool(physical_tab and self._details and
                         0 <= row < len(self._details.physical) and self.physical.selectedItems())
        # A recipe is a mixture, not a selectable filament. Avoid showing an
        # inactive button that implies the mixture can be pinned directly.
        self.review.setVisible(physical_tab)
        self.review.setEnabled(available)
        self.hint.setText(
            'Select a physical filament above to locate it in Filaments; no pins are changed.'
            if physical_tab else
            'Mixed recipes combine numbered physical slots. Switch to Physical Filaments '
            'to find or pin their components.'
        )

    def _review(self):
        if self.tabs.currentWidget() is not self.physical or self._details is None:
            return
        row = self.physical.currentRow()
        if row < 0 or row >= len(self._details.physical):
            return
        self.review_filament.emit(self._details.physical[row]['key'])
