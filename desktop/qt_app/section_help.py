"""Concise contextual help for relevant Qt sections, with a painted circular ? glyph.

The short string is the tooltip; the click dialog supplies additional guidance.
Only trusted, repository-maintained external documentation links are included.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QToolButton, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)


@dataclass(frozen=True)
class HelpTopic:
    title: str
    summary: str
    details: str


README_CUSTOM = ('https://github.com/inspiired-av/FullSpectrum-Studio/'
                 'blob/feat/qt-ui-redesign/README.md#custom-brands')
LIBRARY_EXAMPLE = ('https://github.com/inspiired-av/FullSpectrum-Studio/'
                   'blob/feat/qt-ui-redesign/examples/custom-palette.example.json')

TOPICS = {
    'preview_modes': HelpTopic(
        'Model Preview Modes',
        'Compare the original, forecast prediction, color difference, and anchor influence.',
        """**Original** shows the source model and its existing colors. **Predicted** shows the engine's planned colors before export; a manually opened predicted OBJ is labeled separately.

**Color Loss** maps estimated color difference (ΔE) across the model: green is low (ΔE ≤ 2), yellow is moderate (2–6), and orange-red indicates higher error (> 6). The key appears inside the viewport when this mode is selected. These are estimates, not calibrated measurements.

**Anchor Influence** groups regions by an associated physical filament anchor. For mixed recipes, the engine currently labels the first contributing anchor; it is **not** a proportional contribution map. Its colors are category markers, **not** the filament's real color or ΔE.

**Wireframe** displays the original geometry as an edge mesh. Orbit, pan, zoom and Reset View work in every mode. Predicted analysis modes require a successful forecast; obsolete forecasts remain marked **OUTDATED** until refreshed."""),
    'live_forecast': HelpTopic(
        'Live Forecast',
        'Predicted accuracy, confidence, and color error before slicing.',
        """**Accuracy** estimates color fidelity. **Confidence** indicates how reliable the estimate is. **Worst visible match** compares the target and predicted color with the largest reported ΔE; lower ΔE means a closer match.

**Refresh Forecast** recalculates without exporting. Automatic forecast can be enabled in Advanced Settings. When it is disabled, changed settings retain the previous prediction, labeled **Outdated**, until refreshed.

These are software estimates, **not** measured print accuracy, purge amounts or slicer validation."""),
    'expected_palette': HelpTopic(
        'Expected Palette',
        'The output colors selected by the current forecast.',
        """The palette combines **physical filament slots** and **mixed recipe slots**. These are predicted output colors, not the source swatches below the 3D viewer.

Use **Optimization Details** for the chosen physical filaments and mixer proportions. If planning settings change, an outdated palette remains visible for comparison until the next successful forecast. Printed appearance also depends on material and slicing."""),
    'color_optimization': HelpTopic(
        'Color Optimization',
        'Balance color fidelity, recipe count and maximum palette size.',
        """**Maximum fidelity** favors accurate matches; **Balanced** limits unnecessary mixtures; **Fill palette** attempts to use more available slots.

**Maximum palette size** counts both physical and mixed slots (up to 32). Too few slots for required physical filaments is invalid. Use **Manage Filament Colors…** to enable candidates or pin physical colors. Pinning can change the entire result, so refresh after changes when automatic forecast is off."""),
    'native_project_template': HelpTopic(
        'Native Project Template',
        'Use an empty slicer 3MF containing your printer and process presets.',
        """For later native export, save an **empty project** in Bambu Studio or OrcaSlicer:

1. Select the intended printer, nozzle, plate, process and physical filament presets.
2. **Remove every model** from the build plate.
3. Save as a **3MF project**, then choose it here with **Browse…**.

This supplies slicer profiles; it is not the source model. Confirm the detected printer/nozzle and any compatibility warnings. Conversion and slicer launch remain part of a later stage."""),
    'advanced_settings': HelpTopic(
        'Advanced Settings',
        'Adjust planning effort, physical slots, quality and refresh.',
        """**Planning effort** controls search depth. **Planning sample** determines which source representation is weighted. **Physical slots** limits real materials; **Maximum palette size** separately limits physical plus mixed output colors.

**Smart quality** picks the quality/waste balance automatically; turn it off to use the slider. **Automatic forecast** refreshes after valid edits. Output slicer preferences are saved now; exporting and launching the slicer are later-stage features."""),
    'filament_source': HelpTopic(
        'Filament Source',
        'Use Bambu inventory/catalog colors or load your own JSON filament library.',
        """Choose **My inventory**, **Bambu** materials, **CMYKW**, or **Custom filament library**. Catalog availability is not live store stock.

### Create a custom filament library

1. Open the [Custom Brands section of the README]({readme}).
2. Copy the [custom-palette.example.json example]({example}) and save a local **.json** file.
3. Add one entry per physical filament inside the `filaments` array, using `name`, `brand`, `series` and a six-digit `color` (such as `#F4F1EA`). Include at least two distinct colors for planning.
4. Choose **Custom filament library**, select your JSON with **Browse…**, then click **Load / Refresh**.
5. Enable or pin candidates as needed and click **Save Filaments** to persist your choices.

