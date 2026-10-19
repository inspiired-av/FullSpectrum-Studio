"""Stage 4D-D2 searchable source-to-filament assignment selector."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit,
                              QListWidget, QListWidgetItem, QVBoxLayout)

class SourceColorAssignmentDialog(QDialog):
    def __init__(self, colors, options, assignments, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Assign Source Color to Filament')
        self.setMinimumSize(410,400)
        self._options=list(options)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Source color(s): '+', '.join(colors)))
        layout.addWidget(QLabel('Assign these colors directly to one physical filament. '
                                'The filament will be required and excluded from all mixed recipes.'))
        self.search=QLineEdit(self)
        self.search.setPlaceholderText('Search filament name, brand, series, or HEX…')
        layout.addWidget(self.search)
        self.list=QListWidget(self)
        self.list.setObjectName('sourceAssignmentFilamentList')
        layout.addWidget(self.list)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                      QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Assign Filament')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.search.textChanged.connect(self._filter)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.list.itemDoubleClicked.connect(lambda _item:self.accept())
        for option in sorted(self._options, key=lambda o:str(o.get('name') or o['key']).casefold()):
            name=str(option.get('name') or option['key'])
            color=str(option.get('color') or '')
            series=str(option.get('series') or '')
            brand=str(option.get('brand') or '')
            item=QListWidgetItem(f'{name}  ·  {color}')
            item.setData(Qt.ItemDataRole.UserRole,option['key'])
            item.setData(Qt.ItemDataRole.UserRole+1,
                         f'{name} {color} {series} {brand} {option["key"]}'.casefold())
            pix=QPixmap(16,16)
            pix.fill(QColor(color) if QColor(color).isValid() else QColor('#777777'))
            item.setIcon(QIcon(pix))
            self.list.addItem(item)
        chosen={assignments.get(c) for c in colors}
        if len(chosen)==1:
            existing=next(iter(chosen))
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole)==existing:
                    self.list.setCurrentRow(i)
                    break
        self._update_buttons()
        self.search.setFocus()

    def _filter(self, query):
        value=query.casefold().strip()
        for i in range(self.list.count()):
            item=self.list.item(i)
            item.setHidden(value not in item.data(Qt.ItemDataRole.UserRole+1))
        self._update_buttons()

    def selected_key(self):
        item=self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None and not item.isHidden() else None

    def _update_buttons(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.selected_key()))

    def accept(self):
        if self.selected_key():
            super().accept()
