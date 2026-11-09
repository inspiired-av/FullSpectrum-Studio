"""Physical-size editor shared by manual and automatic OBJ import calibration.

Only uniform vertex-coordinate scaling is requested here. Existing worker,
forecast and export routing decide when/how a derived OBJ is prepared.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QComboBox,
    QDoubleSpinBox, QPushButton, QDialogButtonBox, QFrame,
)
from desktop.qt_app.model_intended_dimensions import (
    AXES, source_dimensions, scaled_dimensions, uniform_scale,
)
from desktop.qt_app.dimension_precision import (
    INPUT_DECIMALS, compact_input_value, display_source_extent,
    display_result_mm, display_scale_factor,
)


# Scoped selectors leave the application's existing combos/buttons untouched.
_DIMENSIONS_STYLE = """
QFrame#dimensionsSourceCard, QFrame#dimensionsTargetCard {
    background-color: #18212a;
    border: 1px solid #34434f;
    border-radius: 7px;
}
QFrame#dimensionsResultCard {
    background-color: #132b32;
    border: 1px solid #317583;
    border-radius: 7px;
}
QLabel#dimensionsHeading {
    color: #e9f2fa; font-size: 15px; font-weight: 700;
}
QLabel#dimensionsSectionHeading {
    color: #77bdd1; font-size: 10px; font-weight: 700;
}
QLabel#dimensionsUnitWarning {
    color: #eac17b; font-size: 11px;
}
QLabel#dimensionsIntro, QLabel#dimensionsFieldLabel,
QLabel#dimensionsFootnote, QLabel#dimensionsAxisLabel {
    color: #b3bfca; font-size: 11px;
}
QLabel#dimensionsSourceValue {
    color: #e1eaf2; font-size: 13px; font-weight: 600;
}
QLabel#dimensionsResultValue {
    color: #83dfd4; font-size: 15px; font-weight: 700;
}
QLabel#dimensionsScaleFactor {
    color: #9fc6c9; font-size: 11px;
}
"""


class CompactDimensionSpinBox(QDoubleSpinBox):
    """Show variable-length decimal text without reducing numeric precision.

    This subclass is local to intended dimensions. It does not modify global
    QDoubleSpinBox defaults or any application accent/focus styling.
    """

    def textFromValue(self, value):
        return compact_input_value(
            value, decimal_point=self.locale().decimalPoint(),
            decimals=self.decimals(),
        )


class IntendedDimensionsDialog(QDialog):
    def __init__(self, bounds, current_factor=1.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Set Intended Dimensions')
        self.setMinimumWidth(470)
        self.setObjectName('intendedDimensionsDialog')
        self.setStyleSheet(_DIMENSIONS_STYLE)
        self.bounds = tuple(bounds)
        self.reset_requested = False
        self._last_factor = float(current_factor)
        dims = source_dimensions(bounds)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 15, 16, 14)
        outer.setSpacing(11)

        self.heading = QLabel('SET PHYSICAL DIMENSIONS')
        self.heading.setObjectName('dimensionsHeading')
        outer.addWidget(self.heading)

        self.intro = QLabel(
            'OBJ files do not declare physical units. Enter one known dimension in '
            'millimeters to scale X, Y, and Z together.')
        self.intro.setObjectName('dimensionsIntro')
        self.intro.setWordWrap(True)
        outer.addWidget(self.intro)

        source_card = QFrame()
        source_card.setObjectName('dimensionsSourceCard')
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(12, 10, 12, 10)
        source_layout.setSpacing(8)
        source_title = QLabel('ORIGINAL COORDINATES')
        source_title.setObjectName('dimensionsSectionHeading')
        source_layout.addWidget(source_title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.source_axis_values = []
        for axis, extent in zip(AXES, dims):
            col = QVBoxLayout()
            col.setSpacing(2)
            axis_label = QLabel(f'{axis} · source units')
            axis_label.setObjectName('dimensionsAxisLabel')
            value_label = QLabel(display_source_extent(extent))
            value_label.setObjectName('dimensionsSourceValue')
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            col.addWidget(axis_label)
            col.addWidget(value_label)
            row.addLayout(col, 1)
            self.source_axis_values.append(value_label)
        source_layout.addLayout(row)
        warning = QLabel('Units unknown — these numbers are not necessarily millimeters.')
        warning.setWordWrap(True)
        warning.setObjectName('dimensionsUnitWarning')
        source_layout.addWidget(warning)
        outer.addWidget(source_card)

        target_card = QFrame()
        target_card.setObjectName('dimensionsTargetCard')
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(12, 10, 12, 11)
        target_layout.setSpacing(8)
        target_title = QLabel('SET INTENDED SIZE')
        target_title.setObjectName('dimensionsSectionHeading')
        target_layout.addWidget(target_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(10)
        axis_col = QVBoxLayout()
        axis_label = QLabel('Axis')
        axis_label.setObjectName('dimensionsFieldLabel')
        self.axis = QComboBox()
        for value in AXES:
            self.axis.addItem(value, value)
        self.axis.setObjectName('intendedDimensionsAxis')
        self.axis.setMinimumWidth(90)
        # Largest nonzero extent avoids selecting a zero-length axis.
        self.axis.setCurrentIndex(max(range(3), key=lambda i: dims[i]))
        axis_col.addWidget(axis_label)
        axis_col.addWidget(self.axis)
        form_row.addLayout(axis_col, 1)

        size_col = QVBoxLayout()
        size_label = QLabel('Physical dimension')
        size_label.setObjectName('dimensionsFieldLabel')
        self.target = CompactDimensionSpinBox()
        self.target.setObjectName('intendedDimensionsMillimeters')
        self.target.setDecimals(INPUT_DECIMALS)
        self.target.setRange(0.001, 1_000_000.0)
        self.target.setSuffix(' mm')
        self.target.setSingleStep(1.0)
        self.target.setMinimumWidth(170)
        self.target.setValue(min(1_000_000, max(.001, dims[self.axis.currentIndex()] * current_factor)))
        size_col.addWidget(size_label)
        size_col.addWidget(self.target)
        form_row.addLayout(size_col, 3)
        target_layout.addLayout(form_row)
        outer.addWidget(target_card)

        result_card = QFrame()
        result_card.setObjectName('dimensionsResultCard')
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(12, 10, 12, 10)
        result_layout.setSpacing(4)
        result_heading = QLabel('RESULTING DIMENSIONS · X × Y × Z')
        result_heading.setObjectName('dimensionsSectionHeading')
        result_layout.addWidget(result_heading)
        self.result_label = QLabel()
        self.result_label.setObjectName('intendedDimensionsResult')
        self.result_label.setProperty('dimensionRole', 'result')
        # Keep the existing object name for existing Qt regression tests.
        self.result_label.setStyleSheet('color: #83dfd4; font-size: 15px; font-weight: 700;')
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        result_layout.addWidget(self.result_label)
        self.scale_note = QLabel()
        self.scale_note.setObjectName('dimensionsScaleFactor')
        self.scale_note.setWordWrap(True)
        result_layout.addWidget(self.scale_note)
        outer.addWidget(result_card)

        footnote = QLabel(
            'Uniform scaling · A temporary copy is used for preview, forecast and export. '
            'The original OBJ stays unchanged.')
        footnote.setObjectName('dimensionsFootnote')
        footnote.setWordWrap(True)
        outer.addWidget(footnote)

        # Keep button box LAST so the automatic dialog can insert its checkbox
        # directly above the actions without rearranging other widgets.
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                        QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Apply Dimensions')
        self.reset = QPushButton('Restore Original Scale')
        self.reset.setObjectName('resetIntendedDimensions')
        self.reset.setEnabled(abs(current_factor - 1.0) > 1e-10)
        self.buttons.addButton(self.reset, QDialogButtonBox.ButtonRole.ResetRole)
        outer.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.reset.clicked.connect(self._reset)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        self.target.valueChanged.connect(self._refresh)
        self._refresh()

    def _axis_changed(self, *_args):
        # Preserve the uniform factor when choosing a different axis.
        dims = source_dimensions(self.bounds)
        target = dims[self.axis.currentIndex()] * self._last_factor
        self.target.blockSignals(True)
        self.target.setValue(max(.001, min(1_000_000.0, target)))
        self.target.blockSignals(False)
        self._refresh()

    @property
    def scale_factor(self):
        return uniform_scale(self.bounds, self.axis.currentData(), self.target.value())

    def _refresh(self, *_unused):
        try:
            factor = self.scale_factor
            self._last_factor = factor
            dims = scaled_dimensions(self.bounds, factor)
            self.result_label.setText(' × '.join(display_result_mm(d) for d in dims) + ' mm')
            self.scale_note.setText(
                f'Uniform scale ×{display_scale_factor(factor)} · All three axes change together')
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        except ValueError as exc:
            self.result_label.setText(str(exc))
            self.scale_note.setText('Choose a nonzero axis and valid physical dimension.')
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _reset(self):
        self.reset_requested = True
        self.accept()
