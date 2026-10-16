"""FullSpectrum Studio Qt Stage 4B: read-only inspection and real plan forecasts.

Conversion/export remain in the existing frontend until Stage 4D.
"""
from __future__ import annotations

import time

from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSlider, QSplitter, QTabWidget,
    QLineEdit, QCheckBox, QToolButton, QMessageBox, QFormLayout,
    QVBoxLayout, QGridLayout, QWidget, QSizePolicy, QProgressBar,
)

from desktop.app_support import APP_VERSION
from desktop.qt_app.plan_preferences import (
    PlanPreferences, PALETTE_STRATEGIES, FILAMENT_SOURCES, REGIONS,
    PHYSICAL_SLOTS, PLAN_EFFORT, PLANNING_SAMPLES, PALETTE_BASE,
    OUTPUT_SLICERS,
)
from desktop.qt_app.filaments_tab import FilamentsTab
from desktop.qt_app.gl_viewport import ModelViewport
from desktop.qt_app.preview_worker import ModelLoadWorker
from desktop.qt_app.forecast_worker import ForecastWorker
from desktop.qt_app.forecast_service import make_request
from desktop.qt_app.forecast_view_state import ForecastViewState
from desktop.qt_app.planning_details_panel import PlanningDetailsPanel
from desktop.qt_app.wheel_safe_combo import WheelSafeComboBox
from desktop.qt_app.section_help import SectionHelpButton, help_heading
from desktop.qt_app.forecast_visuals import RingGauge, WorstMatchPanel
from desktop.qt_app.forecast_setup_gate import evaluate_setup
from desktop.qt_app.source_palette import PaletteSwatch, responsive_columns
from desktop.qt_app.results_tab import ResultsTab
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


