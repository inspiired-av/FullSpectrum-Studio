"""Embedded quick-profile manager for the unified filament library.

A profile references a portable snapshot of selected filaments. This editor only
modifies FullSpectrum-managed profiles, never catalog, slicer, or model files.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)
from desktop.qt_app.filament_library_store import (
    delete_saved_profile, list_profiles, profile_choices, save_profile,
    saved_profile_revision, update_saved_profile,
)


def _filament_item(record):
    label = f"{record['name']} · {record['brand']} · {record['color']}"
    item = QListWidgetItem(label)
    item.setData(Qt.ItemDataRole.UserRole, record['id'])
    pix = QPixmap(17, 17)
    pix.fill(QColor(record['color']))
    item.setIcon(QIcon(pix))
    item.setToolTip(f"{record['name']} · {record['brand']}\n"
                    f"{record.get('product_series') or record['series']} · {record['color']}")
    return item


class FilamentProfileTab(QWidget):
    """One-pane profile workflow; no nested library or profile-manager dialog.

    Left: named profiles. Middle: this profile's colors. Right: library choices.
    Staged edits are never written until the user clicks Save Profile.
    """
    profile_changed = Signal(str)
    profile_activated = Signal(object)
    import_requested = Signal()

    def __init__(self, library_records=(), selected_provider=None, parent=None):
        super().__init__(parent)
        self.setObjectName('embeddedFilamentProfileTab')
        self.library_records = list(library_records)
        # Imported palettes keep their own embedded snapshots. Show those
        # colors as addable options even when they are not in the global catalog.
        self._saved_profile_entries = []
        self.selected_provider = selected_provider or (lambda: [])
        self.changed_profile_ids = set()
        self._available_profiles = {}
        self._profile_id = None
        self._revision = None
        self._draft_name = None
        self._items = []
        self._dirty = False
        self._switching = False
        col = QVBoxLayout(self)
        col.setContentsMargins(5, 8, 5, 4)
        col.setSpacing(7)
        hint = QLabel('Choose a profile, then add or remove colors beside it. '
                      'Saving changes the profile only; the filament library stays intact.')
        hint.setWordWrap(True)
        col.addWidget(hint)

        panes = QSplitter(Qt.Orientation.Horizontal, self)
        panes.setObjectName('profileEditorSplit')
        panes.setChildrenCollapsible(False)
        col.addWidget(panes, 1)

        left = QWidget(panes)
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(2, 2, 4, 2)
        lcol.addWidget(QLabel('SAVED PROFILES'))
        self.profiles = QListWidget(left)
        self.profiles.setObjectName('embeddedProfileList')
        self.profiles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.profiles.currentItemChanged.connect(self._selection_changed)
        lcol.addWidget(self.profiles, 1)
        self.create_button = QPushButton('New Profile…')
        self.create_button.setObjectName('newEmbeddedProfile')
        self.create_button.setToolTip('Start with checked filaments, or create an empty draft and add colors on the right.')
        self.create_button.clicked.connect(self._new_profile)
        lcol.addWidget(self.create_button)
        self.duplicate_button = QPushButton('Duplicate Profile…')
        self.duplicate_button.setToolTip('Create an editable copy, including from a built-in kit.')
        self.duplicate_button.clicked.connect(self._duplicate_profile)
        lcol.addWidget(self.duplicate_button)
        self.import_button = QPushButton('Import Profile…')
        self.import_button.clicked.connect(self.import_requested.emit)
        lcol.addWidget(self.import_button)
        self.delete_button = QPushButton('Delete Profile…')
        self.delete_button.clicked.connect(self._delete_profile)
        lcol.addWidget(self.delete_button)
        panes.addWidget(left)

        middle = QWidget(panes)
        mcol = QVBoxLayout(middle)
        mcol.setContentsMargins(4, 2, 4, 2)
        self.profile_heading = QLabel('PROFILE FILAMENTS')
        mcol.addWidget(self.profile_heading)
        self.in_profile = QListWidget(middle)
        self.in_profile.setObjectName('embeddedProfileFilaments')
        self.in_profile.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.in_profile.itemSelectionChanged.connect(self._update_buttons)
        mcol.addWidget(self.in_profile, 1)
        self.remove_button = QPushButton('Remove Selected ←')
        self.remove_button.setObjectName('removeEmbeddedProfileFilaments')
        self.remove_button.clicked.connect(self._remove_selected)
        mcol.addWidget(self.remove_button)
        panes.addWidget(middle)

        right = QWidget(panes)
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(4, 2, 2, 2)
        rcol.addWidget(QLabel('ADD FROM FILAMENT LIBRARY'))
        self.search = QLineEdit(right)
        self.search.setPlaceholderText('Search brand, color, HEX…')
        self.search.textChanged.connect(self._filter)
        rcol.addWidget(self.search)
        self.available = QListWidget(right)
        self.available.setObjectName('embeddedAvailableFilaments')
        self.available.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.available.itemSelectionChanged.connect(self._update_buttons)
        rcol.addWidget(self.available, 1)
        self.add_button = QPushButton('← Add Selected')
        self.add_button.setObjectName('addEmbeddedProfileFilaments')
        self.add_button.clicked.connect(self._add_selected)
        rcol.addWidget(self.add_button)
        panes.addWidget(right)
        panes.setSizes([210, 315, 340])
        panes.setStretchFactor(0, 0)
        panes.setStretchFactor(1, 1)
        panes.setStretchFactor(2, 1)

        footer = QHBoxLayout()
        self.message = QLabel('Choose an existing profile or create one.')
        self.message.setWordWrap(True)
        footer.addWidget(self.message, 1)
        self.use_button = QPushButton('Use This Profile')
        self.use_button.setObjectName('useEmbeddedProfile')
        self.use_button.clicked.connect(self._use_profile)
        footer.addWidget(self.use_button)
        self.save_button = QPushButton('Save Profile')
        self.save_button.setObjectName('saveEmbeddedProfile')
        self.save_button.clicked.connect(self._save)
        footer.addWidget(self.save_button)
        col.addLayout(footer)
        self.set_library_records(self.library_records)
        self.refresh_profiles()

    @property
    def has_unsaved_changes(self):
        return bool(self._dirty)

    def confirm_discard(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, 'Discard Unsaved Profile Changes?',
            'Your profile changes have not been saved. Discard them?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def set_library_records(self, records):
        self.library_records = list(records)
        self._populate_available()

    def _populate_available(self):
        previous = {i.data(Qt.ItemDataRole.UserRole)
                    for i in self.available.selectedItems()}
        self.available.clear()
        self._catalog = {}
        current_ids = {r['id'] for r in self._items}
        current_keys = {(r['series'], r['color']) for r in self._items}
        seen_ids = set()
        for r in [*self.library_records, *self._saved_profile_entries]:
            if r['id'] in seen_ids:
                continue
            seen_ids.add(r['id'])
            if r['material'] != 'PLA' or r['id'] in current_ids:
                continue
            if (r['series'], r['color']) in current_keys:
                continue  # Engine cannot distinguish duplicate series+HEX.
            self._catalog[r['id']] = r
            item = _filament_item(r)
            self.available.addItem(item)
            if r['id'] in previous:
                item.setSelected(True)
        self._filter(self.search.text())
        self._update_buttons()

    def _filter(self, query):
        needle = query.strip().casefold()
        for i in range(self.available.count()):
            widget = self.available.item(i)
            record = self._catalog[widget.data(Qt.ItemDataRole.UserRole)]
            haystack = ' '.join(str(record.get(k, '')) for k in
                                ('name', 'brand', 'color', 'series', 'product_series')).casefold()
            hidden = bool(needle and needle not in haystack)
            widget.setHidden(hidden)
            if hidden:
                widget.setSelected(False)
        self._update_buttons()

    def refresh_profiles(self, focus=None):
        """Refresh names without overwriting an unsaved editing draft."""
        if self._dirty:
            return
        try:
            profiles = profile_choices()
        except (OSError, ValueError) as exc:
            self.message.setText('Unable to load saved profiles: ' + str(exc))
            return
        self._available_profiles = {r['id']: r for r in profiles}
        self._saved_profile_entries = [record for profile in profiles
                                       for record in profile['filaments']]
        previous = focus or self._profile_id
        self._switching = True
        self.profiles.clear()
        target = None
        for profile in profiles:
            item = QListWidgetItem(profile['name'])
            item.setData(Qt.ItemDataRole.UserRole, profile['id'])
            if str(profile['id']).startswith('builtin:'):
                item.setToolTip('Read-only built-in profile')
            self.profiles.addItem(item)
            if profile['id'] == previous:
                target = item
        if target is None and self.profiles.count():
            target = self.profiles.item(0)
        self.profiles.setCurrentItem(target)
        self._switching = False
        self._selection_changed(target, None)
        self._populate_available()

    def _selection_changed(self, current, previous):
        if self._switching:
            return
        next_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        if self._dirty and not self.confirm_discard():
            self._switching = True
            if previous is None:
                self.profiles.setCurrentRow(-1)
            else:
                self.profiles.setCurrentItem(previous)
            self._switching = False
            return
        self._profile_id = next_id
        self._draft_name = None
        self._dirty = False
        profile = self._available_profiles.get(next_id)
        self._items = list(profile['filaments']) if profile else []
        try:
            self._revision = (saved_profile_revision(next_id)
                              if next_id and not str(next_id).startswith('builtin:') else None)
        except (OSError, ValueError) as exc:
            self._revision = None
            self.message.setText('Profile unavailable: ' + str(exc))
        self._redraw()

    def _new_profile(self):
        if self._dirty and not self.confirm_discard():
            return
        name, ok = QInputDialog.getText(self, 'New Quick Profile', 'Profile name:')
        name = name.strip()
        if not ok or not name:
            return
        if any(p['name'].casefold() == name.casefold()
               for p in self._available_profiles.values()):
            QMessageBox.warning(self, 'Profile Already Exists',
                                'Choose another name, or select and edit the existing profile.')
            return
        self._switching = True
        self.profiles.clearSelection()
        self.profiles.setCurrentRow(-1)
        self._switching = False
        self._profile_id = None
        self._revision = None
        self._draft_name = name
        self._items = [r for r in self.selected_provider() if r['material'] == 'PLA']
        self._dirty = True
        self._redraw()

    def _duplicate_profile(self):
        if self._dirty and not self.confirm_discard():
            return
        source = self._available_profiles.get(self._profile_id)
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, 'Duplicate Quick Profile', 'New profile name:',
            text=source['name'] + ' Copy')
        name = name.strip()
        if not ok or not name:
            return
        if any(p['name'].casefold() == name.casefold()
               for p in self._available_profiles.values()):
            QMessageBox.warning(self, 'Profile Already Exists',
                                'Choose a different name for the editable copy.')
            return
        self._switching = True
        self.profiles.clearSelection()
        self.profiles.setCurrentRow(-1)
        self._switching = False
        self._profile_id = None
        self._revision = None
        self._draft_name = name
        self._items = list(source['filaments'])
        self._dirty = True
        self._redraw()

    def _redraw(self):
        self.in_profile.clear()
        for r in self._items:
            self.in_profile.addItem(_filament_item(r))
        self._populate_available()
        self._update_buttons()

    def _update_buttons(self):
        editing = bool(self._draft_name or (self._profile_id and self._revision is not None))
        built_in = bool(self._profile_id and str(self._profile_id).startswith('builtin:'))
        self.add_button.setEnabled(editing and bool(self.available.selectedItems()))
        self.remove_button.setEnabled(editing and bool(self.in_profile.selectedItems()))
        valid = len(self._items) >= 2 and len({r['color'] for r in self._items}) >= 2
        self.save_button.setEnabled(editing and self._dirty and valid)
        self.delete_button.setEnabled(bool(self._profile_id and not built_in and
                                           self._revision is not None and not self._dirty))
        self.use_button.setEnabled(valid and not self._dirty and bool(self._profile_id))
        self.duplicate_button.setEnabled(bool(self._profile_id))
        label = self._draft_name or (self._available_profiles.get(self._profile_id) or {}).get('name')
        if self._dirty:
            state = 'Unsaved changes' if not self._draft_name else 'New profile draft'
            self.message.setText(f'{label} · {len(self._items)} colors · {state}'
                                 + ('' if valid else ' · Needs at least 2 distinct colors'))
        elif label:
            kind = 'Built-in / read-only' if built_in else 'Saved profile'
            self.message.setText(f'{label} · {len(self._items)} colors · {kind}')
        else:
            self.message.setText('Select a profile, or create one.')
        self.profile_heading.setText('PROFILE FILAMENTS' if not label else f'PROFILE FILAMENTS · {len(self._items)}')

    def _add_selected(self):
        existing_ids = {r['id'] for r in self._items}
        existing_keys = {(r['series'], r['color']) for r in self._items}
        additions = []
        for widget in self.available.selectedItems():
            r = self._catalog[widget.data(Qt.ItemDataRole.UserRole)]
            if r['id'] in existing_ids:
                continue
            key = (r['series'], r['color'])
            if key in existing_keys:
                QMessageBox.warning(self, 'Duplicate Filament Color',
                    'Two entries with the same PLA slicer family and HEX cannot both be active. '
                    'Choose one brand for this palette.')
                return
            additions.append(r)
            existing_ids.add(r['id'])
            existing_keys.add(key)
        if additions:
            self._items.extend(additions)
            self._dirty = True
            self._redraw()

    def _remove_selected(self):
        ids = {item.data(Qt.ItemDataRole.UserRole)
               for item in self.in_profile.selectedItems()}
        if ids:
            self._items = [r for r in self._items if r['id'] not in ids]
            self._dirty = True
            self._redraw()

    def _save(self):
        try:
            if self._draft_name:
                identity = save_profile(self._draft_name, self._items)
            elif self._profile_id and self._revision is not None:
                update_saved_profile(self._profile_id, self._items,
                                     expected_revision=self._revision)
                identity = self._profile_id
            else:
                return
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Cannot Save Profile', str(exc))
            return
        self.changed_profile_ids.add(identity)
        self._dirty = False
        self._draft_name = None
        self.profile_changed.emit(identity)
        self.refresh_profiles(focus=identity)

    def _delete_profile(self):
        if not self._profile_id or self._revision is None or self._dirty:
            return
        name = self._available_profiles[self._profile_id]['name']
        response = QMessageBox.question(
            self, 'Delete Saved Profile',
            f"Delete '{name}'? Filaments in the main library will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_saved_profile(self._profile_id, expected_revision=self._revision)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Cannot Delete Profile', str(exc))
            return
        deleted = self._profile_id
        self.changed_profile_ids.add(deleted)
        self._profile_id = None
        self._revision = None
        self._dirty = False
        self.profile_changed.emit(deleted)
        self.refresh_profiles()

    def _use_profile(self):
        if self._dirty or not self._profile_id:
            return
        self.profile_activated.emit(list(self._items))
