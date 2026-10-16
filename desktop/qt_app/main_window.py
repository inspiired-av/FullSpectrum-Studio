"""Stage 1 PySide6 layout prototype — explicitly not a converter or model viewer.

No engine imports, filesystem writes, 3MF loading, or cached inventory reads.
Existing Tkinter desktop remains the production interface throughout migration.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QAction, QColor, QLinearGradient, QPainter, QPen, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from desktop.app_support import APP_VERSION
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

    def __init__(self):
        super().__init__()
        self.state = ShellState()
        self.setObjectName("qtMainWindow")
        self.setWindowTitle("FullSpectrum Studio — Qt UI Preview")
        self.resize(1440, 880)
        self.setMinimumSize(920, 630)
        self._build()
        self._build_menus()
        self.statusBar().showMessage(
            "UI Stage 1 — no model rendering, color planning, or exporting is active."
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
        h.addWidget(_label("UI prototype · Stage 1", "badge"))
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
        self.bottom_hint = _label("Select a model to prepare the workspace. The existing Tkinter application remains fully functional.", "helpText")
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
        self.tabs.addTab(self._plan_tab(), "Plan")
        self.tabs.addTab(self._empty_tab(
            "Filament Library",
            "Physical filament selection, slot assignments, and protected colors "
            "will be integrated in Stage 2."
        ), "Filaments")
        self.tabs.addTab(self._empty_tab(
            "Results",
            "Conversion summaries, validation reports, and exported projects "
            "will be connected in Stage 4."
        ), "Results")
        outer.addWidget(self.tabs)
        return sidebar

    def _scroll(self, content):
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setWidget(content)
        return scroller

    def _plan_tab(self):
        page = QWidget()
        col = _column(page, margins=(9, 17, 9, 12), spacing=12)
        col.addWidget(_section_heading("Live Forecast"))
        panel = self._section()
        stats = QHBoxLayout(panel)
        stats.setContentsMargins(14, 18, 14, 18)
        self.accuracy = _label("—", "metricBig")
        self.accuracy.setMinimumWidth(55)
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
        empty = self._section()
        e = _column(empty, margins=(12, 14, 12, 14), spacing=3)
        e.addWidget(_label("No palette forecast available", "bodyMuted"))
        e.addWidget(_label("Forecast data will be connected in Stage 4.", "helpText", wrap=True))
        col.addWidget(empty)
        col.addSpacing(8)
        col.addWidget(_section_heading("Color Optimization"))
        col.addWidget(_label("Palette strategy", "smallTitle"))
        strategy = QComboBox()
        strategy.addItems(["Balanced", "Maximum fidelity (recommended)", "Fill palette"])
        strategy.setCurrentIndex(1)
        _disabled(strategy, "Planning controls are connected in Stage 4.")
        col.addWidget(strategy)
        col.addWidget(_label("Maximum palette size", "smallTitle"))
        limit = QSpinBox()
        limit.setRange(2, 32)
        limit.setValue(32)
        limit.setSuffix(" colors")
        _disabled(limit, "Planning controls are connected in Stage 4.")
        col.addWidget(limit)
        col.addWidget(_label("Filament source", "smallTitle"))
        source = QComboBox()
        source.addItems(["Custom", "All Bambu", "My inventory", "CMYKW"])
        _disabled(source, "Filament source selection arrives in Stage 2.")
        col.addWidget(source)
        col.addWidget(_label("Native project template", "smallTitle"))
        col.addWidget(_label("Not connected — template selection arrives in Stage 2.", "helpText", wrap=True))
        col.addStretch(1)
        self.compose_button = QPushButton("Compose Palette")
        self.compose_button.setObjectName("primary")
        _disabled(self.compose_button, "Conversion and export are connected in Stage 4.")
        col.addWidget(self.compose_button)
        col.addWidget(_label("Stage 1 is visual only: no conversion or export is performed.", "helpText", wrap=True))
        return self._scroll(page)

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

    def _open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open 3D Model", "", MODEL_FILE_FILTER)
        if not self.state.select_model(path):
            return
        name = display_filename(path)
        self.project_subtitle.setText(name)
        self.bottom_hint.setText(f"Selected: {name} — the model has not been imported or rendered.")
        self.statusBar().showMessage("Model path selected. Source loading arrives in Stage 3.")

    def _open_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Visual Reference", "", REFERENCE_FILE_FILTER)
        if not self.state.select_reference(path):
            return
        self.statusBar().showMessage(
            "Reference selected: " + display_filename(path) + " — not processed yet."
        )
