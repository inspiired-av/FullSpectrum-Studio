"""FullSpectrum Studio Qt Stage 4D-C: native 3MF export using the existing engine."""
from __future__ import annotations

import time
import os
import subprocess

from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSlider, QSplitter, QTabWidget,
    QLineEdit, QCheckBox, QToolButton, QMessageBox, QMenu, QFormLayout,
    QVBoxLayout, QGridLayout, QLayout, QWidget, QSizePolicy, QProgressBar,
    QDialog,
    QStackedWidget, QRadioButton, QInputDialog,
)

from desktop.app_support import APP_VERSION
from desktop.qt_app.plan_preferences import (
    PlanPreferences, PALETTE_STRATEGIES, FILAMENT_SOURCES, REGIONS,
    PHYSICAL_SLOTS, PLAN_EFFORT, PLANNING_SAMPLES, PALETTE_BASE,
    OUTPUT_SLICERS,
)
from desktop.qt_app.filaments_tab import FilamentsTab
from desktop.qt_app.gl_viewport import ModelViewport
from desktop.qt_app.preview_chrome import PreviewChrome
from desktop.qt_app.preview_performance import format_preview_performance
from desktop.qt_app.plate_ui import PlateCatalogWorker, PlateLoadWorker, PlatePickerDialog
from desktop.qt_app.plate_toolbar_icons import plate_eye_icon
from desktop.qt_app.preview_toolbar_icons import preview_toolbar_icon
from desktop.qt_app.model_open_location import (
    location_path as model_location_path, read_location as read_model_location,
    write_location as write_model_location, initial_directory as initial_model_directory,
    with_default_folder, with_last_opened_model,
)
from desktop.qt_app.preview_grid_policy import (
    read_grid_settings, write_grid_settings, settings_path as preview_grid_settings_path,
    set_grid_mode as change_grid_mode, toggle_grid as toggle_grid_setting,
    GRID_MODES,
)
from desktop.qt_app.preview_mode_combo import ModernPreviewComboBox
from desktop.qt_app.preview_toolbar import (
    AdaptivePreviewToolbar, make_preview_group, separator as preview_toolbar_separator,
)
from desktop.qt_app.plate_workspace import (workspace_path, read_workspace,
    write_workspace, find_default_plate)
from desktop.qt_app.plate_catalog import _profile_root
from desktop.qt_app.preview_worker import ModelLoadWorker
from desktop.qt_app.forecast_worker import ForecastWorker
from desktop.qt_app.export_worker import ExportWorker
from desktop.qt_app.export_service import make_export_request
from desktop.qt_app.export_pending_settings import summarize_pending
from desktop.qt_app.preview_scale_check import scale_warning
from desktop.qt_app.model_intended_dimensions import scaled_dimensions, source_dimensions
from desktop.qt_app.model_dimensions_dialog import IntendedDimensionsDialog
from desktop.qt_app.model_scale_worker import ModelScaleWorker
from desktop.qt_app.model_size_preflight_worker import ModelSizePreflightWorker
from desktop.qt_app.model_auto_dimensions_dialog import AutoIntendedDimensionsDialog
from desktop.qt_app.model_size_preflight import (
    suspicious_obj_bounds, read_dimension_choice, save_dimension_choice,
    forget_dimension_choice,
)
from tempfile import TemporaryDirectory
from desktop.qt_app.export_template_policy import template_requirement
from desktop.slicer_launcher import find_windows_slicer
from desktop.qt_app.forecast_service import make_request
from desktop.qt_app.forecast_view_state import ForecastViewState
from desktop.qt_app.planning_details_panel import PlanningDetailsPanel
from desktop.qt_app.wheel_safe_combo import WheelSafeComboBox
from desktop.qt_app.section_help import SectionHelpButton, help_heading
from desktop.qt_app.forecast_visuals import RingGauge, WorstMatchPanel, forecast_guidance
from desktop.qt_app.preview_legend import ColorLossLegend, AnchorInfluenceLegend
from desktop.qt_app.anchor_legend_state import anchor_legend_rows
from desktop.qt_app.forecast_setup_gate import evaluate_setup
from desktop.qt_app.source_palette import PaletteSwatch, responsive_columns
from desktop.qt_app.source_assignments_panel import SourceAssignmentsPanel
from desktop.qt_app.forecast_countdown_overlay import (
    ForecastCountdownTimer, ForecastCountdownOverlay,
)
from desktop.qt_app.results_tab import ResultsTab
from desktop.qt_app.export_ui_icons import export_icon, compact_icon_button
from desktop.qt_app.export_slicer_segment import ExportSlicerSegment
from PySide6.QtCore import QSize
from desktop.qt_app.shell_state import (
    ShellState, display_filename, MODEL_FILE_FILTER, REFERENCE_FILE_FILTER,
)


def _label(text, kind=None, wrap=False):
    label = QLabel(text)
    if kind:
        label.setObjectName(kind)
    label.setWordWrap(wrap)
    return label


def _column(parent, margins=(14, 14, 14, 14), spacing=12):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def _section_heading(text):
    return _label(text.upper(), "sectionTitle")


def _disabled(widget, reason):
    widget.setEnabled(False)
    widget.setToolTip(reason)
    return widget


from desktop.qt_app.preview_quality import (
    QUALITY_MODES, SETTINGS_FILENAME, read_quality, write_quality)

