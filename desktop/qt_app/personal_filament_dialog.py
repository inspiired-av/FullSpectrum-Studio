"""Qt editor for user-managed custom PLA filament candidates.

This editor does not modify printer inventory or downloaded Bambu catalog files.
The saved JSON is deliberately the format accepted by engine.custom_palette().
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from desktop.qt_app.personal_filament_library import (
    FAMILIES, load_personal_library, normalize_filament, personal_library_path,
    ready_for_planning, save_personal_library, validate_library,
)


class FilamentEntryDialog(QDialog):
    def __init__(self, filament=None, parent=None):
        super().__init__(parent)
        filament = filament or {}
        self.setWindowTitle('Edit Filament' if filament else 'Add Filament')
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Add the filament color and an appropriate PLA profile. '
                                'Mixing accuracy is an estimate, not measured calibration.'))
        form = QFormLayout()
        self.name = QLineEdit(str(filament.get('name', '')))
        self.name.setPlaceholderText('e.g. Panchroma Cyan')
        self.brand = QLineEdit(str(filament.get('brand', 'Custom')))
        self.brand.setPlaceholderText('Manufacturer')
        self.series = QComboBox()
        self.series.addItems(FAMILIES)
        idx = self.series.findText(str(filament.get('series', 'PLA Basic')))
        self.series.setCurrentIndex(max(0, idx))
        self.color = QLineEdit(str(filament.get('color', '#FFFFFF')))
        self.color.setMaxLength(7)
        self.color.setPlaceholderText('#RRGGBB')
        color_row = QHBoxLayout()
        color_row.addWidget(self.color, 1)
        choose = QPushButton('Choose…')
        choose.clicked.connect(self._choose_color)
        color_row.addWidget(choose)
        form.addRow('Name', self.name)
        form.addRow('Brand', self.brand)
        form.addRow('Material profile', self.series)
        form.addRow('HEX color', color_row)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Save Filament')
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.entry = None

    def _choose_color(self):
        initial = QColor(self.color.text())
        chosen = QColorDialog.getColor(initial if initial.isValid() else QColor('#FFFFFF'), self)
        if chosen.isValid():
            self.color.setText(chosen.name().upper())

    def _validate_and_accept(self):
        try:
            self.entry = normalize_filament({
                'name': self.name.text(), 'brand': self.brand.text(),
                'series': self.series.currentText(), 'color': self.color.text(),
            })
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid Filament', str(exc))
            return
        self.accept()


class PersonalFilamentsDialog(QDialog):
    """Small transactional Add/Edit/Remove UI; Save writes the owned JSON."""
    def __init__(self, path=None, parent=None, *, start_with_add=False):
        super().__init__(parent)
        self.path = personal_library_path(path)
        self.items = load_personal_library(self.path)
        self.saved_path = None
        self.setWindowTitle('My Filaments')
        self.setMinimumSize(580, 390)
        layout = QVBoxLayout(self)
        explanation = QLabel('Manage your personal PLA filaments without editing JSON. '
                             'These filaments are used as a Custom library source; '
                             'the built-in catalog and inventory are unchanged.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName('personalFilamentTable')
        self.table.setHorizontalHeaderLabels(['Color', 'Filament', 'Brand', 'Material profile'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 96)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 115)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        layout.addWidget(self.table, 1)
        commands = QHBoxLayout()
        self.add_button = QPushButton('Add Filament…')
        self.edit_button = QPushButton('Edit…')
        self.remove_button = QPushButton('Remove')
        self.add_button.clicked.connect(self.add_entry)
        self.edit_button.clicked.connect(self.edit_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        for button in (self.add_button, self.edit_button, self.remove_button):
            commands.addWidget(button)
        commands.addStretch(1)
        layout.addLayout(commands)
        self.note = QLabel('At least two distinct colors are required to run a forecast or export.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('Save Library')
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._refresh_table()
        if start_with_add:
            QTimer.singleShot(0, self.add_entry)

    def _selected_index(self):
        index = self.table.currentRow()
        return index if 0 <= index < len(self.items) else None

    def _update_actions(self):
        selected = self._selected_index() is not None
        self.edit_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def _refresh_table(self, selected=None):
        self.table.setRowCount(len(self.items))
        for row, entry in enumerate(self.items):
            for col, field in enumerate(('color', 'name', 'brand', 'series')):
                cell = QTableWidgetItem(entry[field])
                if col == 0:
                    cell.setToolTip('Source filament swatch (six-digit HEX)')
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 29)
        if selected is not None and 0 <= selected < len(self.items):
            self.table.selectRow(selected)
        self._update_actions()
        unique = len({item['color'] for item in self.items})
        self.note.setText(f'{len(self.items)} saved candidate(s) · {unique} distinct color(s). '
            + ('Ready for the Custom library optimizer.' if unique >= 2 else
               'Add at least two distinct colors before selecting this library for planning.'))

    def add_entry(self):
        dialog = FilamentEntryDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        proposed = [*self.items, dialog.entry]
        try:
            self.items = validate_library(proposed)
        except ValueError as exc:
            QMessageBox.warning(self, 'Duplicate Filament', str(exc))
            return
        self._refresh_table(len(self.items) - 1)

    def edit_selected(self):
        selected = self._selected_index()
        if selected is None:
            return
        dialog = FilamentEntryDialog(self.items[selected], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        proposed = list(self.items)
        proposed[selected] = dialog.entry
        try:
            self.items = validate_library(proposed)
        except ValueError as exc:
            QMessageBox.warning(self, 'Duplicate Filament', str(exc))
            return
        self._refresh_table(selected)

    def remove_selected(self):
        selected = self._selected_index()
        if selected is None:
            return
        choice = QMessageBox.question(
            self, 'Remove Filament',
            f"Remove '{self.items[selected]['name']}' from My Filaments?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if choice != QMessageBox.StandardButton.Yes:
            return
        del self.items[selected]
        self._refresh_table(min(selected, len(self.items)-1))

    def _save(self):
        try:
            self.saved_path = save_personal_library(self.items, self.path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Save Personal Filaments', str(exc))
            return
        self.accept()

    @property
    def ready(self):
        return ready_for_planning(self.items)
