"""The Qt shell's self-contained dark theme: no global Windows theme changes."""
from __future__ import annotations

# Text, control labels, and sections follow the Mac shell's title-case pattern.
# A shared theme can later be used by the full integrated Qt frontend.
COLORS = {
    "background": "#0f1216",
    "panel": "#171b20",
    "raised": "#20262d",
    "viewport": "#0b0e12",
    "border": "#303943",
    "text": "#edf1f5",
    "muted": "#9faebc",
    "accent": "#67bfd1",
    "primary": "#397cf2",
    "positive": "#64caa2",
}

STYLE = """
QMainWindow, QWidget#root { background: #0f1216; color: #edf1f5; }
QWidget { font-family: 'Segoe UI', 'Arial', sans-serif; font-size: 12px; color: #edf1f5; }
QFrame#header, QFrame#bottomBar { background: #11151a; }
QFrame#sidebar, QFrame#previewCard, QFrame#section, QFrame#emptyPage {
    background: #171b20; border: 1px solid #303943; border-radius: 10px;
}
QFrame#viewport { background: #0b0e12; border: 1px solid #28323b; border-radius: 9px; }
QLabel#brand { font-size: 19px; font-weight: 700; color: #f1f4f7; }
QLabel#smallTitle { font-size: 11px; font-weight: 700; color: #aab6c1; }
QLabel#sectionTitle { font-size: 11px; font-weight: 700; color: #67bfd1; }
QLabel#bodyMuted, QLabel#helpText, QLabel#subtitle { color: #9faebc; }
/* Template metadata is verified (teal), compatibility warnings are amber.
   Errors are red; empty/no-selection state stays muted. */
QLabel#templateStatusReady { color: #89d9c3; font-weight: 600; }
QLabel#templateWarning { color: #f1b66d; }
QLabel#templateStatusError { color: #f0929e; }
QLabel#templateStatusEmpty { color: #9faebc; }
QLabel#metric { font-size: 16px; font-weight: 700; color: #f1f4f7; }
QLabel#metricBig { font-size: 29px; font-weight: 700; color: #a3b7c5; }
QLabel#badge { color: #8bd4b8; background: #1c3431; border: 1px solid #355850;
    border-radius: 8px; padding: 7px 11px; font-weight: 600; }
QPushButton, QToolButton { background: #232a32; border: 1px solid #3a434d;
    border-radius: 7px; padding: 8px 12px; min-height: 16px; }
QPushButton:hover, QToolButton:hover { background: #313b46; border-color: #65bfd0; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #67bfd1; }
QPushButton:disabled, QToolButton:disabled { color: #788695;
    background: #1e242a; border-color: #333a42; }
QPushButton#primary { background: #397cf2; border-color: #397cf2;
    font-weight: 600; color: white; }
QPushButton#primary:hover { background: #538df5; }
QPushButton#primary:disabled { background: #273c5d; border-color: #273c5d; color: #8da5c9; }
QComboBox, QSpinBox { background: #242b33; border: 1px solid #3a434d;
    border-radius: 7px; padding: 7px 10px; min-height: 18px; }
QComboBox:disabled, QSpinBox:disabled { color: #9caab6; background: #1c232a; }
/* Fully style the slider rather than leaving unstyled Fusion/Windows track
   regions. Explicit add-page prevents a system-colored grey rectangle. */
QSlider#qualityBiasSlider {
    background: transparent; border: none;
    min-height: 26px; max-height: 26px;
}
QSlider#qualityBiasSlider::groove:horizontal {
    height: 6px; background: #303b45; border: none; border-radius: 3px;
}
QSlider#qualityBiasSlider::sub-page:horizontal {
    background: #67bfd1; border: none; border-radius: 3px;
}
QSlider#qualityBiasSlider::add-page:horizontal {
    background: #303b45; border: none; border-radius: 3px;
}
QSlider#qualityBiasSlider::handle:horizontal {
    background: #e6f0f5; border: 1px solid #5694a3;
    width: 14px; margin: -6px 0; border-radius: 8px;
}
/* Qt subcontrol states come AFTER the subcontrol selector. The previous
   :disabled::sub-page order could leave the active cyan fill visible. */
QSlider#qualityBiasSlider::groove:horizontal:disabled {
    background: #293038;
}
QSlider#qualityBiasSlider::sub-page:horizontal:disabled {
    background: #3a4650;
}
QSlider#qualityBiasSlider::add-page:horizontal:disabled {
    background: #293038;
}
QSlider#qualityBiasSlider::handle:horizontal:disabled {
    background: #65717c; border-color: #46535e;
}
QLabel#qualityBiasValue { font-weight: 600; color: #b5c9d4; }
QLabel#qualityBiasValue:disabled { color: #6f7e8b; }
QLabel#qualityBiasAuto {
    color: #94d9c2; background: #1c3530; border: 1px solid #376053;
    border-radius: 5px; padding: 3px 6px; font-size: 10px;
    font-weight: 700;
}
QLineEdit { background: #242b33; color: #edf1f5; border: 1px solid #3a434d;
    border-radius: 7px; padding: 7px 10px; min-height: 18px; }
QLineEdit:read-only { background: #1b2229; color: #cbd8e2; }
QLineEdit:focus { border: 1px solid #67bfd1; }
QCheckBox { color: #d6e0e9; spacing: 7px; padding: 3px 0; }
QToolButton#advancedToggle { text-align: left; background: #1c232a; }
QToolButton#advancedToggle:checked { background: #25323a; border-color: #5c8496; }
QTableWidget#filamentTable, QTableWidget#solidColorTable {
    background: #1b2229; alternate-background-color: #202934;
    color: #e8f0f6; border: 1px solid #35414d; border-radius: 7px;
    gridline-color: #35414d; selection-background-color: #294b67;
    selection-color: #f1f7fa;
}
QTableWidget#filamentTable::item, QTableWidget#solidColorTable::item {
    padding: 4px 6px;
}
QHeaderView::section {
    background: #242d36; color: #b8cbd8;
    border: 0; border-bottom: 1px solid #3b4854;
    padding: 6px 7px; font-size: 11px; font-weight: 600;
}
QComboBox QAbstractItemView { background: #252b32; color: #edf1f5;
    selection-background-color: #397cf2; }
QTabWidget::pane { border: 0; background: #171b20; }
QTabBar::tab { background: transparent; color: #9facb8; padding: 10px 21px;
    border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #eef3f8; border-bottom: 2px solid #397cf2; }
QTabBar::tab:hover:!selected { color: #e1eaf2; }
QSplitter::handle { background: #0f1216; width: 8px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #171b20; width: 9px; }
QScrollBar::handle:vertical { background: #44515e; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #11151a; color: #9faebc; border-top: 1px solid #303943; }
QMenuBar { background: #11151a; }
QMenu { background: #242b33; border: 1px solid #45515f; }
QMenu::item:selected { background: #315b95; }
"""


def apply_theme(app):
    # Fusion gives the UI one consistent baseline across Windows and Linux.
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