class MainWindow(QMainWindow):
    """Mac-inspired workspace shell with functioning file selection and navigation."""

    def __init__(self, settings_path=None):
        super().__init__()
        self.state = ShellState()
        self._preview_serial = 0
        self._preview_threads = []
        # FULLSPECTRUM_INTENDED_DIMENSIONS_143: an immutable source and a temporary derived OBJ.
        self._unscaled_bounds = None
        self._intended_scale = 1.0
        self._scaled_model_path = None
        self._scale_workspaces = []
        self._scale_task = None
        self._scale_source = None
        self._scale_target_factor = None
        self._size_probe_serial = 0
        self._size_probe_threads = []
        self._size_probe_active = False
        self._scale_remember = False
        self._auto_scale_loading = False
        self._original_mesh = None
        self._predicted_mesh = None
        self._predicted_serial = 0
        self._predicted_filename = ""
        self._live_preview_meshes = {}
        self._live_preview_stale = False
        self._influence_data = None
        self._use_external_predicted = False
        self.plan_preferences = PlanPreferences(settings_path)
        self._forecast_view = ForecastViewState()  # Current model only; never saved to disk.
        self._forecast_serial = 0
        self._forecast_pending = False
        self._forecast_task = None
        self._pending_review_filament_key = None
        self._export_task = None
        self._export_request = None
        self._export_result = None
        self._export_serial = 0
        self._inspection_serial = 0
        self._inspection_threads = []
        # The one authoritative automatic forecast timer now provides a
        # six-second cancellation window. The toast's clock only updates UI.
        self._forecast_timer = ForecastCountdownTimer(self)
        self._forecast_timer.setSingleShot(True)
        self._forecast_timer.setInterval(6000)
        self._forecast_timer.timeout.connect(self._hide_auto_forecast_countdown)
        self._forecast_timer.timeout.connect(self._automatic_forecast_due)
        self._forecast_heartbeat = QTimer(self)
        self._forecast_heartbeat.setInterval(1500)
        self._forecast_heartbeat.timeout.connect(self._update_forecast_elapsed)
        self._forecast_started_at = 0.0
        self._forecast_last_stage = 'Waiting for engine progress'
        self._active_forecast_serial = -1
        self._loading_plan_ui = False
        # A factory default source is not proof that the user chose filaments.
        # Persisted sources may automatically forecast once the actual library
        # is loaded. Session confirmation is deliberately not written to disk.
        self._filament_setup_confirmed = False
        # Session-only edit gate: user filament work never triggers repeated
        # automatic optimizations. Model opening still gets its first forecast.
        self._filament_forecast_held = False
        self._filament_options_ready = False
        self._filament_load_error = ''
        self._saved_filament_source = self.plan_preferences.saved.get('source')
        self.setObjectName("qtMainWindow")
        self.setWindowTitle("FullSpectrum Studio — Qt")
        self.resize(1440, 880)
        self.setMinimumSize(920, 630)
        self._qt_disposing = False
        self._initial_filament_ui_timer = QTimer(self)
        self._initial_filament_ui_timer.setSingleShot(True)
        self._initial_filament_ui_timer.timeout.connect(self._initialize_filament_setup)
        self._initial_export_layout_timer = QTimer(self)
        self._initial_export_layout_timer.setSingleShot(True)
        self._initial_export_layout_timer.timeout.connect(self._update_export_layout)
        self._plate_catalog = None
        self._plate_catalog_task = None
        self._plate_load_threads = []
        self._plate_custom_roots = []
        self._plate_custom_exes = []  # User-located slicers, no execution.
        self._plate_rescan_pending = False
        self._plate_pending_picker = False
        self._plate_selected = None
        self._plate_load_serial = 0
        self._plate_settings_path = workspace_path(settings_path)
        self._plate_workspace = read_workspace(self._plate_settings_path)
        self._grid_settings_path = preview_grid_settings_path(self._plate_settings_path)
        self._grid_settings = read_grid_settings(self._grid_settings_path)
        self._model_location_path = model_location_path(self._plate_settings_path)
        self._dimension_choices_path = Path(self._model_location_path).with_name(
            'model_dimension_choices.json')
        self._model_location = read_model_location(self._model_location_path)
        self._preview_quality_path = self._plate_settings_path.with_name(SETTINGS_FILENAME)
        self._preview_quality = read_quality(self._preview_quality_path)
        self._preview_quality_generation = 0
        self._preview_quality_source_mesh = None
        self._preview_quality_cache = {}  # at most two finished display buffers
        self._preview_quality_task = None
        self._preview_quality_pending = False
        self._plate_default = self._plate_workspace.get('default')
        self._plate_default_pending = self._plate_default is not None
        self._plate_visible = self._plate_workspace.get('visible', True)
        self._plate_loaded_mesh = None
        self._plate_manually_requested_source = None
        self._plate_custom_exes = [Path(p) for p in self._plate_workspace.get('slicer_executables', []) if Path(p).is_file()]
        self._plate_custom_roots = [Path(p) for p in self._plate_workspace.get('resource_roots', []) if Path(p).is_dir()]
        self._build()
        # Connect after the viewport and its overlay exist. These signals also
        # handle automatic timer restarts and pauses from staged filament edits.
        self._forecast_timer.armed.connect(self._show_auto_forecast_countdown)
        self._forecast_timer.disarmed.connect(self._hide_auto_forecast_countdown)
        self._build_menus()
        # Warm the installed-plate catalog on every launch, even without a
        # saved default. _refresh_plate_catalog runs its filesystem scan in a
        # QThread: the window remains interactive, and only the chosen plate
        # mesh is loaded. A later click can reuse the finished catalog.
        QTimer.singleShot(0, self._refresh_plate_catalog)
        self._initial_filament_ui_timer.start(0)
        self.statusBar().showMessage(
            "Qt Stage 4D-D3 — staged filament edits and explicit forecast updates."
        )

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = _column(root, margins=(12, 0, 12, 9), spacing=12)

        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(8, 12, 8, 12)
        h.setSpacing(9)
        mark = _label("◆")
        mark.setStyleSheet("background: #66bfd1; color: #09232c; font-size: 22px; "
                           "font-weight: 700; border-radius: 7px; padding: 8px;")
        h.addWidget(mark)
        brand = QVBoxLayout()
        brand.setSpacing(3)
        brand.addWidget(_label("FullSpectrum Studio", "brand"))
        self.project_subtitle = _label("No model selected", "subtitle")
        brand.addWidget(self.project_subtitle)
        h.addLayout(brand)
        h.addStretch()
        self.open_button = QPushButton("Open Model")
        self.open_button.setObjectName("openModelButton")
        self.open_button.clicked.connect(self._open_model)
        h.addWidget(self.open_button)
        self.reference_button = QPushButton("Reference")
        self.reference_button.clicked.connect(self._open_reference)
        h.addWidget(self.reference_button)
        self.open_button.setIcon(export_icon('open'))
        self.reference_button.setIcon(export_icon('file'))
        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName('toggleWorkspaceSidebar')
        compact_icon_button(self.sidebar_toggle, 'sidebar', 'Hide sidebar', side=32)
        self.sidebar_toggle.setCheckable(True)
        self.sidebar_toggle.setChecked(True)
        self.sidebar_toggle.toggled.connect(self._set_sidebar_visible)
        h.addWidget(self.sidebar_toggle)
        h.addWidget(_label("v" + APP_VERSION, "bodyMuted"))
        self.workspace_header = header
        main.addWidget(header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.addWidget(self._preview_pane())
        self.workspace_sidebar = self._sidebar()
        self.splitter.addWidget(self.workspace_sidebar)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([920, 455])
        main.addWidget(self.splitter, stretch=1)

        bottom = QFrame()
        bottom.setObjectName("bottomBar")
        foot = QHBoxLayout(bottom)
        foot.setContentsMargins(8, 9, 8, 9)
        self.bottom_hint = _label("Forecast is read-only. Export Native 3MF runs the existing conversion and validation pipeline.", "helpText")
        self.bottom_hint.setWordWrap(True)
        foot.addWidget(self.bottom_hint)
        self.workspace_footer = bottom
        main.addWidget(bottom)

    def _preview_pane(self):
        pane = QFrame()
        pane.setObjectName("previewCard")
        pane.setMinimumWidth(430)
        content = _column(pane, spacing=12)
        # The model view is a selection; specialized import lives in an
        # overflow menu, not in a permanently visible main action button.
        self.preview_mode = ModernPreviewComboBox()
        self.preview_mode.addItems(["Original", "Predicted", "Color Loss", "Anchor Influence", "Wireframe"])
        self.preview_mode.setMaxVisibleItems(self.preview_mode.count())
        self.preview_mode.setCurrentText("Original")
        self.preview_mode.setObjectName("previewMode")
        self.preview_mode.setMinimumWidth(145)
        self.preview_mode.setEnabled(False)
        self.preview_mode.setToolTip(
            "Original, predicted colors, color-loss heatmap, anchor influence, or wireframe. "
            "The analysis views come from the current read-only forecast.")
        self.preview_mode.currentTextChanged.connect(self._preview_mode_changed)
        self.preview_mode_help = SectionHelpButton('preview_modes')
        self.preview_options_button = QToolButton()
        self.preview_options_button.setObjectName('previewOptionsButton')
        self.preview_options_button.setIcon(preview_toolbar_icon('more'))
        self.preview_options_button.setIconSize(QSize(19, 19))
        self.preview_options_button.setFixedSize(32, 32)
        self.preview_options_button.setToolTip('Preview options')
        self.preview_options_button.setAccessibleName('Preview options')
        self.preview_options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.preview_options_menu = QMenu(self.preview_options_button)
        self.preview_import_action = self.preview_options_menu.addAction('Import Predicted OBJ…')
        self.preview_import_action.setObjectName('importPredictedObjAction')
        self.preview_import_action.setToolTip('Import an existing OBJ with MTL colors; does not run a forecast.')
        self.preview_import_action.triggered.connect(self._open_predicted)
        self.preview_options_menu.addSeparator()
        self.preview_use_live_action = self.preview_options_menu.addAction('Use Live Forecast Prediction')
        self.preview_use_live_action.setCheckable(True)
        self.preview_use_live_action.triggered.connect(self._use_live_predicted_preview)
        self.preview_use_imported_action = self.preview_options_menu.addAction('Use Imported OBJ Prediction')
        self.preview_use_imported_action.setCheckable(True)
        self.preview_use_imported_action.triggered.connect(self._use_imported_predicted_preview)
        # Grid configuration belongs to the visible grid control, not prediction overflow.
        self.preview_grid_menu = QMenu('Grid and Axes', self)
        self.preview_grid_actions = {}
        labels = {'automatic': 'Automatic (recommended)', 'plate': 'Plate Grid',
                  'perspective': 'Perspective Grid', 'off': 'Off'}
        for mode in GRID_MODES:
            action = self.preview_grid_menu.addAction(labels[mode])
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, value=mode: self._set_preview_grid_mode(value))
            self.preview_grid_actions[mode] = action
        self.preview_grid_menu.addSeparator()
        # Optional camera framing command; never shrink the model on orbit/zoom.
        self.preview_fit_grid_action = self.preview_grid_menu.addAction('Fit Perspective Grid')
        self.preview_fit_grid_action.setToolTip(
            'Frame the entire perspective grid without changing camera direction.')
        self.preview_fit_grid_action.triggered.connect(self._fit_perspective_grid)
        self.preview_grid_menu.addSeparator()
        self.preview_axes_action = self.preview_grid_menu.addAction('Show XYZ axis marker')
        self.preview_axes_action.setCheckable(True)
        self.preview_axes_action.toggled.connect(self._set_preview_axes_visible)
        self.preview_measurements_action = self.preview_grid_menu.addAction(
            'Show perspective grid measurements')
        self.preview_measurements_action.setObjectName('perspectiveGridMeasurementsAction')
        self.preview_measurements_action.setCheckable(True)
        self.preview_measurements_action.setToolTip(
            'Perspective grid only: small-cell spacing plus X/Y distances (mm) '
            'from the first visible major grid line. These are grid-relative '
            'ruler distances, not world or printer-bed coordinates.')
        self.preview_measurements_action.toggled.connect(self._set_preview_measurements_visible)
        self.preview_grid_menu.aboutToShow.connect(self._refresh_preview_grid_actions)
        self.preview_options_menu.aboutToShow.connect(self._update_preview_options)
        self.preview_options_button.setMenu(self.preview_options_menu)
        self.preview_options_button.hide()  # No model: nothing to import.
        self.preview_view_group = make_preview_group(
            self.preview_mode, self.preview_mode_help, self.preview_options_button,
            name='visualization')

        self.plate_button = QPushButton('Build Plate')
        self.plate_button.setObjectName('buildPlateButton')
        self.plate_button.setIcon(export_icon('plate'))
        self.plate_button.setIconSize(QSize(17, 17))
        self.plate_button.setMinimumHeight(32)
        self.plate_button.setToolTip('Choose a 3D build plate from installed slicers')
        self.plate_button.setAccessibleName('Choose build plate')
        self.plate_button.clicked.connect(self._choose_plate)
        self.plate_visibility_button = QToolButton()
        self.plate_visibility_button.setObjectName('plateVisibilityButton')
        self.plate_visibility_button.setFixedSize(32, 32)
        self.plate_visibility_button.setCheckable(True)
        self.plate_visibility_button.setIcon(plate_eye_icon(False))
        self.plate_visibility_button.setIconSize(QSize(19, 19))
        self.plate_visibility_button.setToolTip('Show or hide the selected build plate')
        self.plate_visibility_button.setAccessibleName('Show build plate')
        self.plate_visibility_button.clicked.connect(self._toggle_plate_visibility)
        # Compact quick-toggle: additional modes and XYZ visibility live in the
        # existing Preview Options > Grid and Axes menu.
        self.preview_grid_button = QToolButton()
        self.preview_grid_button.setObjectName('previewGridButton')
        self.preview_grid_button.setFixedSize(34, 32)
        self.preview_grid_button.setIcon(preview_toolbar_icon('grid'))
        self.preview_grid_button.setIconSize(QSize(20, 20))
        self.preview_grid_button.setCheckable(True)
        # Two real buttons instead of Qt's platform-drawn MenuButtonPopup:
        # the native split arrow was truncated under the shared toolbar skin.
        self.preview_grid_menu_button = QToolButton()
        self.preview_grid_menu_button.setObjectName('previewGridMenuButton')
        self.preview_grid_menu_button.setFixedSize(24, 32)
        self.preview_grid_menu_button.setIcon(preview_toolbar_icon('chevron-down'))
        self.preview_grid_menu_button.setIconSize(QSize(14, 14))
        self.preview_grid_menu_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self.preview_grid_menu_button.setMenu(self.preview_grid_menu)
        # The surrounding previewToolbarGroup supplies normal hover/pressed styling.
        # Remove padding only from this narrow arrow button to avoid clipping.
        self.preview_grid_menu_button.setStyleSheet(
            'QToolButton#previewGridMenuButton { padding: 0px; }'
            'QToolButton#previewGridMenuButton::menu-indicator { '
            'image: none; width: 0px; height: 0px; }')
        self.preview_grid_menu_button.setToolTip('Grid and Axes settings')
        self.preview_grid_menu_button.setAccessibleName('Grid and Axes settings')
        self.preview_grid_button.setChecked(self._grid_settings['mode'] != 'off')
        self.preview_grid_button.setStyleSheet(
            'QToolButton#previewGridButton:checked { background: #2c4555; '
            'border: 1px solid #4a8194; border-radius: 5px; }')
        self.preview_grid_button.setToolTip(
            'Toggle preview grid; use the arrow for grid and axis settings.')
        self.preview_grid_button.setAccessibleName('Toggle preview grid')
        self.preview_grid_button.toggled.connect(self._toggle_preview_grid)
        self.preview_plate_group = make_preview_group(
            self.plate_button, preview_toolbar_separator(), self.plate_visibility_button,
            preview_toolbar_separator(), self.preview_grid_button,
            self.preview_grid_menu_button, name='build_plate')

        self.expand_preview_toggle = QToolButton()
        self.expand_preview_toggle.setObjectName('toggleExpandedPreview')
        self.expand_preview_toggle.setFixedSize(34, 32)
        self.expand_preview_toggle.setIcon(preview_toolbar_icon('expand'))
        self.expand_preview_toggle.setIconSize(QSize(20, 20))
        self.expand_preview_toggle.setToolTip('Expand model preview (F11)')
        self.expand_preview_toggle.setAccessibleName('Expand model preview')
        self.expand_preview_toggle.setCheckable(True)
        self.expand_preview_toggle.toggled.connect(self._set_expanded_preview)
        self.reset_camera_button = QToolButton()
        self.reset_camera_button.setObjectName('resetCameraButton')
        self.reset_camera_button.setFixedSize(34, 32)
        self.reset_camera_button.setIcon(preview_toolbar_icon('reset'))
        self.reset_camera_button.setIconSize(QSize(20, 20))
        self.reset_camera_button.setToolTip('Reset camera to default view (R)')
        self.reset_camera_button.setAccessibleName('Reset camera')
        self.reset_camera_button.setEnabled(False)
        self.reset_camera_button.clicked.connect(self._reset_camera)
        self.preview_camera_group = make_preview_group(
            self.expand_preview_toggle, preview_toolbar_separator(), self.reset_camera_button,
            name='camera')

        self.preview_toolbar = AdaptivePreviewToolbar(
            _label('MODEL PREVIEW', 'smallTitle'),
            self.preview_view_group, self.preview_plate_group, self.preview_camera_group)
        content.addWidget(self.preview_toolbar)
        self._update_plate_actions()
        self._update_preview_options()
        # A vertical splitter makes palette inspection adjustable without taking
        # permanent space from the model. Both panes remain real Qt widgets.
        self.preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_splitter.setObjectName('previewPaletteSplitter')
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(7)
        model_area = QWidget()
        model_layout = QVBoxLayout(model_area)
        model_layout.setContentsMargins(0,0,0,0)
        model_layout.setSpacing(6)
        model_area.setMinimumHeight(195)
        self.preview_surface = ModelViewport()
        self.preview_surface.set_grid_preferences(
            self._grid_settings['mode'], self._grid_settings['axes'],
            self._grid_settings['measurements'])
        self._refresh_preview_grid_actions()
        self.preview_surface.model_file_dropped.connect(self._open_model)
        self.preview_chrome = PreviewChrome(self.preview_surface)
        self.preview_surface.drop_feedback.connect(self.preview_chrome.set_drop_message)
        self.preview_surface.render_error.connect(self._preview_render_error)
        self.preview_surface.plate_render_error.connect(self._plate_render_failed)
        self.preview_surface.grid_render_error.connect(self._grid_render_failed)
        self.preview_surface.background_clicked.connect(self._clear_palette_selection)
        model_layout.addWidget(self.preview_surface, stretch=1)
        # A visible indeterminate progress bar: no inaccurate percentage.
        # Keeping it in the viewport layout avoids overlay/XYZ collisions.
        from PySide6.QtWidgets import QProgressBar
        self.preview_quality_activity = QFrame(model_area)
        self.preview_quality_activity.setObjectName('previewQualityActivity')
        self.preview_quality_activity.setStyleSheet(
            'QFrame#previewQualityActivity { background: #17303c; '
            'border: 1px solid #35637a; border-radius: 5px; }'
            'QLabel { color: #c4e7ef; border: none; font-size: 11px; }'
            'QProgressBar { border: none; background: #264452; '
            'border-radius: 3px; }'
            'QProgressBar::chunk { background: #56b6c9; }')
        activity_row = QHBoxLayout(self.preview_quality_activity)
        activity_row.setContentsMargins(10, 5, 10, 5)
        activity_row.setSpacing(10)
        self.preview_quality_activity_label = QLabel('Preparing preview…')
        activity_row.addWidget(self.preview_quality_activity_label, 1)
        self.preview_quality_activity_bar = QProgressBar()
        self.preview_quality_activity_bar.setRange(0, 0)
        self.preview_quality_activity_bar.setTextVisible(False)
        self.preview_quality_activity_bar.setFixedSize(105, 7)
        activity_row.addWidget(self.preview_quality_activity_bar)
        model_layout.addWidget(self.preview_quality_activity)
        self.preview_quality_activity.hide()
        self.preview_status = _label("Open a 3MF, OBJ or GLB model to view its geometry.", "helpText", wrap=True)
        model_layout.addWidget(self.preview_status)
        # Physical scale is advisory for unitless OBJ and raw GLB coordinates.
        # Never change source units, mesh vertices or export geometry here.
        self.preview_scale_notice = _label('', 'templateWarning', wrap=True)
        self.preview_scale_notice.setObjectName('previewScaleNotice')
        self.preview_scale_notice.setStyleSheet('color: #edbf73;')
        self.preview_scale_notice.hide()
        # Physical-size status stays next to its corrective action. The button
        # changes actual OBJ geometry, never the camera or just the grid.
        self.preview_scale_row = QHBoxLayout()
        self.preview_scale_row.setContentsMargins(0, 1, 0, 1)
        self.preview_scale_row.setSpacing(8)
        self.preview_scale_row.addWidget(self.preview_scale_notice, 1)
        self.preview_adjust_dimensions = QPushButton('Adjust Dimensions…')
        self.preview_adjust_dimensions.setObjectName('previewAdjustDimensions')
        self.preview_adjust_dimensions.setToolTip(
            'Set or restore the physical OBJ size (File → Set Intended Dimensions…).')
        self.preview_adjust_dimensions.setStyleSheet(
            'QPushButton#previewAdjustDimensions {'
            'color: #8bd4e5; border: 1px solid #3c6e80;'
            'background: #1a2d39; border-radius: 5px; padding: 5px 10px;}'
            'QPushButton#previewAdjustDimensions:hover {'
            'background: #244452; border-color: #5eabbe;}'
            'QPushButton#previewAdjustDimensions:disabled {'
            'color: #77858f; border-color: #36414b; background: #1b252d;}')
        self.preview_adjust_dimensions.clicked.connect(self._set_intended_dimensions)
        self.preview_adjust_dimensions.hide()
        self.preview_scale_row.addWidget(self.preview_adjust_dimensions, 0)
        model_layout.addLayout(self.preview_scale_row)
        # A compact in-viewport key is easier to read than an inline footnote.
        # It is a Qt child overlay; no texture, geometry or OpenGL change.
        self.preview_legend = ColorLossLegend(self.preview_surface)
        self.preview_legend.setVisible(False)
        self.anchor_legend = AnchorInfluenceLegend(self.preview_surface)
        self.anchor_legend.anchor_selected.connect(self._anchor_selected)
        self.anchor_legend.palette_mode_changed.connect(self._anchor_palette_changed)
        self.anchor_legend.setVisible(False)
        # Like the two analysis legends, this is a Qt child of the actual
        # OpenGL viewport. It remains visible while navigating sidebar tabs.
        self.forecast_countdown = ForecastCountdownOverlay(self.preview_surface)
        self.forecast_countdown.cancel_requested.connect(self._cancel_scheduled_forecast)
        self.forecast_countdown.run_now_requested.connect(self._run_scheduled_forecast_now)
        # Legends are children of the OpenGL viewport, created after the XYZ
        # indicator; register them for collision-free marker placement.
        self.preview_surface._axis_indicator.refresh_obstacles()
        self.preview_splitter.addWidget(model_area)

        palette_area = QFrame()
        palette_area.setObjectName('sourcePalettePanel')
        palette_area.setMinimumHeight(94)
        self._source_palette_area = palette_area
        self._assigned_inspector_previous_height = None
        self._assigned_inspector_auto_height = None
        # The whole palette (controls, swatches and assignment inspector)
        # scrolls as one region; no competing inner scrollbars.
        palette_outer = QVBoxLayout(palette_area)
        palette_outer.setContentsMargins(0, 0, 0, 0)
        palette_outer.setSpacing(0)
        self.source_palette_scroll = QScrollArea(palette_area)
        self.source_palette_scroll.setObjectName('sourcePaletteScroll')
        self.source_palette_scroll.setWidgetResizable(True)
        self.source_palette_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.source_palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_palette_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_palette_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        palette_outer.addWidget(self.source_palette_scroll)
        self.source_palette_body = QWidget()
        self.source_palette_body.setObjectName('sourcePaletteScrollBody')
        palette_layout = QVBoxLayout(self.source_palette_body)
        palette_layout.setContentsMargins(0, 4, 6, 4)
        palette_layout.setSpacing(5)
        palette_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        title_row = QHBoxLayout()
        title_row.addWidget(_section_heading("Source Palette"))
        self.source_palette_help = SectionHelpButton('source_palette_assignments')
        title_row.addWidget(self.source_palette_help)
        title_row.addStretch()
        self.tint_protected=QCheckBox('Tint Assigned')
        self.tint_protected.setObjectName('tintProtectedToggle')
        self.tint_protected.setToolTip('Optional teal tint on source-color assigned faces. Off preserves original colors.')
        self.tint_protected.setChecked(False)
        self.tint_protected.setEnabled(False)
        self.tint_protected.toggled.connect(self.preview_surface.set_protected_overlay)
        title_row.addWidget(self.tint_protected)
        self.manage_protection_button=QPushButton('Assign Filament…')
        self.manage_protection_button.setObjectName('manageProtectionShortcut')
        self.manage_protection_button.setEnabled(False)
        self.manage_protection_button.setToolTip('Assign selected Source Palette colors to a physical filament without mixing.')
        self.manage_protection_button.clicked.connect(self._show_protection_controls)
        title_row.addWidget(self.manage_protection_button)
        self.clear_palette_button=QPushButton('Clear')
        self.clear_palette_button.setObjectName('clearPaletteSelection')
        self.clear_palette_button.setToolTip('Clear the selected source color (Esc).')
        self.clear_palette_button.setEnabled(False)
        self.clear_palette_button.clicked.connect(self._clear_palette_selection)
        title_row.addWidget(self.clear_palette_button)
        self.palette_help = _label('Drag divider to resize', 'helpText')
        title_row.addWidget(self.palette_help)
        self.palette_help.setVisible(False)  # Preserve width for interactive controls.
        palette_layout.addLayout(title_row)
        self.source_palette_message = _label(
            'Open a model to inspect its exact source color assignments.', 'bodyMuted', wrap=True)
        palette_layout.addWidget(self.source_palette_message)
        self.source_palette_detail = _label('Click or Shift-click for a range; Ctrl-click to toggle; right-click to assign. Teal dots = assigned.', 'helpText')
        self.source_palette_detail.setObjectName('sourcePaletteDetail')
        palette_layout.addWidget(self.source_palette_detail)
        self.assignment_panel = SourceAssignmentsPanel(self)
        self.assignment_panel.setVisible(False)
        self.assignment_panel.source_selected.connect(self._jump_to_assigned_color)
        # FilamentsTab is created later by _sidebar(), so connect in _sidebar.
        self.assigned_colors_summary = self.assignment_panel.toggle
        self.source_palette_content = QWidget()
        self.source_palette_content.setObjectName('sourcePaletteContent')
        self.source_palette_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.source_palette_layout = QGridLayout(self.source_palette_content)
        self.source_palette_layout.setContentsMargins(0, 0, 6, 2)
        self.source_palette_layout.setHorizontalSpacing(5)
        self.source_palette_layout.setVerticalSpacing(5)
        self.source_palette_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._source_palette_cells = []
        self._source_palette_columns = 0
        self._source_palette_selected = None
        self._source_palette_selected_colors = ()
        self._source_palette_anchor = None
        self._source_palette_counts = {}
        self._preview_protected_colors=set()
        self.source_palette_content.installEventFilter(self)
        self.source_palette_content.setVisible(False)
        palette_layout.addWidget(self.source_palette_content)
        # Keep the color grid visible above the expandable assignment inspector.
        palette_layout.addWidget(self.assignment_panel)
        # The scrollable body may be taller than its content when the user
        # expands the lower splitter pane. Without an explicit bottom stretch,
        # QVBoxLayout allocates that extra height to labels, the swatch grid,
        # and the assignment panel, creating huge gaps between them.
        # Put all unused height AFTER the inspector instead: controls, swatches,
        # and assigned filaments remain compact and top-aligned at every size.
        palette_layout.addStretch(1)
        # Set the body only after its widgets and layout have been assembled.
        self.source_palette_scroll.setWidget(self.source_palette_body)
        self.source_palette_scroll.viewport().installEventFilter(self)
        self.assignment_panel.details_toggled.connect(self._resize_palette_for_assignments)
        self.preview_splitter.addWidget(palette_area)
        self.preview_splitter.setStretchFactor(0, 7)
        self.preview_splitter.setStretchFactor(1, 2)
        self.preview_splitter.setSizes([590, 135])
        content.addWidget(self.preview_splitter, stretch=1)
        return pane

    def _resize_palette_for_assignments(self, expanded):
        """Ensure the expanded inspector is visible without manual splitter dragging.

        This changes only the two panes' screen space. It never modifies model
        geometry, assignment preferences, or the forecast. The collapsed pane's
        user-set size is restored unless the user resized it while expanded.
        """
        splitter = self.preview_splitter
        sizes = splitter.sizes()
        if len(sizes) != 2 or sum(sizes) <= 0:
            return
        total = sum(sizes)
        palette = self._source_palette_area
        if expanded:
            self._assigned_inspector_previous_height = sizes[1]
            # Make room for the swatch rows, the searchable tree and buttons.
            # Never shrink the model pane below its existing 195px minimum.
            model_min = max(195, splitter.widget(0).minimumHeight())
            target = min(310, max(94, total - model_min))
            palette.setMinimumHeight(target)
            if sizes[1] < target:
                splitter.setSizes([max(0, total - target), target])
            self._assigned_inspector_auto_height = splitter.sizes()[1]
        else:
            palette.setMinimumHeight(94)
            previous = self._assigned_inspector_previous_height
            automatic = self._assigned_inspector_auto_height
            # Preserve a manual drag performed while the inspector was open.
            if (previous is not None and automatic is not None
                    and abs(sizes[1] - automatic) <= 14):
                splitter.setSizes([max(0, total - previous), previous])
            self._assigned_inspector_previous_height = None
            self._assigned_inspector_auto_height = None

    def _set_sidebar_visible(self, visible):
        """Presentation-only sidebar toggle; do not alter plan preferences."""
        if not hasattr(self, 'workspace_sidebar'):
            return
        if visible:
            self.workspace_sidebar.show()
            saved = getattr(self, '_saved_sidebar_split', None)
            if saved and all(saved):
                QTimer.singleShot(0, lambda sizes=list(saved): self.splitter.setSizes(sizes))
        else:
            if not self.workspace_sidebar.isHidden():
                self._saved_sidebar_split = self.splitter.sizes()
            self.workspace_sidebar.hide()
        label = 'Hide sidebar' if visible else 'Show sidebar'
        self.sidebar_toggle.setToolTip(label)
        self.sidebar_toggle.setAccessibleName(label)

    def _set_expanded_preview(self, expanded):
        """Show a large, popup-safe preview without Windows native fullscreen.

        On some Windows HDR / OpenGL drivers, showFullScreen() promotes the
        QOpenGLWidget into an independent fullscreen presentation path. Qt
        combobox, menu and help popups then re-trigger display negotiation,
        causing blank frames or HDR toggles and sometimes invisible menus.
        A normal maximized window keeps the scene and popups composed together.
        The title bar / taskbar may remain visible by design.
        """
        if expanded:
            self._palette_split_before_expand = self.preview_splitter.sizes()
            self._palette_was_visible = not self._source_palette_area.isHidden()
            self._preview_was_maximized = self.isMaximized()
            self.workspace_sidebar.hide()
            self._source_palette_area.hide()
            self.workspace_header.hide()
            self.workspace_footer.hide()
            self.menuBar().hide()
            self.statusBar().hide()
            # Do NOT call showFullScreen: windowed maximization keeps native
            # dropdown/help popup windows in the regular desktop composition.
            self.showMaximized()
        else:
            if getattr(self, '_preview_was_maximized', False):
                self.showMaximized()
            else:
                self.showNormal()
            self.workspace_header.show()
            self.workspace_footer.show()
            self.menuBar().show()
            self.statusBar().show()
            if getattr(self, '_palette_was_visible', True):
                self._source_palette_area.show()
            if self.sidebar_toggle.isChecked():
                self.workspace_sidebar.show()
            sizes = getattr(self, '_palette_split_before_expand', None)
            if sizes and all(sizes):
                QTimer.singleShot(0, lambda values=list(sizes): self.preview_splitter.setSizes(values))
        self.expand_preview_toggle.setIcon(preview_toolbar_icon(
            'restore' if expanded else 'expand'))
        label = ('Restore workspace (Esc or F11)' if expanded
                 else 'Expand model preview (F11)')
        self.expand_preview_toggle.setToolTip(label)
        self.expand_preview_toggle.setAccessibleName(label)
        self.preview_surface.update()

    def _handle_view_escape(self):
        """Esc closes fullscreen; otherwise retains the existing palette shortcut."""
        if self.expand_preview_toggle.isChecked():
            self.expand_preview_toggle.setChecked(False)
        else:
            self._clear_palette_selection()

    def _sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(340)
        outer = _column(sidebar, margins=(8, 10, 8, 10), spacing=3)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("workspaceTabs")
        # Construct Filaments first so the single source selector lives on that
        # tab while existing PlanPreferences and Stage 2A tests keep references.
        self.filaments_panel = FilamentsTab(
            self.plan_preferences, settings_path=self.plan_preferences.path, parent=self.tabs)
        self.filament_source = self.filaments_panel.filament_source
        self.custom_file_row = self.filaments_panel.custom_file_row
        self.custom_library_path = self.filaments_panel.custom_library_path
        self.custom_library_browse = self.filaments_panel.custom_library_browse
        self.custom_library_browse.clicked.connect(self._browse_custom_library)
        self.filaments_panel.library_palette_ready.connect(self._activate_library_palette)
        # Export widgets must exist before _plan_tab restores and wires preferences.
        self.export_settings_panel = self._build_export_settings()
        # Start compact before Qt evaluates minimum size hints: the legacy
        # two-column Export grid must not raise the sidebar's own minimum.
        self._arrange_export_grid(True)
        self.export_action_panel = self._build_export_actions()
        self.tabs.addTab(self._plan_tab(), "Plan")
        self.tabs.addTab(self.filaments_panel, "Filaments")
        self.tabs.currentChanged.connect(self._tab_changed)
        # _plan_tab wired preference updates first; load filament options only
        # after the plan values have received the new source selection.
        self.filament_source.currentIndexChanged.connect(
            lambda _: self.filaments_panel.load_options())
        self.results_panel = ResultsTab(self.tabs)
        self.results_panel.open_export_requested.connect(self._open_export_in_slicer)
        self.results_panel.show_export_folder_requested.connect(self._show_export_folder)
        self.results_panel.attach_export_panels(self.export_settings_panel, self.export_action_panel)
        self.results_panel.export_viewport_resized.connect(self._update_export_layout)
        self._initial_export_layout_timer.start(0)
        # Single source of truth for validated output actions, on the Export tab.
        self.open_export_button = self.results_panel.open_export_button
        self.export_folder_button = self.results_panel.export_folder_button
        self.tabs.addTab(self.results_panel, "Export")
        self.filaments_panel.activity_event.connect(self._filament_activity)
        self.filaments_panel.planning_changed.connect(self._filament_planning_changed)
        self.filaments_panel.explicit_refresh_requested.connect(self._stage_filament_forecast)
        self.filaments_panel.source_color_selected.connect(self._filament_color_selected)
        self.filaments_panel.protections_changed.connect(self._protections_updated)
        self.assignment_panel.remove_requested.connect(self.filaments_panel.remove_source_assignments)
        self.assignment_panel.clear_requested.connect(self._confirm_clear_all_assignments)
        self.confirm_filaments_tab_button = QPushButton('Use These Filaments for Forecast')
        self.confirm_filaments_tab_button.setObjectName('confirmFilamentsTab')
        self.confirm_filaments_tab_button.clicked.connect(self._confirm_filament_setup)
        filament_layout = self.filaments_panel.content.layout()
        filament_layout.insertWidget(
            filament_layout.indexOf(self.filaments_panel.selection_hint) + 1,
            self.confirm_filaments_tab_button)
        self.confirm_filaments_tab_button.setVisible(False)
        # Reuse the existing read-only forecast worker; no second optimizer.
        self.update_filament_forecast_button = QPushButton('Update Forecast')
        self.update_filament_forecast_button.setObjectName('updateFilamentForecast')
        self.update_filament_forecast_button.setToolTip(
            'Apply all staged filament and source-color changes in one read-only forecast.')
        self.update_filament_forecast_button.clicked.connect(self._update_filament_forecast)
        self.update_filament_forecast_hint = _label(
            'Filament changes are staged; the previous forecast is outdated until updated.',
            'helpText', wrap=True)
        index = filament_layout.indexOf(self.confirm_filaments_tab_button) + 1
        filament_layout.insertWidget(index, self.update_filament_forecast_button)
        filament_layout.insertWidget(index + 1, self.update_filament_forecast_hint)
        self.update_filament_forecast_button.setVisible(False)
        self.update_filament_forecast_hint.setVisible(False)
        self._refresh_export_directory()
        self._refresh_results_context()
        outer.addWidget(self.tabs)
        return sidebar

    def _scroll(self, content):
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(content)
        return scroller

    @staticmethod
    def _choice(items):
        combo = WheelSafeComboBox()
        for text, value in items:
            combo.addItem(text, value)
        return combo

    @staticmethod
    def _set_combo_value(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _build_export_settings(self):
        """Stage 5 v3: compact two-column setup, independent details disclosures."""
        panel = QWidget()
        panel.setObjectName('exportSettingsPanel')
        # QScrollArea must be allowed to size the compact form to its viewport.
        # Preferred size hints from the previous two-column grid must not force
        # the whole page wider than the narrow sidebar.
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        col = _column(panel, margins=(0, 0, 0, 0), spacing=9)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # First row: matching filename/directory pickers. Keep full paths in
        # tooltips; Qt's line edit handles ellipsis/scroll without truncation.
        template_box = QWidget()
        template_box.setMinimumWidth(0)
        template_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        template_col = _column(template_box, margins=(0, 0, 0, 0), spacing=5)
        template_title = QHBoxLayout()
        template_title.setContentsMargins(0, 0, 0, 0)
        template_title.setSpacing(4)
        template_help = help_heading('native_project_template', 'NATIVE TEMPLATE')
        template_help.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        template_title.addWidget(template_help)
        template_title.addStretch()
        template_col.addLayout(template_title)
        template_row = QHBoxLayout()
        template_row.setContentsMargins(0, 0, 0, 0)
        template_row.setSpacing(5)
        self.template_path = QLineEdit()
        self.template_path.setObjectName('nativeTemplatePath')
        self.template_path.setReadOnly(True)
        self.template_path.setMinimumWidth(0)
        self.template_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.template_path.setMinimumHeight(34)
        self.template_path.setPlaceholderText('Choose a 3MF template…')
        template_row.addWidget(self.template_path, 1)
        self.template_browse = QPushButton()
        compact_icon_button(self.template_browse, 'folder', 'Browse native project template', side=34)
        self.template_browse.clicked.connect(self._browse_template)
        template_row.addWidget(self.template_browse)
        self.template_clear = QPushButton()
        compact_icon_button(self.template_clear, 'x', 'Clear native project template', side=34)
        self.template_clear.clicked.connect(self._clear_template)
        template_row.addWidget(self.template_clear)
        template_col.addLayout(template_row)
        grid.addWidget(template_box, 0, 0)

        directory_box = QWidget()
        directory_box.setMinimumWidth(0)
        directory_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        directory_col = _column(directory_box, margins=(0, 0, 0, 0), spacing=5)
        directory_title = QHBoxLayout()
        directory_title.setContentsMargins(0, 0, 0, 0)
        directory_title.addWidget(_label('OUTPUT DIRECTORY', 'sectionTitle'))
        directory_title.addStretch()
        directory_col.addLayout(directory_title)
        directory_row = QHBoxLayout()
        directory_row.setContentsMargins(0, 0, 0, 0)
        directory_row.setSpacing(5)
        self.export_directory = QLineEdit()
        self.export_directory.setObjectName('exportOutputDirectory')
        self.export_directory.setReadOnly(True)
        self.export_directory.setMinimumWidth(0)
        self.export_directory.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.export_directory.setMinimumHeight(34)
        self.export_directory.setPlaceholderText('Model folder (default)')
        self.export_directory.setToolTip('Defaults to the source model folder. Choose another folder for this session.')
        directory_row.addWidget(self.export_directory, 1)
        self.export_directory_browse = QPushButton()
        self.export_directory_browse.setObjectName('exportDirectoryBrowse')
        compact_icon_button(self.export_directory_browse, 'folder', 'Browse output directory', side=34)
        self.export_directory_browse.clicked.connect(self._choose_export_directory)
        directory_row.addWidget(self.export_directory_browse)
        # Match the two path-entry widths even though only a template can be
        # cleared; reserve the rightmost clear-button column on both sides.
        directory_row.addSpacing(39)
        directory_col.addLayout(directory_row)
        grid.addWidget(directory_box, 0, 1)

        # Actionable warnings start open, but can be collapsed into one compact
        # amber line. They are independent of the advanced executable settings.
        self.template_attention = QToolButton()
        self.template_attention.setObjectName('exportTemplateAttention')
        self.template_attention.setIcon(export_icon('alert', '#e9b66c'))
        self.template_attention.setIconSize(QSize(16, 16))
        self.template_attention.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.template_attention.setText('Template compatibility  ▾')
        self.template_attention.setCheckable(True)
        self.template_attention.setMinimumHeight(26)
        self.template_attention.setToolTip('Show or hide template compatibility details')
        self.template_attention.setStyleSheet(
            'QToolButton { color: #edbf73; font-weight: 600; '
            'border: 0; background: transparent; padding: 2px 4px; text-align: left; }'
            'QToolButton:hover { background: #302b22; border-radius: 5px; }')
        self.template_attention.hide()
        grid.addWidget(self.template_attention, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self.template_warning_panel = QFrame()
        self.template_warning_panel.setObjectName('exportTemplateWarningPanel')
        self.template_warning_panel.setStyleSheet(
            'QFrame#exportTemplateWarningPanel { background: #27251f; '
            'border: 1px solid #6d5739; border-radius: 6px; }')
        warning_col = _column(self.template_warning_panel, margins=(10, 8, 10, 8), spacing=4)
        self.template_status = _label('No template selected.', 'templateStatus', wrap=True)
        warning_col.addWidget(self.template_status)
        self.template_compatibility = _label('', 'templateWarning', wrap=True)
        warning_col.addWidget(self.template_compatibility)
        self.template_warning_panel.hide()
        self.template_attention.toggled.connect(self._toggle_template_warning)
        grid.addWidget(self.template_warning_panel, 2, 0, 1, 2)

        # Slicer controls and Advanced share one baseline across columns.
        slicer_box = QWidget()
        slicer_box.setMinimumWidth(0)
        slicer_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        slicer_col = _column(slicer_box, margins=(0, 0, 0, 0), spacing=5)
        slicer_heading = _label('OUTPUT SLICER', 'sectionTitle')
        slicer_heading.setFixedHeight(20)
        slicer_col.addWidget(slicer_heading)
        self.output_application = self._choice(OUTPUT_SLICERS)
        self.output_application.setParent(slicer_box)
        self.output_application.hide()  # Real PlanPreferences source of truth.
        self.slicer_segment = ExportSlicerSegment()
        self.slicer_segment.setObjectName('exportSlicerSegment')
        self.slicer_segment.setMaximumWidth(268)
        self.slicer_segment.setMinimumWidth(240)
        self.slicer_segment.setMinimumHeight(36)
        self.slicer_segment.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        slicer_row = QHBoxLayout(self.slicer_segment)
        slicer_row.setContentsMargins(0, 0, 0, 0)
        slicer_row.setSpacing(0)
        self.slicer_choice_buttons = {}
        for title, value in (('OrcaSlicer', 'OrcaSlicer'), ('Bambu Studio', 'Bambu Studio')):
            button = QPushButton(title, self.slicer_segment)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setObjectName('slicerChoiceOrca' if value == 'OrcaSlicer' else 'slicerChoiceBambu')
            button.setToolTip('Use ' + title + ' for exported projects')
            button.setAccessibleName(title)
            # Parent draws selected background and centered labels together.
            # Transparent QPushButtons remain the real interactive targets,
            # preserving click, keyboard, and saved-preference behavior.
            button.setStyleSheet(
                'QPushButton { background: transparent; color: transparent; border: none; '
                'border-radius: 0; padding: 5px 7px; }'
                'QPushButton:hover { background: transparent; }'
                'QPushButton:pressed { background: transparent; }'
                'QPushButton:checked { background: transparent; color: transparent; font-weight: 600; }')
            # Ignore each button's unequal native text size hint. Stretch=1
            # on the QHBoxLayout then gives exactly half to each click target.
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
            button.setMinimumWidth(0)
            button.setMinimumHeight(36)
            button.clicked.connect(
                lambda _checked=False, v=value: self._set_combo_value(self.output_application, v))
            self.slicer_choice_buttons[value] = button
            self.slicer_segment.watch_button(button)
            slicer_row.addWidget(button, 1)
        slicer_col.addWidget(self.slicer_segment, 0, Qt.AlignmentFlag.AlignLeft)
        self.output_application.currentIndexChanged.connect(self._sync_slicer_choice_buttons)
        self._sync_slicer_choice_buttons()
        grid.addWidget(slicer_box, 3, 0, Qt.AlignmentFlag.AlignTop)

        options_box = QWidget()
        options_box.setMinimumWidth(0)
        options_box.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        options_col = _column(options_box, margins=(0, 0, 0, 0), spacing=5)
        options_heading = _label('AFTER EXPORTING', 'sectionTitle')
        options_heading.setFixedHeight(20)
        options_col.addWidget(options_heading)
        options_row = QHBoxLayout()
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.setSpacing(6)
        self.auto_open = QCheckBox('Open automatically')
        self.auto_open.setToolTip('Open validated output in the selected slicer after export.')
        self.auto_open.setMinimumHeight(36)
        options_row.addWidget(self.auto_open, 1)
        self.export_advanced_toggle = QToolButton()
        self.export_advanced_toggle.setObjectName('exportAdvancedToggle')
        self.export_advanced_toggle.setText('Advanced')
        self.export_advanced_toggle.setIcon(export_icon('settings'))
        self.export_advanced_toggle.setIconSize(QSize(16, 16))
        self.export_advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export_advanced_toggle.setMinimumHeight(36)
        self.export_advanced_toggle.setCheckable(True)
        self.export_advanced_toggle.setToolTip('Advanced slicer executable and preference settings')
        options_row.addWidget(self.export_advanced_toggle)
        options_col.addLayout(options_row)
        grid.addWidget(options_box, 3, 1, Qt.AlignmentFlag.AlignTop)
        self._export_settings_grid = grid
        self._export_grid_sections = (
            template_box, directory_box, self.template_attention,
            self.template_warning_panel, slicer_box, options_box,
        )
        self._export_grid_compact = None
        col.addLayout(grid)

        # Only slicer-launch configuration belongs under Advanced. The mode
        # mirrors the existing per-slicer executable preference; selecting
        # Custom without choosing a file never invents a saved EXE path.
        self.export_advanced_panel = QFrame()
        self.export_advanced_panel.setObjectName('exportAdvancedPanel')
        self.export_advanced_panel.setStyleSheet(
            'QFrame#exportAdvancedPanel { background: #1a222a; '
            'border: 1px solid #364652; border-radius: 6px; }')
        advanced_col = _column(self.export_advanced_panel, margins=(12, 10, 12, 10), spacing=7)
        advanced_col.addWidget(_label('SLICER LAUNCH', 'sectionTitle'))
        self.slicer_executable_row = QWidget()
        executable_col = _column(self.slicer_executable_row, margins=(0, 0, 0, 0), spacing=7)
        launch_modes = QGridLayout()
        launch_modes.setContentsMargins(0, 0, 0, 0)
        launch_modes.setHorizontalSpacing(16)
        launch_modes.setVerticalSpacing(4)
        self._export_launch_modes = launch_modes
        self.slicer_executable_auto = QRadioButton('Automatic detection')
        self.slicer_executable_auto.setObjectName('slicerExecutableAuto')
        self.slicer_executable_auto.setToolTip('Find the installed executable for the selected slicer.')
        self.slicer_executable_custom = QRadioButton('Custom executable')
        self.slicer_executable_custom.setObjectName('slicerExecutableCustom')
        self.slicer_executable_custom.setToolTip('Use a portable, nightly, or manually installed slicer.')
        launch_modes.addWidget(self.slicer_executable_auto, 0, 0)
        launch_modes.addWidget(self.slicer_executable_custom, 0, 1)
        launch_modes.setColumnStretch(2, 1)
        executable_col.addLayout(launch_modes)
        self.slicer_custom_controls = QWidget()
        custom_row = QHBoxLayout(self.slicer_custom_controls)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(8)
        self.slicer_executable_status = _label('automatic executable detection', 'helpText')
        self.slicer_executable_status.setObjectName('slicerExecutableStatus')
        self.slicer_executable_status.setWordWrap(False)
        self.slicer_executable_status.setMinimumWidth(0)
        self.slicer_executable_status.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        custom_row.addWidget(self.slicer_executable_status, 1)
        self.slicer_executable_browse = QPushButton('Browse…')
        self.slicer_executable_browse.setIcon(export_icon('folder'))
        self.slicer_executable_browse.setIconSize(QSize(16, 16))
        self.slicer_executable_browse.setMinimumHeight(34)
        self.slicer_executable_browse.setObjectName('slicerExecutableBrowse')
        self.slicer_executable_browse.clicked.connect(self._browse_slicer_executable)
        custom_row.addWidget(self.slicer_executable_browse)
        executable_col.addWidget(self.slicer_custom_controls)
        self.slicer_executable_auto.toggled.connect(self._automatic_slicer_mode_selected)
        self.slicer_executable_custom.toggled.connect(self._custom_slicer_mode_selected)
        advanced_col.addWidget(self.slicer_executable_row)
        # FULLSPECTRUM_STAGE_1_3_1_4: Optional reports affect publication only;
        # engine validation continues generating all diagnostics in staging.
        advanced_col.addWidget(_label('ADDITIONAL OUTPUT FILES', 'sectionTitle'))
        self.export_recipe_csv = QCheckBox('Recipe CSV (.csv)')
        self.export_report_txt = QCheckBox('Conversion report (.txt)')
        self.export_validation_md = QCheckBox('Color validation report (.md)')
        for checkbox, field, detail in (
            (self.export_recipe_csv, 'export_recipe_csv', 'Recipe and filament mapping data'),
            (self.export_report_txt, 'export_report_txt', 'Human-readable conversion report'),
            (self.export_validation_md, 'export_validation_md', 'Detailed color validation findings'),
        ):
            checkbox.setObjectName(field)
            checkbox.setChecked(self.plan_preferences.get(field))
            checkbox.setToolTip(detail + '. Unchecking does not disable 3MF validation.')
            advanced_col.addWidget(checkbox)
        self.export_advanced_toggle.toggled.connect(self.export_advanced_panel.setVisible)
        self.export_advanced_panel.hide()
        col.addWidget(self.export_advanced_panel)

        # Save/Revert is contextual, not an advanced executable preference.
        # The row is absent entirely until any PlanPreferences value is dirty.
        self.export_preferences_row = QWidget()
        self.export_preferences_row.setMinimumWidth(0)
        self.export_preferences_row.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        # A narrow export sidebar must not collapse these controls to zero.
        self.export_preferences_row.setMinimumHeight(114)
        preference_buttons = QVBoxLayout(self.export_preferences_row)
        preference_buttons.setContentsMargins(0, 0, 0, 0)
        preference_buttons.setSpacing(4)
        self.export_preferences_caption = _label('UNSAVED SETTINGS', 'sectionTitle')
        preference_buttons.addWidget(self.export_preferences_caption)
        self.export_pending_details = _label('', 'helpText', wrap=True)
        self.export_pending_details.setObjectName('exportPendingChanges')
        self.export_pending_details.setToolTip('Edits are not saved until you choose Save Settings.')
        preference_buttons.addWidget(self.export_pending_details)
        preference_actions = QHBoxLayout()
        preference_actions.setContentsMargins(0, 0, 0, 0)
        preference_actions.setSpacing(7)
        preference_actions.addStretch(1)
        self.export_save_settings_button = QPushButton('Save Settings')
        self.export_save_settings_button.setIcon(export_icon('save'))
        self.export_save_settings_button.setMinimumHeight(34)
        self.export_save_settings_button.setObjectName('exportSaveSettings')
        self.export_save_settings_button.clicked.connect(self._save_plan_settings)
        self.export_save_settings_button.setMinimumWidth(116)
        self.export_save_settings_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        preference_actions.addWidget(self.export_save_settings_button)
        self.export_revert_settings_button = QPushButton('Revert')
        self.export_revert_settings_button.setIcon(export_icon('reset'))
        self.export_revert_settings_button.setMinimumHeight(34)
        self.export_revert_settings_button.setObjectName('exportRevertSettings')
        self.export_revert_settings_button.clicked.connect(self._revert_plan_settings)
        self.export_revert_settings_button.setMinimumWidth(84)
        self.export_revert_settings_button.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        preference_actions.addWidget(self.export_revert_settings_button)
        preference_buttons.addLayout(preference_actions)
        self.export_preferences_row.hide()
        col.addWidget(self.export_preferences_row)
        return panel

    def _arrange_export_grid(self, compact):
        """Move existing widgets without reconstructing controls or preferences."""
        compact = bool(compact)
        if self._export_grid_compact is compact:
            return
        grid = self._export_settings_grid
        grid.setHorizontalSpacing(0 if compact else 12)
        template, directory, warning_toggle, warning, slicer, after = self._export_grid_sections
        for widget in self._export_grid_sections:
            grid.removeWidget(widget)
        if compact:
            # Narrow sidebar: no two-column minimum size hint can crop fields.
            for row, widget in enumerate((template, warning_toggle, warning,
                                          directory, slicer, after)):
                alignment = (Qt.AlignmentFlag.AlignLeft if widget is warning_toggle
                             else Qt.AlignmentFlag.AlignTop if widget in (slicer, after)
                             else Qt.AlignmentFlag(0))
                grid.addWidget(widget, row, 0, alignment)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)
        else:
            grid.addWidget(template, 0, 0)
            grid.addWidget(directory, 0, 1)
            grid.addWidget(warning_toggle, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(warning, 2, 0, 1, 2)
            grid.addWidget(slicer, 3, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(after, 3, 1, Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
        # Slicer launch modes must also wrap when Advanced is expanded.
        radios = self._export_launch_modes
        radios.removeWidget(self.slicer_executable_auto)
        radios.removeWidget(self.slicer_executable_custom)
        radios.addWidget(self.slicer_executable_auto, 0, 0)
        radios.addWidget(self.slicer_executable_custom, 1 if compact else 0,
                         0 if compact else 1)
        # Remove only the unsaved-settings caption in narrow view; the actual
        # Save/Revert buttons stay accessible on the same row.
        self.export_preferences_caption.setVisible(True)
        self._export_grid_compact = compact
        grid.invalidate()
        self.export_settings_panel.updateGeometry()

    def _qt_widgets_alive(self, *widgets):
        """Avoid callbacks on deleted C++ children during test teardown."""
        import shiboken6
        if getattr(self, '_qt_disposing', False) or not shiboken6.isValid(self):
            return False
        return all(w is not None and shiboken6.isValid(w) for w in widgets)

    def _update_export_layout(self, viewport_width=None):
        """Qt viewport width determines whether Export is one or two columns."""
        if not hasattr(self, 'results_panel') or not self._qt_widgets_alive(self.results_panel):
            return
        try:
            scroll = self.results_panel.content_scroll
            if not self._qt_widgets_alive(scroll):
                return
            viewport = scroll.viewport()
            if not self._qt_widgets_alive(viewport):
                return
            if not isinstance(viewport_width, int):
                viewport_width = viewport.width()
        except RuntimeError:  # A Qt C++ child may already be gone during teardown.
            return
        # The scroll-page has 12px margins on both sides. A roomy breakpoint
        # prevents two-column size hints from exceeding available width.
        available = viewport_width - 24
        # Hysteresis prevents two-column minimum hints and a transient
        # scrollbar from oscillating around a single breakpoint.
        limit = 690 if self._export_grid_compact else 650
        compact = available < limit
        if compact != self._export_grid_compact:
            # Diagnostics is now inside a normal QVBoxLayout header; it follows
            # Export geometry automatically. Do not call the removed overlay API.
            self._arrange_export_grid(compact)

    def _toggle_template_warning(self, checked):
        """Only this disclosure controls template information, not Advanced."""
        self.template_warning_panel.setVisible(bool(checked))
        self.template_attention.setText(
            ('Compatibility warning' if (
                self.template_compatibility.text().strip() or
                self.template_status.objectName() == 'templateStatusError'
            ) else 'Template required') + ('  ▾' if checked else '  ▸'))
    def _sync_slicer_choice_buttons(self, *_unused):
        """Mirror saved preference in transparent hit targets and painted pill."""
        value = self.output_application.currentData()
        for key, button in self.slicer_choice_buttons.items():
            button.setChecked(key == value)
        self.slicer_segment.set_selected(1 if value == 'Bambu Studio' else 0)

    def _build_export_actions(self):
        """One export action footprint: ready button or progress plus Cancel."""
        panel = QWidget()
        panel.setObjectName('exportActionsPanel')
        col = _column(panel, margins=(0, 0, 0, 0), spacing=5)
        self.export_section_divider = QFrame()
        self.export_section_divider.setObjectName('exportActionDivider')
        self.export_section_divider.setFixedHeight(1)
        self.export_section_divider.setStyleSheet('background: #36414b; border: none;')
        col.addWidget(self.export_section_divider)
        col.addSpacing(8)
        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.setSpacing(6)
        self.export_action_stack = QStackedWidget()
        self.export_action_stack.setObjectName('exportActionStack')
        self.compose_button = QPushButton('Export Native 3MF')
        self.compose_button.setObjectName('primary')
        self.compose_button.setAccessibleName('export3mfButton')
        self.compose_button.setEnabled(False)
        self.compose_button.setToolTip('Generate and validate a native 3MF; optional reports are controlled under Advanced.')
        self.compose_button.clicked.connect(self._begin_export)
        self.compose_button.setIcon(export_icon('export'))
        self.compose_button.setIconSize(QSize(18, 18))
        self.compose_button.setMinimumHeight(36)
        self.export_action_stack.addWidget(self.compose_button)
        self.export_progress = QProgressBar()
        self.export_progress.setObjectName('exportProgress')
        self.export_progress.setRange(0, 100)
        self.export_progress.setFormat('Exporting native 3MF  ·  %p%')
        self.export_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.export_progress.setMinimumHeight(36)
        self.export_progress.setStyleSheet(
            'QProgressBar#exportProgress { background: #202c3d; color: #f1f6ff; '
            'border: 1px solid #375781; border-radius: 6px; text-align: center; '
            'font-weight: 600; }'
            'QProgressBar#exportProgress::chunk { background: #357fee; border-radius: 5px; }')
        self.export_action_stack.addWidget(self.export_progress)
        export_row.addWidget(self.export_action_stack, 1)
        self.export_cancel_button = QPushButton('Cancel')
        self.export_cancel_button.setObjectName('cancelExportButton')
        self.export_cancel_button.setIcon(export_icon('x'))
        self.export_cancel_button.setIconSize(QSize(16, 16))
        self.export_cancel_button.setMinimumHeight(36)
        self.export_cancel_button.setMinimumWidth(90)
        self.export_cancel_button.setToolTip('Request cancellation at the next safe export checkpoint')
        self.export_cancel_button.setEnabled(False)
        self.export_cancel_button.clicked.connect(self._cancel_export)
        self.export_cancel_button.setVisible(False)
        export_row.addWidget(self.export_cancel_button)
        col.addLayout(export_row)
        self.export_status = _label('', 'helpText', wrap=True)
        self.export_status.setObjectName('exportStatus')
        self.export_status.hide()
        col.addWidget(self.export_status)
        return panel

    def _show_export_tab(self):
        self.tabs.setCurrentWidget(self.results_panel)

    def _refresh_export_directory(self):
        if getattr(self, '_export_directory_override', None):
            folder = self._export_directory_override
        elif self.state.model_path:
            folder = str(Path(self.state.model_path).parent)
        else:
            folder = ''
        self.export_directory.setText(folder)
        self.export_directory.setToolTip(folder or 'Open a model to select the default output directory.')

    def _choose_export_directory(self):
        if self._export_task is not None:
            return
        initial = (self.export_directory.text().strip() or
                   str(Path(self.state.model_path).parent) if self.state.model_path else str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, 'Choose 3MF Output Folder', initial)
        if folder:
            self._export_directory_override = str(Path(folder).resolve())
            self._refresh_export_directory()

    def _plan_tab(self):
        page = QWidget()
        col = _column(page, margins=(10, 15, 10, 12), spacing=11)
        col.addWidget(help_heading("live_forecast", "LIVE FORECAST"))
        panel = self._section()
        stats = QHBoxLayout(panel)
        stats.setContentsMargins(14, 14, 14, 14)
        self.accuracy = RingGauge('Accuracy', '#66c797')
        self.accuracy.setObjectName('forecastAccuracy')
        self.confidence_gauge = RingGauge('Confidence', '#5fb8d0')
        self.confidence_gauge.setObjectName('forecastConfidence')
        stats.addWidget(self.accuracy,1)
        stats.addWidget(self.confidence_gauge,1)
        detail = QVBoxLayout()
        detail.setSpacing(9)
        self.forecast_metrics = {}
        for field in ("Confidence", "Mean ΔE", "Palette"):
            line = QHBoxLayout()
            line.addWidget(_label(field, "bodyMuted"))
            line.addStretch()
            value = _label("—", "helpText")
            self.forecast_metrics[field] = value
            line.addWidget(value)
            detail.addLayout(line)
        stats.addLayout(detail, stretch=2)
        col.addWidget(panel)
        progress_row = QHBoxLayout()
        self.forecast_refresh = QPushButton('Refresh Forecast')
        self.forecast_refresh.setObjectName('refreshForecastButton')
        self.forecast_refresh.setEnabled(False)
        self.forecast_refresh.clicked.connect(self._request_forecast)
        progress_row.addWidget(self.forecast_refresh)
        self.forecast_cancel = QPushButton('Cancel')
        self.forecast_cancel.setObjectName('cancelForecastButton')
        self.forecast_cancel.setEnabled(False)
        self.forecast_cancel.clicked.connect(self._cancel_forecast)
        progress_row.addWidget(self.forecast_cancel)
        col.addLayout(progress_row)
        self.forecast_progress = QProgressBar()
        self.forecast_progress.setObjectName('forecastProgress')
        self.forecast_progress.setRange(0, 100)
        self.forecast_progress.setValue(0)
        self.forecast_progress.setVisible(False)
        col.addWidget(self.forecast_progress)
        self.forecast_status = _label('Open a model to inspect and forecast its palette.', 'helpText', wrap=True)
        self.forecast_status.setObjectName('forecastStatus')
        self.forecast_status.setAccessibleName('Forecast status')
        col.addWidget(self.forecast_status)
        self.filament_setup_banner = QFrame()
        self.filament_setup_banner.setObjectName('filamentSetupBanner')
        self.filament_setup_banner.setStyleSheet(
            'QFrame#filamentSetupBanner {background: #17232b; border: 1px solid #3b6471; '
            'border-radius: 7px;}'
        )
        setup_col = QVBoxLayout(self.filament_setup_banner)
        setup_col.setContentsMargins(12, 10, 12, 10)
        setup_col.setSpacing(8)
        self.filament_setup_message = _label(
            'Configure your available filaments before the first forecast.',
            'helpText', wrap=True)
        setup_col.addWidget(self.filament_setup_message)
        actions = QHBoxLayout()
        self.configure_filaments_button = QPushButton('Configure Filaments…')
        self.configure_filaments_button.setObjectName('configureFilamentsFirstRun')
        self.configure_filaments_button.clicked.connect(
            lambda: self.tabs.setCurrentWidget(self.filaments_panel))
        actions.addWidget(self.configure_filaments_button)
        self.confirm_filaments_button = QPushButton('Use These Filaments')
        self.confirm_filaments_button.setObjectName('confirmFilamentsFirstRun')
        self.confirm_filaments_button.setEnabled(False)
        self.confirm_filaments_button.clicked.connect(self._confirm_filament_setup)
        actions.addWidget(self.confirm_filaments_button)
        setup_col.addLayout(actions)
        col.addWidget(self.filament_setup_banner)
        self.filament_setup_ready_note = _label('', 'helpText', wrap=True)
        self.filament_setup_ready_note.setObjectName('filamentSetupReadyNote')
        self.filament_setup_ready_note.setStyleSheet('color: #77d3b3;')
        self.filament_setup_ready_note.setVisible(False)
        col.addWidget(self.filament_setup_ready_note)
        self.source_inspection = _label('Source: not inspected', 'bodyMuted', wrap=True)
        self.source_inspection.setObjectName('sourceInspection')
        col.addWidget(self.source_inspection)
        col.addWidget(help_heading("expected_palette", "EXPECTED PALETTE"))
        forecast = self._section()
        inner = _column(forecast, margins=(12, 12, 12, 12), spacing=7)
        self.forecast_palette_label = _label('No forecast yet. Select Refresh Forecast to run the existing optimizer without exporting.', 'bodyMuted', wrap=True)
        self.forecast_palette_label.setObjectName('forecastPaletteSummary')
        inner.addWidget(self.forecast_palette_label)
        self.forecast_swatch_panel = QWidget()
        self.forecast_swatch_panel.setObjectName('forecastSwatches')
        self.forecast_swatch_grid = QGridLayout(self.forecast_swatch_panel)
        self.forecast_swatch_grid.setContentsMargins(0,0,0,0)
        self.forecast_swatch_grid.setSpacing(5)
        inner.addWidget(self.forecast_swatch_panel)
        # Compact Mac-style comparison belongs with the expected palette,
        # not as a second full-width banner above Refresh Forecast.
        self.worst_match_panel = WorstMatchPanel()
        inner.addWidget(self.worst_match_panel)
        self.forecast_warning = _label('', 'helpText', wrap=True)
        inner.addWidget(self.forecast_warning)
        col.addWidget(forecast)
        # Stage 4B: inspect the engine-selected physical and mixed filament
        # slots without adding a second optimizer or mutating existing pins.
        self.details_toggle = QToolButton()
        self.details_toggle.setObjectName('optimizationDetailsToggle')
        self.details_toggle.setText('Optimization Details ▸')
        self.details_toggle.setCheckable(True)
        self.details_toggle.setEnabled(False)
        self.details_toggle.toggled.connect(self._toggle_planning_details)
        details_title_row = QHBoxLayout()
        details_title_row.setSpacing(7)
        details_title_row.addWidget(self.details_toggle)
        details_title_row.addStretch()
        col.addLayout(details_title_row)
        self.planning_details_panel = PlanningDetailsPanel()
        self.planning_details_panel.setVisible(False)
        self.planning_details_panel.review_filament.connect(self._review_planned_filament)
        col.addWidget(self.planning_details_panel)
        col.addWidget(help_heading("color_optimization", "COLOR OPTIMIZATION"))
        col.addWidget(_label("Optimization strategy", "smallTitle"))
        self.palette_strategy = self._choice(PALETTE_STRATEGIES)
        self.palette_strategy.setObjectName("paletteStrategy")
        col.addWidget(self.palette_strategy)
        self.strategy_hint = _label("", "helpText", wrap=True)
        col.addWidget(self.strategy_hint)
        col.addWidget(_label("Maximum palette size", "smallTitle"))
        # Compact common presets, with precise 2–32 values through Custom.
        # The existing planner/3MF cap is deliberately unchanged here.
        self.palette_limit = self._choice((("Auto", "auto"),
            ("8 colors", "8"), ("16 colors", "16"),
            ("24 colors", "24"), ("32 colors", "32")))
        self.palette_limit.setObjectName("paletteLimit")
        palette_limit_row = QHBoxLayout()
        palette_limit_row.setSpacing(6)
        palette_limit_row.addWidget(self.palette_limit, 1)
        self.palette_limit_custom = QPushButton("Custom…")
        self.palette_limit_custom.setObjectName("paletteLimitCustom")
        self.palette_limit_custom.setToolTip("Enter an exact palette budget from 2 to 32.")
        self.palette_limit_custom.clicked.connect(self._choose_custom_palette_limit)
        palette_limit_row.addWidget(self.palette_limit_custom)
        col.addLayout(palette_limit_row)
        col.addWidget(_label("Current FullSpectrum planner limit: 32 total colors. "
                               "Bambu Studio 2.9.1 exempts mixed-color recipes "
                               "from its 32 project-filament limit; larger budgets "
                               "require separately validated engine/export support.",
                               "helpText", wrap=True))
        shortcut = QPushButton('Manage Filament Colors…')
        shortcut.setObjectName('manageFilamentsButton')
        shortcut.setToolTip('Choose usable and required filament colors under Filaments.')
        shortcut.clicked.connect(lambda: self.tabs.setCurrentWidget(self.filaments_panel))
        col.addWidget(shortcut)
        col.addWidget(_label('Filament source and material selection are managed on the Filaments tab.',
                             'helpText', wrap=True))
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced Settings ▸")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setObjectName("advancedToggle")
        advanced_title_row = QHBoxLayout()
        advanced_title_row.setSpacing(7)
        advanced_title_row.addWidget(self.advanced_toggle)
        advanced_title_row.addWidget(SectionHelpButton('advanced_settings'))
        advanced_title_row.addStretch()
        col.addLayout(advanced_title_row)
        self.advanced_panel = self._section()
        form = QFormLayout(self.advanced_panel)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(9)
        self.palette_base = self._choice(PALETTE_BASE)
        form.addRow("Palette base", self.palette_base)
        self.planner_effort = self._choice(PLAN_EFFORT)
        form.addRow("Planning effort", self.planner_effort)
        self.planning_sample = self._choice(PLANNING_SAMPLES)
        form.addRow("Planning sample", self.planning_sample)
        self.physical_slots = self._choice(PHYSICAL_SLOTS)
        form.addRow("Physical slots", self.physical_slots)
        self.catalog_region = self._choice(REGIONS)
        form.addRow("Catalog region", self.catalog_region)
        self.smart_quality = QCheckBox("Smart quality")
        form.addRow(self.smart_quality)
        # The engine already stores quality_bias as an integer from 0–100.
        # Keep the same property so both Qt and Tkinter share preferences.
        self.quality_bias_row = QWidget()
        quality_controls = QHBoxLayout(self.quality_bias_row)
        quality_controls.setContentsMargins(0, 0, 0, 0)
        quality_controls.setSpacing(9)
        self.quality_bias = QSlider(Qt.Orientation.Horizontal)
        self.quality_bias.setObjectName("qualityBiasSlider")
        self.quality_bias.setRange(0, 100)
        self.quality_bias.setSingleStep(1)
        self.quality_bias.setPageStep(5)
        self.quality_bias.setAccessibleName("Quality versus waste")
        self.quality_bias.setToolTip(
            "Lower values prioritize reduced material waste; "
            "higher values prioritize color accuracy."
        )
        quality_controls.addWidget(self.quality_bias, stretch=1)
        self.quality_bias_value = _label("60", "qualityBiasValue")
        self.quality_bias_value.setMinimumWidth(27)
        self.quality_bias_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        quality_controls.addWidget(self.quality_bias_value)
        # A separate, ENABLED status chip makes automatic management obvious.
        # Do not disable the containing row: that would mute this indicator too.
        self.quality_auto_badge = _label("AUTO", "qualityBiasAuto")
        self.quality_auto_badge.setToolTip("Smart Quality manages this setting automatically.")
        self.quality_auto_badge.setAccessibleName("Managed automatically by Smart Quality")
        quality_controls.addWidget(self.quality_auto_badge)
        self.quality_bias_caption = QLabel("Quality vs. waste")
        form.addRow(self.quality_bias_caption, self.quality_bias_row)
        self.auto_forecast = QCheckBox("Automatic forecast")
        self.auto_forecast.setToolTip("Refreshes the forecast after model or planning changes; uses the existing optimizer.")
        form.addRow(self.auto_forecast)
        col.addWidget(self.advanced_panel)
        self.advanced_panel.setVisible(False)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        col.addStretch(1)
        actions = QHBoxLayout()
        self.save_plan_button = QPushButton("Save Settings")
        self.save_plan_button.setObjectName("savePlanSettings")
        self.save_plan_button.clicked.connect(self._save_plan_settings)
        actions.addWidget(self.save_plan_button)
        self.revert_plan_button = QPushButton("Revert")
        self.revert_plan_button.clicked.connect(self._revert_plan_settings)
        actions.addWidget(self.revert_plan_button)
        col.addLayout(actions)
        self.plan_save_status = _label("Settings loaded", "helpText", wrap=True)
        col.addWidget(self.plan_save_status)
        self.review_export_button = QPushButton('Review && Export →')
        self.review_export_button.setObjectName('reviewExportShortcut')
        self.review_export_button.setToolTip('Open the Export tab to review native project settings and generate a validated 3MF.')
        self.review_export_button.clicked.connect(self._show_export_tab)
        col.addWidget(self.review_export_button)
        col.addWidget(_label('Live Forecast is read-only; conversion settings and validation are on Export.',
                              'helpText', wrap=True))
        self._restore_plan_widgets()
        self._wire_plan_widgets()
        return self._scroll(page)

    def _toggle_planning_details(self, checked):
        self.planning_details_panel.setVisible(bool(checked))
        self.details_toggle.setText('Optimization Details ▾' if checked else 'Optimization Details ▸')

    def _review_planned_filament(self, key):
        """Navigate to an existing physical option, never silently change pins."""
        if not key:
            return
        self.tabs.setCurrentWidget(self.filaments_panel)
        # First visit may still be loading the source-specific filament list.
        # Complete the navigation after that worker returns.
        if (self.filaments_panel._source_signature != self.filaments_panel._source_settings()
                or getattr(self.filaments_panel, '_population_active', False)
                or (not self.filaments_panel.options and self.filaments_panel._workers)):
            self._pending_review_filament_key = key
            self.results_panel.record_event('Planning details', 'Waiting for filament colors to load…', 'info')
            return
        match = next((option for option in self.filaments_panel.options
                      if option.get('key') == key), None)
        if match:
            # The table already filters by name/series/HEX. This sets a useful
            # search term but does not edit its enable/pin checkboxes.
            self.filaments_panel.search.setText(str(match.get('name') or match.get('color') or ''))
            for index, option in enumerate(self.filaments_panel.options):
                if option.get('key') == key and not self.filaments_panel.filaments.isRowHidden(index):
                    self.filaments_panel.filaments.selectRow(index)
                    self.filaments_panel.filaments.scrollToItem(
                        self.filaments_panel.filaments.item(index, 2))
                    break
            self.filaments_panel.search.setFocus()
            self.results_panel.record_event('Planning details',
                'Showing the chosen physical filament in the Filaments list.', 'info')
        else:
            self.filaments_panel.search.setText('')
            self.results_panel.record_event('Planning details',
                'Planned material is not in the currently loaded filament choices; check the source.', 'warning')

    def _toggle_advanced(self, checked):
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setText("Advanced Settings ▾" if checked else "Advanced Settings ▸")

    def _set_palette_limit_choice(self, value):
        """Show a saved 2–32 custom value without a 31-row dropdown."""
        value = str(value)
        standard = {'auto', '8', '16', '24', '32'}
        if value != 'auto' and (not value.isdecimal() or not 2 <= int(value) <= 32):
            value = 'auto'
        previous = getattr(self, '_palette_custom_value', None)
        if previous and previous not in standard:
            index = self.palette_limit.findData(previous)
            if index >= 0:
                self.palette_limit.removeItem(index)
        self._palette_custom_value = None
        if self.palette_limit.findData(value) < 0:
            self.palette_limit.addItem(f'(Custom) {value} colors', value)
            self._palette_custom_value = value
        self._set_combo_value(self.palette_limit, value)

    def _choose_custom_palette_limit(self, _checked=False):
        current = self.palette_limit.currentData()
        starting = int(current) if str(current).isdecimal() else 32
        value, accepted = QInputDialog.getInt(
            self, 'Custom Palette Size', 'Maximum output colors:',
            starting, 2, 32, 1)
        if not accepted:
            return
        # Suppress intermediate signal emissions when swapping a custom item.
        with QSignalBlocker(self.palette_limit):
            self._set_palette_limit_choice(str(value))
        self._update_plan_value('max_output_colors', str(value))

    def _restore_plan_widgets(self):
        self._loading_plan_ui = True
        mapping = (
            (self.palette_strategy, "output_color_strategy"),
            (self.palette_limit, "max_output_colors"),
            (self.filament_source, "source"),
            (self.palette_base, "strategy"),
            (self.planner_effort, "planner_mode"),
            (self.planning_sample, "planning_sample"),
            (self.physical_slots, "real_slots"),
            (self.catalog_region, "catalog_region"),
            (self.output_application, "output_application"),
        )
        for widget, field in mapping:
            self._set_combo_value(widget, self.plan_preferences.get(field))
        # Saved custom palette budgets must survive UI restore/revert.
        self._set_palette_limit_choice(self.plan_preferences.get("max_output_colors"))
        for widget, field in (
            (self.smart_quality, "smart_quality"),
            (self.auto_forecast, "auto_preview"),
            (self.auto_open, "auto_open"),
            (self.export_recipe_csv, "export_recipe_csv"),
            (self.export_report_txt, "export_report_txt"),
            (self.export_validation_md, "export_validation_md"),
        ):
            widget.setChecked(self.plan_preferences.get(field))
        self.quality_bias.setValue(self.plan_preferences.get("quality_bias"))
        self.quality_bias_value.setNum(self.quality_bias.value())
        self.template_path.setText(self.plan_preferences.get("native_project_template"))
        self.custom_library_path.setText(self.plan_preferences.get("custom"))
        self._loading_plan_ui = False
        self._refresh_dependent_plan_widgets()
        self._update_plan_dirty_state()

    def _wire_plan_widgets(self):
        for widget, field in (
            (self.palette_strategy, "output_color_strategy"),
            (self.palette_limit, "max_output_colors"),
            (self.filament_source, "source"),
            (self.palette_base, "strategy"),
            (self.planner_effort, "planner_mode"),
            (self.planning_sample, "planning_sample"),
            (self.physical_slots, "real_slots"),
            (self.catalog_region, "catalog_region"),
            (self.output_application, "output_application"),
        ):
            widget.currentIndexChanged.connect(
                lambda _index, cb=widget, key=field: self._update_plan_value(key, cb.currentData()))
        for widget, field in (
            (self.smart_quality, "smart_quality"),
            (self.auto_forecast, "auto_preview"),
            (self.auto_open, "auto_open"),
            (self.export_recipe_csv, "export_recipe_csv"),
            (self.export_report_txt, "export_report_txt"),
            (self.export_validation_md, "export_validation_md"),
        ):
            widget.toggled.connect(lambda checked, key=field: self._update_plan_value(key, checked))
        self.quality_bias.valueChanged.connect(self.quality_bias_value.setNum)
        self.quality_bias.valueChanged.connect(
            lambda value: self._update_plan_value("quality_bias", value))

    def _update_plan_value(self, field, value):
        if self._loading_plan_ui:
            return
        changed = self.plan_preferences.set(field, value)
        if changed and field in ('source', 'custom'):
            self._hold_filament_forecast()
            self._filament_options_ready = False
            self._filament_load_error = ''
            self._filament_setup_confirmed = True  # Explicit user source choice.
        self._refresh_dependent_plan_widgets()
        self._update_plan_dirty_state()
        # Saving the same value should never invalidate an existing forecast.
        if not changed and field != 'auto_preview':
            return
        # Automatic forecasting is a scheduling preference, not a planner input.
        # Turning it off must not erase (or invalidate) a successful result.
        if field == 'auto_preview':
            # Changing the scheduling preference does not invalidate the
            # engine result. It only changes how an already-outdated forecast
            # is presented, and whether a refresh is queued.
            if (value and self.state.model_path and self._original_mesh is not None and
                    # Stage 4A's lightweight behavior harness predates the
                    # first-run gate. A real window always provides it.
                    (not hasattr(self, '_filament_decision') or self._filament_decision().ready) and
                    (self._forecast_view.stale or not self._forecast_view.has_previous) and
                    not getattr(self, '_filament_forecast_held', False)):
                self._forecast_timer.start()
            elif not value:
                self._forecast_timer.stop()
                self._forecast_pending = False
            if self._forecast_view.stale or not self._forecast_view.has_previous:
                self._present_forecast_pending()
            return
        # Export-only configuration does not affect the palette forecast.
        if field in ('native_project_template', 'auto_open', 'output_application',
                     'bambu_studio_executable', 'orcaslicer_executable',
                     'export_recipe_csv', 'export_report_txt', 'export_validation_md'):
            return
        self._invalidate_forecast()
        if changed and field in ('source', 'custom'):
            self.filaments_panel.load_options()
        self._refresh_filament_setup_ui()

    def _refresh_dependent_plan_widgets(self):
        strategy = self.palette_strategy.currentData()
        self.strategy_hint.setText({
            "balanced": "Fewer mixtures while preserving useful detail.",
            "maximum_fidelity": "Adds recipes when they improve predicted color matching.",
            "fill_palette": "Attempts to fill available slots with distinct recipes.",
        }.get(strategy, ""))
        self.custom_file_row.setVisible(self.filament_source.currentData() == "custom")
        manual_quality = not self.smart_quality.isChecked()
        # Keep the indicator readable while the manual controls are disabled.
        self.quality_bias.setEnabled(manual_quality)
        self.quality_bias_value.setEnabled(manual_quality)
        self.quality_bias_caption.setEnabled(manual_quality)
        self.quality_auto_badge.setVisible(not manual_quality)
        self.quality_bias.setToolTip(
            "Smart Quality is on: this value is managed automatically. "
            "Uncheck Smart Quality to edit it."
            if not manual_quality else
            "Lower values prioritize reduced material waste; "
            "higher values prioritize color accuracy."
        )
        self._refresh_template_status()
        self._update_export_template_attention()
        self._refresh_slicer_executable_status()

    def _update_plan_dirty_state(self):
        dirty = self.plan_preferences.is_dirty
        self.save_plan_button.setEnabled(dirty)
        self.revert_plan_button.setEnabled(dirty)
        self.plan_save_status.setText("Unsaved changes" if dirty else "Settings saved or unchanged")
        if hasattr(self, 'export_save_settings_button'):
            self.export_pending_details.setText(summarize_pending(self.plan_preferences))
            self.export_save_settings_button.setEnabled(dirty)
            self.export_revert_settings_button.setEnabled(dirty)
            self.export_preferences_row.setVisible(dirty)
        if hasattr(self, 'results_panel'):
            self._refresh_results_context()

    def _activate_library_palette(self, path):
        """Apply a selected quick profile through the established engine source.

        No existing inventory, Bambu library, external JSON or export project is
        modified; the app-managed active palette is a normal custom library.
        """
        from desktop.qt_app.filament_library_store import active_file
        path = str(Path(path).resolve())
        if Path(path) != active_file().resolve():
            QMessageBox.warning(self, 'Unsafe Palette Path',
                                'Only the app-managed active palette may be selected here.')
            return
        self._hold_filament_forecast()
        self.custom_library_path.setText(path)
        self._update_plan_value('custom', path)
        index = self.filament_source.findData('custom')
        if index < 0:
            QMessageBox.warning(self, 'Custom Source Missing',
                                'The Custom filament library source is unavailable.')
            return
        if self.filament_source.currentIndex() != index:
            self.filament_source.setCurrentIndex(index)
        else:
            # Content may have changed while path stays identical.
            self._invalidate_forecast()
            self.filaments_panel.load_options(force=True)
        self.statusBar().showMessage(
            'Quick palette selected. Save Filaments to persist your source and Use/Require choices.')

    def _browse_custom_library(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Filament Library", "",
                                               "JSON filament libraries (*.json)")
        if path:
            self.custom_library_path.setText(path)
            self._update_plan_value("custom", path)
            self.filaments_panel.load_options()

    def _browse_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose Blank Native 3MF Project", "",
                                               "3MF projects (*.3mf)")
        if not path:
            return
        try:
            from native_project_template import inspect_template
            details = inspect_template(path)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Invalid Native Project Template", str(exc))
            return
        self.template_path.setText(details.get("path", path))
        self._update_plan_value("native_project_template", self.template_path.text())

    def _clear_template(self):
        self.template_path.clear()
        self._update_plan_value("native_project_template", "")

    def _refresh_template_status(self):
        path = self.template_path.text().strip()
        self.template_clear.setEnabled(bool(path))
        self.template_compatibility.setText("")
        requirement = template_requirement(self.state.model_path)
        if requirement.kind == 'native':
            # Neither an empty nor a saved template affects a native slicer
            # source. Keep the saved path usable for the next generic import.
            self.template_status.setObjectName('templateStatusReady')
            self.template_status.setText(
                'Using slicer settings embedded in the selected native 3MF. '
                'The saved template is ignored for this export.' if path
                else requirement.description)
            self.template_path.setToolTip(
                'Saved template (not used for this native 3MF export).' if path
                else 'Native 3MF provides its own printer and process settings.')
            self._repolish_template_status()
            return
        if not path:
            self.template_status.setObjectName('templateStatusEmpty')
            self.template_status.setText(requirement.description)
            self.template_path.setToolTip('Choose a blank slicer project for generic model inputs.')
            self._repolish_template_status()
            return
        self.template_path.setToolTip(path)
        try:
            from native_project_template import inspect_template
            details = inspect_template(path)
            self.template_status.setObjectName("templateStatusReady")
            self.template_status.setText(
                f"{details['slicer']} {details['slicerVersion']} · "
                f"{details['printerPreset']} · {details['nozzle']} mm · {details['processPreset']}")
            self._repolish_template_status()
            # The selected launch target takes precedence. Do not also show
            # Orca-specific H2C release guidance when launching in Bambu Studio.
            selected_app = self.output_application.currentData()
            template_app = details.get('slicer')
            if template_app and selected_app and template_app != selected_app:
                warning = (f"Template was saved by {template_app}, but output opens in "
                           f"{selected_app}. Use a matching native template if possible.")
            else:
                from orca_profile_warning import orca_h2c_warning
                warning = orca_h2c_warning(details, selected_app)
            if warning:
                self.template_compatibility.setText(warning)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self.template_status.setObjectName("templateStatusError")
            self.template_status.setText("Template unavailable or invalid: " + str(exc))
            self._repolish_template_status()

    def _update_export_template_attention(self):
        """Show an actionable compatibility notice without hiding real warnings.

        A new compatibility problem opens by default, but a user-collapsed
        notice stays collapsed until the underlying problem changes.
        """
        if not hasattr(self, 'template_attention'):
            return
        requirement = template_requirement(self.state.model_path)
        selected = bool(self.template_path.text().strip())
        missing = requirement.required and not selected
        # A selected template is harmless for native slicer input: the export
        # request ignores it without changing saved preferences.
        error = (self.template_status.objectName() == 'templateStatusError'
                 and requirement.kind != 'native')
        message = (self.template_compatibility.text().strip()
                   if requirement.kind != 'native' else '')
        if missing:
            short = 'Select a native 3MF template'
            detail = requirement.description
        elif requirement.kind == 'unreadable':
            short = 'Unable to inspect source 3MF'
            detail = requirement.description
        elif error:
            short = 'Native template unavailable'
            detail = self.template_status.text()
        elif message:
            short = 'Slicer / template compatibility warning'
            detail = message
        else:
            short = ''
            detail = ''
        self.template_attention.setToolTip(detail)
        self.template_attention.setAccessibleName(short or 'Template compatibility')
        key = (self.template_path.text().strip(),
               self.output_application.currentData(), short, detail)
        if key != getattr(self, '_export_template_warning_key', None):
            self._export_template_warning_key = key
            # A genuinely unsafe/incompatible selection needs immediate
            # visibility. Do not expand the missing-template hint on startup.
            self.template_attention.setChecked(bool(error or message))
        if not short:
            self.template_attention.setChecked(False)
        self.template_attention.setVisible(bool(short))
        self.template_warning_panel.setVisible(bool(short) and self.template_attention.isChecked())
        self.template_attention.setText(
            ('Compatibility warning' if (message or error or requirement.kind == 'unreadable')
             else 'Template required')
            + ('  ▾' if self.template_attention.isChecked() else '  ▸'))
    def _repolish_template_status(self):
        # Qt caches widget styles: changing objectName requires re-polishing.
        style = self.template_status.style()
        style.unpolish(self.template_status)
        style.polish(self.template_status)
        self.template_status.update()

    def _selected_slicer_executable_key(self):
        return ("orcaslicer_executable" if self.output_application.currentData() == "OrcaSlicer"
                else "bambu_studio_executable")

    def _automatic_slicer_mode_selected(self, checked):
        if checked and self.plan_preferences.get(self._selected_slicer_executable_key()).strip():
            self._clear_slicer_executable()
        if checked:
            self.slicer_custom_controls.hide()

    def _custom_slicer_mode_selected(self, checked):
        if checked:
            self.slicer_custom_controls.show()
            if not self.plan_preferences.get(self._selected_slicer_executable_key()).strip():
                self.slicer_executable_status.setText('Select an executable with Browse…')
                self.slicer_executable_status.setToolTip('Choose a portable or nightly slicer EXE.')

    def _refresh_slicer_executable_status(self):
        selected = self.output_application.currentData() or 'Bambu Studio'
        path = self.plan_preferences.get(self._selected_slicer_executable_key()).strip()
        # Programmatic restores must not fire the radio change handlers,
        # otherwise revisiting a saved Custom mode would clear its preference.
        with QSignalBlocker(self.slicer_executable_auto), QSignalBlocker(self.slicer_executable_custom):
            self.slicer_executable_auto.setChecked(not bool(path))
            self.slicer_executable_custom.setChecked(bool(path))
        self.slicer_custom_controls.setVisible(bool(path))
        if not path:
            self.slicer_executable_status.setText('automatic executable detection · ' + selected)
            self.slicer_executable_status.setStyleSheet('color: #aebfca;')
            tooltip = f'{selected}: automatic executable detection.'
        elif not Path(path).is_file():
            self.slicer_executable_status.setText('Missing custom executable · ' + path)
            self.slicer_executable_status.setStyleSheet('color: #f1b66d;')
            tooltip = f'Saved executable not found: {path}. Choose a new file or select Automatic.'
        else:
            self.slicer_executable_status.setText('Custom executable · ' + path)
            self.slicer_executable_status.setStyleSheet('color: #b8c9d6;')
            tooltip = path
        self.slicer_executable_status.setToolTip(tooltip)
    def _browse_slicer_executable(self):
        selected = self.output_application.currentData() or "Bambu Studio"
        path, _ = QFileDialog.getOpenFileName(
            self, f"Choose {selected} Executable", "",
            "Windows executables (*.exe);;All files (*)")
        if not path:
            return
        if Path(path).suffix.lower() != ".exe" or not Path(path).is_file():
            QMessageBox.warning(self, "Invalid Slicer Executable",
                                "Choose an existing Windows .exe file for the selected slicer.")
            return
        self._update_plan_value(self._selected_slicer_executable_key(), path)

    def _clear_slicer_executable(self):
        self._update_plan_value(self._selected_slicer_executable_key(), "")

    def _save_plan_settings(self):
        try:
            target = self.plan_preferences.save()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Unable to Save Settings", str(exc))
            return
        self._saved_filament_source = self.plan_preferences.saved.get('source')
        self._update_plan_dirty_state()
        self._refresh_filament_setup_ui()
        self.statusBar().showMessage("Plan settings saved to the existing FullSpectrum preferences file.")
        self.results_panel.record_event('Plan settings', 'Preferences saved successfully.', 'success')
        self._refresh_results_context()

    def _revert_plan_settings(self):
        # Only optimizer-affecting preferences can invalidate the forecast.
        # The exported template, slicer, executable and auto-open choices cannot.
        planning_keys = (
            'strategy', 'source', 'custom', 'real_slots', 'quality_bias',
            'smart_quality', 'catalog_region', 'planner_mode', 'planning_sample',
            'max_output_colors', 'output_color_strategy',
        )
        before = tuple(self.plan_preferences.get(key) for key in planning_keys)
        source_before = (self.plan_preferences.get('source'),
                         self.plan_preferences.get('custom'))
        self.plan_preferences.revert()
        after = tuple(self.plan_preferences.get(key) for key in planning_keys)
        source_after = (self.plan_preferences.get('source'),
                        self.plan_preferences.get('custom'))
        source_changed = source_before != source_after
        self._saved_filament_source = self.plan_preferences.saved.get('source')
        if source_changed:
            self._filament_setup_confirmed = False
            self._filament_options_ready = False
            self._filament_load_error = ''
        self._restore_plan_widgets()
        if source_changed:
            self._hold_filament_forecast()
            self.filaments_panel.load_options()
        self.statusBar().showMessage("Settings reloaded from disk.")
        self.results_panel.record_event('Settings', 'Unsaved settings reverted.', 'info')
        self._refresh_results_context()
        if before != after:
            self._invalidate_forecast()
        else:
            self._refresh_filament_setup_ui()

    def _refresh_export_availability(self):
        if not hasattr(self, 'compose_button'):
            return
        busy = self._export_task is not None
        ready = bool(self.state.model_path and Path(self.state.model_path).is_file())
        # Do not run conversion with a partial or invalid filament source.
        if ready and hasattr(self, 'filament_setup_banner'):
            ready = self._filament_decision().ready and getattr(
                self.filaments_panel, 'selection_is_valid', True)
        self.compose_button.setEnabled(ready and not busy and self._forecast_task is None
                                       and self._scale_task is None
                                       and not self._size_probe_active)
        self.export_cancel_button.setEnabled(busy and self._export_task.isRunning())
        self.export_cancel_button.setVisible(busy)
        self.export_action_stack.setCurrentIndex(1 if busy else 0)
        self.open_export_button.setEnabled(not busy and bool(self._export_result))
        self.export_folder_button.setEnabled(not busy and bool(self._export_result))

    def _refresh_results_context(self):
        if not hasattr(self, 'results_panel'):
            return
        self.results_panel.set_context(
            self.state.model_path,
            self.plan_preferences.get('native_project_template'),
            self.plan_preferences.get('output_application'),
            self.plan_preferences.is_dirty,
        )
        if getattr(self, '_export_result', None):
            output = Path(self._export_result['output'])
            self.results_panel.set_export_result(self._export_result)

    def _filament_decision(self):
        return evaluate_setup(
            source=self.plan_preferences.get('source'),
            custom_path=self.plan_preferences.get('custom'),
            saved_source=self._saved_filament_source,
            confirmed=self._filament_setup_confirmed,
            loaded=self._filament_options_ready,
            options=self.filaments_panel.options,
            disabled=self.filaments_panel.preferences.disabled,
            selection_valid=getattr(self.filaments_panel, 'selection_is_valid', True),
            selection_error=getattr(self.filaments_panel, 'selection_error', ''),
        )

    def _initialize_filament_setup(self):
        if not self._qt_widgets_alive(getattr(self, "filaments_panel", None)):
            return
        # Returning users should not need to open Filaments manually, but the
        # source must finish loading before any forecast starts.
        if self._saved_filament_source:
            self.filaments_panel.load_options()
        self._refresh_filament_setup_ui()

    def _refresh_filament_setup_ui(self):
        if not self._qt_widgets_alive(getattr(self, "filament_setup_banner", None)):
            return None
        decision = self._filament_decision()
        need_setup = not decision.ready
        self.filament_setup_banner.setVisible(need_setup)
        self.filament_setup_ready_note.setVisible(not need_setup)
        if not need_setup:
            origin = ('saved configuration' if not self._filament_setup_confirmed
                      else 'current session')
            self.filament_setup_ready_note.setText(f'Filaments ready · {origin}')
        message = (self._filament_load_error if decision.state == 'loading' and
                   self._filament_load_error else decision.message)
        self.filament_setup_message.setText(message)
        self.confirm_filaments_button.setEnabled(decision.can_confirm)
        # Also provide a one-click confirmation on the Filaments tab itself.
        self.confirm_filaments_tab_button.setVisible(need_setup)
        self.confirm_filaments_tab_button.setEnabled(decision.can_confirm)
        self.confirm_filaments_tab_button.setToolTip(decision.message)
        if need_setup:
            self._forecast_timer.stop()
            if self._forecast_task is None:
                self.forecast_refresh.setEnabled(False)
            self._set_forecast_status(message, 'normal')
        elif self._forecast_task is None:
            self.forecast_refresh.setEnabled(bool(self.state.model_path))
            if not self.state.model_path:
                self._set_forecast_status('Filaments ready. Open a model to begin forecasting.')
        self._refresh_export_availability()
        self._update_filament_forecast_controls()
        return decision

    def _confirm_filament_setup(self):
        decision = self._filament_decision()
        if not decision.can_confirm:
            self._refresh_filament_setup_ui()
            return
        self._filament_setup_confirmed = True
        self._filament_forecast_held = False  # Explicit initial setup confirmation.
        self._refresh_filament_setup_ui()
        self.results_panel.record_event(
            'Filament setup', 'Current filament selection confirmed for this session.', 'success')
        if self.state.model_path and self._original_mesh is not None:
            self._invalidate_forecast()
        elif not self.state.model_path:
            self._set_forecast_status('Filaments ready. Open a model to begin forecasting.')

    def _hold_filament_forecast(self):
        """Pause automatic recalculation; do not discard the previous result."""
        self._filament_forecast_held = True
        self._forecast_timer.stop()
        self._forecast_pending = False
        self._update_filament_forecast_controls()

    def _stage_filament_forecast(self):
        """One invalidation for a user batch, with no scheduled optimizer run."""
        self._hold_filament_forecast()
        self._invalidate_forecast()

    def _update_filament_forecast_controls(self):
        button = getattr(self, 'update_filament_forecast_button', None)
        hint = getattr(self, 'update_filament_forecast_hint', None)
        if button is None or hint is None:
            return
        pending = bool(getattr(self, '_filament_forecast_held', False))
        button.setVisible(pending)
        hint.setVisible(pending)
        if pending:
            valid = bool(getattr(self.filaments_panel, 'selection_is_valid', True))
            ready = bool(self.state.model_path and self._filament_decision().ready)
            button.setEnabled(ready and valid and self._forecast_task is None
                              and self._export_task is None)
            hint.setText('Filament changes staged — select Update Forecast once when ready.'
                         if ready else 'Filament changes staged — finish loading a valid library first.')

    def _update_filament_forecast(self):
        """Explicitly plan the latest unsaved settings, without saving to disk."""
        self._forecast_timer.stop()
        self._request_forecast()

    def _show_auto_forecast_countdown(self):
        """Display a nonmodal notice for a real queued automatic forecast."""
        if (not self.auto_forecast.isChecked() or
                getattr(self, '_filament_forecast_held', False)):
            self._forecast_timer.stop()
            return
        self.forecast_countdown.begin(self._forecast_timer)
        self._set_forecast_status(
            'Automatic forecast scheduled — Cancel or Run Now in the 3D preview.', 'busy')

    def _hide_auto_forecast_countdown(self):
        self.forecast_countdown.dismiss()

    def _cancel_scheduled_forecast(self):
        """Skip this pending automatic run, not the global automatic setting."""
        if not self._forecast_timer.isActive():
            return
        self._forecast_timer.stop()
        self._set_forecast_status(
            'Automatic forecast skipped — select Refresh Forecast to update.', 'stale')

    def _run_scheduled_forecast_now(self):
        """Use the existing worker immediately; never make a second request."""
        if not self._forecast_timer.isActive():
            return
        self._forecast_timer.stop()
        if not getattr(self, '_filament_forecast_held', False):
            self._request_forecast()

    def _automatic_forecast_due(self):
        """A queued timer event cannot bypass a newly staged filament edit."""
        if not getattr(self, '_filament_forecast_held', False) and self.auto_forecast.isChecked():
            self._request_forecast()

    def _filament_planning_changed(self, valid):
        # Use/Require and source-color assignments are session-local edits.
        if valid and self._filament_options_ready:
            self._filament_setup_confirmed = True
        self._hold_filament_forecast()
        self._invalidate_forecast()
        if not valid:
            self._forecast_timer.stop()
            self._forecast_pending = False
            reason = self.filaments_panel.selection_error or 'Correct the filament selection.'
            self._set_forecast_status('Filament selection unavailable: ' + reason, 'error')
        self._refresh_filament_setup_ui()

    def _filament_activity(self, severity, title, message):
        self.results_panel.record_event(title, message, severity)
        self.statusBar().showMessage(message)
        if title == 'Filament source':
            self._filament_options_ready = (severity == 'success' or
                (severity == 'info' and self.plan_preferences.get('source') == 'exact-cmykw'))
            self._filament_load_error = (message if severity == 'warning' else '')
            decision = self._refresh_filament_setup_ui()
            if (decision.ready and self.auto_forecast.isChecked() and
                    self.state.model_path and self._original_mesh is not None and
                    (self._forecast_view.stale or not self._forecast_view.has_previous) and
                    not self._filament_forecast_held):
                self._forecast_timer.start()
        elif title == 'Filaments' and severity == 'success':
            self._filament_setup_confirmed = True
            self._refresh_filament_setup_ui()
        # Save Filaments only writes preferences; changes were already staged.
        # Legacy protection controls still emit an activity event rather than
        # planning_changed, so keep those edits in the same hold workflow.
        if title == 'Protected colors' and severity in ('success', 'info'):
            self._stage_filament_forecast()
        # Loading the same filament source is not itself a settings edit and
        # must not invalidate the forecast merely because a tab was opened.
        if title == 'Filament source' and severity == 'success' and self._pending_review_filament_key:
            key = self._pending_review_filament_key
            self._pending_review_filament_key = None
            QTimer.singleShot(0, lambda k=key: self._review_planned_filament(k))

    def _open_existing_report(self):
        self.tabs.setCurrentWidget(self.results_panel)
        self.results_panel.browse_report()

    def _empty_tab(self, title, description):
        page = QWidget()
        col = _column(page, margins=(15, 19, 15, 14), spacing=14)
        col.addWidget(_section_heading(title))
        card = self._section()
        inner = _column(card, margins=(16, 22, 16, 22), spacing=10)
        inner.addWidget(_label("Coming in a later stage", "metric"))
        inner.addWidget(_label(description, "bodyMuted", wrap=True))
        col.addWidget(card)
        col.addStretch()
        return page

    @staticmethod
    def _section():
        frame = QFrame()
        frame.setObjectName("section")
        return frame

    def _build_menus(self):
        menu = self.menuBar().addMenu("&File")
        action = QAction("&Open Model…", self)
        action.setShortcut(QKeySequence.StandardKey.Open)
        action.triggered.connect(self._open_model)
        menu.addAction(action)
        reference = QAction("Open &Reference…", self)
        reference.setShortcut(QKeySequence("Ctrl+Shift+R"))
        reference.triggered.connect(self._open_reference)
        menu.addAction(reference)
        report = QAction("Open Existing &Report…", self)
        report.setShortcut(QKeySequence('Ctrl+Shift+O'))
        report.triggered.connect(self._open_existing_report)
        menu.addAction(report)
        # The source remains unchanged; the derived OBJ is used by all pipelines.
        self.intended_dimensions_action = QAction("Set Intended Dimensions…", self)
        self.intended_dimensions_action.setObjectName("setIntendedDimensionsAction")
        self.intended_dimensions_action.setEnabled(False)
        self.intended_dimensions_action.triggered.connect(self._set_intended_dimensions)
        menu.addAction(self.intended_dimensions_action)
        menu.addSeparator()
        close = QAction("E&xit", self)
        close.setShortcut(QKeySequence.StandardKey.Quit)
        close.triggered.connect(self.close)
        menu.addAction(close)
        clear_color=QAction('Clear Source Color Selection', self)
        clear_color.setShortcut(QKeySequence('Escape'))
        clear_color.triggered.connect(self._handle_view_escape)
        self.addAction(clear_color)
        navigate = self.menuBar().addMenu("&Navigate")
        for idx, name in enumerate(("Plan", "Filaments", "Export")):
            nav = QAction(name, self)
            nav.setShortcut(QKeySequence(f"Ctrl+{idx+1}"))
            nav.triggered.connect(lambda checked=False, index=idx: self.tabs.setCurrentIndex(index))
            navigate.addAction(nav)
        view = self.menuBar().addMenu("&View")
        fullscreen = QAction('Toggle Expanded Model Preview', self)
        fullscreen.setShortcut(QKeySequence('F11'))
        fullscreen.triggered.connect(self.expand_preview_toggle.toggle)
        view.addAction(fullscreen)
        self.addAction(fullscreen)  # Active even while the menu bar is hidden.
        metrics = QAction('Preview Performance…', self)
        metrics.setObjectName('previewPerformanceAction')
        metrics.triggered.connect(self._show_preview_performance)
        view.addAction(metrics)
        self.preview_quality_menu = view.addMenu("Preview Quality")
        self.preview_quality_actions = {}
        for mode, label in (("auto", "Automatic (recommended)"),
                            ("full", "Full Detail"),
                            ("balanced", "Balanced"),
                            ("performance", "Performance")):
            action = self.preview_quality_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, chosen=mode: self._set_preview_quality(chosen))
            self.preview_quality_actions[mode] = action
        self.preview_quality_menu.aboutToShow.connect(self._refresh_preview_quality_actions)
        settings = self.menuBar().addMenu("&Settings")
        folder = QAction("Set Default Model Folder…", self)
        folder.triggered.connect(self._choose_default_model_folder)
        settings.addAction(folder)
        reset_folder = QAction("Use Last Opened Model Folder", self)
        reset_folder.triggered.connect(self._reset_default_model_folder)
        settings.addAction(reset_folder)
        settings.addSeparator()
        export_options = QAction("Export Options…", self)
        export_options.triggered.connect(self._open_export_options)
        settings.addAction(export_options)
        settings.addSeparator()
        save = QAction("&Save Settings", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(self._save_plan_settings)
        settings.addAction(save)
        revert = QAction("Revert Unsaved Changes", self)
        revert.triggered.connect(self._revert_plan_settings)
        settings.addAction(revert)

    def _open_export_options(self):
        """Navigate to the existing options; never duplicate settings state."""
        self.tabs.setCurrentWidget(self.results_panel)
        self.export_advanced_toggle.setChecked(True)
        if hasattr(self.results_panel, 'content_scroll'):
            self.results_panel.content_scroll.ensureWidgetVisible(
                self.export_advanced_toggle)

    def _show_preview_performance(self):
        """On-demand display diagnostics; never changes forecast or export."""
        snapshot=self.preview_surface.preview_performance_snapshot()
        QMessageBox.information(self, "Preview Performance",
                                format_preview_performance(snapshot))

    def _refresh_preview_quality_actions(self):
        for mode, action in self.preview_quality_actions.items():
            action.setChecked(mode == self._preview_quality)

    def _set_preview_quality_busy(self, message=''):
        self.preview_quality_activity_label.setText(message)
        self.preview_quality_activity.setVisible(bool(message))

    def _set_preview_quality(self, mode):
        if mode not in QUALITY_MODES or mode == self._preview_quality:
            return
        self._preview_quality = mode
        write_quality(self._preview_quality_path, mode)
        self._refresh_preview_quality_actions()
        self._reload_preview_quality()

    def _reload_preview_quality(self):
        if self._original_mesh is None or not self.state.model_path:
            return  # Next normal load uses this preference.
        self._preview_quality_generation += 1
        self._preview_quality_pending = True
        label = {'auto': 'Automatic', 'full': 'Full Detail',
                 'balanced': 'Balanced', 'performance': 'Performance'}[
                     self._preview_quality]
        self._set_preview_quality_busy(f'Preparing {label} preview…')
        # Rapid mode selections must not spawn simultaneous expensive workers.
        if self._preview_quality_task is not None:
            self._preview_quality_task.requestInterruption()
        self._start_preview_quality_if_idle()

    def _start_preview_quality_if_idle(self):
        if self._preview_quality_task is not None or not self._preview_quality_pending:
            return
        self._preview_quality_pending = False
        generation = self._preview_quality_generation
        serial = self._preview_serial
        path = self.state.model_path
        mode = self._preview_quality
        cached = self._preview_quality_cache.get(mode)
        if cached is not None:
            self._preview_quality_loaded(serial, generation, path, cached, None)
            self._set_preview_quality_busy('')
            return
        task = ModelLoadWorker(
            self._active_geometry_path(), self, quality=mode,
            source_mesh=self._preview_quality_source_mesh)
        task._preview_source_serial = serial
        self._preview_quality_task = task
        self._preview_threads.append(task)
        task.completed.connect(
            lambda mesh, error, filename, g=generation, s=serial, m=mode:
                self._preview_quality_loaded(s, g, filename, mesh, error, m))
        task.finished.connect(lambda t=task: self._preview_quality_finished(t))
        self.statusBar().showMessage('Preparing display-only preview quality…')
        task.start()

    def _preview_quality_finished(self, task):
        if self._preview_quality_task is task:
            self._preview_quality_task = None
        self._release_preview_task(task)
        if self._preview_quality_pending and self._original_mesh is not None:
            QTimer.singleShot(0, self._start_preview_quality_if_idle)
        elif task._preview_source_serial == self._preview_serial:
            self._set_preview_quality_busy('')

    def _preview_quality_loaded(self, serial, generation, path, mesh, error, mode=None):
        if (serial != self._preview_serial or
                generation != self._preview_quality_generation or
                path != self.state.model_path):
            return  # Never install an obsolete display mesh.
        if error:
            self.statusBar().showMessage('Preview quality update failed: ' + error)
            return  # Previous working viewport remains intact.
        mode = mode or self._preview_quality
        self._preview_quality_cache[mode] = mesh
        while len(self._preview_quality_cache) > 2:
            self._preview_quality_cache.pop(next(iter(self._preview_quality_cache)))
        self._original_mesh = mesh
        if self.preview_mode.currentText() in ('Original', 'Wireframe'):
            self.preview_surface.set_mesh(mesh, preserve_camera=True)
            self._update_preview_highlights()
            self.preview_status.setText(
                f'{len(mesh.triangles):,} display / {mesh.source_triangles:,} source triangles'
                ' · display-only quality; original file unchanged')
        profile = getattr(mesh, 'load_profile', None)
        details = profile.quality_reason if profile else 'Full detail'
        self.statusBar().showMessage('Preview quality updated: ' + details)

    def _fit_perspective_grid(self):
        if not self.preview_surface.fit_perspective_grid():
            self.statusBar().showMessage('Show the perspective grid and open a model to fit it.')
        else:
            self.statusBar().showMessage('Camera fitted to complete perspective grid.')

    def _refresh_preview_grid_actions(self):
        if hasattr(self, 'preview_fit_grid_action'):
            mode = self._grid_settings['mode']
            has_scene = hasattr(self, 'preview_surface') and self.preview_surface.mesh is not None
            plate_on = (hasattr(self, 'preview_surface') and
                        self.preview_surface._plate_renderer.mesh is not None)
            self.preview_fit_grid_action.setEnabled(
                has_scene and (mode == 'perspective' or
                               (mode == 'automatic' and not plate_on)))
        for mode, action in self.preview_grid_actions.items():
            with QSignalBlocker(action):
                action.setChecked(mode == self._grid_settings['mode'])
        with QSignalBlocker(self.preview_axes_action):
            self.preview_axes_action.setChecked(self._grid_settings['axes'])
        with QSignalBlocker(self.preview_measurements_action):
            self.preview_measurements_action.setChecked(self._grid_settings['measurements'])
        self.preview_measurements_action.setEnabled(
            self._grid_settings['mode'] in ('automatic', 'perspective'))
        if hasattr(self, 'preview_grid_button'):
            with QSignalBlocker(self.preview_grid_button):
                self.preview_grid_button.setChecked(self._grid_settings['mode'] != 'off')
            self.preview_grid_button.setToolTip(
                'Grid: ' + self._grid_settings['mode'].title() +
                ' · Click to toggle; arrow opens Grid and Axes settings')

    def _commit_preview_grid_settings(self):
        self._refresh_preview_grid_actions()
        self.preview_surface.set_grid_preferences(
            self._grid_settings['mode'], self._grid_settings['axes'],
            self._grid_settings['measurements'])
        try:
            write_grid_settings(self._grid_settings_path, self._grid_settings)
        except OSError as exc:
            self.statusBar().showMessage('Unable to save preview grid settings: ' + str(exc))

    def _set_preview_grid_mode(self, mode):
        self._grid_settings = change_grid_mode(self._grid_settings, mode)
        self._commit_preview_grid_settings()

    def _toggle_preview_grid(self, enabled):
        self._grid_settings = toggle_grid_setting(self._grid_settings, enabled)
        self._commit_preview_grid_settings()

    def _set_preview_axes_visible(self, enabled):
        self._grid_settings['axes'] = bool(enabled)
        self._commit_preview_grid_settings()

    def _set_preview_measurements_visible(self, enabled):
        # Only the perspective grid has configurable measurement overlays.
        self._grid_settings['measurements'] = bool(enabled)
        self._commit_preview_grid_settings()

    def _save_plate_workspace(self):
        """Persist preview-only state, separate from export/filament settings."""
        state = dict(self._plate_workspace)
        if self._plate_default is None:
            state.pop('default', None)
        else:
            state['default'] = dict(self._plate_default)
        state['visible'] = self._plate_visible
        state['slicer_executables'] = [str(p) for p in self._plate_custom_exes]
        state['resource_roots'] = [str(p) for p in self._plate_custom_roots]
        try:
            write_workspace(self._plate_settings_path, state)
            self._plate_workspace = state
        except OSError as exc:
            self.statusBar().showMessage('Unable to save preview plate settings: ' + str(exc))

    def _update_plate_actions(self):
        if not hasattr(self, 'plate_visibility_button'):
            return
        selected = self._plate_selected
        showing = bool(selected is not None and self._plate_visible)
        self.plate_visibility_button.setEnabled(selected is not None)
        self.plate_visibility_button.setChecked(showing)
        self.plate_visibility_button.setIcon(plate_eye_icon(showing))
        label = 'Hide build plate' if showing else 'Show build plate'
        self.plate_visibility_button.setAccessibleName(label)
        self.plate_visibility_button.setToolTip(
            f'{label}: {selected.label}' if selected is not None
            else 'Choose a build plate to enable visibility')
        self.plate_button.setToolTip('Choose a build plate from installed slicers')

    def _set_plate_visible(self, visible):
        """A cheap hide/show that retains the selected printer and loaded STL."""
        if self._plate_selected is None:
            return
        self._plate_visible = bool(visible)
        if self._plate_visible and self._plate_loaded_mesh is not None:
            self.preview_surface.set_plate(self._plate_loaded_mesh,
                                           self._plate_selected.texture)
        else:
            self.preview_surface.set_plate(None)
        self._update_plate_actions()
        self._save_plate_workspace()
        self.statusBar().showMessage(
            ('Showing ' if self._plate_visible else 'Hiding ') +
            self._plate_selected.label + ' · model unchanged')

    def _toggle_plate_visibility(self):
        if self._plate_selected is None:
            self._choose_plate()
            return
        self._set_plate_visible(not self._plate_visible)

    def _make_selected_plate_default(self):
        asset = self._plate_selected
        if asset is None:
            return
        self._plate_default = dict(printer=asset.printer, vendor=asset.vendor,
                                   source=asset.source)
        self._plate_default_pending = False
        self._save_plate_workspace()
        self.statusBar().showMessage('Default 3D build plate saved: ' + asset.label)

    def _clear_plate_default(self):
        """Forget the saved preference, not the active preview plate.

        An explicitly selected plate (or an in-progress load) belongs to
        this session and must not be removed by editing the default.
        Cancel any pending *automatic* default restoration instead.
        """
        self._plate_default = None
        self._plate_default_pending = False
        self._save_plate_workspace()
        self.statusBar().showMessage('Saved default build plate cleared; displayed plate unchanged.')

    def _refresh_plate_catalog(self):
        """Discover installed slicer plate profiles without blocking the viewport."""
        # Startup singleShot can arrive after offscreen tests close the window.
        if not self._qt_widgets_alive(self.plate_button):
            return
        if self._plate_catalog_task is not None:
            self._plate_rescan_pending = True
            return
        self.plate_button.setToolTip('Scanning local slicer build plates…')
        worker = PlateCatalogWorker(resource_roots=tuple(self._plate_custom_roots),
                                    slicer_executables=tuple(self._plate_custom_exes),
                                    parent=self)
        self._plate_catalog_task = worker
        worker.completed.connect(self._plate_catalog_ready)
        worker.finished.connect(lambda t=worker: self._release_plate_catalog(t))
        worker.start()

    def _plate_catalog_ready(self, catalog, error):
        if not self._qt_widgets_alive(self.plate_button):
            return
        if error is not None:
            self._plate_catalog = None
            self._plate_pending_picker = False
            self.plate_button.setToolTip('Build plate discovery unavailable: ' + str(error))
            self.statusBar().showMessage('Build plate discovery error: ' + str(error))
            return
        self._plate_catalog = catalog
        if self._plate_manually_requested_source and not self._plate_rescan_pending:
            source = self._plate_manually_requested_source
            self._plate_manually_requested_source = None
            if not any(p.source == source for p in catalog.plates):
                QMessageBox.warning(self, 'No ' + source + ' Build Plates',
                    source + ' was located, but no usable STL printer profiles were discovered. '
                    'Use Build Plate → Choose Profile Folder and select its resources/profiles directory, '
                    'then refresh the catalog. No files were modified.')
        count = len(catalog.plates)
        from collections import Counter
        by_source = Counter(asset.source for asset in catalog.plates)
        source_text = ', '.join(f'{source}: {n}' for source, n in sorted(by_source.items()))
        self.plate_button.setToolTip(f'Build Plate · {count} profiles · {source_text or "No slicer assets found"}')
        # When rescanning, do not show the stale catalog first.
        if self._plate_default_pending and not self._plate_rescan_pending:
            self._plate_default_pending = False
            preferred = find_default_plate(catalog, self._plate_default)
            if preferred is not None:
                self._select_plate_asset(preferred, preserve_visibility=True)
            elif self._plate_default:
                self.statusBar().showMessage('Saved default plate not found in installed slicers.')
        if self._plate_pending_picker and not self._plate_rescan_pending:
            self._plate_pending_picker = False
            QTimer.singleShot(0, self._choose_plate)

    def _release_plate_catalog(self, worker):
        if getattr(self, '_qt_disposing', False):
            return  # parent QObject owns worker teardown
        if not self._qt_widgets_alive(self.plate_button):
            return
        if self._plate_catalog_task is worker:
            self._plate_catalog_task = None
        worker.deleteLater()
        if self._plate_rescan_pending:
            self._plate_rescan_pending = False
            QTimer.singleShot(0, self._refresh_plate_catalog)

    def _choose_plate(self):
        catalog = self._plate_catalog
        if catalog is None:
            self._plate_pending_picker = True
            # Startup warming may already be scanning in a QThread. Joining
            # that scan avoids marking an unnecessary second full rescan.
            if self._plate_catalog_task is None:
                self._refresh_plate_catalog()
            return
        if not catalog.plates:
            QMessageBox.information(self, 'No Installed Build Plates',
                'No slicer bed models were discovered. Install OrcaSlicer or Bambu Studio, '
                'or select an existing resources/profiles folder from the build-plate menu.')
            return
        dialog = PlatePickerDialog(catalog.plates, self, saved_default=self._plate_default)
        # Picker changes are staged: Cancel leaves both the saved default
        # and the current preview untouched.
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.clear_saved_default:
            self._clear_plate_default()
        # A clear-only action is valid; choosing a plate is optional.
        if dialog.selected_asset is not None:
            self._select_plate_asset(dialog.selected_asset)
            if dialog.remember_default.isChecked():
                self._make_selected_plate_default()

    def _choose_plate_slicer_executable(self):
        """Locate a slicer whose installed resources were missed by autodetection.

        Only read the executable path to locate its neighboring resource folder;
        this method never executes or modifies the slicer program.
        """
        from desktop.slicer_launcher import SLICER_EXECUTABLES
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Locate OrcaSlicer or Bambu Studio', '', 'Windows executables (*.exe)')
        if not filename:
            return
        path = Path(filename)
        recognized = {name.casefold() for names in SLICER_EXECUTABLES.values()
                      for name in names}
        if not path.is_file() or path.name.casefold() not in recognized:
            QMessageBox.warning(self, 'Unsupported Slicer Executable',
                'Choose the existing OrcaSlicer or Bambu Studio .exe file. '
                'For a different slicer, use Choose Profile Folder instead.')
            return
        if _profile_root(path) is None:
            QMessageBox.warning(self, 'Slicer Resources Not Found',
                'The selected executable exists, but no resources/profiles folder '
                'was found near it. The executable alone does not contain plate STLs. '
                'Choose Profile Folder and point to OrcaSlicer\\resources\\profiles, '
                'or run python -m desktop.qt_app.plate_catalog --slicer-exe with this path.')
            return
        if path not in self._plate_custom_exes:
            self._plate_custom_exes.append(path)
        self._plate_manually_requested_source = next(
            (source for source, names in SLICER_EXECUTABLES.items()
             if path.name.casefold() in {n.casefold() for n in names}), None)
        self._save_plate_workspace()
        self._plate_pending_picker = True
        self._refresh_plate_catalog()

    def _choose_plate_profile_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, 'Choose Slicer resources/profiles Folder', '')
        if not directory:
            return
        path = Path(directory)
        if path not in self._plate_custom_roots:
            self._plate_custom_roots.append(path)
        self._save_plate_workspace()
        self._refresh_plate_catalog()

    def _clear_plate(self):
        # Legacy menu entry now hides without losing the selected printer.
        self._set_plate_visible(False)

    def _select_plate_asset(self, asset, *, preserve_visibility=False):
        self._plate_visible = self._plate_visible if preserve_visibility else True
        self._plate_loaded_mesh = None
        self._plate_load_serial += 1
        serial = self._plate_load_serial
        self._plate_selected = asset
        self._update_plate_actions()
        self.plate_button.setToolTip('Loading 3D build plate: ' + asset.label)
        worker = PlateLoadWorker(asset.model, parent=self)
        self._plate_load_threads.append(worker)
        worker.completed.connect(
            lambda mesh, error, s=serial, a=asset: self._plate_loaded(s, a, mesh, error))
        worker.finished.connect(lambda t=worker: self._release_plate_load(t))
        worker.start()

    def _plate_loaded(self, serial, asset, mesh, error):
        if serial != self._plate_load_serial or self._plate_selected != asset:
            return
        if error or mesh is None:
            self.preview_surface.set_plate(None)
            self.plate_button.setToolTip('Build plate unavailable: ' + str(error))
            self.statusBar().showMessage('Unable to read installed build plate: ' + str(error))
            return
        self._plate_loaded_mesh = mesh
        if self._plate_visible:
            self.preview_surface.set_plate(mesh, asset.texture)
            # Choosing a plate is an explicit request to frame the scene.
            # Subsequent show/hide never changes the camera.
            if self.preview_surface.mesh is not None:
                self.preview_surface.reset_camera()
        else:
            self.preview_surface.set_plate(None)
        self._update_plate_actions()
        self.statusBar().showMessage(
            f'Loaded {asset.label} · {mesh.faces:,} plate faces · Reset Camera to frame both objects')

    def _release_plate_load(self, worker):
        if worker in self._plate_load_threads:
            self._plate_load_threads.remove(worker)
        worker.deleteLater()

    def _grid_render_failed(self, message):
        self.statusBar().showMessage('Perspective grid unavailable: ' + message)

    def _plate_render_failed(self, message):
        self.plate_button.setToolTip('Build plate renderer unavailable: ' + message)
        self.statusBar().showMessage('3D build plate unavailable: ' + message)

    def _tab_changed(self, index):
        if index == 1:
            self.filaments_panel.on_selected()
        elif index == 2:
            self._refresh_results_context()

    def _qt_widgets_alive_for_shutdown(self, widget):
        import shiboken6
        return shiboken6.isValid(self) and shiboken6.isValid(widget)

    def closeEvent(self, event):
        self._qt_disposing = True
        self._initial_filament_ui_timer.stop()
        self._initial_export_layout_timer.stop()
        if hasattr(self, "results_panel") and self._qt_widgets_alive_for_shutdown(self.results_panel):
            self.results_panel.stop_deferred_ui()
        # Let any 3MF/inventory reads finish so Qt never destroys a live QThread.
        self._forecast_timer.stop()
        self._forecast_heartbeat.stop()
        if self._export_task is not None:
            self._export_task.requestInterruption()
        if self._forecast_task is not None:
            self._forecast_task.requestInterruption()
        if self._scale_task is not None:
            self._scale_task.requestInterruption()
        for worker in list(self._size_probe_threads):
            worker.requestInterruption()
        plate_workers = list(self._plate_load_threads)
        if self._plate_catalog_task is not None:
            plate_workers.append(self._plate_catalog_task)
        for worker in list(self.filaments_panel._workers) + list(self._preview_threads) + list(self._inspection_threads) + list(self._size_probe_threads) + plate_workers + ([self._forecast_task] if self._forecast_task is not None else []) + ([self._export_task] if self._export_task is not None else []) + ([self._scale_task] if self._scale_task is not None else []):
            if worker.isRunning():
                worker.wait()
        for workspace in self._scale_workspaces:
            workspace.cleanup()
        self._scale_workspaces.clear()
        super().closeEvent(event)

    def _active_geometry_path(self):
        """One immutable model source for preview, planning, and export."""
        return self._scaled_model_path or self.state.model_path

    def _remember_auto_dimension_choice(self, action, factor=None):
        try:
            save_dimension_choice(self._dimension_choices_path,
                                  self.state.model_path, action, factor)
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage('Unable to save model dimension preference: ' + str(exc))

    def _forget_auto_dimension_choice(self):
        try:
            forget_dimension_choice(self._dimension_choices_path, self.state.model_path)
        except OSError as exc:
            self.statusBar().showMessage('Unable to update dimension preference: ' + str(exc))

    def _start_model_size_preflight(self, path):
        """Only scan bounds first; no expanded mesh/GL preparations yet."""
        self._size_probe_serial += 1
        serial = self._size_probe_serial
        self._size_probe_active = True
        self._preview_serial += 1  # A late earlier-model mesh may not replace this one.
        self._original_mesh = None
        self.preview_surface.clear_mesh()
        self.preview_scale_notice.hide()
        self.preview_adjust_dimensions.hide()
        self.preview_status.setText('')
        self.source_palette_content.setVisible(False)
        self._set_preview_quality_busy('Checking model dimensions…')
        task = ModelSizePreflightWorker(path, self)
        self._size_probe_threads.append(task)
        task.completed.connect(
            lambda bounds, error, s=serial, p=str(path):
                self._model_size_preflight_done(s, p, bounds, error))
        task.finished.connect(lambda t=task: self._release_size_preflight(t))
        task.start()

    def _release_size_preflight(self, worker):
        if worker in self._size_probe_threads:
            self._size_probe_threads.remove(worker)
        worker.deleteLater()

    def _model_size_preflight_done(self, serial, path, bounds, error):
        if (serial != self._size_probe_serial or path != self.state.model_path or
                self._qt_disposing):
            return
        self._size_probe_active = False
        self._set_preview_quality_busy('')
        self._unscaled_bounds = bounds
        if error:
            # The existing model loader is responsible for reporting invalid
            # source geometry in detail. Do not silently reject or repair it.
            self.results_panel.record_event('Dimensions check', error, 'warning')
        elif suspicious_obj_bounds(bounds):
            choice = read_dimension_choice(self._dimension_choices_path, path)
            if choice is not None:
                if choice['action'] == 'apply':
                    self._begin_obj_scaling(choice['factor'], automatic=True)
                    return
            else:
                dialog = AutoIntendedDimensionsDialog(bounds, self)
                accepted = dialog.exec() == QDialog.DialogCode.Accepted
                if self._qt_disposing or self.state.model_path != path:
                    return
                if accepted:
                    self._begin_obj_scaling(dialog.scale_factor,
                                            remember=dialog.remember_choice,
                                            automatic=True)
                    return
                if dialog.remember_choice:
                    self._remember_auto_dimension_choice('skip')
        # Skipped, unchanged, unsupported, or formerly remembered Skip.
        self._load_preview(path)
        self._refresh_export_availability()

    def _set_intended_dimensions(self, _checked=False):
        """Ask for exact physical size; rescale source OBJ off the GUI thread."""
        if (self._scale_task is not None or self._export_task is not None or
                self._forecast_task is not None or self._unscaled_bounds is None or
                Path(self.state.model_path).suffix.lower() != '.obj'):
            return
        dialog = IntendedDimensionsDialog(self._unscaled_bounds, self._intended_scale, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Manual changes supersede any previously remembered auto import rule.
        self._forget_auto_dimension_choice()
        if dialog.reset_requested or abs(dialog.scale_factor - 1.0) <= 1e-10:
            self._scaled_model_path = None
            self._intended_scale = 1.0
            self._load_preview(self.state.model_path)
            self._invalidate_forecast(clear_inspection=True)
            self.statusBar().showMessage('Restored original OBJ coordinates; forecast requires refresh.')
            return
        self._begin_obj_scaling(dialog.scale_factor)

    def _begin_obj_scaling(self, factor, *, remember=False, automatic=False):
        """One derived geometry source shared by preview, forecast and export."""
        self._scale_remember = bool(remember)
        self._auto_scale_loading = bool(automatic)
        if abs(factor - 1.0) <= 1e-10:
            self._scaled_model_path = None
            self._intended_scale = 1.0
            if remember:
                self._remember_auto_dimension_choice('apply', factor)
            self._auto_scale_loading = False
            self._load_preview(self.state.model_path)
            self._invalidate_forecast(clear_inspection=True)
            return
        workspace = TemporaryDirectory(prefix='fullspectrum_scaled_obj_')
        self._scale_workspaces.append(workspace)
        target = Path(workspace.name) / Path(self.state.model_path).name
        worker = ModelScaleWorker(self.state.model_path, target, factor, self)
        self._scale_task = worker
        self._scale_source = self.state.model_path
        self._scale_target_factor = factor
        self.intended_dimensions_action.setEnabled(False)
        self._forecast_timer.stop()
        self._set_preview_quality_busy('Applying intended dimensions…')
        self._refresh_export_availability()
        worker.completed.connect(
            lambda output, error, t=worker: self._scaled_obj_ready(t, output, error))
        worker.finished.connect(lambda t=worker: self._release_scale_task(t))
        worker.start()

    def _scaled_obj_ready(self, worker, output, error):
        if worker is not self._scale_task or self.state.model_path != self._scale_source:
            return
        self._set_preview_quality_busy('')
        if error or not output or not Path(output).is_file():
            automatic = self._auto_scale_loading
            self._auto_scale_loading = False
            self._scale_remember = False
            QMessageBox.warning(self, 'Unable to Set Intended Dimensions',
                                str(error or 'Scaled OBJ was not produced'))
            self.statusBar().showMessage('Original model and dimensions retained.')
            if automatic:
                # A failed optional calibration must not strand the import.
                self._load_preview(self.state.model_path)
            return
        self._scaled_model_path = str(output)
        self._intended_scale = self._scale_target_factor
        if self._scale_remember:
            self._remember_auto_dimension_choice('apply', self._intended_scale)
        self._scale_remember = False
        self._auto_scale_loading = False
        # Changing geometry always invalidates forecasts, but never changes
        # the source path used to track unsaved filament assignments.
        self._load_preview(self.state.model_path)
        self._invalidate_forecast(clear_inspection=True)
        self.statusBar().showMessage('Intended OBJ dimensions applied to preview, forecast and export.')

    def _release_scale_task(self, worker):
        if self._scale_task is worker:
            self._scale_task = None
            self._scale_source = None
            self._scale_target_factor = None
        worker.deleteLater()
        self.intended_dimensions_action.setEnabled(
            self._unscaled_bounds is not None and
            Path(self.state.model_path).suffix.lower() == '.obj')
        # Scaling tasks sometimes complete after a preview callback. Keep the
        # in-preview adjustment action synchronized with the File action.
        self.preview_adjust_dimensions.setEnabled(
            self.intended_dimensions_action.isEnabled())
        self._refresh_export_availability()

    def _persist_model_location(self):
        try:
            write_model_location(self._model_location_path, self._model_location)
        except OSError as exc:
            if self._qt_widgets_alive(self):
                self.statusBar().showMessage('Unable to save model folder preference: ' + str(exc))

    def _choose_default_model_folder(self, _checked=False):
        starting = initial_model_directory(self._model_location)
        directory = QFileDialog.getExistingDirectory(
            self, 'Choose Default Model Folder', starting)
        if directory:
            try:
                self._model_location = with_default_folder(self._model_location, directory)
            except (OSError, ValueError):
                return
            self._persist_model_location()
            self.statusBar().showMessage('Default model folder: ' + directory)

    def _reset_default_model_folder(self, _checked=False):
        self._model_location['default_directory'] = ''
        self._persist_model_location()
        self.statusBar().showMessage('Model picker will use the last opened folder.')

    def _open_model(self, path=None):
        if self._scale_task is not None:
            QMessageBox.information(self, "Model dimensions", "Finish preparing intended dimensions before opening another model.")
            return
        if self._export_task is not None:
            QMessageBox.information(self, 'Export in progress', 'Wait for export to finish before changing models.')
            return
        # QAction/QPushButton passes a bool, while the viewport emits a file path.
        if not isinstance(path, (str, os.PathLike)):
            path, _ = QFileDialog.getOpenFileName(
                self, "Open 3D Model", initial_model_directory(self._model_location),
                MODEL_FILE_FILTER)
        if not self.state.select_model(path):
            return
        for running_probe in self._size_probe_threads:
            running_probe.requestInterruption()
        self._size_probe_serial += 1
        self._size_probe_active = False
        self._scaled_model_path = None
        self._intended_scale = 1.0
        self._unscaled_bounds = None
        self.intended_dimensions_action.setEnabled(False)
        # Handles both Open Model and drag-and-drop, but not cancelled picks.
        self._model_location = with_last_opened_model(self._model_location, path)
        self._persist_model_location()
        name = display_filename(path)
        self.project_subtitle.setText(name)
        # The previous source may have had the opposite template requirement.
        self._refresh_template_status()
        self._update_export_template_attention()
        self._pending_review_filament_key = None
        self._filament_forecast_held = False  # A new model starts a new session.
        self.filaments_panel.set_model(path)
        self._update_filament_forecast_controls()
        self.bottom_hint.setText(f"Selected: {name} — loading preview geometry (original files are unchanged).")
        self.statusBar().showMessage("Loading 3D model geometry…")
        self.results_panel.record_event('Model selected', f'{name} selected; loading preview geometry.', 'busy')
        self._refresh_export_directory()
        self._refresh_results_context()
        if Path(path).suffix.lower() == '.obj':
            self._start_model_size_preflight(path)
        else:
            self._load_preview(path)
        self._invalidate_forecast(clear_inspection=True)
        self._refresh_export_availability()

    def _open_reference(self):
        if self._export_task is not None:
            QMessageBox.information(self, 'Export in progress', 'Wait for export to finish before changing references.')
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Visual Reference", "", REFERENCE_FILE_FILTER)
        if not self.state.select_reference(path):
            return
        self.statusBar().showMessage(
            "Reference selected: " + display_filename(path) + " — not processed yet."
        )
        self.results_panel.record_event('Reference selected',
                                        display_filename(path) + ' selected for forecasting.', 'info')
        self._invalidate_forecast()

    def _load_preview(self, path):
        # The original user-visible path remains the model identity.
        # Only the worker opens the temporary, uniformly scaled copy.
        geometry_path = self._active_geometry_path()
        self._preview_quality_generation += 1
        self._preview_quality_pending = False
        if self._preview_quality_task is not None:
            self._preview_quality_task.requestInterruption()
        self._preview_quality_source_mesh = None
        self._preview_quality_cache.clear()
        self._preview_serial += 1
        self._predicted_serial += 1  # obsolete predicted loads must not replace a different model
        self._original_mesh = None
        self._predicted_mesh = None
        self._predicted_filename = ''
        self.preview_import_action.setEnabled(False)
        self._update_preview_options()
        self.source_palette_content.setVisible(False)
        self.source_palette_scroll.verticalScrollBar().setValue(0)
        self._source_palette_selected=None
        self._preview_protected_colors=set()
        self.assignment_panel.setVisible(False)
        self._source_palette_anchor = None
        self.clear_palette_button.setEnabled(False)
        self.manage_protection_button.setEnabled(False)
        self.tint_protected.setChecked(False)
        self.tint_protected.setEnabled(False)
        self.preview_surface.set_highlights(None, ())
        self.source_palette_message.setText('Reading source color assignments…')
        serial = self._preview_serial
        self.preview_surface.clear_mesh()
        if hasattr(self, 'preview_chrome'):
            self.preview_chrome.set_model()
            self.preview_chrome.set_estimate(None)
        self.preview_mode.setEnabled(False)
        self.reset_camera_button.setEnabled(False)
        # Progress widget owns the in-flight message; don't duplicate it.
        # Restore this label when the load completes (success or error).
        self.preview_status.setText('')
        self.preview_scale_notice.hide()
        self.preview_adjust_dimensions.hide()
        self._set_preview_quality_busy('Loading model geometry…')
        task = ModelLoadWorker(geometry_path, self, quality=self._preview_quality)
        self._preview_threads.append(task)
        task.completed.connect(
            lambda mesh, error, filename, s=serial, t=task, original=path:
                self._preview_loaded(s, original, mesh, error, t.source_mesh))
        task.finished.connect(lambda t=task: self._release_preview_task(t))
        task.start()

    def _release_preview_task(self, task):
        if task in self._preview_threads:
            self._preview_threads.remove(task)
        task.deleteLater()

    def _preview_loaded(self, serial, path, mesh, error, source_mesh=None):
        if serial != self._preview_serial or path != self.state.model_path:
            return  # Ignore obsolete loads when a user selects a different file.
        self._set_preview_quality_busy('')
        if error:
            self.preview_status.setText("Preview unavailable: " + error)
            self.bottom_hint.setText("Source selection retained; preview could not be loaded.")
            self.statusBar().showMessage("Model preview unavailable.")
            self.results_panel.record_event('Model preview', error, 'warning')
            return
        if self._scaled_model_path is None:
            self._unscaled_bounds = mesh.bounds
        self.intended_dimensions_action.setEnabled(
            Path(path).suffix.lower() == ".obj" and self._scale_task is None)
        self._preview_quality_source_mesh = source_mesh or mesh
        profile = getattr(mesh, 'load_profile', None)
        mode = profile.quality_mode if profile else self._preview_quality
        self._preview_quality_cache[mode] = mesh
        self._original_mesh = mesh
        self.preview_surface.set_mesh(mesh)
        if (getattr(mesh, "load_profile", None) is not None and
                mesh.load_profile.quality_mode != self._preview_quality):
            self._reload_preview_quality()
        if hasattr(self, 'preview_chrome'):
            self.preview_chrome.set_model(display_filename(path), len(mesh.triangles),
                                          mesh.source_triangles, sampled=mesh.sampled)
        self._update_preview_highlights()
        self.reset_camera_button.setEnabled(True)
        self.preview_mode.setEnabled(True)
        # Stage 4C enables only the analysis modes actually generated by the engine.
        self._refresh_preview_modes()
        self.preview_mode.setCurrentText('Original')
        self.preview_surface.set_wireframe(False)
        self.preview_import_action.setEnabled(True)
        self._update_preview_options()
        self._populate_source_palette(mesh)
        # Populate Protect Solid Colors without making the user scan again.
        # This uses the authoritative engine/native color scanner, not just
        # render-time color averages or approximate visual gradients.
        self.filaments_panel.auto_load_source_colors()
        quality_profile = getattr(mesh, 'load_profile', None)
        is_lod = bool(mesh.sampled and quality_profile and
                      quality_profile.quality_effective != 'full')
        suffix = (' · display-only LOD' if is_lod else
                  ' · sampled display only' if mesh.sampled else '')
        info = f"{len(mesh.triangles):,} visible triangles / {mesh.source_triangles:,} source triangles{suffix}"
        self.preview_status.setText(info + ' · Left drag orbit · Right drag pan · Wheel zoom · R reset')
        size_notice = scale_warning(mesh.bounds, path)
        if self._scaled_model_path is not None and self._unscaled_bounds is not None:
            sizes = scaled_dimensions(self._unscaled_bounds, self._intended_scale)
            size_notice = ("Intended dimensions: " + " × ".join(f"{v:.4g}" for v in sizes)
                           + f" mm (uniform scale ×{self._intended_scale:.5g}). "
                           "Temporary source for preview, forecast and export; original OBJ unchanged.")
        self.preview_scale_notice.setStyleSheet('color: #77d3b3;' if self._scaled_model_path is not None
                                               else 'color: #edbf73;')
        self.preview_scale_notice.setText(size_notice)
        if self._scaled_model_path is not None:
            self.results_panel.record_event('Model dimensions', size_notice, 'info')
        self.preview_scale_notice.setVisible(bool(size_notice))
        if size_notice:
            self.results_panel.record_event('Model scale', size_notice, 'warning')
        # Dimension UI polish: show an editable physical-size summary.
        if Path(path).suffix.lower() == '.obj' and self._unscaled_bounds is not None:
            if self._scaled_model_path is not None:
                physical_sizes = scaled_dimensions(self._unscaled_bounds, self._intended_scale)
                self.preview_scale_notice.setText(
                    'Intended size: ' + ' × '.join(f'{v:.4g}' for v in physical_sizes)
                    + f' mm · Uniform scale ×{self._intended_scale:.5g}. Original OBJ unchanged.')
                self.preview_scale_notice.setStyleSheet('color: #83dfd4;')
            else:
                original_sizes = source_dimensions(self._unscaled_bounds)
                questionable_scale = bool(scale_warning(self._unscaled_bounds, path))
                self.preview_scale_notice.setText(
                    ('Scale not verified: ' if questionable_scale else 'OBJ coordinate size: ')
                    + ' × '.join(f'{v:.5g}' for v in original_sizes)
                    + ' source units · Physical size in mm not specified.')
                self.preview_scale_notice.setStyleSheet(
                    'color: #eac17b;' if questionable_scale else 'color: #a7becb;')
            self.preview_scale_notice.show()
            self.preview_adjust_dimensions.setEnabled(self._scale_task is None)
            self.preview_adjust_dimensions.show()
        else:
            self.preview_adjust_dimensions.hide()
        self.bottom_hint.setText('Source geometry loaded. Refresh Forecast for read-only analysis or open Export to generate a native 3MF.')
        self.statusBar().showMessage('3D preview ready: ' + info)
        self.results_panel.record_event('Model preview', info, 'success')
        self.source_inspection.setText(f'Source geometry: {mesh.source_triangles:,} triangles; inspecting project metadata…')
        self._start_inspection(path)
        if (self.auto_forecast.isChecked() and self._filament_decision().ready
                and not getattr(self, '_filament_forecast_held', False)):
            self._forecast_timer.start()
        self._refresh_filament_setup_ui()

    # Stage 4A: no 3MF export; all engine operations run on QThreads.
    def _set_forecast_status(self, message, severity='normal'):
        """Explicit severity is readable with or without Qt theme styling."""
        self.forecast_status.setText(message)
        self.forecast_status.setProperty('severity', severity)
        styles = {
            'error': 'color: #f38a86; font-weight: 600;',
            'stale': 'color: #e9b66c; font-weight: 600;',
            'busy': 'color: #80c8db;',
        }
        self.forecast_status.setStyleSheet(styles.get(severity, ''))

    def _show_previous_forecast(self):
        """Keep an earlier result visible without repeating refresh instructions."""
        previous = self._forecast_view.previous
        if previous is None:
            return False
        count = len(previous.get('forecast', {}).get('colors') or [])
        self.forecast_palette_label.setText(f'Previous forecast · {count} planned colors')
        # Color semantics belong in the single status line, not the palette.
        self.forecast_palette_label.setStyleSheet('')
        return True

    def _present_forecast_pending(self):
        """Retain stale palette context even if first-run setup blocks replanning."""
        automatic = self.auto_forecast.isChecked() and not getattr(self, '_filament_forecast_held', False)
        # Update the visible palette label before checking the first-run gate.
        # A setup-required state blocks an engine run, but must not prevent
        # same-model previous results from being identified as outdated.
        showing_previous = self._show_previous_forecast()
        if not showing_previous:
            self.forecast_palette_label.setText('No forecast yet')
            self.forecast_palette_label.setStyleSheet('')
        if getattr(self, '_filament_setup_confirmed', None) is not None:
            decision = self._filament_decision()
            if not decision.ready:
                return self._set_forecast_status(decision.message)
        if showing_previous:
            if getattr(self, '_filament_forecast_held', False):
                self._set_forecast_status(
                    'Previous forecast outdated — filament edits staged. Select Update Forecast.', 'stale')
            elif automatic:
                self._set_forecast_status('Updating forecast automatically…', 'busy')
            else:
                self._set_forecast_status(
                    'Previous forecast is outdated — select Refresh Forecast to update.', 'stale')
            return
        if getattr(self, '_filament_forecast_held', False) and self.state.model_path:
            self._set_forecast_status('Filament edits staged — select Update Forecast when ready.', 'stale')
        elif automatic:
            if self.state.model_path and self._original_mesh is not None:
                self._set_forecast_status('Updating forecast automatically…', 'busy')
            elif self.state.model_path:
                self._set_forecast_status('Automatic forecast will start when the model is ready.')
            else:
                self._set_forecast_status('Open a model to start automatic forecasting.')
        elif self.state.model_path:
            self._set_forecast_status('Select Refresh Forecast to calculate a palette.')
        else:
            self._set_forecast_status('Open a model to calculate a forecast.')

    def _invalidate_forecast(self, clear_inspection=False):
        self._forecast_serial += 1
        self._forecast_timer.stop()
        if getattr(self, '_forecast_heartbeat', None) is not None:
            self._forecast_heartbeat.stop()
        self._forecast_pending = False
        if self._forecast_task is not None:
            self._forecast_task.requestInterruption()
        if hasattr(self, '_live_preview_meshes'):
            if clear_inspection:
                self._clear_live_preview()
            else:
                self._mark_live_preview_stale()
        if hasattr(self, 'preview_chrome'):
            if clear_inspection:
                self.preview_chrome.set_estimate(None)
            else:
                self.preview_chrome.mark_outdated()
        if clear_inspection:
            # Prevent ever displaying an unrelated model's last forecast.
            self._forecast_view.reset(self.state.model_path)
        else:
            self._forecast_view.invalidate()
        # Earlier Stage 4A tests exercise this method on a lightweight
        # BehaviorHarness without Stage 4B widgets. Those details are optional
        # presentation, not a prerequisite for invalidating a forecast.
        details = getattr(self, 'planning_details_panel', None)
        toggle = getattr(self, 'details_toggle', None)
        if clear_inspection:
            if details is not None:
                self.planning_details_panel.clear_result()
            if toggle is not None:
                self.details_toggle.setChecked(False)
                self.details_toggle.setEnabled(False)
        elif self._forecast_view.has_previous:
            if details is not None:
                if self.auto_forecast.isChecked() and not getattr(self, '_filament_forecast_held', False):
                    self.planning_details_panel.set_stale(True, updating=True)
                else:
                    self.planning_details_panel.set_stale(True)
        else:
            if details is not None:
                self.planning_details_panel.clear_result()
            if toggle is not None:
                toggle.setEnabled(False)
        if not self._forecast_view.has_previous:
            # Stage 4A tests embed these methods in a small label-only
            # behavior harness. Keep that contract without replacing the
            # production RingGauge widgets or their values.
            if hasattr(self.accuracy, 'set_value'):
                self.accuracy.set_value(None)
            else:
                self.accuracy.setText('—')
            if hasattr(self, 'confidence_gauge'):
                self.confidence_gauge.set_value(None)
            if hasattr(self, 'worst_match_panel'):
                self.worst_match_panel.set_forecast(None)
            for value in self.forecast_metrics.values():
                value.setText('—')
            self._render_forecast_palette([])
            self.forecast_warning.clear()
        # Previous metrics, swatches and details remain visible for this model.
        # Do not show amber while an automatic refresh is already queued.
        self._present_forecast_pending()
        self.forecast_refresh.setEnabled(bool(self.state.model_path))
        if clear_inspection:
            self._inspection_serial += 1
            self.source_inspection.setText('Source: not inspected')
        allowed = (not hasattr(self, '_filament_setup_confirmed') or
                   self._filament_decision().ready)
        if (allowed and self.auto_forecast.isChecked() and bool(self.state.model_path)
                and self._original_mesh is not None
                and not getattr(self, '_filament_forecast_held', False)):
            self._forecast_timer.start()
        if hasattr(self, 'filament_setup_banner'):
            self._refresh_filament_setup_ui()

    def _start_inspection(self, path):
        if not Path(path).is_file():
            return
        self._inspection_serial += 1
        serial = self._inspection_serial
        thread = ForecastWorker('inspection', path, self)
        self._inspection_threads.append(thread)
        thread.completed.connect(lambda result, error, s=serial, p=path: self._inspection_done(s,p,result,error))
        thread.finished.connect(lambda t=thread: self._release_inspection(t))
        thread.start()

    def _release_inspection(self, thread):
        if thread in self._inspection_threads:
            self._inspection_threads.remove(thread)
        thread.deleteLater()

    def _inspection_done(self, serial, path, result, error):
        if serial != self._inspection_serial or path != self.state.model_path:
            return
        if error:
            self.source_inspection.setText('Project inspection unavailable: ' + str(error))
            self.results_panel.record_event('Model inspection', str(error), 'warning')
        else:
            slots = result.get('sourceSlots')
            label = (f'Engine source palette: {slots} slots' if slots is not None
                     else result.get('note', 'Geometry inspected'))
            if self._original_mesh is not None:
                label += f' · {self._original_mesh.source_triangles:,} mesh triangles'
            self.source_inspection.setText(label)
            self.results_panel.record_event('Model inspection', label, 'success')

    def _request_forecast(self):
        decision = self._filament_decision()
        if not decision.ready:
            self._forecast_timer.stop()
            self._refresh_filament_setup_ui()
            return
        if self._size_probe_active:
            self._set_forecast_status('Checking model dimensions before forecasting…', 'busy')
            return
        if self._scale_task is not None:
            self._set_forecast_status("Applying intended dimensions before forecasting…", "busy")
            return
        path = self._active_geometry_path()
        if not path or not Path(path).is_file():
            self._set_forecast_status('Choose a model before running a forecast.')
            return
        if not getattr(self.filaments_panel, 'selection_is_valid', True):
            self._forecast_timer.stop()
            self._set_forecast_status(
                'Filament selection unavailable: ' +
                (self.filaments_panel.selection_error or 'Correct the filament selection.'),
                'error')
            return
        # Explicit Plan refreshes supersede a pending automatic countdown;
        # do not let the timer fire again while this worker runs.
        self._forecast_timer.stop()
        if self._forecast_task is not None:
            self._filament_forecast_held = False
            self._forecast_pending = True
            self._update_filament_forecast_controls()
            self._set_forecast_status('Waiting for the previous plan to finish before updating…', 'busy')
            return
        self._forecast_pending = False
        serial = self._forecast_serial
        request = make_request(path, self.state.reference_path,
                               self.plan_preferences, self.filaments_panel.preferences)
        thread = ForecastWorker('forecast', request, self)
        # Release hold only when a valid request is constructed.
        self._filament_forecast_held = False
        self._update_filament_forecast_controls()
        self._forecast_task = thread
        self.forecast_refresh.setEnabled(False)
        self.forecast_cancel.setEnabled(True)
        self.forecast_progress.setValue(0)
        self.forecast_progress.setVisible(True)
        self._forecast_started_at = time.monotonic()
        self._active_forecast_serial = serial
        self._forecast_last_stage = 'Preparing palette planning'
        self._forecast_heartbeat.start()
        self._set_forecast_status('Running the existing FullSpectrum palette planner…', 'busy')
        self.results_panel.record_event('Live forecast', 'Read-only engine preview started.', 'busy')
        thread.progress_changed.connect(lambda fraction, message, s=serial: self._forecast_progress_changed(s, fraction, message))
        thread.completed.connect(lambda result, error, s=serial: self._forecast_done(s,result,error))
        thread.finished.connect(lambda t=thread: self._release_forecast(t))
        self._refresh_export_availability()
        thread.start()

    def _cancel_forecast(self):
        self._forecast_serial += 1
        self._forecast_heartbeat.stop()
        self._forecast_pending = False
        self._forecast_timer.stop()
        if self._forecast_task is not None:
            self._forecast_task.requestInterruption()
        self.forecast_cancel.setEnabled(False)
        self._set_forecast_status('Cancellation requested (at the next engine progress checkpoint).', 'stale')

    def _update_forecast_elapsed(self):
        if (self._active_forecast_serial != self._forecast_serial or
                self._forecast_task is None or not self._forecast_task.isRunning()):
            self._forecast_heartbeat.stop()
            return
        if self._forecast_started_at <= 0:
            return
        elapsed = int(max(0, time.monotonic() - self._forecast_started_at))
        self._set_forecast_status(
            f'Planning · {elapsed // 60:d}:{elapsed % 60:02d} elapsed · '
            f'{self._forecast_last_stage}', 'busy'
        )

    def _forecast_progress_changed(self, serial, fraction, message):
        if serial != self._forecast_serial:
            return
        self.forecast_progress.setValue(min(100,max(0,int(100*fraction))))
        self._forecast_last_stage = str(message)
        self._update_forecast_elapsed()

    def _forecast_done(self, serial, result, error):
        if serial != self._forecast_serial:
            return  # Stale model/settings result must never update the UI.
        if getattr(self, '_forecast_heartbeat', None) is not None:
            self._forecast_heartbeat.stop()
        if error:
            if getattr(self, '_live_preview_meshes', None):
                self._mark_live_preview_stale()
            self._forecast_view.invalidate()
            if self._forecast_view.has_previous:
                details = getattr(self, 'planning_details_panel', None)
                if details is not None:
                    details.set_stale(True)
            if not self._show_previous_forecast():
                self.forecast_palette_label.setText('No forecast yet')
                self.forecast_palette_label.setStyleSheet('')
            # Smart Quality can retry the same invalid physical-slot count
            # several times. Explain the one actionable configuration issue.
            from desktop.qt_app.filament_forecast_errors import describe_forecast_failure
            panel = getattr(self, 'filaments_panel', None)
            if panel is None:
                # Older forecast behavior tests use a lightweight window
                # harness without FilamentsTab. Keep their error presentation
                # contract without weakening the real app's richer guidance.
                self._set_forecast_status('Forecast unavailable: ' + str(error), 'error')
                self.results_panel.record_event('Live forecast', str(error), 'warning')
                return
            options = getattr(panel, 'options', ())
            disabled = getattr(getattr(panel, 'preferences', None), 'disabled', set())
            enabled_colors = len({str(option.get('color', '')).upper()
                                  for option in options if option.get('key') not in disabled})
            message = describe_forecast_failure(
                error, self.plan_preferences.get('real_slots'),
                enabled_colors if options else None)
            self._set_forecast_status('Forecast unavailable: ' + message, 'error')
            self.results_panel.record_event('Live forecast', message, 'warning')
            return
        if not self._forecast_view.accept(self.state.model_path, result):
            return  # Do not reuse a forecast for another model.
        if hasattr(self, '_live_preview_meshes'):
            self._accept_live_preview(result)
        # Engine result is already fully computed on a worker thread; update
        # read-only detail tables on Qt's owning GUI thread only.
        self.planning_details_panel.set_result(result.get('planningDetails') or {})
        self.details_toggle.setEnabled(True)
        forecast = result['forecast']
        self.accuracy.set_value(forecast['accuracy'])
        if hasattr(self, 'preview_chrome'):
            self.preview_chrome.set_estimate(forecast['accuracy'])
        self.confidence_gauge.set_value(forecast['confidence'])
        self.worst_match_panel.set_forecast(forecast)
        self.forecast_metrics['Confidence'].setText(f"{forecast['confidence']:.0f}%")
        # Worst *visible* match and maximum ΔE belong together once, in the
        # swatch comparison below. Use a different, native engine metric here.
        mean_delta = (result.get('quality') or {}).get('estimatedDeltaE')
        try:
            from math import isfinite
            mean_delta = float(mean_delta)
            self.forecast_metrics['Mean ΔE'].setText(
                f'{mean_delta:.1f}' if isfinite(mean_delta) else '—')
        except (TypeError, ValueError):
            self.forecast_metrics['Mean ΔE'].setText('—')
        self.forecast_metrics['Palette'].setText(forecast['slotSummary'])
        colors = forecast['colors']
        self._render_forecast_palette(colors)
        self.forecast_palette_label.setText(f'{len(colors)} planned output colors · Estimated before slicing')
        self.forecast_palette_label.setStyleSheet('')
        warnings = result.get('warnings') or []
        # The panel already owns target/predicted HEX and worst ΔE. Show only
        # actionable filament guidance or a separate engine warning here.
        self.forecast_warning.setText(forecast_guidance(forecast, warnings))
        self._set_forecast_status('Read-only plan ready. No native 3MF was exported.')
        self.results_panel.record_event('Live forecast',
            f"Estimated quality {forecast['accuracy']:.1f}%, {forecast['slotSummary']}; no 3MF written.", 'success')

    def _release_forecast(self, thread):
        if self._forecast_task is thread:
            self._forecast_heartbeat.stop()
            self._forecast_task = None
        self.forecast_progress.setVisible(False)
        self.forecast_cancel.setEnabled(False)
        self.forecast_refresh.setEnabled(bool(self.state.model_path))
        thread.deleteLater()
        self._refresh_export_availability()
        self._update_filament_forecast_controls()
        if self._forecast_pending:
            self._forecast_pending = False
            QTimer.singleShot(0, self._resume_queued_forecast)

    def _resume_queued_forecast(self):
        if not getattr(self, '_filament_forecast_held', False):
            self._request_forecast()

    def _render_forecast_palette(self, colors):
        from PySide6.QtGui import QColor
        while self.forecast_swatch_grid.count():
            item = self.forecast_swatch_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, color in enumerate(colors[:32]):
            if not isinstance(color, str) or not QColor(color).isValid():
                continue
            swatch = QLabel('')
            swatch.setMinimumHeight(23)
            swatch.setMinimumWidth(16)
            swatch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            swatch.setStyleSheet(f'background-color: {color}; border: 1px solid #5b6774; border-radius: 4px;')
            swatch.setToolTip(f'Output slot {index+1}: {color}')
            self.forecast_swatch_grid.addWidget(swatch, index//16, index%16)

    def _preview_render_error(self, message):
        self.preview_status.setText(message)
        self.statusBar().showMessage('OpenGL renderer unavailable.')
        self.results_panel.record_event('3D renderer', message, 'warning')

    def eventFilter(self, watched, event):
        if (hasattr(self, 'source_palette_scroll') and
            watched is self.source_palette_scroll.viewport() and
            event.type() == QEvent.Type.Resize and
            getattr(self, '_source_palette_cells', None)):
            # Prefer the event's new width: Qt may still report the old geometry
            # inside an active resize/layout pass.
            self._reflow_source_palette(event.size().width())
        if (event.type() == QEvent.Type.MouseButtonPress and
            watched is getattr(self, 'source_palette_content', None) and
            event.button() == Qt.MouseButton.LeftButton):
            # Only empty background reaches the container; actual swatches
            # receive their own click events and remain selectable.
            self._clear_palette_selection()
        return super().eventFilter(watched, event)

    def _reflow_source_palette(self, viewport_width=None):
        cells = getattr(self, '_source_palette_cells', [])
        if not cells:
            return
        if viewport_width is None:
            viewport_width = self.source_palette_scroll.viewport().width()
        columns = responsive_columns(viewport_width, len(cells))
        grid = self.source_palette_layout
        if columns != self._source_palette_columns:
            old_cols = self._source_palette_columns
            while grid.count():
                grid.takeAt(0)
            for col in range(max(old_cols, columns)):
                grid.setColumnStretch(col, 1 if col < columns else 0)
                grid.setColumnMinimumWidth(col, 0)
            for i, cell in enumerate(cells):
                grid.addWidget(cell, i // columns, i % columns)
            self._source_palette_columns = columns
        # The grid contributes its natural row height to the ONE outer
        # scrollbar; the inspector below remains reachable by wheel scrolling.

    def _on_palette_hover(self, color):
        if color in self._source_palette_counts:
            count = self._source_palette_counts[color]
            total = sum(self._source_palette_counts.values())
            fraction = 100 * count / total if total else 0
            self.source_palette_detail.setText(
                f'{color}  ·  {count:,} faces  ·  {fraction:.1f}% of colored faces')

    def _on_palette_leave(self):
        if len(self._source_palette_selected_colors) > 1:
            selected = self._source_palette_selected_colors
            total = sum(self._source_palette_counts.get(c, 0) for c in selected)
            self.source_palette_detail.setText(f'{len(selected)} selected colors · {total:,} faces · Ctrl+click to add/remove')
        elif self._source_palette_selected_colors:
            self._on_palette_hover(self._source_palette_selected_colors[0])
        else:
            self.source_palette_detail.setText('Click or Shift-click for a range; Ctrl-click to toggle; right-click to assign. Teal dots = assigned.')

    def _clear_palette_selection(self):
        self._select_palette_color(None)

    def _toggle_palette_color(self, color):
        # Plain click replaces the set or deselects a sole selected swatch.
        value = None if self._source_palette_selected_colors == (color,) else color
        self._source_palette_anchor = value
        self._select_palette_color(value)

    def _toggle_palette_multi(self, color):
        selected = list(self._source_palette_selected_colors)
        if color in selected:
            selected.remove(color)
        else:
            selected.append(color)
        self._source_palette_anchor = color
        self._select_palette_colors(selected)

    def _select_palette_range(self, color, additive=False):
        """Shift-click selects a contiguous swatch range in visual order.

        Ctrl+Shift adds the range to the existing selection. The anchor is kept
        while Shift is held, so repeated Shift-click extends/shrinks predictably.
        """
        ordered = [cell.hex_color for cell in self._source_palette_cells]
        if color not in ordered:
            return
        anchor = self._source_palette_anchor
        if anchor not in ordered:
            anchor = (self._source_palette_selected_colors[-1]
                      if self._source_palette_selected_colors else color)
        self._source_palette_anchor = anchor
        a,b=ordered.index(anchor),ordered.index(color)
        segment=ordered[min(a,b):max(a,b)+1]
        selected=(list(self._source_palette_selected_colors)+segment
                  if additive else segment)
        self._select_palette_colors(list(dict.fromkeys(selected)))

    def _show_protection_controls(self):
        # Existing toolbar shortcut now opens the Source Palette dialog directly.
        self.filaments_panel.open_assignment_dialog(self._source_palette_selected_colors)

    def _source_palette_context_menu(self, color):
        # Right-clicking one of the currently selected colors preserves the
        # whole selection for bulk assignment and removal.
        if color not in self._source_palette_selected_colors:
            self._source_palette_anchor = color
            self._select_palette_color(color)
        selected = self._source_palette_selected_colors
        assignments = self.filaments_panel.preferences.solid_assignments
        selected_assigned = tuple(c for c in selected if c in assignments)
        menu = QMenu(self)
        assign = menu.addAction('Assign Filament…')
        remove = menu.addAction(
            f'Remove Selected Assignments ({len(selected_assigned)})')
        remove.setEnabled(bool(selected_assigned))
        menu.addSeparator()
        clear_all = menu.addAction(f'Clear All Assignments… ({len(assignments)})')
        clear_all.setEnabled(bool(assignments))
        action = menu.exec(self.cursor().pos())
        if action == assign:
            self._show_protection_controls()
        elif action == remove:
            self.filaments_panel.remove_source_assignments(selected_assigned)
        elif action == clear_all:
            self._confirm_clear_all_assignments()

    def _confirm_clear_all_assignments(self):
        count = len(self.filaments_panel.preferences.solid_assignments)
        if not count:
            return
        result = QMessageBox.question(
            self, 'Clear Source Color Assignments',
            f'Remove all {count} source-color assignments from this model? '
            'The original model remains unchanged.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if result == QMessageBox.StandardButton.Yes:
            self.filaments_panel.remove_source_assignments(
                tuple(self.filaments_panel.preferences.solid_assignments))

    def _jump_to_assigned_color(self, color):
        """Clicking an inspector source HEX highlights and scrolls to its swatch."""
        self._source_palette_anchor = color
        self._select_palette_color(color)
        for swatch in self._source_palette_cells:
            if swatch.hex_color == color:
                self.source_palette_scroll.ensureWidgetVisible(swatch)
                break

    def _select_palette_color(self, color, sync_table=True):
        self._select_palette_colors([color] if color else (), sync_table=sync_table)

    def _select_palette_colors(self, colors, sync_table=True):
        """Exact source-key selection, kept in sync with the protection table."""
        selected = tuple(dict.fromkeys(c for c in colors if c in self._source_palette_counts))
        self._source_palette_selected_colors = selected
        self._source_palette_selected = selected[-1] if selected else None
        self.clear_palette_button.setEnabled(bool(selected))
        self.manage_protection_button.setEnabled(bool(selected) and bool(self.state.model_path))
        for swatch in self._source_palette_cells:
            swatch.set_selected(swatch.hex_color in selected)
        if selected:
            if len(selected) == 1:
                self._on_palette_hover(selected[0])
            else:
                total_faces = sum(self._source_palette_counts[c] for c in selected)
                self.source_palette_detail.setText(
                    f'{len(selected)} selected colors · {total_faces:,} faces · Ctrl+click to add/remove')
        else:
            self._on_palette_leave()
        if sync_table:
            if len(selected) == 1:
                color = selected[0]
                self.filaments_panel.select_source_color(color)
            else:
                self.filaments_panel.select_source_colors(selected)
        self._update_preview_highlights()

    def _filament_color_selected(self, color):
        if isinstance(color, (tuple, list, set)):
            self._select_palette_colors(color, sync_table=False)
        elif color in self._source_palette_counts:
            self._select_palette_color(color, sync_table=False)
        elif color is None:
            self._select_palette_color(None, sync_table=False)

    def _protections_updated(self, assignments):
        self._preview_protected_colors=set(assignments or ())
        self.assignment_panel.set_assignments(
            assignments, self.filaments_panel.options, self._source_palette_counts)
        self.tint_protected.setEnabled(bool(self._preview_protected_colors))
        if not self._preview_protected_colors:
            self.tint_protected.setChecked(False)
        for swatch in self._source_palette_cells:
            swatch.set_protected(swatch.hex_color in self._preview_protected_colors)
        self._update_preview_highlights()

    def _update_preview_highlights(self):
        # An external saved Predicted OBJ has unrelated material assignments.
        if self.preview_mode.currentText() in ('Predicted', 'Color Loss', 'Anchor Influence'):
            self.preview_surface.set_highlights(None, ())
        else:
            self.preview_surface.set_highlights(self._source_palette_selected_colors,
                                                self._preview_protected_colors)

    def _populate_source_palette(self, mesh):
        grid = self.source_palette_layout
        while grid.count():
            old_item = grid.takeAt(0)
            if old_item.widget() is not None:
                old_item.widget().deleteLater()
        self._source_palette_cells = []
        self._source_palette_columns = 0
        self._source_palette_selected = None
        self._source_palette_selected_colors = ()
        self._source_palette_anchor = None
        self.clear_palette_button.setEnabled(False)
        self.manage_protection_button.setEnabled(False)
        palette = tuple(getattr(mesh, 'palette_counts', ()))
        self._source_palette_counts = dict(palette)
        self.assignment_panel.set_assignments(
            self.filaments_panel.preferences.solid_assignments,
            self.filaments_panel.options, self._source_palette_counts)
        colors = len(palette)
        faces = sum(count for _, count in palette)
        if palette:
            if getattr(mesh, 'split_painted_faces', 0):
                # 3MF_SPLIT_PAINT_VERIFICATION_STAGE1_1: Counts are expanded
                # display tessellation, not original slicer mesh triangles.
                self.source_palette_message.setText(
                    f'{colors:,} source colors · {mesh.source_triangles:,} source triangles · '
                    f'{faces:,} colored display facets')
            else:
                self.source_palette_message.setText(
                    f'{colors:,} source colors · {faces:,} colored faces')
        else:
            self.source_palette_message.setText(
                getattr(mesh, 'color_status', 'No source colors available'))
        self._on_palette_leave()
        for color, count in palette:
            chip = PaletteSwatch(color, count)
            chip.set_protected(color in self._preview_protected_colors)
            chip.hovered.connect(self._on_palette_hover)
            chip.left.connect(self._on_palette_leave)
            chip.chosen.connect(self._toggle_palette_color)
            chip.multi_chosen.connect(self._toggle_palette_multi)
            chip.range_chosen.connect(self._select_palette_range)
            chip.context_requested.connect(self._source_palette_context_menu)
            self._source_palette_cells.append(chip)
        self.source_palette_content.setVisible(bool(palette))
        if palette:
            self._reflow_source_palette()
            # Recalculate after show/layout activation so first render uses the
            # real splitter width, not QScrollArea's pre-layout size hint.
            QTimer.singleShot(0, self._reflow_source_palette)

    # Stage 4C visual previews use the engine's analysis results; no conversion.
    def _refresh_preview_modes(self):
        if not hasattr(self, 'preview_mode'):
            return
        availability = {
            'Predicted': bool(self._live_preview_meshes.get('predicted') or self._predicted_mesh),
            'Color Loss': bool(self._live_preview_meshes.get('loss')),
            'Anchor Influence': bool(self._live_preview_meshes.get('influence') and self._influence_data),
        }
        for index in range(self.preview_mode.count()):
            name = self.preview_mode.itemText(index)
            item = self.preview_mode.model().item(index)
            if item is not None:
                item.setEnabled(name in ('Original', 'Wireframe') or availability.get(name, False))

    def _clear_live_preview(self):
        self._live_preview_meshes = {}
        self._live_preview_stale = False
        self._influence_data = None
        self.preview_surface.set_influence_analysis(None)
        self._use_external_predicted = False
        self._update_preview_options()
        if not hasattr(self, 'preview_mode'):
            return
        if self.preview_mode.currentText() in ('Predicted', 'Color Loss', 'Anchor Influence'):
            self.preview_mode.setCurrentText('Original')
        self._refresh_preview_modes()
        self.preview_legend.setVisible(False)
        self.anchor_legend.set_rows(())
        self.anchor_legend.setVisible(False)

    def _mark_live_preview_stale(self):
        if not self._live_preview_meshes:
            return
        self._live_preview_stale = True
        if hasattr(self, 'preview_chrome'):
            self.preview_chrome.mark_outdated()
        self.anchor_legend.selected_slot = 0
        self.anchor_legend.setVisible(False)
        if hasattr(self, 'preview_mode') and self.preview_mode.currentText() in (
                'Predicted', 'Color Loss', 'Anchor Influence'):
            self._preview_mode_changed(self.preview_mode.currentText())

    def _accept_live_preview(self, result):
        meshes = result.get('previewMeshes') or {}
        self._live_preview_meshes = dict(meshes)
        self._live_preview_stale = False
        self._use_external_predicted = False
        self._influence_data = result.get('previewInfluence')
        self.anchor_legend.set_rows(
            anchor_legend_rows(result) if meshes.get('influence') and self._influence_data else ())
        self._refresh_preview_modes()
        self._update_preview_options()
        if self.preview_mode.currentText() in ('Predicted', 'Color Loss', 'Anchor Influence'):
            if self.preview_mode.currentText() == 'Predicted' and not meshes.get('predicted') and self._predicted_mesh:
                # A manually loaded external OBJ is still available; never call it live.
                pass
            elif not meshes.get({'Predicted':'predicted','Color Loss':'loss',
                                  'Anchor Influence':'influence'}[self.preview_mode.currentText()]):
                self.preview_mode.setCurrentText('Original')
            else:
                self._preview_mode_changed(self.preview_mode.currentText())
        present = ', '.join(mode.title() for mode in ('predicted', 'loss', 'influence') if meshes.get(mode))
        note = str(result.get('previewNote') or '')
        if note:
            self.results_panel.record_event('3D forecast preview', note, 'warning')
        if present:
            self.statusBar().showMessage('Live 3D views available: ' + present)

    def _update_preview_options(self):
        """Sync an optional menu with the actual model/preview sources."""
        if not hasattr(self, 'preview_options_button'):
            return
        from desktop.qt_app.preview_toolbar_state import preview_options_state
        available = preview_options_state(
            self._original_mesh is not None,
            self._live_preview_meshes.get('predicted') is not None,
            self._predicted_mesh is not None,
            self._use_external_predicted)
        self.preview_options_button.setVisible(available['menu_visible'])
        self.preview_import_action.setEnabled(available['import_enabled'])
        self.preview_use_live_action.setVisible(available['sources_visible'])
        self.preview_use_live_action.setEnabled(available['live_enabled'])
        self.preview_use_live_action.setChecked(available['live_checked'])
        self.preview_use_imported_action.setVisible(available['sources_visible'])
        self.preview_use_imported_action.setEnabled(available['imported_enabled'])
        self.preview_use_imported_action.setChecked(available['imported_checked'])
        if hasattr(self, 'preview_toolbar'):
            self.preview_toolbar.refresh()

    def _use_live_predicted_preview(self):
        """Select the already-calculated engine mesh; do not run optimization."""
        if self._original_mesh is None or not self._live_preview_meshes.get('predicted'):
            return
        self._use_external_predicted = False
        self.preview_mode.setCurrentText('Predicted')
        self._preview_mode_changed('Predicted')
        self._update_preview_options()

    def _use_imported_predicted_preview(self):
        """Restore a manually imported OBJ if one has been loaded."""
        if self._original_mesh is None or self._predicted_mesh is None:
            return
        self._use_external_predicted = True
        self.preview_mode.setCurrentText('Predicted')
        self._preview_mode_changed('Predicted')
        self._update_preview_options()

    def _open_predicted(self):
        if self._original_mesh is None:return
        path,_=QFileDialog.getOpenFileName(self,'Open Existing Predicted Preview (OBJ)', '', 'Wavefront OBJ (*.obj)')
        if not path:return
        self._predicted_serial+=1
        serial=self._predicted_serial
        source=self.state.model_path
        self.preview_import_action.setEnabled(False)
        self.statusBar().showMessage('Reading saved predicted OBJ and matching MTL…')
        thread=ModelLoadWorker(path,self)
        self._preview_threads.append(thread)
        thread.completed.connect(lambda mesh,error,filename,s=serial,src=source:
                                 self._predicted_loaded(s,src,filename,mesh,error))
        thread.finished.connect(lambda t=thread:self._release_preview_task(t))
        thread.start()

    def _predicted_loaded(self,serial,source,path,mesh,error):
        if serial!=self._predicted_serial or source!=self.state.model_path:return
        self.preview_import_action.setEnabled(True)
        self._update_preview_options()
        if error:
            self.results_panel.record_event('Saved predicted preview',error,'warning')
            self.statusBar().showMessage('Unable to load saved predicted OBJ: '+error)
            return
        if not getattr(mesh,'palette_counts',()):
            self.statusBar().showMessage('Predicted OBJ has no MTL diffuse colors; preview was not activated.')
            self.results_panel.record_event('Saved predicted preview', 'OBJ lacks diffuse MTL swatches; color preview not activated.','warning')
            return
        self._predicted_mesh = mesh
        self._predicted_filename = path
        self._use_external_predicted = True
        self._refresh_preview_modes()
        self._update_preview_options()
        self.preview_mode.setCurrentText('Predicted')
        self._preview_mode_changed('Predicted')
        self.results_panel.record_event('Saved predicted preview',display_filename(path)+' opened (no conversion run).','success')
        self.statusBar().showMessage('Showing saved predicted colors from '+display_filename(path))

    def _preview_mode_changed(self, name):
        meshes = self._live_preview_meshes
        lookup = {'Predicted': 'predicted', 'Color Loss': 'loss',
                  'Anchor Influence': 'influence'}
        if name in lookup:
            target = meshes.get(lookup[name])
            if name == 'Predicted' and self._use_external_predicted and self._predicted_mesh is not None:
                target = self._predicted_mesh
            elif name == 'Predicted' and target is None:
                target = self._predicted_mesh  # Historical manual OBJ inspection.
            if name == 'Anchor Influence' and not self._influence_data:
                target = None
            if target is None:
                if self.preview_mode.currentText() != 'Original':
                    self.preview_mode.setCurrentText('Original')
                return
            if self.preview_surface.mesh is not target:
                self.preview_surface.set_mesh(target, preserve_camera=True)
            self.preview_surface.set_wireframe(False)
            if name == 'Predicted' and target is self._predicted_mesh:
                caption = 'Saved external predicted OBJ · not the current live forecast'
            else:
                caption = {'Predicted': 'Live engine-predicted color preview',
                           'Color Loss': 'Engine color-loss heatmap (ΔE estimate)',
                           'Anchor Influence': 'Physical anchor influence regions'}[name]
                if self._live_preview_stale:
                    caption += ' · OUTDATED — refresh forecast'
            self.preview_status.setText(caption)
        else:
            if self._original_mesh is not None and self.preview_surface.mesh is not self._original_mesh:
                self.preview_surface.set_mesh(self._original_mesh, preserve_camera=True)
            self.preview_surface.set_wireframe(name == 'Wireframe')
            if self._original_mesh is not None:
                mesh = self._original_mesh
                suffix = ' · sampled display' if mesh.sampled else ''
                self.preview_status.setText(
                    f'{len(mesh.triangles):,} visible / {mesh.source_triangles:,} source triangles'
                    f'{suffix} · {name}')
        self.preview_surface.set_influence_analysis(
            self._influence_data if name == 'Anchor Influence' else None,
            display=self.anchor_legend.color_mode,
            selected=self.anchor_legend.selected_slot if not self._live_preview_stale else 0)
        self.preview_legend.setVisible(name == 'Color Loss' and 'loss' in meshes)
        self.anchor_legend.setVisible(
            name == 'Anchor Influence' and 'influence' in meshes
            and not self._live_preview_stale and self.anchor_legend.has_rows)
        # Source palette selection/tagging is meaningful only on original color IDs.
        self.tint_protected.setEnabled(name in ('Original', 'Wireframe') and bool(self._preview_protected_colors))
        self.preview_surface.set_protected_overlay(
            self.tint_protected.isChecked() and name in ('Original', 'Wireframe'))
        self._update_preview_highlights()

    def _anchor_selected(self, slot):
        if self._live_preview_stale or self.preview_mode.currentText() != 'Anchor Influence':
            return
        if self._influence_data:
            self.preview_surface.set_influence_analysis(
                self._influence_data, display=self.anchor_legend.color_mode,
                selected=slot)

    def _anchor_palette_changed(self, mode):
        if self._live_preview_stale or self.preview_mode.currentText() != 'Anchor Influence':
            return
        if self._influence_data:
            self.preview_surface.set_influence_analysis(
                self._influence_data, display=mode,
                selected=self.anchor_legend.selected_slot)

    # Stage 4D-C: leave Stage 4D-A preview/forecast code untouched.
    def _begin_export(self):
        if self._size_probe_active:
            QMessageBox.information(self, 'Model dimensions',
                                    'Finish checking dimensions before exporting.')
            return
        if self._scale_task is not None:
            QMessageBox.information(self, "Model dimensions", "Finish preparing intended dimensions before exporting.")
            return
        if self._export_task is not None or self._forecast_task is not None:
            QMessageBox.information(self, 'Export busy', 'Wait for the current background task to finish.')
            return
        decision = self._filament_decision()
        if not decision.ready or not self.state.model_path or not Path(self.state.model_path).is_file():
            QMessageBox.warning(self, 'Cannot Export', 'Open a model and configure valid filaments first.')
            return
        if not getattr(self.filaments_panel, 'selection_is_valid', True):
            QMessageBox.warning(self, 'Cannot Export', self.filaments_panel.selection_error)
            return
        # Directory is explicitly displayed on Export; no surprise folder dialog.
        directory = self.export_directory.text().strip() or str(Path(self.state.model_path).parent)
        if not Path(directory).is_dir():
            QMessageBox.warning(self, 'Output Folder Unavailable',
                'Choose an existing output folder on the Export tab before exporting.')
            return
        request = make_export_request(
            self._active_geometry_path(), self.state.reference_path,
            self.plan_preferences, self.filaments_panel.preferences, directory)
        self._forecast_timer.stop()  # no concurrent palette planning
        self.forecast_refresh.setEnabled(False)
        self._export_serial += 1
        serial = self._export_serial
        self._export_request = request
        self._completed_export_success = False
        self.open_button.setEnabled(False)
        self.reference_button.setEnabled(False)
        self.preview_surface.set_drop_enabled(False)
        self.export_directory_browse.setEnabled(False)
        worker = ExportWorker(request, self)
        self._export_task = worker
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_action_stack.setCurrentWidget(self.export_progress)
        self.export_status.setText('Preparing native 3MF export…')
        self.export_status.show()
        self.export_status.show()
        self._refresh_export_availability()
        self.results_panel.record_event('Native 3MF export',
            f'Export requested for {Path(request.plan.model).name}', 'busy')
        worker.progress_changed.connect(
            lambda fraction, message, s=serial: self._export_progress_changed(s, fraction, message))
        worker.completed.connect(
            lambda result, error, s=serial: self._export_finished(s, result, error))
        worker.finished.connect(lambda w=worker: self._release_export(w))
        worker.start()
        self.export_cancel_button.setEnabled(True)

    def _export_progress_changed(self, serial, fraction, message):
        if serial != self._export_serial:
            return
        self.export_progress.setValue(max(0, min(100, int(float(fraction) * 100))))
        self.export_status.setText(str(message))
        self.statusBar().showMessage('Export: ' + str(message))

    def _cancel_export(self):
        if self._export_task is None:
            return
        self._export_task.requestInterruption()
        self.export_cancel_button.setEnabled(False)
        self.export_status.setText('Cancelling at the next safe conversion checkpoint…')

    def _export_finished(self, serial, result, error):
        if serial != self._export_serial:
            return
        self.export_cancel_button.setEnabled(False)
        if error is not None:
            cancelled = isinstance(error, InterruptedError)
            title = 'Export cancelled' if cancelled else 'Export failed'
            self.export_status.setText(title + ': ' + str(error))
            self.export_status.setVisible(not cancelled)
            self.results_panel.record_event('Native 3MF export', str(error),
                                            'warning' if cancelled else 'error')
            if not cancelled:
                QMessageBox.warning(self, title, str(error))
            return
        self._export_result = result
        self._last_export_path = result['output']
        self._completed_export_success = True
        self.export_progress.setValue(100)
        self.export_status.setText('Validated 3MF saved: ' + Path(result['output']).name)
        self.export_status.hide()
        self.results_panel.record_event('Native 3MF export',
            'Validated: ' + Path(result['output']).name, 'success')
        self._refresh_results_context()
        report = result.get('report')
        if report:
            self.results_panel.load_report(report)
        else:
            # A previous export's report must not appear to describe this 3MF.
            self.results_panel.clear_report()
        self.tabs.setCurrentWidget(self.results_panel)
        extra = sum(bool(result.get(key)) for key in ('csv', 'report', 'colorValidationReport'))
        self.statusBar().showMessage('Validated 3MF saved' +
            (f' with {extra} additional file(s).' if extra else ' (no additional files).'))

    def _release_export(self, worker):
        should_open = (self._export_request is not None and self._export_request.auto_open
                       and self._export_result is not None
                       and self._completed_export_success)
        if self._export_task is worker:
            self._export_task = None
        self._export_request = None
        self._completed_export_success = False
        self.open_button.setEnabled(True)
        self.reference_button.setEnabled(True)
        self.preview_surface.set_drop_enabled(True)
        self.export_directory_browse.setEnabled(True)
        self.forecast_refresh.setEnabled(bool(self.state.model_path) and self._filament_decision().ready)
        self.export_action_stack.setCurrentWidget(self.compose_button)
        worker.deleteLater()
        self._refresh_export_availability()
        if should_open:
            QTimer.singleShot(0, self._open_export_in_slicer)
        # Any settings changed during export are staged but never silently
        # applied to the in-flight frozen request.
        if (self.auto_forecast.isChecked() and self.state.model_path and
                not getattr(self, '_filament_forecast_held', False) and
                (self._forecast_view.stale or not self._forecast_view.has_previous)):
            self._forecast_timer.start()

    def _open_export_in_slicer(self):
        result = self._export_result
        if not result or self._export_task is not None:
            return
        path = Path(result['output'])
        if not path.is_file():
            QMessageBox.warning(self, 'Output unavailable', 'The exported 3MF file was moved or deleted.')
            return
        app = result['slicer']
        if app not in ('Bambu Studio', 'OrcaSlicer'):
            return
        try:
            if os.name == 'nt':
                configured = result.get('slicerExecutable') or ''
                executable = Path(configured) if configured else find_windows_slicer(app)
                if executable is None or not executable.is_file():
                    selected, _ = QFileDialog.getOpenFileName(
                        self, f'Locate {app} Executable', '', 'Windows executables (*.exe)')
                    if not selected:
                        self.results_panel.record_event('Slicer not opened',
                            'Export is saved. Select a slicer executable to open it.', 'warning')
                        return
                    executable = Path(selected)
                if not executable.is_file() or executable.suffix.lower() != '.exe':
                    raise ValueError('Choose an existing slicer .exe file.')
                subprocess.Popen([str(executable), str(path)], cwd=str(executable.parent))
            elif os.name == 'posix':
                # Match the legacy Mac frontend's explicit application selection.
                import sys
                if sys.platform != 'darwin':
                    raise RuntimeError('Automatic slicer launch is currently supported on Windows/macOS.')
                subprocess.Popen(['open', '-a', app, str(path)])
            else:
                raise RuntimeError('Unsupported slicer launch platform.')
            self.results_panel.record_event('Open in slicer', f'Sent 3MF to {app}.', 'success')
        except (OSError, ValueError, RuntimeError) as exc:
            self.results_panel.record_event('Slicer not opened', str(exc), 'warning')
            QMessageBox.warning(self, 'Unable to Open Slicer',
                'Your validated 3MF was saved, but the slicer could not be opened: ' + str(exc))

    def _show_export_folder(self):
        if not self._export_result or self._export_task is not None:
            return
        output = Path(self._export_result['output'])
        if not output.is_file():
            QMessageBox.warning(self, 'Output unavailable', 'The exported 3MF was moved or deleted.')
            return
        if os.name == 'nt':
            subprocess.Popen(['explorer', '/select,', str(output)])
        else:
            import sys
            if sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', str(output)])
            else:
                subprocess.Popen(['xdg-open', str(output.parent)])

    def _reset_camera(self):
        self.preview_surface.reset_camera()
        self.statusBar().showMessage('3D camera reset.')
