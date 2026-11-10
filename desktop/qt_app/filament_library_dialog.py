"""Unified PLA-first library chooser and personal filament editor.

Only app-managed user records are editable. Catalog data is read-only, and
catalog discovery never writes to Bambu Studio or OrcaSlicer directories.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, QThread, Signal, QTimer, QSize, QByteArray, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox, QColorDialog, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableView, QVBoxLayout, QWidget, QHeaderView, QListView, QListWidget, QListWidgetItem, QGridLayout, QAbstractItemView,
)
from desktop.qt_app.filament_library_store import (
    EXPERIMENTAL, FAMILIES, OPTICS, active_ids, activate_palette,
    bambu_catalog_filaments, generic_filaments, import_profile,
    merged_filaments, normalize, profile_choices, read_personal,
    save_personal, save_profile, list_profiles, saved_profile_revision,
    update_saved_profile, parse_import_profile,
)


# QtSvg rasterizes this embedded SVG at 2x for HiDPI displays. Keeping the
# vector source in Python avoids external resource-path issues in PyInstaller.
_ALL_FILAMENTS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <title>All Filaments — CMYK spool</title>
  <path d="M7.0 2.7C4.2 2.7 2.6 6.9 2.6 12s1.6 9.3 4.4 9.3l5.3-1.4V4.1Z" fill="#7D91A0"/>
  <path d="M6.8 4.1C4.7 5.1 3.8 8.3 3.8 12s.9 6.9 3 7.9l6.1-.1V4.2Z" fill="#14212B"/>
  <path d="M7.4 4.2C5.5 6.1 4.9 8.2 4.9 12s.6 6 2.5 7.8H9.2C7.6 17.7 7 15.5 7 12s.6-5.7 2.2-7.8Z" fill="#00CFFF"/>
  <path d="M9.2 4.2C7.6 6.1 7 8.4 7 12s.6 5.9 2.2 7.8H11C9.5 17.8 9 15.5 9 12s.5-5.8 2-7.8Z" fill="#FF2D95"/>
  <path d="M11 4.2C9.5 6.2 9 8.5 9 12s.5 5.8 2 7.8h2.1c-1.4-2-1.9-4.3-1.9-7.8s.5-5.8 1.9-7.8Z" fill="#F5D600"/>
  <ellipse cx="16.5" cy="12" rx="5.5" ry="9.25" fill="#8092A2"/>
  <ellipse cx="16.5" cy="12" rx="4.2" ry="7.8" fill="#111D26"/>
  <ellipse cx="16.5" cy="12" rx="3.35" ry="6.6" fill="none" stroke="#C1D0DA" stroke-width="1.0"/>
  <ellipse cx="16.5" cy="12" rx="1.15" ry="2.0" fill="#B6C9D5"/>
</svg>"""


def _all_filaments_icon() -> QIcon:
    renderer = QSvgRenderer(QByteArray(_ALL_FILAMENTS_SVG.encode('utf-8')))
    if not renderer.isValid():
        raise ValueError('Bundled All Filaments SVG is invalid')
    # Draw in physical pixels; assign the 2x device ratio only afterward.
    # This avoids SVG clipping/partial symbols at Windows DPI scaling.
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0.0, 0.0, 48.0, 48.0))
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


class CatalogLoadWorker(QThread):
    loaded = Signal(object, object)

    def run(self):
        try:
            self.loaded.emit(bambu_catalog_filaments(), None)
        except Exception as exc:
            self.loaded.emit(None, str(exc))


