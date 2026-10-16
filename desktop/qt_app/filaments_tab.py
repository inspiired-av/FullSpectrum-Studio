"""Stage 2B Qt Filaments tab. Existing engine adapters; staged preferences only.

Material selection can be persisted. Protected source colors are session-only and
will not affect a model until Stage 4 wires them into the conversion engine.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLayout,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from desktop.qt_app.plan_preferences import FILAMENT_SOURCES
from desktop.settings_store import load_settings, save_settings

from desktop.qt_app.filament_preferences import (
    FilamentPreferences, load_filament_options, scan_source_colors,
)


class _Worker(QThread):
    completed = Signal(object, object)

    def __init__(self, task, *args, parent=None):
        super().__init__(parent)
        self.task = task
        self.args = args

    def run(self):
        try:
            value = self.task(*self.args)
            self.completed.emit(value, None)
        except Exception as exc:
            self.completed.emit(None, str(exc))


def _text(value, name=None):
    label = QLabel(str(value))
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _swatch(value):
    label = QLabel('')
    label.setFixedSize(26, 20)
    color = QColor(str(value))
    label.setStyleSheet(f'background: {color.name() if color.isValid() else "#777777"};'
                        'border: 1px solid #69747e; border-radius: 4px;')
    label.setToolTip(str(value))
    return label


class FilamentsTab(QWidget):
    activity_event = Signal(str, str, str)
    def __init__(self, plan_preferences, settings_path=None, parent=None):
        super().__init__(parent)
        self.plan_preferences = plan_preferences
        self.preferences = FilamentPreferences(settings_path)
        self.options = []
        self.source_colors = {}
        self.model_path = ''
        self._source_signature = None
        self._load_serial = 0
        self._scan_serial = 0
        self._workers = []
        self._rows = []
        self._changing = False
        self._build()
        self._sync_status()

    def _build(self):
        # All filament controls share one scrolling page. Previously the two
        # tables and action rows were placed directly into the tab, so a short
        # window forced widgets below the tables to overlap their contents.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.content_scroll = QScrollArea(self)
        self.content_scroll.setObjectName('filamentsScroll')
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(self.content_scroll)
        self.content = QWidget()
        self.content.setObjectName('filamentsContent')
        lay = QVBoxLayout(self.content)
        # Keep content taller than the viewport when space is insufficient;
        # Qt may otherwise squash table/action widgets into each other.
        lay.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        lay.setContentsMargins(10, 13, 10, 14)
        lay.setSpacing(9)
        self.content_scroll.setWidget(self.content)
        lay.addWidget(_text('FILAMENT SOURCE', 'sectionTitle'))
        self.filament_source = QComboBox()
        self.filament_source.setObjectName('filamentSource')
        for label, value in FILAMENT_SOURCES:
            self.filament_source.addItem(label, value)
        lay.addWidget(self.filament_source)
        self.custom_file_row = QWidget()
        library_row = QHBoxLayout(self.custom_file_row)
        library_row.setContentsMargins(0, 0, 0, 0)
        library_row.setSpacing(7)
        self.custom_library_path = QLineEdit()
        self.custom_library_path.setObjectName('customLibraryPath')
        self.custom_library_path.setReadOnly(True)
        self.custom_library_path.setPlaceholderText('Select a custom filament library (.json)')
        library_row.addWidget(self.custom_library_path, 1)
        self.custom_library_browse = QPushButton('Browse…')
        library_row.addWidget(self.custom_library_browse)
        lay.addWidget(self.custom_file_row)
        lay.addWidget(_text('FILAMENT COLORS', 'sectionTitle'))
        self.source_info = _text('Select a filament source above and load available colors.', 'bodyMuted')
        lay.addWidget(self.source_info)
        tools = QHBoxLayout()
        self.reload_button = QPushButton('Load / Refresh')
        self.reload_button.clicked.connect(lambda: self.load_options(force=True))
        tools.addWidget(self.reload_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search name, series, hex…')
        self.search.textChanged.connect(self._filter)
        tools.addWidget(self.search, 1)
        lay.addLayout(tools)
        self.summary = _text('No filament source loaded.', 'helpText')
        lay.addWidget(self.summary)
        self.filaments = QTableWidget(0, 4)
        self.filaments.setObjectName('filamentTable')
        self.filaments.setHorizontalHeaderLabels(['Use', 'Color', 'Filament', 'Pin'])
        self.filaments.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.filaments.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.filaments.verticalHeader().setVisible(False)
        self.filaments.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.filaments.setColumnWidth(0, 46)
        self.filaments.setColumnWidth(1, 54)
        self.filaments.setColumnWidth(3, 47)
        # Use independent row scrolling instead of a table that stretches
        # beyond the space available in shorter Windows application windows.
        self.filaments.setFixedHeight(230)
        lay.addWidget(self.filaments)
        bulk = QHBoxLayout()
        self.enable_all = QPushButton('Enable All')
        self.enable_all.clicked.connect(self._enable_all)
        bulk.addWidget(self.enable_all)
        self.clear_pins = QPushButton('Clear Pins')
        self.clear_pins.clicked.connect(self._clear_pins)
        bulk.addWidget(self.clear_pins)
        bulk.addStretch()
        lay.addLayout(bulk)
        self.selection_hint = _text('Pinned filaments occupy physical slots; other enabled colors remain candidates.', 'helpText')
        lay.addWidget(self.selection_hint)
        actions = QHBoxLayout()
        self.save_button = QPushButton('Save Filaments')
        self.save_button.setObjectName('primary')
        self.save_button.clicked.connect(self.save)
        actions.addWidget(self.save_button)
        self.revert_button = QPushButton('Revert')
        self.revert_button.clicked.connect(self.revert)
        actions.addWidget(self.revert_button)
        lay.addLayout(actions)

        lay.addSpacing(6)
        lay.addWidget(_text('PROTECT SOLID COLORS', 'sectionTitle'))
        self.protected_intro = _text('Assign source colors to enabled physical filaments. '
                                      'Assignments apply only to the selected model.', 'bodyMuted')
        lay.addWidget(self.protected_intro)
        control = QHBoxLayout()
        self.scan_button = QPushButton('Scan Source Colors')
        self.scan_button.clicked.connect(self.scan_colors)
        control.addWidget(self.scan_button)
        self.protected_count = _text('No protected colors', 'helpText')
        control.addWidget(self.protected_count, 1)
        lay.addLayout(control)
        self.solid_table = QTableWidget(0, 3)
        self.solid_table.setObjectName('solidColorTable')
        self.solid_table.setHorizontalHeaderLabels(['Source color', 'Faces', 'Assigned filament'])
        self.solid_table.verticalHeader().setVisible(False)
        self.solid_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.solid_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.solid_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.solid_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.solid_table.setColumnWidth(0,115)
        self.solid_table.setColumnWidth(1,65)
        self.solid_table.setFixedHeight(178)
        self.solid_table.itemSelectionChanged.connect(self._selection_changed)
        lay.addWidget(self.solid_table)
        self.target = QComboBox()
        self.target.setMinimumWidth(100)
        lay.addWidget(self.target)
        assign_row = QHBoxLayout()
        self.protect_button = QPushButton('Protect Selected')
        self.protect_button.clicked.connect(self._protect)
        assign_row.addWidget(self.protect_button)
        self.remove_button = QPushButton('Remove Protection')
        self.remove_button.clicked.connect(self._remove_protection)
        assign_row.addWidget(self.remove_button)
        lay.addLayout(assign_row)
        lay.addWidget(_text('Model highlighting will be connected in Stage 3. '
                            'Protected colors will be passed to the engine in Stage 4.', 'helpText'))
        lay.addStretch(1)
        self._update_actions()

    def _source_settings(self):
        return (self.plan_preferences.get('source'), self.plan_preferences.get('custom'))

    def _max_pins(self):
        value = self.plan_preferences.get('real_slots')
        return int(value) if str(value).isdigit() else 6

    def _start(self, task, args, receiver):
        thread = _Worker(task, *args, parent=self)
        self._workers.append(thread)
        thread.completed.connect(receiver)
        thread.finished.connect(lambda t=thread: self._release_worker(t))
        thread.start()

    def _release_worker(self, thread):
        if thread in self._workers:
            self._workers.remove(thread)
        thread.deleteLater()

    def on_selected(self):
        if self._source_signature != self._source_settings():
            self.load_options()

    def load_options(self, force=False):
        source, library = self._source_settings()
        sig = source, library
        if not force and sig == self._source_signature:
            return
        # A source change or refresh is navigation, not Save Filaments. An
        # inventory can contain just one color; it must not trap the user in
        # that source with a modal validation error. Stage valid edits only.
        # Explicit Save / Protect still enforce the >=2 distinct-color rule.
        if self.options:
            self._accept_table(show_error=False)
        self._source_signature = sig
        self._load_serial += 1
        serial = self._load_serial
        self.options = []
        self.filaments.setRowCount(0)
        self._rows = []
        self._refresh_targets()
        if source == 'exact-cmykw':
            self.activity_event.emit('info', 'Filament source', 'CMYKW selection is automatic.')
            self.source_info.setText('CMYKW material selection is automatic for this source.')
            self.summary.setText('Individual filament selection is not available for CMYKW.')
            self._update_actions()
            return
        if source == 'custom' and not library.strip():
            self.activity_event.emit('warning', 'Filament source', 'Select a custom JSON library before loading filaments.')
            self.source_info.setText('Choose a custom filament JSON library above.')
            self.summary.setText('No library selected')
            self._update_actions()
            return
        self.activity_event.emit('busy', 'Filament source', 'Loading available filament colors…')
        self.source_info.setText('Loading filament options from the current source…')
        self.summary.setText('Loading…')
        self.reload_button.setEnabled(False)
        self._update_actions()
        self._start(load_filament_options, (source, None, library),
                    lambda value, error, s=serial: self._options_loaded(s,value,error))

    def _options_loaded(self, serial, value, error):
        if serial != self._load_serial:
            return
        self.reload_button.setEnabled(True)
        if error:
            self.activity_event.emit('warning', 'Filament source', 'Unable to load filament source: ' + str(error))
            self.source_info.setText('Unable to read filament source.')
            self.summary.setText(str(error))
            self._update_actions()
            return
        self.options = list(value or [])
        self.activity_event.emit('success', 'Filament source',
                                 f'Loaded {len(self.options)} available filament colors.')
        self._populate_options()
        self.source_info.setText('Filament source: ' + self._source_settings()[0].replace('-', ' ').title())
        self._sync_status()

    def _populate_options(self):
        self._changing = True
        self.filaments.setRowCount(len(self.options))
        self._rows = []
        for i, opt in enumerate(self.options):
            key = opt['key']
            enabled = QCheckBox()
            enabled.setChecked(self.preferences.selected(key))
            cell = QWidget(); h = QHBoxLayout(cell)
            h.setContentsMargins(7,0,0,0); h.addWidget(enabled)
            self.filaments.setCellWidget(i,0,cell)
            sw = QWidget(); sh = QHBoxLayout(sw)
            sh.setContentsMargins(5,0,0,0); sh.addWidget(_swatch(opt.get('color','#777777')))
            self.filaments.setCellWidget(i,1,sw)
            name = QTableWidgetItem(str(opt.get('name') or key))
            details = ' · '.join(str(v) for v in (opt.get('series'),opt.get('color')) if v)
            if isinstance(opt.get('remainingGrams'),(float,int)):
                details += f" · {opt['remainingGrams']:.0f} g remaining"
            name.setToolTip(details + '\n' + str(key))
            self.filaments.setItem(i,2,name)
            pin = QCheckBox()
            pin.setToolTip('Pin to a physical filament slot')
            pin.setChecked(self.preferences.is_pinned(key))
            cell2 = QWidget(); ph=QHBoxLayout(cell2)
            ph.setContentsMargins(7,0,0,0); ph.addWidget(pin)
            self.filaments.setCellWidget(i,3,cell2)
            self._rows.append((opt,enabled,pin))
            enabled.toggled.connect(lambda checked, idx=i: self._toggle_enabled(idx, checked))
            pin.toggled.connect(lambda checked, idx=i: self._toggle_pinned(idx, checked))
            self.filaments.setRowHeight(i,32)
        self._changing = False
        self._filter()
        self._refresh_targets()
        self._update_actions()

    def _toggle_enabled(self, index, checked):
        if self._changing:
            return
        enabled,pin=self._rows[index][1:]
        if not checked and pin.isChecked():
            self._changing=True;pin.setChecked(False);self._changing=False
        self._table_changed()

    def _toggle_pinned(self, index, checked):
        if self._changing:
            return
        enabled,pin=self._rows[index][1:]
        if checked and not enabled.isChecked():
            self._changing=True;enabled.setChecked(True);self._changing=False
        self._table_changed()

    def _table_changed(self):
        self._sync_status(table_pending=True)
        self._refresh_targets()
        self._update_actions()

    def _read_rows(self):
        enabled = {o['key'] for o, e, p in self._rows if e.isChecked()}
        pinned = {o['key'] for o, e, p in self._rows if p.isChecked()}
        return enabled, pinned

    def _accept_table(self, show_error):
        if not self.options:
            return True
        enabled,pinned = self._read_rows()
        try:
            self.preferences.apply(self.options,enabled,pinned,self._max_pins())
        except ValueError as exc:
            if show_error:
                QMessageBox.warning(self, 'Invalid Filament Selection', str(exc))
            return False
        return True

    def _sync_status(self, table_pending=False):
        if self.options:
            active,pinned = self._read_rows() if table_pending else (
                {o['key'] for o in self.options if self.preferences.selected(o['key'])},
                {o['key'] for o in self.options if self.preferences.is_pinned(o['key'])})
            self.summary.setText(f'{len(active)} of {len(self.options)} enabled · {len(pinned)} pinned'
                                 + (' · Unsaved changes' if table_pending or self.preferences.is_dirty else ''))
        self._update_actions()

    def _enable_all(self):
        self._changing=True
        for opt,enabled,pin in self._rows:
            enabled.setChecked(True)
        self._changing=False
        self._table_changed()

    def _clear_pins(self):
        self._changing=True
        for opt,enabled,pin in self._rows:
            pin.setChecked(False)
        self._changing=False
        self._table_changed()

    def _filter(self):
        query=self.search.text().casefold().strip()
        for i,opt in enumerate(self.options):
            text=' '.join(str(opt.get(k,'') or '') for k in ('name','series','color','key')).casefold()
            self.filaments.setRowHidden(i, bool(query and query not in text))

    def save(self):
        if not self._accept_table(True):
            return
        try:
            # Persist only source/library choices, not unrelated unsaved edits
            # elsewhere on Plan. Both tabs share the same versioned settings.
            source_keys = self.plan_preferences.dirty_keys & {'source', 'custom'}
            if source_keys:
                current = load_settings(self.plan_preferences.path)
                for key in source_keys:
                    current[key] = self.plan_preferences.get(key)
                save_settings(current, self.plan_preferences.path)
                self.plan_preferences.saved = load_settings(self.plan_preferences.path)
                self.plan_preferences.dirty_keys.difference_update(source_keys)
            self.preferences.save()
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'Unable to Save Filaments',str(exc))
            return
        self._sync_status()
        if hasattr(self.window(), '_update_plan_dirty_state'):
            self.window()._update_plan_dirty_state()
        self.activity_event.emit('success', 'Filaments', 'Filament selections and pins saved.')
        self._update_actions()

    def revert(self):
        self.preferences.revert()
        # Revert should not revalidate unsaved current-table selections.
        self.options = []
        self._rows = []
        self._source_signature = None
        saved = load_settings(self.plan_preferences.path)
        old_source = saved.get('source', 'inventory')
        old_custom = saved.get('custom', '')
        self.plan_preferences.set('source', old_source)
        self.plan_preferences.set('custom', old_custom)
        self.custom_library_path.setText(old_custom)
        idx = self.filament_source.findData(old_source)
        if idx >= 0:
            self.filament_source.setCurrentIndex(idx)
        self.custom_file_row.setVisible(old_source == 'custom')
        self.load_options()
        if self.options:
            self._populate_options()
        self._sync_status()
        if hasattr(self.window(), '_update_plan_dirty_state'):
            self.window()._update_plan_dirty_state()

    def set_model(self, path):
        self.model_path=str(path or '')
        self.preferences.use_model(self.model_path)
        self.source_colors={}
        self.protected_intro.setObjectName('bodyMuted')
        self.protected_intro.style().unpolish(self.protected_intro)
        self.protected_intro.style().polish(self.protected_intro)
        self.protected_intro.setText('Assign source colors to enabled physical filaments. Assignments apply only to the selected model.')
        self.solid_table.setRowCount(0)
        self.protected_count.setText('No protected colors')
        self._update_actions()

    def scan_colors(self):
        if not Path(self.model_path).is_file():
            QMessageBox.information(self,'Protect Solid Colors','Select a 3MF model with color assignments first.')
            return
        self._scan_serial+=1
        serial=self._scan_serial
        path=self.model_path
        self.scan_button.setEnabled(False)
        self.activity_event.emit('busy', 'Source colors', 'Scanning the selected model for source colors…')
        self.protected_count.setText('Reading exact source colors…')
        self._start(scan_source_colors,(path,),lambda data,error,s=serial,p=path:self._colors_loaded(s,p,data,error))

    def _colors_loaded(self, serial, path, data, error):
        if serial!=self._scan_serial or path!=self.model_path:
            return
        self.scan_button.setEnabled(True)
        if error:
            self.activity_event.emit('warning', 'Source colors', 'Source color scan failed: ' + str(error))
            self.protected_count.setText('Unable to scan source colors')
            QMessageBox.warning(self,'Protect Solid Colors',str(error))
            return
        self.source_colors={str(k).upper():v for k,v in (data or {}).items()}
        self.activity_event.emit('success', 'Source colors',
                                 f'Found {len(self.source_colors)} source colors in the selected model.')
        kind = getattr(data, 'source_kind', None)
        native = kind in ('native_object_colors', 'native_painted_faces')
        self.protected_intro.setObjectName('templateWarning' if native else 'bodyMuted')
        self.protected_intro.style().unpolish(self.protected_intro)
        self.protected_intro.style().polish(self.protected_intro)
        if kind == 'native_painted_faces':
            self.protected_intro.setText(
                'Bambu/Orca painted project: colors include face-painted and '
                'object-assigned filaments. Counts describe whole triangles with '
                'one unambiguous color only. Protection is UI-only; the exporter '
                'does not yet support native painted-source protection.')
        elif native:
            self.protected_intro.setText(
                'Bambu/Orca native project: swatches represent entire objects assigned '
                'to physical filament slots (not painted faces). Assignments are UI-only '
                'until the Stage 4 exporter supports object-color protection.')
        else:
            self.protected_intro.setText(
                'Standard 3MF material colors: exact face-color assignments. '
                'Protection choices are model-specific and UI-only until Stage 4.')
        self._populate_solid_colors()

    def _populate_solid_colors(self):
        self.solid_table.setRowCount(len(self.source_colors))
        for row,(hexcolor,count) in enumerate(self.source_colors.items()):
            item=QTableWidgetItem(hexcolor)
            item.setForeground(QColor('#101418') if QColor(hexcolor).lightness()>140 else QColor('#ffffff'))
            item.setBackground(QColor(hexcolor))
            self.solid_table.setItem(row,0,item)
            self.solid_table.setItem(row,1,QTableWidgetItem(str(count)))
            key=self.preferences.solid_assignments.get(hexcolor)
            match=next((o for o in self.options if o['key']==key),None)
            text=(match.get('name') or key) if match else ('Not protected' if not key else 'Unavailable filament')
            self.solid_table.setItem(row,2,QTableWidgetItem(text))
            self.solid_table.setRowHeight(row,29)
        self.protected_count.setText(f'{len(self.preferences.solid_assignments)} protected · {len(self.source_colors)} source colors')
        self._update_actions()

    def _current_color(self):
        row=self.solid_table.currentRow()
        return self.solid_table.item(row,0).text() if row>=0 and self.solid_table.item(row,0) else None

    def _selection_changed(self):
        chosen=self._current_color()
        self._update_actions()
        if chosen in self.preferences.solid_assignments:
            i=self.target.findData(self.preferences.solid_assignments[chosen])
            if i>=0:self.target.setCurrentIndex(i)

    def _refresh_targets(self):
        previous=self.target.currentData()
        self.target.clear()
        if self._rows:
            for opt,enabled,pin in self._rows:
                if enabled.isChecked():
                    self.target.addItem(f"{opt.get('name') or opt['key']} · {opt.get('color','')}",opt['key'])
        index=self.target.findData(previous)
        if index>=0:self.target.setCurrentIndex(index)
        self._update_actions()

    def _protect(self):
        color=self._current_color(); key=self.target.currentData()
        try:
            if not self._accept_table(True):return
            self.preferences.protect(color,key,self.source_colors,self.options)
        except ValueError as exc:
            QMessageBox.warning(self,'Protect Solid Colors',str(exc));return
        self._populate_solid_colors()
        self.activity_event.emit('info', 'Protected color',
                                 'Model-specific protection assigned (not yet exported).')

    def _remove_protection(self):
        color=self._current_color()
        if color:
            self.preferences.unprotect(color)
            self._populate_solid_colors()
            self.activity_event.emit('info', 'Protected color',
                                     'Model-specific protection cleared.')

    def _update_actions(self):
        has_options=bool(self._rows)
        self.enable_all.setEnabled(has_options)
        self.clear_pins.setEnabled(has_options)
        self.save_button.setEnabled(has_options)
        self.revert_button.setEnabled(has_options)
        self.scan_button.setEnabled(bool(self.model_path) and Path(self.model_path).is_file())
        self.protect_button.setEnabled(bool(self._current_color()) and self.target.count()>0)
        self.remove_button.setEnabled(bool(self._current_color()) and self._current_color() in self.preferences.solid_assignments)

    def closeEvent(self,event):
        # Do not cancel Python threads mid-archive-read. Wait for workers to finish
        # so QThread wrappers aren't destroyed while still running.
        for thread in list(self._workers):
            if thread.isRunning():
                thread.wait()
        super().closeEvent(event)
