"""Automatic OBJ physical-size prompt, with Skip and per-model preference."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialogButtonBox
from desktop.qt_app.model_dimensions_dialog import IntendedDimensionsDialog


class AutoIntendedDimensionsDialog(IntendedDimensionsDialog):
    def __init__(self, bounds, parent=None):
        super().__init__(bounds, current_factor=1.0, parent=parent)
        self.setWindowTitle('Check Model Dimensions')
        self.setObjectName('autoIntendedDimensionsDialog')
        self.heading.setText('CHECK MODEL DIMENSIONS')
        self.intro.setText(
            'This OBJ may be unusually sized. Enter its intended physical size, '
            'or Skip to keep the source coordinates.')
        self.reset.hide()  # Original-scale restoration is in the manual editor.
        self.remember = QCheckBox("Don't show again for this model")
        self.remember.setObjectName('rememberModelDimensionDecision')
        self.remember.setChecked(False)
        self.remember.setToolTip(
            'Remember Skip or the applied size for this unchanged model. '
            'Use File → Set Intended Dimensions… to adjust it later.')
        self.layout().insertWidget(self.layout().count() - 1, self.remember)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Skip')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(False)
        # Unitless values must never be accepted as physical millimeters merely
        # because the dialog was opened. Require an explicit size edit.
        self._explicit_target = False
        self.result_label.setText('Enter a physical dimension to preview the result.')
        self.scale_note.setText('No physical size has been confirmed.')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.target.valueChanged.connect(self._target_edited)
        self.axis.currentIndexChanged.connect(self._axis_changed_auto)

    @property
    def remember_choice(self):
        return self.remember.isChecked()

    def _target_edited(self, *_unused):
        self._explicit_target = True
        self._refresh_apply()

    def _axis_changed_auto(self, *_unused):
        # Merely selecting a different axis is not a physical-size decision.
        if not self._explicit_target:
            self.result_label.setText('Enter a physical dimension to preview the result.')
            self.scale_note.setText('No physical size has been confirmed.')
        self._refresh_apply()

    def _refresh_apply(self):
        valid = True
        try:
            _ = self.scale_factor
        except ValueError:
            valid = False
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self._explicit_target and valid)