class FilamentTableModel(QAbstractTableModel):
    HEADERS = ('Use', 'Color', 'Filament', 'Brand', 'PLA profile', 'Finish', 'Source')

    def __init__(self, records, selected=(), parent=None):
        super().__init__(parent)
        self.records = list(records)
        self.selected_ids = set(selected)
        self.membership_editable = False
        self.membership_visible = False

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.records)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return ('In Profile' if self.membership_visible else '') if section == 0 else self.HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole and orientation == Qt.Orientation.Horizontal:
            # Left-align named columns; center only the profile checkbox heading.
            return (Qt.AlignmentFlag.AlignCenter if section == 0 else
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        r=self.records[index.row()]
        c=index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            provenance = {
                'installed-slicer-catalog': 'Bambu catalog',
                'bundled-fallback': 'Bundled catalog',
                'approximate': 'Generic / approximate',
            }.get(r['color_source'], 'Personal' if r['source'] == 'personal'
                  else 'Imported' if r['source'] == 'imported' else r['color_source'])
            return ('', r['color'], r['name'], r['brand'], r['series'],
                    r['finish'], provenance)[c]
        if role == Qt.ItemDataRole.CheckStateRole and c == 0 and self.membership_visible:
            return (Qt.CheckState.Checked if r['id'] in self.selected_ids
                    else Qt.CheckState.Unchecked)
        if role == Qt.ItemDataRole.DecorationRole and c == 1:
            # A small readable swatch, not a full HEX-cell background. It keeps
            # the table theme consistent and works for both black and white.
            pixmap = QPixmap(18, 18)
            pixmap.fill(QColor('transparent'))
            painter = QPainter(pixmap)
            painter.setBrush(QColor(r['color']))
            painter.setPen(QPen(QColor('#627986'), 1))
            painter.drawRoundedRect(1, 1, 16, 16, 3, 3)
            painter.end()
            return QIcon(pixmap)
        if role == Qt.ItemDataRole.ToolTipRole:
            mode='Experimental — not supported for PLA color optimization' if r['experimental'] else 'PLA optimizer candidate'
            series_label = (f"{r.get('product_series')} (slicer family: {r['series']})"
                            if r.get('product_series') else r['series'])
            return (f"{r['name']} ({r['brand']})\n{r['material']} / {series_label}\n"
                    f"{r['color']} · {r['optics']} · {mode}\n"
                    f"Color provenance: {r['color_source']}\nID: {r['id']}")
        if role == Qt.ItemDataRole.UserRole:
            return r['id']
        return None

    def flags(self, index):
        flags=super().flags(index)
        if (index.isValid() and index.column() == 0 and self.membership_editable
                and self.records[index.row()]['material'] == 'PLA'):
            flags |= Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        return flags

    def setData(self,index,value,role=Qt.ItemDataRole.EditRole):
        if (role != Qt.ItemDataRole.CheckStateRole or not index.isValid()
                or index.column() != 0 or not self.membership_editable
                or self.records[index.row()]['material'] != 'PLA'):
            return False
        identity=self.records[index.row()]['id']
        if value == Qt.CheckState.Checked.value or value == Qt.CheckState.Checked:
            self.selected_ids.add(identity)
        else:
            self.selected_ids.discard(identity)
        self.dataChanged.emit(index,index,[Qt.ItemDataRole.CheckStateRole])
        return True

    def set_records(self,records):
        self.beginResetModel()
        self.records=list(records)
        self.endResetModel()

    def selected(self):
        return [record for record in self.records if record['id'] in self.selected_ids]


class FilamentFilter(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.query=''
        self.brand='All brands'
        self.origin='All sources'
        self.material='All materials'
        self.available_only=False
        self.profile_editing=False

    def filterAcceptsRow(self,row,parent):
        item=self.sourceModel().records[row]
        # A profile member remains visible even while filtering for new colors.
        if (self.profile_editing and
                item['id'] in self.sourceModel().selected_ids):
            return True
        if self.brand!='All brands' and item['brand']!=self.brand:return False
        if self.origin!='All sources' and item['source']!=self.origin:return False
        if self.material!='All materials' and item['material']!=self.material:return False
        if self.available_only and item['id'] not in self.sourceModel().selected_ids:return False
        if self.query:
            search=' '.join(str(item.get(k,'')) for k in
                            ('name','brand','series','color','finish','sku','source')).casefold()
            if self.query not in search:return False
        return True


class FilamentEntryDialog(QDialog):
    def __init__(self, record=None, parent=None):
        super().__init__(parent)
        record=record or {}
        self.editing=bool(record)
        self.setWindowTitle('Edit Custom Filament' if record else 'Add Custom Filament')
        self.setMinimumWidth(420)
        layout=QVBoxLayout(self)
        info=QLabel('PLA colors are estimates until calibrated. Non-PLA entries may be saved '
                    'but cannot currently be used by the PLA optimizer.')
        info.setWordWrap(True)
        layout.addWidget(info)
        form=QFormLayout()
        self.name=QLineEdit(record.get('name',''))
        self.name.setPlaceholderText('Filament color / product name')
        self.brand=QLineEdit(record.get('brand','Custom'))
        self.brand.setPlaceholderText('Manufacturer')
        self.material=QComboBox()
        self.material.addItems(('PLA',*EXPERIMENTAL))
        self.material.setCurrentText(record.get('material','PLA'))
        self.series=QComboBox()
        self.series.addItems(FAMILIES)
        self.series.setCurrentText(record.get('series','PLA Basic'))
        self.material.currentTextChanged.connect(
            lambda val:self.series.setEnabled(val=='PLA'))
        self.series.setEnabled(self.material.currentText()=='PLA')
        self.finish=QLineEdit(record.get('finish','Standard'))
        self.optics=QComboBox()
        self.optics.addItems(OPTICS)
        self.optics.setCurrentText(record.get('optics','opaque'))
        self.color=QLineEdit(record.get('color','#FFFFFF'))
        self.color.setMaxLength(7)
        self.color.setPlaceholderText('#RRGGBB')
        choose=QPushButton('Color wheel…')
        choose.clicked.connect(self._choose_color)
        color_box=QWidget(self)
        colorrow=QHBoxLayout(color_box)
        colorrow.setContentsMargins(0,0,0,0)
        colorrow.addWidget(self.color,1)
        colorrow.addWidget(choose)
        self.color.textChanged.connect(self._update_swatch)
        self.swatch=QLabel('   ')
        self.swatch.setMinimumWidth(36)
        colorrow.addWidget(self.swatch)
        form.addRow('Color name',self.name)
        form.addRow('Brand',self.brand)
        form.addRow('Material',self.material)
        form.addRow('PLA profile',self.series)
        form.addRow('Finish',self.finish)
        form.addRow('Optical type',self.optics)
        form.addRow('HEX',color_box)
        layout.addLayout(form)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                      QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.entry=None
        self.previous_id=record.get('id')
        self._update_swatch()

    def _update_swatch(self,*_):
        color=QColor(self.color.text())
        self.swatch.setStyleSheet('background: '+color.name()+'; border: 1px solid #647786;'
                                  if color.isValid() else 'background: transparent;')

    def _choose_color(self):
        color=QColor(self.color.text())
        chosen=QColorDialog.getColor(color if color.isValid() else QColor('#FFFFFF'),self)
        if chosen.isValid():self.color.setText(chosen.name().upper())

    def _accept(self):
        data={'name':self.name.text(),'brand':self.brand.text(),
              'material':self.material.currentText(),
              'series':self.series.currentText() if self.material.currentText()=='PLA' else 'PLA Basic',
              'color':self.color.text(),'finish':self.finish.text(),
              'optics':self.optics.currentText(),'source':'personal',
              'color_source':'user-entered'}
        if self.previous_id:data['id']=self.previous_id
        try:self.entry=normalize(data,personal=True)
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid Filament',str(exc));return
        self.accept()


class FilamentLibraryDialog(QDialog):
    """One catalog table, with a permanent quick-profile navigation sidebar.

    No profile change here activates a print palette. The Filaments workspace
    owns active palette selection. All writes are confined to app-managed files.
    """

    def __init__(self, parent=None, *, browse_only=False):
        super().__init__(parent)
        self.setObjectName('unifiedFilamentLibraryDialog')
        self.setWindowTitle('Filament Library')
        self.browse_only = bool(browse_only)  # Legacy API: editing is always here now.
        self.resize(1120, 660)
        self.setMinimumSize(810, 470)
        self.personal, self.revision = read_personal()
        self.catalog = []
        self.palette_path = None
        self.changed_profile_ids = set()
        self._profiles_by_id = {}
        self._profile_identity = None
        self._profile_revision = None
        self._draft_name = None
        self._profile_items = []
        self._profile_original = []
        self._profile_dirty = False
        self._switching = False
        self._updating_table = False
        self._closing_confirmed = False
        self.model = FilamentTableModel(merged_filaments(personal=self.personal), (), self)
        self.proxy = FilamentFilter(self)
        self.proxy.setSourceModel(self.model)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # Persistent navigation; never another representation of profile colors.
        sidebar = QWidget(self)
        sidebar.setObjectName('libraryProfileSidebar')
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(245)
        # Both navigation choices share selected/hover/idle colors. A saved
        # profile must look just as active as All Filaments, even without focus.
        sidebar.setStyleSheet(
            'QWidget#libraryProfileSidebar {background: #171d24; '
            'border: 1px solid #344550; border-radius: 6px;}'
            'QLabel#librarySidebarTitle, QLabel#librarySavedProfilesHeading {'
            'color: #d8e5ed; font-weight: 700;}'
            'QListWidget#libraryProfileList {background: #171d24; color: #d8e5ed; '
            'border: none; outline: none;}'
            'QListWidget#libraryProfileList::item {padding: 8px 7px; '
            'border-left: 3px solid transparent; border-radius: 4px;}'
            'QListWidget#libraryProfileList::item:hover:!selected {background: #24333d;}'
            'QListWidget#libraryProfileList::item:selected {background: #2b5361; '
            'border-left: 3px solid #77d9e3; color: #ffffff; font-weight: 600;}'
            'QPushButton#libraryAllFilaments {text-align: left; padding: 7px 9px; '
            'background: transparent; color: #d8e5ed; border: none; '
            'border-left: 3px solid transparent; border-radius: 4px; min-height: 24px;}'
            'QPushButton#libraryAllFilaments:hover:!checked {background: #24333d;}'
            'QPushButton#libraryAllFilaments:checked {background: #2b5361; '
            'border-left: 3px solid #77d9e3; color: #ffffff; font-weight: 600;}'
        )
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(8, 9, 8, 8)
        left.setSpacing(7)
        heading = QLabel('Filament Library', sidebar)
        heading.setObjectName('librarySidebarTitle')
        left.addWidget(heading)
        self.all_filaments_button = QPushButton('All Filaments', sidebar)
        self.all_filaments_button.setObjectName('libraryAllFilaments')
        self.all_filaments_button.setCheckable(True)
        self.all_filaments_button.setChecked(True)
        self.all_filaments_button.setToolTip('Manage the complete built-in and custom filament catalog')
        self.all_filaments_button.setIcon(_all_filaments_icon())
        self.all_filaments_button.setIconSize(QSize(18, 18))
        self.all_filaments_button.clicked.connect(self._select_all_filaments)
        left.addWidget(self.all_filaments_button)
        saved_heading = QLabel('Saved Profiles', sidebar)
        saved_heading.setObjectName('librarySavedProfilesHeading')
        left.addWidget(saved_heading)
        self.profiles = QListWidget(sidebar)
        self.profiles.setObjectName('libraryProfileList')
        self.profiles.setWordWrap(True)
        self.profiles.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.profiles.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.profiles.setUniformItemSizes(False)
        self.profiles.setResizeMode(QListView.ResizeMode.Adjust)
        self.profiles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.profiles.currentItemChanged.connect(self._on_profile_selected)
        self.profiles.itemDoubleClicked.connect(self._rename_profile_from_double_click)
        left.addWidget(self.profiles, 1)
        buttons = QGridLayout()
        buttons.setSpacing(5)
        self.new_profile_button = QPushButton('New…')
        self.new_profile_button.setObjectName('libraryNewProfile')
        self.new_profile_button.clicked.connect(self._new_profile)
        buttons.addWidget(self.new_profile_button, 0, 0)
        self.duplicate_profile_button = QPushButton('Duplicate…')
        self.duplicate_profile_button.clicked.connect(self._duplicate_profile)
        buttons.addWidget(self.duplicate_profile_button, 0, 1)
        self.rename_profile_button = QPushButton('Rename…')
        self.rename_profile_button.clicked.connect(self._rename_profile)
        buttons.addWidget(self.rename_profile_button, 1, 0)
        self.delete_profile_button = QPushButton('Delete…')
        self.delete_profile_button.clicked.connect(self._delete_profile)
        buttons.addWidget(self.delete_profile_button, 1, 1)
        self.import_button = QPushButton('Import Profile…')
        self.import_button.setObjectName('libraryImportProfile')
        self.import_button.clicked.connect(self._import_profile)
        buttons.addWidget(self.import_button, 2, 0, 1, 2)
        left.addLayout(buttons)
        outer.addWidget(sidebar, 0)

        panel = QWidget(self)
        panel.setObjectName('libraryCatalogPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        intro = QLabel('Browse Generic PLA, installed Bambu catalog entries, and custom colors. '
                       'Manufacturer/slicer HEX is not a measured mixing calibration; slicer presets are not modified.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search name, brand, type, HEX…')
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 2)
        self.brands = QComboBox(); self.brands.currentTextChanged.connect(self._filter)
        top.addWidget(self.brands, 1)
        self.sources = QComboBox(); self.sources.currentTextChanged.connect(self._filter)
        top.addWidget(self.sources, 1)
        self.materials = QComboBox(); self.materials.addItems(('All materials', 'PLA', *EXPERIMENTAL))
        self.materials.currentTextChanged.connect(self._filter)
        top.addWidget(self.materials, 1)
        layout.addLayout(top)
        self.mode_hint = QLabel('All Filaments · Browse and manage the complete filament catalog.')
        self.mode_hint.setObjectName('libraryModeHint')
        self.mode_hint.setStyleSheet('color: #9abac8;')
        layout.addWidget(self.mode_hint)

        self.table = QTableView(self)
        self.table.setObjectName('unifiedFilamentTable')
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(
            'QTableView#unifiedFilamentTable {background: #171d24; '
            'color: #d8e5ed; border: 1px solid #344550; '
            'selection-background-color: #2b5361; selection-color: #ffffff;}'
            'QTableView#unifiedFilamentTable::item {border-bottom: 1px solid #2b3640; '
            'padding: 2px 4px;}'
            'QTableView#unifiedFilamentTable::item:selected {background: #2b5361; '
            'color: #ffffff;}'
        )
        for column, width in ((1, 106), (3, 108), (4, 113), (5, 88), (6, 130)):
            self.table.setColumnWidth(column, width)
        # The label changes from blank/Use to "In Profile" in profile mode.
        # Derive width from the actual UI font to avoid clipping at high DPI.
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, max(92,
            self.table.horizontalHeader().fontMetrics().horizontalAdvance('In Profile') + 24))
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        self.add = QPushButton('Add Filament…'); self.add.clicked.connect(self._add)
        self.edit = QPushButton('Edit…'); self.edit.clicked.connect(self._edit)
        self.remove = QPushButton('Remove'); self.remove.clicked.connect(self._remove)
        self.duplicate = QPushButton('Duplicate as Custom'); self.duplicate.clicked.connect(self._duplicate)
        for button in (self.add, self.edit, self.remove, self.duplicate):
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        actions = QHBoxLayout()
        self.note = QLabel('Loading catalog…')
        actions.addWidget(self.note, 1)
        self.revert_profile_button = QPushButton('Revert Edits')
        self.revert_profile_button.setObjectName('libraryRevertProfile')
        self.revert_profile_button.clicked.connect(self._revert_profile)
        actions.addWidget(self.revert_profile_button)
        self.save_profile_button = QPushButton('Save Profile')
        self.save_profile_button.setObjectName('librarySaveProfile')
        self.save_profile_button.clicked.connect(self._save_profile)
        actions.addWidget(self.save_profile_button)
        # Kept solely as a compatibility handle; activation belongs on Filaments tab.
        self.apply = QPushButton('Use Selected Filaments')
        self.apply.hide()
        self.apply.setEnabled(False)
        layout.addLayout(actions)
        outer.addWidget(panel, 1)

        self.model.dataChanged.connect(self._on_membership_change)
        self.table.selectionModel().selectionChanged.connect(self._update_status)
        self._refresh_profile_list(focus=None)
        self._reload()
        self.worker = CatalogLoadWorker(self)
        self.worker.loaded.connect(self._catalog_loaded)
        self.worker.start()
        # FULLSPECTRUM_LIBRARY_USABILITY_V11
        from desktop.qt_app.filament_library_interactions_v11 import install_library_usability_v11
        install_library_usability_v11(self)

    @property
    def has_unsaved_changes(self):
        return self._profile_dirty

    def _selected_record(self):
        current = self.table.currentIndex()
        if not current.isValid():
            return None
        index = self.proxy.mapToSource(current)
        return self.model.records[index.row()] if index.isValid() else None

    def _catalog_records(self):
        return merged_filaments(self.catalog, self.personal)

    def _display_records(self):
        from desktop.qt_app.filament_library_membership import (
            merge_with_profile, sorted_for_profile)
        base = self._catalog_records()
        if self._profile_identity is None and self._draft_name is None:
            return base
        return sorted_for_profile(
            merge_with_profile(base, [*self._profile_original, *self._profile_items]),
            self.model.selected_ids)

    def _refresh_profile_list(self, focus=None):
        """All Filaments stays first; loaded profiles are never activated here."""
        profiles = profile_choices()
        self._profiles_by_id = {p['id']: p for p in profiles}
        if focus is None:
            focus = self._profile_identity or '__all__'
        self._switching = True
        self.profiles.clear()
        for profile in profiles:
            # U+200B adds visual wrap opportunities to machine-style names;
            # the stored profile name and stable ID remain unmodified.
            item = QListWidgetItem(str(profile['name']).replace('_', '_\u200b'))
            item.setData(Qt.ItemDataRole.UserRole, profile['id'])
            item.setToolTip((str(profile['name']) + '\nBuilt-in kit · Duplicate to edit') if
                            profile['id'].startswith('builtin:') else profile['name'])
            self.profiles.addItem(item)
        if self._draft_name is not None:
            draft = QListWidgetItem(self._draft_name + ' · unsaved')
            draft.setData(Qt.ItemDataRole.UserRole, '__draft__')
            self.profiles.addItem(draft)
            focus = '__draft__'
        chosen = next((self.profiles.item(i) for i in range(self.profiles.count())
                       if self.profiles.item(i).data(Qt.ItemDataRole.UserRole) == focus), None)
        if chosen is None:
            self.profiles.setCurrentRow(-1)
        else:
            self.profiles.setCurrentItem(chosen)
        self.all_filaments_button.setChecked(chosen is None)
        self._switching = False
        self._load_profile(chosen.data(Qt.ItemDataRole.UserRole) if chosen else '__all__')

    def _select_all_filaments(self):
        if self._profile_identity is None:
            self.all_filaments_button.setChecked(True)
            return
        if not self._confirm_leave_profile():
            self.all_filaments_button.setChecked(False)
            return
        self._switching = True
        self.profiles.setCurrentRow(-1)
        self._switching = False
        self._load_profile('__all__')

    def _on_profile_selected(self, current, previous):
        if self._switching or current is None:
            return
        choice = current.data(Qt.ItemDataRole.UserRole)
        leaving_draft = self._draft_name is not None
        if not self._confirm_leave_profile():
            self._switching = True
            self.profiles.setCurrentItem(previous)
            self._switching = False
            return
        self._load_profile(choice)
        if leaving_draft:
            # Remove a discarded draft sidebar row; no phantom unsaved profile.
            self._refresh_profile_list(focus=choice)

    def _load_profile(self, identity):
        if identity == '__draft__':
            self._profile_identity = '__draft__'
            self._profile_dirty = True
            self.model.selected_ids = {r['id'] for r in self._profile_items}
            self.model.membership_editable = True
            self.model.membership_visible = True
            self.proxy.profile_editing = True
            self._reload()
            return
        self._draft_name = None
        self._profile_dirty = False
        self._profile_identity = None if identity == '__all__' else identity
        self.all_filaments_button.setChecked(self._profile_identity is None)
        if identity in ('__all__', None):
            self._profile_items = []
            self._profile_original = []
            self._profile_revision = None
            # All Filaments means the complete, unfiltered catalog by default.
            self.search.clear()
            for selector in (self.brands, self.sources, self.materials):
                selector.setCurrentIndex(0)
        elif identity == '__draft__':
            # A draft is set explicitly by New/Duplicate; never lose it here.
            pass
        else:
            profile = self._profiles_by_id.get(identity)
            if not profile:
                self._profile_identity = None
                self._profile_items = []
                self._profile_original = []
                self._profile_revision = None
            else:
                self._profile_items = [dict(entry) for entry in profile['filaments']]
                self._profile_original = [dict(entry) for entry in self._profile_items]
                self._profile_revision = (None if identity.startswith('builtin:') else
                                          saved_profile_revision(identity))
        self.model.selected_ids = {r['id'] for r in self._profile_items}
        self.model.membership_editable = bool(self._draft_name or self._profile_revision is not None)
        self.model.membership_visible = self._profile_identity is not None
        self.proxy.profile_editing = self._profile_identity is not None
        self._reload()

    def _confirm_leave_profile(self):
        if not self._profile_dirty:
            return True
        buttons = (QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                   QMessageBox.StandardButton.Cancel)
        answer = QMessageBox.question(
            self, 'Unsaved Profile Changes',
            'Save changes to the current profile before switching?', buttons,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_profile()
        return True

    def _refill_filters(self):
        values = (
            (self.brands, ['All brands'] + sorted({r['brand'] for r in self.model.records}, key=str.casefold)),
            (self.sources, ['All sources'] + sorted({r['source'] for r in self.model.records})),
        )
        for widget, choices in values:
            # Source display names are human-readable; filtering still uses the
            # original stable raw keys such as 'bambu' and 'personal'.
            before = (widget.currentData() if widget is self.sources else widget.currentText())
            widget.blockSignals(True)
            widget.clear()
            if widget is self.sources:
                for raw in choices:
                    widget.addItem(raw if raw == 'All sources' else raw.replace('_', ' ').title(), raw)
                index = widget.findData(before)
                widget.setCurrentIndex(index if index >= 0 else 0)
            else:
                widget.addItems(choices)
                widget.setCurrentText(before if before in choices else choices[0])
            widget.blockSignals(False)
        self._filter()

    def _filter(self, *_):
        self.proxy.query = self.search.text().strip().casefold()
        self.proxy.brand = self.brands.currentText() or 'All brands'
        self.proxy.origin = self.sources.currentData() or 'All sources'
        self.proxy.material = self.materials.currentText()
        self.proxy.invalidateFilter()

    def _catalog_loaded(self, records, error):
        if error:
            self.mode_hint.setText('Local Bambu catalog unavailable: ' + str(error))
        else:
            self.catalog = records or []
            self._reload()

    def _reload(self):
        """The same source table handles both modes; no second filament list."""
        self._updating_table = True
        try:
            profile_mode = self._profile_identity is not None
            self.table.setSortingEnabled(not profile_mode)
            if profile_mode:
                self.proxy.sort(-1)  # Show source order (checked first), never previous catalog sort.
            self.model.set_records(self._display_records())
            if not profile_mode:
                self.table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
            self._refill_filters()
        finally:
            self._updating_table = False
        self._update_status()

    def _on_membership_change(self, *args):
        if self._updating_table or not self.model.membership_editable:
            return
        from desktop.qt_app.filament_library_membership import reconcile_membership
        self._profile_items = reconcile_membership(
            self._profile_items, self.model.records, self.model.selected_ids)
        self._profile_dirty = (self._draft_name is not None or
                               self._profile_items != self._profile_original)
        # Do not reset a Qt model from inside its synchronous dataChanged delivery.
        self._update_status()
        QTimer.singleShot(0, self._reload)

    def _update_status(self, *_):
        selected = self._selected_record()
        mine = bool(selected and selected['source'] == 'personal')
        self.edit.setEnabled(mine)
        self.remove.setEnabled(mine)
        self.duplicate.setEnabled(bool(selected))
        current = self._profiles_by_id.get(self._profile_identity)
        editing = (self._draft_name is not None or self._profile_revision is not None)
        profile_mode = bool(self._profile_identity is not None)
        self.duplicate_profile_button.setEnabled(bool(current) or self._draft_name is not None)
        self.rename_profile_button.setEnabled(self._profile_revision is not None and not self._profile_dirty)
        self.delete_profile_button.setEnabled(self._profile_revision is not None and not self._profile_dirty)
        self.revert_profile_button.setVisible(profile_mode)
        self.revert_profile_button.setEnabled(self._profile_dirty)
        self.save_profile_button.setVisible(profile_mode)
        valid = (len(self._profile_items) >= 2 and
                 len({r['color'] for r in self._profile_items}) >= 2)
        self.save_profile_button.setEnabled(editing and self._profile_dirty and valid)
        if self._profile_identity is None:
            self.mode_hint.setText('All Filaments · Manage built-in and custom colors. Select a profile to edit its membership.')
            self.note.setText(f'{len(self.model.records):,} library entries')
        elif self._draft_name:
            self.mode_hint.setText(f'New profile: {self._draft_name} · Check colors to add them.')
            self.note.setText(f'{len(self._profile_items)} selected · Unsaved new profile'
                              + (' · At least two distinct colors required' if not valid else ''))
        elif current and self._profile_revision is None:
            self.mode_hint.setText(f"{current['name']} · Built-in profile (duplicate to edit)")
            self.note.setText(f'{len(self._profile_items)} included · Read-only built-in')
        else:
            self.mode_hint.setText(f"Editing {current['name'] if current else 'saved profile'} · Check or uncheck colors to change membership")
            self.note.setText(f'{len(self._profile_items)} selected · '
                              + ('Unsaved edits' if self._profile_dirty else 'Saved profile')
                              + (' · At least two distinct colors required' if self._profile_dirty and not valid else ''))

    def _write_personal(self, items):
        try:
            new_revision = save_personal(items, expected_revision=self.revision)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Save Custom Filaments', str(exc))
            return False
        self.personal, self.revision = items, new_revision
        # A revised personal color is reflected in the current draft, but not
        # silently written to other saved profiles' embedded snapshots.
        changed = {r['id']: r for r in items}
        new_items = [dict(changed.get(r['id'], r)) for r in self._profile_items]
        if new_items != self._profile_items:
            self._profile_items = new_items
            self._profile_dirty = True
        self._reload()
        return True

    def _add(self):
        dialog = FilamentEntryDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._write_personal([*self.personal, dialog.entry])

    def _edit(self):
        record = self._selected_record()
        if not record or record['source'] != 'personal':
            return
        dialog = FilamentEntryDialog(record, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        items = [dialog.entry if p['id'] == record['id'] else p for p in self.personal]
        self._write_personal(items)

    def _remove(self):
        record = self._selected_record()
        if not record or record['source'] != 'personal':
            return
        referenced = [p['name'] for p in profile_choices()
                      if any(entry['id'] == record['id'] for entry in p['filaments'])]
        note = ('Referenced in: ' + ', '.join(referenced[:4]) + '.\n'
                if referenced else '')
        answer = QMessageBox.question(
            self, 'Remove Custom Filament',
            f"Remove '{record['name']}' from your personal library?\n" + note +
            'Saved profiles retain their embedded snapshot; no profile will be deleted.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._write_personal([p for p in self.personal if p['id'] != record['id']])

    def _duplicate(self):
        record = self._selected_record()
        if record is None:
            return
        copy = dict(record)
        copy.pop('id', None)
        copy.update(source='personal', color_source='user-entered')
        dialog = FilamentEntryDialog(copy, self)
        dialog.previous_id = None
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._write_personal([*self.personal, dialog.entry])

    def _new_profile(self):
        if not self._confirm_leave_profile():
            return
        title, ok = QInputDialog.getText(self, 'New Palette Profile', 'Profile name:')
        title = title.strip()
        if not ok or not title:
            return
        if any(p['name'].casefold() == title.casefold() for p in profile_choices()):
            QMessageBox.warning(self, 'Profile Exists', 'Choose another name or edit the existing profile.')
            return
        self._start_draft(title, [])

    def _duplicate_profile(self):
        profile = self._profiles_by_id.get(self._profile_identity)
        if profile is None:
            return
        if not self._confirm_leave_profile():
            return
        title, ok = QInputDialog.getText(
            self, 'Duplicate Palette Profile', 'New profile name:',
            text=profile['name'] + ' Copy')
        title = title.strip()
        if not ok or not title:
            return
        if any(p['name'].casefold() == title.casefold() for p in profile_choices()):
            QMessageBox.warning(self, 'Profile Exists', 'Choose a different name.')
            return
        self._start_draft(title, list(profile['filaments']))

    def _start_draft(self, title, records):
        self._draft_name = title
        self._profile_identity = '__draft__'
        self._profile_revision = None
        self._profile_items = [dict(item) for item in records]
        self._profile_original = [dict(item) for item in records]
        self._profile_dirty = True
        self.model.selected_ids = {r['id'] for r in self._profile_items}
        self.model.membership_editable = True
        self.model.membership_visible = True
        self.proxy.profile_editing = True
        # Do not reload the draft by asking the store for a profile that does not exist.
        self._switching = True
        self.profiles.clearSelection()
        self._switching = False
        self._refresh_profile_list(focus='__draft__')

    def _save_profile(self):
        if not self._profile_dirty:
            return True
        try:
            if self._draft_name is not None:
                identity = save_profile(self._draft_name, self._profile_items)
            elif self._profile_revision is not None:
                identity = self._profile_identity
                update_saved_profile(identity, self._profile_items,
                                     expected_revision=self._profile_revision)
            else:
                return False
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Save Profile', str(exc))
            return False
        self.changed_profile_ids.add(identity)
        self._profile_dirty = False
        self._draft_name = None
        self._profile_identity = identity
        self._refresh_profile_list(focus=identity)
        return True

    def _revert_profile(self):
        if self._draft_name is not None:
            self._draft_name = None
            self._profile_dirty = False
            self._profile_identity = None
            self._refresh_profile_list(focus='__all__')
        else:
            self._profile_items = [dict(r) for r in self._profile_original]
            self._profile_dirty = False
            self.model.selected_ids = {r['id'] for r in self._profile_items}
            self._reload()

    def _delete_profile(self):
        if self._profile_revision is None:
            return
        if not self._confirm_leave_profile():
            return
        name = self._profiles_by_id[self._profile_identity]['name']
        answer = QMessageBox.question(
            self, 'Delete Palette Profile',
            f"Delete '{name}'? Its filaments will remain in the library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            from desktop.qt_app.filament_library_store import delete_saved_profile
            delete_saved_profile(self._profile_identity,
                                 expected_revision=self._profile_revision)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Delete Profile', str(exc))
            return
        self.changed_profile_ids.add(self._profile_identity)
        self._profile_identity = None
        self._profile_dirty = False
        self._refresh_profile_list(focus='__all__')

    def _rename_profile_from_double_click(self, item):
        # Double-click means rename only for a saved, editable profile.
        # Built-in kits, drafts, and unsaved changes retain their safeguards.
        identity = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if identity is None or identity != self._profile_identity:
            return
        if self._profile_revision is None:
            return  # Built-in profiles must be duplicated first.
        if self._profile_dirty:
            QMessageBox.information(
                self, 'Unsaved Profile Changes',
                'Save or revert profile edits before renaming.')
            return
        self._rename_profile()

    def _rename_profile(self):
        if self._profile_revision is None or self._profile_dirty:
            return
        existing = self._profiles_by_id[self._profile_identity]
        title, ok = QInputDialog.getText(
            self, 'Rename Palette Profile', 'New profile name:', text=existing['name'])
        title = title.strip()
        if not ok or title == existing['name']:
            return
        try:
            from desktop.qt_app.filament_library_store import rename_saved_profile
            rename_saved_profile(self._profile_identity, title,
                                 expected_revision=self._profile_revision)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Rename Profile', str(exc))
            return
        self.changed_profile_ids.add(self._profile_identity)
        self._refresh_profile_list(focus=self._profile_identity)

    def _import_profile(self):
        if not self._confirm_leave_profile():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Portable Palette', '', 'JSON palette files (*.json)')
        if not filename:
            return
        try:
            title, _ = parse_import_profile(filename)
            existing = next((p for p in list_profiles()
                             if p['name'].casefold() == title.casefold()), None)
            if existing:
                answer = QMessageBox.question(
                    self, 'Replace Existing Profile?',
                    f"Replace '{existing['name']}' with the imported colors? "
                    'The original JSON file will not be modified.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
                identity = import_profile(filename, replace_profile_id=existing['id'],
                                          expected_revision=saved_profile_revision(existing['id']))
            else:
                identity = import_profile(filename)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Import Palette', str(exc))
            return
        self.changed_profile_ids.add(identity)
        self._profile_dirty = False
        self._draft_name = None
        self._refresh_profile_list(focus=identity)

    def done(self, result):
        if not self._confirm_leave_profile():
            return
        self._closing_confirmed = True
        self._stop_catalog_worker()
        super().done(result)

    def _stop_catalog_worker(self):
        worker = getattr(self, 'worker', None)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait()

    def closeEvent(self, event):
        if not self._closing_confirmed:
            if not self._confirm_leave_profile():
                event.ignore()
                return
            self._closing_confirmed = True
        self._stop_catalog_worker()
        super().closeEvent(event)
