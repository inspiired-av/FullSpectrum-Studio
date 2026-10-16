"""Stage 2A PySide6 plan settings — intentionally not a converter or model viewer.

No optimizer imports or conversion calls. Settings are saved only when requested.
Native template inspection reads metadata but never modifies the source 3MF.
Existing Tkinter desktop remains the production interface throughout migration.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QAction, QColor, QLinearGradient, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSplitter, QTabWidget,
    QLineEdit, QCheckBox, QToolButton, QMessageBox, QFormLayout,
    QVBoxLayout, QWidget,
)

from desktop.app_support import APP_VERSION
from desktop.qt_app.plan_preferences import (
    PlanPreferences, PALETTE_STRATEGIES, FILAMENT_SOURCES, REGIONS,
    PHYSICAL_SLOTS, PLAN_EFFORT, PLANNING_SAMPLES, PALETTE_BASE,
    OUTPUT_SLICERS,
)
from desktop.qt_app.filaments_tab import FilamentsTab
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


class PreviewPlaceholder(QFrame):
    """Noninteractive perspective grid; actual 3D rendering arrives in Stage 3."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewport")
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addStretch(4)
        title = _label("3D Preview", "metric")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        info = _label("Model rendering will be connected in Stage 3.", "bodyMuted")
        info.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(info)
        layout.addStretch(5)
        self._note = _label("Drag-to-orbit, zoom, and paint overlays are not active yet.", "helpText")
        layout.addWidget(self._note)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Decorative background: never misrepresents the loaded 3MF or analysis.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        floor = h * 0.43
        fade = QLinearGradient(0, floor, 0, h)
        fade.setColorAt(0, QColor(25, 36, 43, 42))
        fade.setColorAt(1, QColor(30, 52, 63, 150))
        p.fillRect(QRectF(1, floor, max(0, w - 2), h - floor - 1), fade)
        pen = QPen(QColor(67, 94, 105, 80), 1)
        p.setPen(pen)
        vanishing = QPointF(w * 0.5, floor)
        for i in range(-9, 10):
            p.drawLine(vanishing, QPointF(w * (0.5 + i * .25), h))
        for row in range(1, 11):
            # Quadratic spacing suggests depth without a fake displayed mesh.
            y = floor + (h - floor) * (row / 10) ** 2
            p.drawLine(QPointF(0, y), QPointF(w, y))
        p.end()