class MainWindow(QMainWindow):
    """Mac-inspired workspace shell with functioning file selection and navigation."""

    def __init__(self, settings_path=None):
        super().__init__()
        self.state = ShellState()
        self._preview_serial = 0
        self._preview_threads = []
        self._original_mesh = None
        self._predicted_mesh = None
        self._predicted_serial = 0
        self._predicted_filename = ""
        self.plan_preferences = PlanPreferences(settings_path)
        self._forecast_view = ForecastViewState()  # Current model only; never saved to disk.
        self._forecast_serial = 0
        self._forecast_pending = False
        self._forecast_task = None
        self._pending_review_filament_key = None
        self._inspection_serial = 0
        self._inspection_threads = []
        self._forecast_timer = QTimer(self)
        self._forecast_timer.setSingleShot(True)
        self._forecast_timer.setInterval(950)
        self._forecast_timer.timeout.connect(self._request_forecast)
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
        self._filament_options_ready = False
        self._filament_load_error = ''
        self._saved_filament_source = self.plan_preferences.saved.get('source')
        self.setObjectName("qtMainWindow")
        self.setWindowTitle("FullSpectrum Studio — Qt UI Preview")
        self.resize(1440, 880)
        self.setMinimumSize(920, 630)
        self._build()
        self._build_menus()
        QTimer.singleShot(0, self._initialize_filament_setup)
        self.statusBar().showMessage(
            "Qt Stage 4B — real read-only engine forecasts and project inspection; native 3MF export remains in Stage 4D."
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
        h.addWidget(_label("UI prototype · Stage 4B", "badge"))
        self.open_button = QPushButton("Open Model")
        self.open_button.setObjectName("openModelButton")
        self.open_button.clicked.connect(self._open_model)
        h.addWidget(self.open_button)
        self.reference_button = QPushButton("Reference")
        self.reference_button.clicked.connect(self._open_reference)
        h.addWidget(self.reference_button)
        h.addWidget(_label("v" + APP_VERSION, "bodyMuted"))
        main.addWidget(header)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.addWidget(self._preview_pane())
        self.splitter.addWidget(self._sidebar())
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([920, 455])
        main.addWidget(self.splitter, stretch=1)

        bottom = QFrame()
        bottom.setObjectName("bottomBar")
        foot = QHBoxLayout(bottom)
        foot.setContentsMargins(8, 9, 8, 9)
        self.bottom_hint = _label("Plan and filament settings are saved normally. Results shows session activity and previously saved reports; Qt conversion is not active.", "helpText")
        self.bottom_hint.setWordWrap(True)
        foot.addWidget(self.bottom_hint)
        main.addWidget(bottom)

    def _preview_pane(self):
        pane = QFrame()
        pane.setObjectName("previewCard")
        pane.setMinimumWidth(430)
        content = _column(pane, spacing=12)
        row = QHBoxLayout()
        row.addWidget(_label("MODEL PREVIEW", "smallTitle"))
        row.addStretch()
        self.preview_mode = WheelSafeComboBox()
        self.preview_mode.addItems(["Original", "Predicted", "Color Loss", "Wireframe"])
        self.preview_mode.setCurrentText("Original")
        self.preview_mode.setObjectName("previewMode")
        self.preview_mode.setEnabled(False)
        self.preview_mode.setToolTip("Original source colors, saved predicted OBJ (when loaded), or wireframe. Live prediction is not run in Qt yet.")
        self.preview_mode.currentTextChanged.connect(self._preview_mode_changed)
        row.addWidget(self.preview_mode)
        self.load_predicted_button = QPushButton('Load Predicted…')
        self.load_predicted_button.setObjectName('loadPredictedButton')
        self.load_predicted_button.setToolTip('Load an existing FullSpectrum predicted .obj with its matching .mtl. Does not run a conversion.')
        self.load_predicted_button.setEnabled(False)
        self.load_predicted_button.clicked.connect(self._open_predicted)
        row.addWidget(self.load_predicted_button)
        self.reset_camera_button = QPushButton("Reset View")
        self.reset_camera_button.setObjectName("resetCameraButton")
        self.reset_camera_button.setEnabled(False)
        self.reset_camera_button.clicked.connect(self._reset_camera)
        row.addWidget(self.reset_camera_button)
        content.addLayout(row)
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
        self.preview_surface.render_error.connect(self._preview_render_error)
        self.preview_surface.background_clicked.connect(self._clear_palette_selection)
        model_layout.addWidget(self.preview_surface, stretch=1)
        self.preview_status = _label("Open a 3MF, OBJ or GLB model to view its geometry.", "helpText", wrap=True)
        model_layout.addWidget(self.preview_status)
        self.preview_splitter.addWidget(model_area)

        palette_area = QFrame()
        palette_area.setObjectName('sourcePalettePanel')
        palette_area.setMinimumHeight(94)
        palette_layout = QVBoxLayout(palette_area)
        palette_layout.setContentsMargins(0, 4, 0, 0)
        palette_layout.setSpacing(5)
        title_row = QHBoxLayout()
        title_row.addWidget(_section_heading("Source Palette"))
        title_row.addStretch()
        self.tint_protected=QCheckBox('Tint Protected')
        self.tint_protected.setObjectName('tintProtectedToggle')
        self.tint_protected.setToolTip('Optional teal tint on protected model faces. Off preserves original colors.')
        self.tint_protected.setChecked(False)
        self.tint_protected.setEnabled(False)
        self.tint_protected.toggled.connect(self.preview_surface.set_protected_overlay)
        title_row.addWidget(self.tint_protected)
        self.manage_protection_button=QPushButton('Assign Filament…')
        self.manage_protection_button.setObjectName('manageProtectionShortcut')
        self.manage_protection_button.setEnabled(False)
        self.manage_protection_button.setToolTip('Choose one or more source colors first; opens the matching filament assignment, scanning source colors automatically if needed.')
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
        self.source_palette_detail = _label('Click to select; Ctrl+click for multiple; click again or Esc to clear. Teal dots = protected.', 'helpText')
        self.source_palette_detail.setObjectName('sourcePaletteDetail')
        palette_layout.addWidget(self.source_palette_detail)
        self.source_palette_scroll = QScrollArea()
        self.source_palette_scroll.setObjectName('sourcePaletteScroll')
        self.source_palette_scroll.setWidgetResizable(True)
        self.source_palette_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.source_palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.source_palette_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_palette_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.source_palette_content = QWidget()
        self.source_palette_content.setObjectName('sourcePaletteContent')
        self.source_palette_layout = QGridLayout(self.source_palette_content)
        self.source_palette_layout.setContentsMargins(0, 0, 6, 2)
        self.source_palette_layout.setHorizontalSpacing(5)
        self.source_palette_layout.setVerticalSpacing(5)
        self.source_palette_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.source_palette_scroll.setWidget(self.source_palette_content)
        self._source_palette_cells = []
        self._source_palette_columns = 0
        self._source_palette_selected = None
        self._source_palette_selected_colors = ()
        self._source_palette_counts = {}
        self._preview_protected_colors=set()
        self.source_palette_scroll.viewport().installEventFilter(self)
        self.source_palette_content.installEventFilter(self)
        self.source_palette_scroll.setVisible(False)
        palette_layout.addWidget(self.source_palette_scroll, stretch=1)
        self.preview_splitter.addWidget(palette_area)
        self.preview_splitter.setStretchFactor(0, 7)
        self.preview_splitter.setStretchFactor(1, 2)
        self.preview_splitter.setSizes([590, 135])
        content.addWidget(self.preview_splitter, stretch=1)
        return pane

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
        self.tabs.addTab(self._plan_tab(), "Plan")
        self.tabs.addTab(self.filaments_panel, "Filaments")
        self.tabs.currentChanged.connect(self._tab_changed)
        # _plan_tab wired preference updates first; load filament options only
        # after the plan values have received the new source selection.
        self.filament_source.currentIndexChanged.connect(
            lambda _: self.filaments_panel.load_options())
        self.results_panel = ResultsTab(self.tabs)
        self.tabs.addTab(self.results_panel, "Results")
        self.filaments_panel.activity_event.connect(self._filament_activity)
        self.filaments_panel.planning_changed.connect(self._filament_planning_changed)
        self.filaments_panel.source_color_selected.connect(self._filament_color_selected)
        self.filaments_panel.protections_changed.connect(self._protections_updated)
        self.confirm_filaments_tab_button = QPushButton('Use These Filaments for Forecast')
        self.confirm_filaments_tab_button.setObjectName('confirmFilamentsTab')
        self.confirm_filaments_tab_button.clicked.connect(self._confirm_filament_setup)
        filament_layout = self.filaments_panel.content.layout()
        filament_layout.insertWidget(
            filament_layout.indexOf(self.filaments_panel.selection_hint) + 1,
            self.confirm_filaments_tab_button)
        self.confirm_filaments_tab_button.setVisible(False)
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
        for field in ("Confidence", "Worst match", "Palette"):
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
        self.palette_limit = self._choice((("Auto", "auto"),) +
                                          tuple((f"{i} colors", str(i)) for i in range(2, 33)))
        self.palette_limit.setObjectName("paletteLimit")
        col.addWidget(self.palette_limit)
        col.addWidget(_label("Upper limit for physical + mixed filaments (32 maximum).",
                               "helpText", wrap=True))
        shortcut = QPushButton('Manage Filament Colors…')
        shortcut.setObjectName('manageFilamentsButton')
        shortcut.setToolTip('Choose your filament source, library and pinned colors under Filaments.')
        shortcut.clicked.connect(lambda: self.tabs.setCurrentWidget(self.filaments_panel))
        col.addWidget(shortcut)
        col.addWidget(_label('Filament source and material selection are managed on the Filaments tab.',
                             'helpText', wrap=True))
        col.addWidget(help_heading("native_project_template", "NATIVE PROJECT TEMPLATE"))
        template_row = QHBoxLayout()
        self.template_path = QLineEdit()
        self.template_path.setObjectName("nativeTemplatePath")
        self.template_path.setReadOnly(True)
        self.template_path.setPlaceholderText("Select a blank slicer-saved 3MF project")
        template_row.addWidget(self.template_path, 1)
        self.template_browse = QPushButton("Browse…")
        self.template_browse.clicked.connect(self._browse_template)
        template_row.addWidget(self.template_browse)
        col.addLayout(template_row)
        template_actions = QHBoxLayout()
        self.template_clear = QPushButton("Clear")
        self.template_clear.clicked.connect(self._clear_template)
        template_actions.addWidget(self.template_clear)
        template_actions.addStretch()
        col.addLayout(template_actions)
        self.template_status = _label("No native project template selected.", "templateStatus", wrap=True)
        col.addWidget(self.template_status)
        self.template_compatibility = _label("", "templateWarning", wrap=True)
        col.addWidget(self.template_compatibility)
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
        self.auto_open = QCheckBox("Open validated output automatically (Stage 4)")
        self.auto_open.setToolTip("Preference saved now; no conversion is performed.")
        form.addRow(self.auto_open)
        self.output_application = self._choice(OUTPUT_SLICERS)
        form.addRow("Output slicer", self.output_application)
        # Portable/nightly slicer executable choice mirrors the existing Tkinter
        # settings, but never starts a slicer in this UI-only stage.
        self.slicer_executable_row = QWidget()
        slicer_controls = QHBoxLayout(self.slicer_executable_row)
        slicer_controls.setContentsMargins(0, 0, 0, 0)
        slicer_controls.setSpacing(6)
        self.slicer_executable_browse = QPushButton("Choose EXE…")
        self.slicer_executable_browse.setObjectName("slicerExecutableBrowse")
        self.slicer_executable_browse.clicked.connect(self._browse_slicer_executable)
        slicer_controls.addWidget(self.slicer_executable_browse)
        self.slicer_executable_auto = QPushButton("Auto")
        self.slicer_executable_auto.setObjectName("slicerExecutableAuto")
        self.slicer_executable_auto.clicked.connect(self._clear_slicer_executable)
        slicer_controls.addWidget(self.slicer_executable_auto)
        form.addRow("Slicer executable", self.slicer_executable_row)
        self.slicer_executable_status = _label("Automatic executable detection (Stage 4)", "helpText", wrap=True)
        self.slicer_executable_status.setObjectName("slicerExecutableStatus")
        form.addRow("", self.slicer_executable_status)
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
        self.compose_button = QPushButton("Compose Palette")
        self.compose_button.setObjectName("primary")
        _disabled(self.compose_button, "Conversion and export will be connected in Stage 4.")
        col.addWidget(self.compose_button)
        col.addWidget(_label("Planning runs as a read-only preview. 3MF conversion and export remain in Stage 4D.",
                               "helpText", wrap=True))
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
        for widget, field in (
            (self.smart_quality, "smart_quality"),
            (self.auto_forecast, "auto_preview"),
            (self.auto_open, "auto_open"),
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
            self._filament_options_ready = False
            self._filament_load_error = ''
            self._filament_setup_confirmed = True  # Explicit user source choice.
        self._refresh_dependent_plan_widgets()
        self._update_plan_dirty_state()
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
                    (self._forecast_view.stale or not self._forecast_view.has_previous)):
                self._forecast_timer.start()
            elif not value:
                self._forecast_timer.stop()
                self._forecast_pending = False
            if self._forecast_view.stale or not self._forecast_view.has_previous:
                self._present_forecast_pending()
            return
        # Slicer launch settings do not affect the read-only palette forecast.
        if field in ('auto_open', 'output_application', 'bambu_studio_executable', 'orcaslicer_executable'):
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
        self._refresh_slicer_executable_status()

    def _update_plan_dirty_state(self):
        dirty = self.plan_preferences.is_dirty
        self.save_plan_button.setEnabled(dirty)
        self.revert_plan_button.setEnabled(dirty)
        self.plan_save_status.setText("Unsaved changes" if dirty else "Settings saved or unchanged")
        if hasattr(self, 'results_panel'):
            self._refresh_results_context()

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
        if not path:
            self.template_status.setObjectName("templateStatusEmpty")
            self.template_status.setText("No template selected. A blank slicer-saved 3MF is required for generic colored inputs.")
            self._repolish_template_status()
            return
        try:
            from native_project_template import inspect_template
            details = inspect_template(path)
            self.template_status.setObjectName("templateStatusReady")
            self.template_status.setText(
                f"{details['slicer']} {details['slicerVersion']} · "
                f"{details['printerPreset']} · {details['nozzle']} mm · {details['processPreset']}")
            self._repolish_template_status()
            from orca_profile_warning import orca_h2c_warning
            warning = orca_h2c_warning(details, self.output_application.currentData())
            if warning:
                self.template_compatibility.setText(warning)
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self.template_status.setObjectName("templateStatusError")
            self.template_status.setText("Template unavailable or invalid: " + str(exc))
            self._repolish_template_status()

    def _repolish_template_status(self):
        # Qt caches widget styles: changing objectName requires re-polishing.
        style = self.template_status.style()
        style.unpolish(self.template_status)
        style.polish(self.template_status)
        self.template_status.update()

    def _selected_slicer_executable_key(self):
        return ("orcaslicer_executable" if self.output_application.currentData() == "OrcaSlicer"
                else "bambu_studio_executable")

    def _refresh_slicer_executable_status(self):
        selected = self.output_application.currentData() or "Bambu Studio"
        path = self.plan_preferences.get(self._selected_slicer_executable_key()).strip()
        self.slicer_executable_auto.setEnabled(bool(path))
        if not path:
            self.slicer_executable_status.setText(
                f"{selected}: automatic executable detection (launch integration in Stage 4).")
        elif not Path(path).is_file():
            self.slicer_executable_status.setText(
                f"{selected}: saved EXE not found: {path}. Choose a new executable or select Auto.")
        else:
            self.slicer_executable_status.setText(f"{selected}: {path}")
        self.slicer_executable_status.setToolTip(path)

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
        self.plan_preferences.revert()
        self._saved_filament_source = self.plan_preferences.saved.get('source')
        self._filament_setup_confirmed = False
        self._filament_options_ready = False
        self._filament_load_error = ''
        self._restore_plan_widgets()
        self.filaments_panel.load_options()
        self.statusBar().showMessage("Plan edits discarded; settings reloaded from disk.")
        self.results_panel.record_event('Plan settings', 'Unsaved Plan edits reverted.', 'info')
        self._refresh_results_context()
        self._invalidate_forecast()

    def _refresh_results_context(self):
        if not hasattr(self, 'results_panel'):
            return
        self.results_panel.set_context(
            self.state.model_path,
            self.plan_preferences.get('native_project_template'),
            self.plan_preferences.get('output_application'),
            self.plan_preferences.is_dirty,
        )

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
        # Returning users should not need to open Filaments manually, but the
        # source must finish loading before any forecast starts.
        if self._saved_filament_source:
            self.filaments_panel.load_options()
        self._refresh_filament_setup_ui()

    def _refresh_filament_setup_ui(self):
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
        return decision

    def _confirm_filament_setup(self):
        decision = self._filament_decision()
        if not decision.can_confirm:
            self._refresh_filament_setup_ui()
            return
        self._filament_setup_confirmed = True
        self._refresh_filament_setup_ui()
        self.results_panel.record_event(
            'Filament setup', 'Current filament selection confirmed for this session.', 'success')
        if self.state.model_path and self._original_mesh is not None:
            self._invalidate_forecast()
        elif not self.state.model_path:
            self._set_forecast_status('Filaments ready. Open a model to begin forecasting.')

    def _filament_planning_changed(self, valid):
        # A valid user checkbox edit is intentional configuration for this session.
        if valid and self._filament_options_ready:
            self._filament_setup_confirmed = True
        # A pin/enable click is a planning change, not just a Save event.
        # This uses the same debounce as Plan controls. No save to disk.
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
                    (self._forecast_view.stale or not self._forecast_view.has_previous)):
                self._forecast_timer.start()
        elif title == 'Filaments' and severity == 'success':
            self._filament_setup_confirmed = True
            self._refresh_filament_setup_ui()
        if title in ('Filaments', 'Protected colors') and severity in ('success', 'info'):
            self._invalidate_forecast()
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
        save = QAction("&Save Settings", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(self._save_plan_settings)
        menu.addAction(save)
        menu.addSeparator()
        close = QAction("E&xit", self)
        close.setShortcut(QKeySequence.StandardKey.Quit)
        close.triggered.connect(self.close)
        menu.addAction(close)
        clear_color=QAction('Clear Source Color Selection', self)
        clear_color.setShortcut(QKeySequence('Escape'))
        clear_color.triggered.connect(self._clear_palette_selection)
        self.addAction(clear_color)
        view = self.menuBar().addMenu("&View")
        for idx, name in enumerate(("Plan", "Filaments", "Results")):
            nav = QAction(name, self)
            nav.setShortcut(QKeySequence(f"Ctrl+{idx+1}"))
            nav.triggered.connect(lambda checked=False, index=idx: self.tabs.setCurrentIndex(index))
            view.addAction(nav)

    def _tab_changed(self, index):
        if index == 1:
            self.filaments_panel.on_selected()
        elif index == 2:
            self._refresh_results_context()

    def closeEvent(self, event):
        # Let any 3MF/inventory reads finish so Qt never destroys a live QThread.
        self._forecast_timer.stop()
        self._forecast_heartbeat.stop()
        if self._forecast_task is not None:
            self._forecast_task.requestInterruption()
        for worker in list(self.filaments_panel._workers) + list(self._preview_threads) + list(self._inspection_threads) + ([self._forecast_task] if self._forecast_task is not None else []):
            if worker.isRunning():
                worker.wait()
        super().closeEvent(event)

    def _open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open 3D Model", "", MODEL_FILE_FILTER)
        if not self.state.select_model(path):
            return
        name = display_filename(path)
        self.project_subtitle.setText(name)
        self._pending_review_filament_key = None
        self.filaments_panel.set_model(path)
        self.bottom_hint.setText(f"Selected: {name} — loading preview geometry (original files are unchanged).")
        self.statusBar().showMessage("Loading 3D model geometry…")
        self.results_panel.record_event('Model selected', f'{name} selected; loading preview geometry.', 'busy')
        self._refresh_results_context()
        self._load_preview(path)
        self._invalidate_forecast(clear_inspection=True)

    def _open_reference(self):
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
        self._preview_serial += 1
        self._predicted_serial += 1  # obsolete predicted loads must not replace a different model
        self._original_mesh = None
        self._predicted_mesh = None
        self._predicted_filename = ''
        self.load_predicted_button.setEnabled(False)
        self.source_palette_scroll.setVisible(False)
        self._source_palette_selected=None
        self._preview_protected_colors=set()
        self.clear_palette_button.setEnabled(False)
        self.manage_protection_button.setEnabled(False)
        self.tint_protected.setChecked(False)
        self.tint_protected.setEnabled(False)
        self.preview_surface.set_highlights(None, ())
        self.source_palette_message.setText('Reading source color assignments…')
        serial = self._preview_serial
        self.preview_surface.clear_mesh()
        self.preview_mode.setEnabled(False)
        self.reset_camera_button.setEnabled(False)
        self.preview_status.setText("Reading model geometry…")
        task = ModelLoadWorker(path, self)
        self._preview_threads.append(task)
        task.completed.connect(
            lambda mesh, error, filename, s=serial: self._preview_loaded(s, filename, mesh, error))
        task.finished.connect(lambda t=task: self._release_preview_task(t))
        task.start()

    def _release_preview_task(self, task):
        if task in self._preview_threads:
            self._preview_threads.remove(task)
        task.deleteLater()

    def _preview_loaded(self, serial, path, mesh, error):
        if serial != self._preview_serial or path != self.state.model_path:
            return  # Ignore obsolete loads when a user selects a different file.
        if error:
            self.preview_status.setText("Preview unavailable: " + error)
            self.bottom_hint.setText("Source selection retained; preview could not be loaded.")
            self.statusBar().showMessage("Model preview unavailable.")
            self.results_panel.record_event('Model preview', error, 'warning')
            return
        self._original_mesh = mesh
        self.preview_surface.set_mesh(mesh)
        self._update_preview_highlights()
        self.reset_camera_button.setEnabled(True)
        self.preview_mode.setEnabled(True)
        # Stage 3A does not display predicted colors or error maps.
        for index in range(self.preview_mode.count()):
            label = self.preview_mode.itemText(index)
            if label not in ('Original', 'Wireframe'):
                # Items remain visible but unavailable, avoiding a fake preview.
                item = self.preview_mode.model().item(index)
                if item is not None:
                    item.setEnabled(False)
        self.preview_mode.setCurrentText('Original')
        self.preview_surface.set_wireframe(False)
        self.load_predicted_button.setEnabled(True)
        self._populate_source_palette(mesh)
        # Populate Protect Solid Colors without making the user scan again.
        # This uses the authoritative engine/native color scanner, not just
        # render-time color averages or approximate visual gradients.
        self.filaments_panel.auto_load_source_colors()
        suffix = ' · sampled display only' if mesh.sampled else ''
        info = f"{len(mesh.triangles):,} visible triangles / {mesh.source_triangles:,} source triangles{suffix}"
        self.preview_status.setText(info + ' · Left drag orbit · Right drag pan · Wheel zoom · R reset')
        self.bottom_hint.setText('Source geometry and colors loaded. Forecasts run on Plan; predicted 3D and export arrive in Stages 4C/4D.')
        self.statusBar().showMessage('3D preview ready: ' + info)
        self.results_panel.record_event('Model preview', info, 'success')
        self.source_inspection.setText(f'Source geometry: {mesh.source_triangles:,} triangles; inspecting project metadata…')
        self._start_inspection(path)
        if self.auto_forecast.isChecked() and self._filament_decision().ready:
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
        automatic = self.auto_forecast.isChecked()
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
            if automatic:
                self._set_forecast_status('Updating forecast automatically…', 'busy')
            else:
                self._set_forecast_status(
                    'Previous forecast is outdated — select Refresh Forecast to update.', 'stale')
            return
        if automatic:
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
                if self.auto_forecast.isChecked():
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
                and self._original_mesh is not None):
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
        path = self.state.model_path
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
        if self._forecast_task is not None:
            self._forecast_pending = True
            self._set_forecast_status('Waiting for the previous plan to finish before updating…', 'busy')
            return
        self._forecast_pending = False
        serial = self._forecast_serial
        request = make_request(path, self.state.reference_path,
                               self.plan_preferences, self.filaments_panel.preferences)
        thread = ForecastWorker('forecast', request, self)
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
            self._forecast_view.invalidate()
            if self._forecast_view.has_previous:
                details = getattr(self, 'planning_details_panel', None)
                if details is not None:
                    details.set_stale(True)
            if not self._show_previous_forecast():
                self.forecast_palette_label.setText('No forecast yet')
                self.forecast_palette_label.setStyleSheet('')
            self._set_forecast_status('Forecast unavailable: ' + str(error), 'error')
            self.results_panel.record_event('Live forecast', str(error), 'warning')
            return
        if not self._forecast_view.accept(self.state.model_path, result):
            return  # Do not reuse a forecast for another model.
        # Engine result is already fully computed on a worker thread; update
        # read-only detail tables on Qt's owning GUI thread only.
        self.planning_details_panel.set_result(result.get('planningDetails') or {})
        self.details_toggle.setEnabled(True)
        forecast = result['forecast']
        self.accuracy.set_value(forecast['accuracy'])
        self.confidence_gauge.set_value(forecast['confidence'])
        self.worst_match_panel.set_forecast(forecast)
        self.forecast_metrics['Confidence'].setText(f"{forecast['confidence']:.0f}%")
        self.forecast_metrics['Worst match'].setText(f"dE {forecast['maximumDeltaE']:.1f}")
        self.forecast_metrics['Palette'].setText(forecast['slotSummary'])
        colors = forecast['colors']
        self._render_forecast_palette(colors)
        self.forecast_palette_label.setText(f'{len(colors)} planned output colors · Estimated before slicing')
        self.forecast_palette_label.setStyleSheet('')
        warnings = result.get('warnings') or []
        self.forecast_warning.setText(forecast.get('gapMessage') or ('Warnings: '+str(warnings[0]) if warnings else ''))
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
        if self._forecast_pending:
            self._forecast_pending = False
            QTimer.singleShot(0, self._request_forecast)

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
            watched in (getattr(self, 'source_palette_content', None),
                        getattr(self.source_palette_scroll, 'viewport', lambda: None)()) and
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
        # No fixed height: the user can drag the vertical splitter and the
        # palette uses its own scrollbar only when its rows exceed that height.

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
            self.source_palette_detail.setText('Click to select; Ctrl+click for multiple; click again or Esc to clear. Teal dots = protected.')

    def _clear_palette_selection(self):
        self._select_palette_color(None)

    def _toggle_palette_color(self, color):
        # Plain click replaces the set, or clears an already-sole selection.
        self._select_palette_color(None if self._source_palette_selected_colors == (color,) else color)

    def _toggle_palette_multi(self, color):
        selected = list(self._source_palette_selected_colors)
        if color in selected:
            selected.remove(color)
        else:
            selected.append(color)
        self._select_palette_colors(selected)

    def _show_protection_controls(self):
        # Preserve the Source Palette selection until the asynchronous scan
        # populates the Filaments table; navigation alone cannot select rows.
        selected = self._source_palette_selected_colors
        if not selected or not self.state.model_path:
            return
        self.tabs.setCurrentWidget(self.filaments_panel)
        self.filaments_panel.prepare_source_assignments(selected)
        def scroll_to_protection():
            content=self.filaments_panel.content
            label=self.filaments_panel.protected_intro
            top=label.mapTo(content, label.rect().topLeft()).y()
            self.filaments_panel.content_scroll.verticalScrollBar().setValue(max(0,top-35))
        QTimer.singleShot(0, scroll_to_protection)

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
        self.tint_protected.setEnabled(bool(self._preview_protected_colors))
        if not self._preview_protected_colors:
            self.tint_protected.setChecked(False)
        for swatch in self._source_palette_cells:
            swatch.set_protected(swatch.hex_color in self._preview_protected_colors)
        self._update_preview_highlights()

    def _update_preview_highlights(self):
        # An external saved Predicted OBJ has unrelated material assignments.
        if self.preview_mode.currentText()=='Predicted':
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
        self.clear_palette_button.setEnabled(False)
        self.manage_protection_button.setEnabled(False)
        palette = tuple(getattr(mesh, 'palette_counts', ()))
        self._source_palette_counts = dict(palette)
        colors = len(palette)
        faces = sum(count for _, count in palette)
        if palette:
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
            self._source_palette_cells.append(chip)
        self.source_palette_scroll.setVisible(bool(palette))
        if palette:
            self._reflow_source_palette()
            # Recalculate after show/layout activation so first render uses the
            # real splitter width, not QScrollArea's pre-layout size hint.
            QTimer.singleShot(0, self._reflow_source_palette)

    def _open_predicted(self):
        if self._original_mesh is None:return
        path,_=QFileDialog.getOpenFileName(self,'Open Existing Predicted Preview (OBJ)', '', 'Wavefront OBJ (*.obj)')
        if not path:return
        self._predicted_serial+=1
        serial=self._predicted_serial
        source=self.state.model_path
        self.load_predicted_button.setEnabled(False)
        self.statusBar().showMessage('Reading saved predicted OBJ and matching MTL…')
        thread=ModelLoadWorker(path,self)
        self._preview_threads.append(thread)
        thread.completed.connect(lambda mesh,error,filename,s=serial,src=source:
                                 self._predicted_loaded(s,src,filename,mesh,error))
        thread.finished.connect(lambda t=thread:self._release_preview_task(t))
        thread.start()

    def _predicted_loaded(self,serial,source,path,mesh,error):
        if serial!=self._predicted_serial or source!=self.state.model_path:return
        self.load_predicted_button.setEnabled(True)
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
        for i in range(self.preview_mode.count()):
            if self.preview_mode.itemText(i)=='Predicted':
                item=self.preview_mode.model().item(i)
                if item:item.setEnabled(True)
        self.preview_mode.setCurrentText('Predicted')
        self.results_panel.record_event('Saved predicted preview',display_filename(path)+' opened (no conversion run).','success')
        self.statusBar().showMessage('Showing saved predicted colors from '+display_filename(path))

    def _preview_mode_changed(self, name):
        if name == 'Predicted' and self._predicted_mesh is not None:
            self.preview_surface.set_mesh(self._predicted_mesh)
            self.preview_surface.set_wireframe(False)
            self.preview_status.setText('Saved predicted OBJ · '+display_filename(self._predicted_filename)+' · Not a live Qt forecast')
        elif name in ('Original','Wireframe'):
            if self._original_mesh is not None and self.preview_surface.mesh is not self._original_mesh:
                self.preview_surface.set_mesh(self._original_mesh)
            self.preview_surface.set_wireframe(name=='Wireframe')
            if self._original_mesh is not None:
                mesh=self._original_mesh
                suffix=' · sampled display' if mesh.sampled else ''
                self.preview_status.setText(f'{len(mesh.triangles):,} visible / {mesh.source_triangles:,} source triangles{suffix} · {name}')
        elif self.preview_mode.currentText()!='Original':
            self.preview_mode.setCurrentText('Original')
        self._update_preview_highlights()

    def _reset_camera(self):
        self.preview_surface.reset_camera()
        self.statusBar().showMessage('3D camera reset.')
