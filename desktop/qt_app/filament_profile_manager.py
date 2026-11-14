"""Edit or delete saved portable filament profiles; library filaments stay intact."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)
from desktop.qt_app.filament_library_store import (
    delete_saved_profile, generic_filaments, list_profiles, merged_filaments,
    read_personal, saved_profile_revision, update_saved_profile,
)


class ProfileFilamentPicker(QDialog):
    """Search and add known filaments; never mutate the library itself."""
    def __init__(self, records, existing, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Filaments to Profile')
        self.resize(600, 460)
        self.selected_records = []
        from desktop.qt_app.filament_variant_profile_selection import available_profile_variants
        self.records = available_profile_variants(records, existing)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Choose one or more filaments to add to this profile.'))
        self.search=QLineEdit(self)
        self.search.setPlaceholderText('Search name, brand, material or HEX…')
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list=QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for record in self.records:
            label=(f"{record['name']}  ·  {record['brand']}  ·  "
                   f"{record['color']}  ·  {record.get('product_series') or record['series']}")
            item=QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole,record['id'])
            pixmap=QPixmap(16,16);pixmap.fill(QColor(record['color']))
            item.setIcon(QIcon(pixmap))
            self.list.addItem(item)
        layout.addWidget(self.list,1)
        actions=QHBoxLayout()
        self.add=QPushButton('Add Selected')
        self.add.clicked.connect(self._accept)
        self.list.itemSelectionChanged.connect(
            lambda: self.add.setEnabled(bool(self.list.selectedItems())))
        self.add.setEnabled(False)
        actions.addWidget(self.add)
        cancel=QPushButton('Cancel');cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def _filter(self, query):
        needle=query.strip().casefold()
        for i,record in enumerate(self.records):
            item=self.list.item(i)
            search=' '.join(str(record.get(k,'')) for k in
                            ('name','brand','series','product_series','color'))
            item.setHidden(bool(needle and needle not in search.casefold()))
            if item.isHidden():item.setSelected(False)

    def _accept(self):
        ids={item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()
             if not item.isHidden()}
        self.selected_records=[r for r in self.records if r['id'] in ids]
        if not self.selected_records:return
        # Entries are distinguished by stable variant ID, not family + HEX.
        self.accept()


class FilamentProfileManager(QDialog):
    def __init__(self, parent=None, *, library_records=None):
        super().__init__(parent)
        if library_records is None:
            personal,_=read_personal()
            library_records=merged_filaments(personal=personal)
        self.library_records=list(library_records)
        self.setObjectName('filamentProfileManager')
        self.setWindowTitle('Manage Quick Profiles')
        self.resize(620, 460)
        layout = QVBoxLayout(self)
        info = QLabel('Edit a saved palette without removing filaments from the library. '
                      'Built-in profiles cannot be edited or deleted.')
        info.setWordWrap(True)
        layout.addWidget(info)
        top = QHBoxLayout()
        top.addWidget(QLabel('Saved profile:'))
        self.profiles = QComboBox(self)
        self.profiles.setObjectName('savedPaletteProfile')
        self.profiles.currentIndexChanged.connect(self._selection_changed)
        top.addWidget(self.profiles, 1)
        layout.addLayout(top)
        self.filaments = QListWidget(self)
        self.filaments.setObjectName('profileFilaments')
        self.filaments.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.filaments.itemSelectionChanged.connect(self._buttons)
        layout.addWidget(self.filaments, 1)
        controls = QHBoxLayout()
        self.add = QPushButton('Add from Library…')
        self.add.setObjectName('addToSavedProfile')
        self.add.clicked.connect(self._add_from_library)
        controls.addWidget(self.add)
        self.remove = QPushButton('Remove Selected from Profile')
        self.remove.setObjectName('removeProfileFilaments')
        self.remove.clicked.connect(self._remove_selected)
        controls.addWidget(self.remove)
        controls.addStretch(1)
        self.save = QPushButton('Save Profile')
        self.save.setObjectName('saveEditedProfile')
        self.save.clicked.connect(self._save)
        controls.addWidget(self.save)
        self.delete = QPushButton('Delete Profile…')
        self.delete.setObjectName('deleteSavedProfile')
        self.delete.clicked.connect(self._delete)
        controls.addWidget(self.delete)
        layout.addLayout(controls)
        self.message = QLabel('Profiles require at least two different colors.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self._items = []
        self._profile_id = None
        self._revision = None
        self._dirty = False
        self.changed_profile_ids = set()
        self._refresh_profiles()

    def _refresh_profiles(self, focus=None):
        try:
            profiles = list_profiles()
        except (OSError, ValueError) as exc:
            self.message.setText('Unable to read saved profiles: ' + str(exc))
            profiles = []
        self._available = {entry['id']:entry for entry in profiles}
        self.profiles.blockSignals(True)
        self.profiles.clear()
        for entry in profiles:
            self.profiles.addItem(entry['name'], entry['id'])
        self.profiles.setCurrentIndex(max(0, self.profiles.findData(focus)))
        self.profiles.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *_):
        next_id = self.profiles.currentData()
        if self._dirty and next_id != self._profile_id:
            answer = QMessageBox.question(
                self, 'Discard Unsaved Profile Changes?',
                'Changes to this profile have not been saved. Discard them?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.profiles.blockSignals(True)
                self.profiles.setCurrentIndex(self.profiles.findData(self._profile_id))
                self.profiles.blockSignals(False)
                return
        self._profile_id = next_id
        self._items = list(self._available[next_id]['filaments']) if next_id else []
        try:
            self._revision = saved_profile_revision(next_id) if next_id else None
        except (OSError, ValueError) as exc:
            self._revision = None
            self.message.setText('Profile is unavailable: ' + str(exc))
        self._dirty = False
        self._redraw()

    def _redraw(self):
        self.filaments.clear()
        for record in self._items:
            label = f"{record['name']} · {record['brand']} · {record['color']} · {record['series']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, record['id'])
            self.filaments.addItem(item)
        self._buttons()

    def _buttons(self):
        ready = self._profile_id is not None and self._revision is not None
        self.add.setEnabled(ready)
        self.remove.setEnabled(ready and bool(self.filaments.selectedItems()))
        self.save.setEnabled(ready and self._dirty)
        self.delete.setEnabled(ready and not self._dirty)
        if not self._profile_id:
            self.message.setText('No saved profiles. Create one with Save as Quick Profile in the library.')
        elif self._dirty:
            self.message.setText(f'{len(self._items)} filaments · Unsaved profile changes')
        elif self._revision is not None:
            self.message.setText(f'{len(self._items)} filaments · Saved profile')

    def _add_from_library(self):
        if not self._profile_id or self._revision is None:
            return
        picker=ProfileFilamentPicker(self.library_records,self._items,self)
        if picker.exec()!=QDialog.DialogCode.Accepted:
            return
        self._items.extend(picker.selected_records)
        self._dirty=True
        self._redraw()

    def _remove_selected(self):
        identities = {item.data(Qt.ItemDataRole.UserRole) for item in self.filaments.selectedItems()}
        if not identities:
            return
        self._items = [item for item in self._items if item['id'] not in identities]
        self._dirty = True
        self._redraw()

    def _save(self):
        if not self._profile_id or self._revision is None or not self._dirty:
            return
        try:
            new_revision = update_saved_profile(
                self._profile_id, self._items, expected_revision=self._revision)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Save Profile', str(exc))
            return
        self._revision = new_revision
        self._dirty = False
        self._available[self._profile_id]['filaments'] = list(self._items)
        self.changed_profile_ids.add(self._profile_id)
        self._buttons()

    def _delete(self):
        if not self._profile_id or self._revision is None or self._dirty:
            return
        title = self._available[self._profile_id]['name']
        answer = QMessageBox.question(
            self, 'Delete Saved Profile',
            f"Delete '{title}'? Filaments in your library will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_saved_profile(self._profile_id, expected_revision=self._revision)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Delete Profile', str(exc))
            return
        self._dirty = False
        self.changed_profile_ids.add(self._profile_id)
        self._refresh_profiles()

    def reject(self):
        if self._dirty:
            answer = QMessageBox.question(
                self, 'Discard Profile Changes?', 'Discard unsaved changes?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        super().reject()