class MainWindow(QMainWindow):
    """Mac-inspired workspace shell with functioning file selection and navigation."""

    def __init__(self, settings_path=None):
        super().__init__()
        self.state = ShellState()
        self.plan_preferences = PlanPreferences(settings_path)
        self._loading_plan_ui = False
        self.setObjectName("qtMainWindow")
        self.setWindowTitle("FullSpectrum Studio — Qt UI Preview")
        self.resize(1440, 880)
        self.setMinimumSize(920, 630)
        self._build()
        self._build_menus()
        self.statusBar().showMessage(
            "Qt Stage 2C — Results and activity are available; conversion remains in the Tkinter application."
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
        h.addWidget(_label("UI prototype · Stage 2C", "badge"))
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
        self.preview_mode = QComboBox()
        self.preview_mode.addItems(["Original", "Predicted", "Color Loss", "Wireframe"])
        self.preview_mode.setCurrentText("Predicted")
        _disabled(self.preview_mode, "Live 3D model preview arrives in Stage 3.")
        self.preview_mode.setObjectName("previewMode")
        row.addWidget(self.preview_mode)
        content.addLayout(row)
        self.preview_surface = PreviewPlaceholder()
        content.addWidget(self.preview_surface, stretch=1)
        content.addWidget(_section_heading("Source Palette"))
        self.source_palette_message = _label("No source palette loaded. Source inspection will be connected in Stage 3.", "bodyMuted", wrap=True)
        content.addWidget(self.source_palette_message)
        content.addSpacing(8)
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
        combo = QComboBox()
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
        col.addWidget(_section_heading("Live Forecast"))
        panel = self._section()
        stats = QHBoxLayout(panel)
        stats.setContentsMargins(14, 17, 14, 17)
        self.accuracy = _label("—", "metricBig")
        self.accuracy.setMinimumWidth(50)
        stats.addWidget(self.accuracy)
        detail = QVBoxLayout()
        detail.setSpacing(7)
        for field in ("Estimated accuracy", "Confidence", "Worst match", "Palette"):
            line = QHBoxLayout()
            line.addWidget(_label(field, "bodyMuted"))
            line.addStretch()
            line.addWidget(_label("—", "helpText"))
            detail.addLayout(line)
        stats.addLayout(detail, stretch=1)
        col.addWidget(panel)
        col.addWidget(_section_heading("Expected Palette"))
        forecast = self._section()
        inner = _column(forecast, margins=(12, 12, 12, 12), spacing=3)
        inner.addWidget(_label("No palette forecast available", "bodyMuted"))
        inner.addWidget(_label("The forecast will be connected with the engine in Stage 4.",
                               "helpText", wrap=True))
        col.addWidget(forecast)
        col.addWidget(_section_heading("Color Optimization"))
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
        col.addWidget(_section_heading("Native Project Template"))
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
        self.template_about = QPushButton("About Templates")
        self.template_about.clicked.connect(self._about_templates)
        template_actions.addWidget(self.template_about)
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
        col.addWidget(self.advanced_toggle)
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
        self.auto_forecast = QCheckBox("Automatic forecast (Stage 4)")
        self.auto_forecast.setToolTip("Preference saved now; automatic planning is not active yet.")
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
        col.addWidget(_label("Plan settings are active. Forecast and conversion will be connected in Stage 4.",
                               "helpText", wrap=True))
        self._restore_plan_widgets()
        self._wire_plan_widgets()
        return self._scroll(page)

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
        self.plan_preferences.set(field, value)
        self._refresh_dependent_plan_widgets()
        self._update_plan_dirty_state()

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

    def _about_templates(self):
        QMessageBox.information(self, "About Native Project Templates",
            "Use a blank 3MF project saved from Bambu Studio or OrcaSlicer.\n\n"
            "1. Select the correct printer, nozzle, build plate, and process.\n"
            "2. Configure the intended physical filament presets.\n"
            "3. Remove every model and save the empty project as a .3mf.\n"
            "4. Select that file as the native project template here.\n\n"
            "The template preserves slicer-specific profiles; the filament library controls"
            " color choices. Neither file is modified when selected.")

    def _save_plan_settings(self):
        try:
            target = self.plan_preferences.save()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Unable to Save Settings", str(exc))
            return
        self._update_plan_dirty_state()
        self.statusBar().showMessage("Plan settings saved to the existing FullSpectrum preferences file.")
        self.results_panel.record_event('Plan settings', 'Preferences saved successfully.', 'success')
        self._refresh_results_context()

    def _revert_plan_settings(self):
        self.plan_preferences.revert()
        self._restore_plan_widgets()
        self.filaments_panel.load_options()
        self.statusBar().showMessage("Plan edits discarded; settings reloaded from disk.")
        self.results_panel.record_event('Plan settings', 'Unsaved Plan edits reverted.', 'info')
        self._refresh_results_context()

    def _refresh_results_context(self):
        if not hasattr(self, 'results_panel'):
            return
        self.results_panel.set_context(
            self.state.model_path,
            self.plan_preferences.get('native_project_template'),
            self.plan_preferences.get('output_application'),
            self.plan_preferences.is_dirty,
        )

    def _filament_activity(self, severity, title, message):
        self.results_panel.record_event(title, message, severity)
        self.statusBar().showMessage(message)

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
        for worker in list(self.filaments_panel._workers):
            if worker.isRunning():
                worker.wait()
        super().closeEvent(event)

    def _open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open 3D Model", "", MODEL_FILE_FILTER)
        if not self.state.select_model(path):
            return
        name = display_filename(path)
        self.project_subtitle.setText(name)
        self.filaments_panel.set_model(path)
        self.bottom_hint.setText(f"Selected: {name} — the model has not been imported or rendered.")
        self.statusBar().showMessage("Model path selected. Source loading arrives in Stage 3.")
        self.results_panel.record_event('Model selected', f'{name} selected; not yet imported or rendered.', 'info')
        self._refresh_results_context()

    def _open_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Visual Reference", "", REFERENCE_FILE_FILTER)
        if not self.state.select_reference(path):
            return
        self.statusBar().showMessage(
            "Reference selected: " + display_filename(path) + " — not processed yet."
        )
        self.results_panel.record_event('Reference selected',
                                        display_filename(path) + ' selected; not processed yet.', 'info')