Loading the file does not upload it to a server. Changes to its contents require refreshing the library.""".format(readme=README_CUSTOM, example=LIBRARY_EXAMPLE)),
    'filament_colors': HelpTopic(
        'Filament Colors',
        'Enable candidates; pin the physical filaments that must be used.',
        """**Use** makes a color available to the optimizer. **Pin** requires that physical color in the plan. Pinning also enables the color; disabling removes its pin. The pin limit follows **Physical slots**.

Search by name, series or HEX. Search filters the table only; it does not change selections. Valid edits affect the current forecast immediately, but **Save Filaments** is still required to save those choices to disk. **Revert** restores saved settings."""),
    'protect_solid_colors': HelpTopic(
        'Protect Solid Colors',
        'Assign exact source colors to specific physical filaments.',
        """For supported standard material-colored 3MF files, choose one or more source colors in the automatically populated table, select an enabled filament, then click **Protect Selected**. **Remove Protection** clears an assignment.

The source palette shares the selection. Protections apply to the selected model, not every future model. Native painted faces may be inspectable but not safely assignable. Visual tint does not change or export a project."""),
}


def circle_bounds(width: float, height: float, margin: float = 1.5):
    """A square outline centered inside any widget geometry (even stretched).

    Some Windows Qt styles can enlarge the *button* vertically despite the
    requested fixed widget size. Its outline must never become an ellipse.
    Returns (center_x, center_y, radius) in logical widget coordinates.
    """
    radius = max(0.0, (min(width, height) - 2 * margin) / 2.0)
    return width / 2.0, height / 2.0, radius


class SectionHelpButton(QToolButton):
    """A genuinely circular control: QPainter draws both outline and '?' glyph.

    We intentionally don't rely on the global QPushButton/QToolButton stylesheet:
    Fusion/Windows may clip a small glyph when it inherits large padding.
    """

    def __init__(self, topic_key: str, parent=None):
        super().__init__(parent)
        if topic_key not in TOPICS:
            raise ValueError(f'Unknown help topic: {topic_key}')
        self.topic_key = topic_key
        topic = TOPICS[topic_key]
        self.setText('?')  # Accessibility / UI tests; glyph is painted directly.
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setObjectName('sectionHelpButton')
        self.setAccessibleName(f'Help: {topic.title}')
        self.setAccessibleDescription(topic.summary)
        self.setToolTip(topic.summary)
        self.setFixedSize(20, 20)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Neutralize any broad QToolButton padding/min-width rules from the
        # app stylesheet, without relying on border-radius to draw the circle.
        self.setStyleSheet(
            'QToolButton#sectionHelpButton {'
            'background: transparent; border: none; padding: 0px; margin: 0px; '
            'min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;'
            '}'
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self.show_help)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        focused = self.hasFocus()
        hover = self.underMouse()
        center_x, center_y, radius = circle_bounds(self.width(), self.height())
        painter.setPen(QPen(QColor('#81dae8' if focused else '#507887'), 1.3))
        painter.setBrush(QColor('#2c4b59' if hover else '#1b303b'))
        # drawEllipse(center, rx, ry) uses precisely the same radius on BOTH
        # axes; drawing to a widget-sized rectangle caused ovals on Windows.
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)
        font = QFont('Segoe UI', 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor('#f6fcff' if hover else '#a7eaf4'))
        # The letter is painted over the whole circle, not inside a padded
        # QPushButton content rect, so the question mark remains visible.
        # Keep the glyph centered on the circle, not stretched with the
        # widget's bounding rectangle when Windows styles alter its height.
        painter.drawText(QRectF(center_x-radius, center_y-radius-0.5,
                                2*radius, 2*radius+1.0),
                         Qt.AlignmentFlag.AlignCenter, '?')
        painter.end()

    def create_dialog(self) -> QDialog:
        topic = TOPICS[self.topic_key]
        dialog = QDialog(self.window())
        dialog.setObjectName('sectionHelpDialog')
        dialog.setWindowTitle(f'{topic.title} — FullSpectrum Help')
        dialog.setMinimumSize(440, 300)
        dialog.resize(560, 400)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        heading = QLabel(topic.title)
        heading.setObjectName('helpDialogTitle')
        heading.setStyleSheet('font-size: 18px; font-weight: 650;')
        layout.addWidget(heading)
        summary = QLabel(topic.summary)
        summary.setWordWrap(True)
        summary.setObjectName('helpDialogSummary')
        layout.addWidget(summary)
        browser = QTextBrowser(dialog)
        browser.setObjectName('helpDialogContent')
        browser.setMarkdown(topic.details)
        # The only external URLs in help topics are static README/example links.
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet('QTextBrowser {background: #141c23; color: #d5e3ec; '
                              'border: 1px solid #364957; border-radius: 6px; padding: 10px;}')
        browser.setReadOnly(True)
        layout.addWidget(browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog

    def show_help(self):
        self.create_dialog().exec()


def help_heading(topic_key: str, label: str, *, title_object='sectionTitle', parent=None) -> QWidget:
    frame = QWidget(parent)
    frame.setObjectName('sectionHelpHeading')
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(5)
    label_widget = QLabel(label)
    label_widget.setObjectName(title_object)
    row.addWidget(label_widget, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(SectionHelpButton(topic_key, frame), 0, Qt.AlignmentFlag.AlignVCenter)
    row.addStretch(1)
    return frame
