"""Qt controls and background workers for locally installed slicer build plates.

No renderer objects or QOpenGLWidget methods are called from worker threads.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QCheckBox, QPushButton,
    QListWidgetItem, QVBoxLayout,
)

from desktop.qt_app.plate_catalog import discover_installed_plates
from desktop.qt_app.plate_picker_policy import preferred_plate_assets
from desktop.qt_app.plate_mesh import load_plate_mesh


class PlateCatalogWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, *, resource_roots=(), slicer_executables=(), parent=None):
        super().__init__(parent)
        self.resource_roots = tuple(resource_roots)
        self.slicer_executables = tuple(slicer_executables)

    def run(self):
        try:
            catalog = discover_installed_plates(
                resource_roots=self.resource_roots,
                slicer_executables=self.slicer_executables)
            self.completed.emit(catalog, None)
        except Exception as exc:
            self.completed.emit(None, str(exc))


class PlateLoadWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = Path(path)

    def run(self):
        try:
            self.completed.emit(load_plate_mesh(self.path), None)
        except Exception as exc:
            self.completed.emit(None, str(exc))


class PlatePickerDialog(QDialog):
    """Searchable list; unlike a giant QMenu, scales to hundreds of vendors."""

    def __init__(self, plates, parent=None, *, saved_default=None):
        super().__init__(parent)
        self.setWindowTitle('Choose Installed 3D Build Plate')
        self.setMinimumSize(540, 440)
        self.plates = preferred_plate_assets(plates)
        self.saved_default = saved_default if isinstance(saved_default, dict) else {}
        self.clear_saved_default = False
        self.selected_asset = None
        layout = QVBoxLayout(self)
        description = QLabel('Choose a printer plate from your installed slicers. Preview only.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.filter = QLineEdit()
        self.filter.setObjectName('plateSearch')
        self.filter.setPlaceholderText('Search printers, vendors or slicers…')
        self.filter.textChanged.connect(self._filter_items)
        layout.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setObjectName('installedPlateList')
        self.list.itemDoubleClicked.connect(self._accept)
        self.list.itemSelectionChanged.connect(self._refresh_actions)
        layout.addWidget(self.list, stretch=1)
        self.count = QLabel()
        layout.addWidget(self.count)
        defaults = QHBoxLayout()
        self.remember_default = QCheckBox('Remember selected plate as default')
        self.remember_default.setEnabled(True)
        self.remember_default.setObjectName("rememberBuildPlateDefault")
        defaults.addWidget(self.remember_default, 1)
        self.forget_default_button = QPushButton('Clear default')
        self.forget_default_button.setObjectName("clearBuildPlateDefault")
        self.forget_default_button.setVisible(bool(self.saved_default))
        self.forget_default_button.setToolTip("Forget saved build plate selection")
        self.forget_default_button.clicked.connect(self._forget_default)
        defaults.addWidget(self.forget_default_button)
        layout.addLayout(defaults)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._filter_items('')
        self.filter.setFocus()

    def _filter_items(self, query):
        query = query.casefold().strip()
        self.list.clear()
        matches = 0
        for asset in self.plates:
            label = f'{asset.printer} · {asset.vendor} · from {asset.source}'
            if query and query not in label.casefold():
                continue
            item = QListWidgetItem(label)
            item.setToolTip(f'Mesh: {asset.model.name}\nTexture: {asset.texture.name if asset.texture else "None"}')
            item.setData(Qt.ItemDataRole.UserRole, asset)
            self.list.addItem(item)
            matches += 1
        self.count.setText(f'{matches} matching build plates')
        self._refresh_actions()

    def _forget_default(self):
        self.clear_saved_default = True
        self.saved_default = {}
        self.remember_default.setChecked(False)
        self.forget_default_button.setVisible(False)

    def _refresh_actions(self):
        item = self.list.currentItem()
        self.remember_default.setEnabled(True)
        if item is not None:
            asset = item.data(Qt.ItemDataRole.UserRole)
            saved = self.saved_default
            same_default = (str(saved.get('printer', '')).casefold() == asset.printer.casefold()
                            and str(saved.get('vendor', '')).casefold() == asset.vendor.casefold()
                            and str(saved.get('source', '')).casefold() == asset.source.casefold())
            self.remember_default.setChecked(same_default)
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok:
            ok.setEnabled(self.list.currentItem() is not None)

    def _accept(self, *_args):
        item = self.list.currentItem()
        if item is None:
            return
        self.selected_asset = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
