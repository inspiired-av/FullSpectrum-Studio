"""Compact, in-app quick-profile editor for the Filaments workspace.

User profiles are always edited in FullSpectrum-managed storage. Existing
filament catalog entries are immutable; removing a color from a profile never
removes it from the catalog. No model, slicer preset, or engine file is written.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from desktop.qt_app import filament_library_store as store


class FilamentProfileSidebar(QWidget):
    """Small persistent profile list beside the normal filament-selection table."""

    palette_ready = Signal(str)
    profiles_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('filamentProfileSidebar')
        self._profiles = {}
        self._identity = None
        self._revision = None
        self._draft_name = None
        self._items = []
        self._original_items = []
        self._dirty = False
        self._switching = False
        self._active = False
        self.setMinimumWidth(168)
        self.setMaximumWidth(252)
        self.setStyleSheet('''
            QWidget#filamentProfileSidebar {
                background: #171d24; border: 1px solid #344550; border-radius: 6px;
            }
            QWidget#filamentProfileSidebar QLabel { color: #c2dce8; }
            QWidget#filamentProfileSidebar QListWidget {
                color: #d9e6ec; background: #171d24;
                border: 1px solid #2b3945; outline: none;
            }
            QWidget#filamentProfileSidebar QListWidget::item { padding: 3px; }
            QWidget#filamentProfileSidebar QListWidget::item:selected {
                color: #fff; background: #2b5361;
            }
        ''')
        col = QVBoxLayout(self)
        col.setContentsMargins(7, 8, 7, 7)
        col.setSpacing(6)
        heading = QLabel('SAVED PROFILES')
        heading.setObjectName('profileSidebarHeading')
        col.addWidget(heading)
        self.profiles = QListWidget(self)
        self.profiles.setObjectName('sidebarSavedProfiles')
        self.profiles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.profiles.setMinimumHeight(82)
        self.profiles.currentItemChanged.connect(self._selected_profile)
        col.addWidget(self.profiles, 1)
        self.color_heading = QLabel('PROFILE FILAMENTS')
        col.addWidget(self.color_heading)
        self.colors = QListWidget(self)
        self.colors.setObjectName('sidebarProfileFilaments')
        self.colors.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.colors.setMinimumHeight(108)
        self.colors.itemSelectionChanged.connect(self._update_controls)
        col.addWidget(self.colors, 2)
        edit_row = QHBoxLayout()
        edit_row.setSpacing(4)
        self.add_button = QPushButton('+ Add')
        self.add_button.setObjectName('sidebarAddProfileFilaments')
        self.add_button.setToolTip('Select one or more filaments from the full library')
        self.add_button.clicked.connect(self._add_from_library)
        edit_row.addWidget(self.add_button, 1)
        self.remove_button = QPushButton('− Remove')
        self.remove_button.setObjectName('sidebarRemoveProfileFilaments')
        self.remove_button.clicked.connect(self._remove)
        edit_row.addWidget(self.remove_button, 1)
        col.addLayout(edit_row)
        profile_row = QHBoxLayout()
        profile_row.setSpacing(4)
        self.new_button = QPushButton('New')
        self.new_button.setObjectName('sidebarNewProfile')
        self.new_button.clicked.connect(self._new)
        profile_row.addWidget(self.new_button, 1)
        self.copy_button = QPushButton('Copy')
        self.copy_button.setToolTip('Duplicate the selected profile, including built-in kits')
        self.copy_button.clicked.connect(self._copy)
        profile_row.addWidget(self.copy_button, 1)
        self.import_button = QPushButton('Import')
        self.import_button.clicked.connect(self._import)
        profile_row.addWidget(self.import_button, 1)
        col.addLayout(profile_row)
        self.message = QLabel('Select a profile to edit or use.')
        self.message.setObjectName('profileSidebarStatus')
        self.message.setWordWrap(True)
        col.addWidget(self.message)
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        self.save_button = QPushButton('Save')
        self.save_button.setObjectName('sidebarSaveProfile')
        self.save_button.clicked.connect(self._save)
        action_row.addWidget(self.save_button, 1)
        self.use_button = QPushButton('Use Profile')
        self.use_button.setObjectName('sidebarActivateProfile')
        self.use_button.clicked.connect(self._use)
        action_row.addWidget(self.use_button, 1)
        col.addLayout(action_row)
        self.delete_button = QPushButton('Delete Profile…')
        self.delete_button.setObjectName('sidebarDeleteProfile')
        self.delete_button.clicked.connect(self._delete)
        col.addWidget(self.delete_button)
        self.refresh()

    @property
    def has_unsaved_changes(self):
        return self._dirty

    def confirm_discard(self):
        if not self._dirty:
            return True
        choice = QMessageBox.question(
            self, 'Discard Profile Edits?', 'Discard unsaved profile changes?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return choice == QMessageBox.StandardButton.Yes

    def refresh(self, focus=None):
        """Refresh names without clobbering any staged edits."""
        if self._dirty:
            return
        try:
            profiles = store.profile_choices()
        except (OSError, ValueError) as error:
            self.message.setText('Profiles unavailable: ' + str(error))
            return
        self._profiles = {p['id']: p for p in profiles}
        target_id = focus or self._identity
        self._switching = True
        self.profiles.clear()
        target = None
        for profile in profiles:
            item = QListWidgetItem(profile['name'])
            item.setData(Qt.ItemDataRole.UserRole, profile['id'])
            item.setToolTip('Built-in profile (copy to edit)' if
                            profile['id'].startswith('builtin:') else profile['name'])
            self.profiles.addItem(item)
            if profile['id'] == target_id:
                target = item
        if target is None and self.profiles.count():
            target = self.profiles.item(0)
        self.profiles.setCurrentItem(target)
        self._switching = False
        self._selected_profile(target, None)

    def _selected_profile(self, current, previous):
        if self._switching:
            return
        if self._dirty and not self.confirm_discard():
            self._switching = True
            self.profiles.setCurrentItem(previous)
            self._switching = False
            return
        identity = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._identity = identity
        self._draft_name = None
        self._dirty = False
        profile = self._profiles.get(identity)
        self._items = list(profile['filaments']) if profile else []
        self._original_items = list(self._items)
        self._revision = None
        if identity and not identity.startswith('builtin:'):
            try:
                self._revision = store.saved_profile_revision(identity)
            except (OSError, ValueError) as error:
                self.message.setText('Profile unavailable: ' + str(error))
        self._redraw()

    def _redraw(self):
        self.colors.clear()
        for record in self._items:
            item = QListWidgetItem(record['name'])
            item.setData(Qt.ItemDataRole.UserRole, record['id'])
            item.setToolTip(f"{record['name']} · {record['brand']} · {record['color']}\n"
                            f"{record.get('product_series') or record['series']}")
            icon = QPixmap(15, 15)
            icon.fill(QColor(record['color']))
            item.setIcon(QIcon(icon))
            self.colors.addItem(item)
        self._update_controls()

    def _update_controls(self):
        editable = bool(self._draft_name or self._revision is not None)
        valid = len(self._items) >= 2 and len({r['color'] for r in self._items}) >= 2
        self.add_button.setEnabled(editable)
        self.remove_button.setEnabled(editable and bool(self.colors.selectedItems()))
        self.save_button.setEnabled(editable and self._dirty and valid)
        self.delete_button.setEnabled(self._revision is not None and not self._dirty)
        self.copy_button.setEnabled(bool(self._identity))
        self.use_button.setEnabled(bool(self._identity) and not self._dirty and valid)
        self.color_heading.setText(f'PROFILE FILAMENTS · {len(self._items)}')
        if self._draft_name:
            label = self._draft_name + ' · unsaved'
        elif self._identity:
            label = ('Built-in · copy to edit' if self._identity.startswith('builtin:') else
                     'Unsaved edits' if self._dirty else 'Saved profile')
        else:
            label = 'Select a profile or create one.'
        if self._dirty and not valid:
            label += ' · Needs 2 distinct colors'
        self.message.setText(label)

    def _new(self):
        if not self.confirm_discard():
            return
        title, ok = QInputDialog.getText(self, 'New Quick Profile', 'Profile name:')
        title = title.strip()
        if not ok or not title:
            return
        if any(p['name'].casefold() == title.casefold() for p in self._profiles.values()):
            QMessageBox.warning(self, 'Profile Exists', 'Choose another name or edit the existing profile.')
            return
        self._switching = True
        self.profiles.setCurrentRow(-1)
        self._switching = False
        self._identity = None
        self._revision = None
        self._draft_name = title
        self._items = []
        self._original_items = []
        self._dirty = True
        self._redraw()

    def _copy(self):
        profile = self._profiles.get(self._identity)
        if not profile or not self.confirm_discard():
            return
        title, ok = QInputDialog.getText(
            self, 'Duplicate Profile', 'New profile name:', text=profile['name'] + ' Copy')
        title = title.strip()
        if not ok or not title:
            return
        if any(p['name'].casefold() == title.casefold() for p in self._profiles.values()):
            QMessageBox.warning(self, 'Profile Exists', 'Choose a different profile name.')
            return
        self._switching = True
        self.profiles.setCurrentRow(-1)
        self._switching = False
        self._identity = None
        self._revision = None
        self._draft_name = title
        self._items = list(profile['filaments'])
        self._original_items = list(self._items)
        self._dirty = True
        self._redraw()

    def _known_records(self):
        # Imported profiles have embedded snapshots that may not appear in the
        # Bambu catalog; preserve access to those records after a removal.
        personal, _ = store.read_personal()
        catalog = store.bambu_catalog_filaments()
        known = [*store.merged_filaments(catalog, personal), *self._original_items]
        for profile in store.profile_choices():
            known.extend(profile['filaments'])
        unique = {}
        for record in known:
            unique[record['id']] = record
        return list(unique.values())

    def _add_from_library(self):
        if not (self._draft_name or self._revision is not None):
            return
        try:
            from desktop.qt_app.filament_profile_manager import ProfileFilamentPicker
            picker = ProfileFilamentPicker(self._known_records(), self._items, self)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot Browse Filaments', str(error))
            return
        if picker.exec() != picker.DialogCode.Accepted:
            return
        additions = list(picker.selected_records)
        if not additions:
            return
        candidate = [*self._items, *additions]
        # An unfinished draft may contain one color. Validate the identity
        # constraints now; the store enforces >=2 distinct colors at Save.
        keys = [(r['series'], r['color']) for r in candidate]
        if (len(candidate) > 32 or len(keys) != len(set(keys)) or
                any(r['material'] != 'PLA' for r in candidate)):
            QMessageBox.warning(self, 'Cannot Add Filaments',
                'The palette needs unique PLA family/HEX combinations and at most 32 candidates.')
            return
        self._items = candidate
        self._dirty = True
        self._redraw()

    def _remove(self):
        identities = {item.data(Qt.ItemDataRole.UserRole)
                      for item in self.colors.selectedItems()}
        if not identities:
            return
        self._items = [record for record in self._items if record['id'] not in identities]
        self._dirty = True
        self._redraw()

    def _save(self):
        try:
            if self._draft_name:
                identity = store.save_profile(self._draft_name, self._items)
            elif self._revision is not None:
                store.update_saved_profile(self._identity, self._items,
                                           expected_revision=self._revision)
                identity = self._identity
            else:
                return
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot Save Profile', str(error))
            return
        self._dirty = False
        self._draft_name = None
        self._identity = identity
        self.profiles_changed.emit(identity)
        self.refresh(focus=identity)

    def _delete(self):
        if self._revision is None or self._dirty:
            return
        profile = self._profiles.get(self._identity)
        if not profile:
            return
        answer = QMessageBox.question(
            self, 'Delete Quick Profile',
            f"Delete '{profile['name']}'? Its filaments will remain in the library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            store.delete_saved_profile(self._identity, expected_revision=self._revision)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot Delete Profile', str(error))
            return
        deleted = self._identity
        self._dirty = False
        self._identity = None
        self.profiles_changed.emit(deleted)
        self.refresh()

    def _import(self):
        if not self.confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Palette Profile', '', 'JSON palette files (*.json)')
        if not filename:
            return
        try:
            title, _ = store.parse_import_profile(filename)
            existing = next((p for p in store.list_profiles()
                             if p['name'].casefold() == title.casefold()), None)
            if existing:
                answer = QMessageBox.question(
                    self, 'Replace Existing Profile?',
                    f"Replace '{existing['name']}' with the imported colors? "
                    'The original JSON will remain unchanged.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                identity = store.import_profile(
                    filename, replace_profile_id=existing['id'],
                    expected_revision=store.saved_profile_revision(existing['id']))
            else:
                identity = store.import_profile(filename)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot Import Palette', str(error))
            return
        self._dirty = False
        self.profiles_changed.emit(identity)
        self.refresh(focus=identity)

    def _use(self):
        if not self._identity or self._dirty:
            return
        try:
            path = store.activate_palette(self._items)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Cannot Use Profile', str(error))
            return
        self.palette_ready.emit(str(path))
