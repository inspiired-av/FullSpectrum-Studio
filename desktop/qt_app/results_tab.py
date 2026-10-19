"""Results and activity workspace for validated Qt 3MF export."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget, QToolButton,
)

from desktop.qt_app.results_state import event_tail, model_summary, read_existing_report, shorten


def _text(value, kind=None):
    label = QLabel(value)
    label.setWordWrap(True)
    if kind:
        label.setObjectName(kind)
    return label


class ResultsTab(QWidget):
    open_export_requested = Signal()
    show_export_folder_requested = Signal()
    """Validated 3MF exports, progress, reports and current-session activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []
        self._report_path = None
        self._report_content = ''
        self.setObjectName('resultsTab')
        self._build()
        self.set_context('', '', 'Bambu Studio', False)
        self.record_event('Ready', 'Stage 4D-C session initialized. No export has run.', 'info')

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName('resultsScroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        layout.addWidget(_text('CURRENT SESSION', 'sectionTitle'))
        heading = QHBoxLayout()
        self.phase_label = _text('Export not started', 'resultsStatus')
        self.phase_label.setStyleSheet('color: #89d9c3; font-weight: 600;')
        heading.addWidget(self.phase_label)
        heading.addStretch()
        self.stage_label = _text('Stage 4D-C', 'helpText')
        heading.addWidget(self.stage_label)
        layout.addLayout(heading)
        layout.addWidget(_text('Review output settings and export your optimized native 3MF here. Live Forecast remains read-only.', 'bodyMuted'))
        details = QFrame()
        details.setObjectName('section')
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(11, 11, 11, 11)
        detail_layout.setSpacing(7)
        self.fields = {}
        for key, caption in (('model', 'Model'), ('template', 'Native template'),
                             ('slicer', 'Output slicer'), ('settings', 'Plan settings'),
                             ('conversion', 'Conversion'), ('validation', 'Validation')):
            row = QHBoxLayout()
            title = _text(caption, 'bodyMuted')
            title.setMinimumWidth(100)
            row.addWidget(title)
            val = _text('—', 'helpText')
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(val, 1)
            detail_layout.addLayout(row)
            self.fields[key] = val
        self.session_toggle = QToolButton()
        self.session_toggle.setObjectName('exportSessionToggle')
        self.session_toggle.setText('Session details ▸')
        self.session_toggle.setCheckable(True)
        self.session_toggle.setChecked(False)
        self.session_toggle.toggled.connect(
            lambda opened: self.session_toggle.setText('Session details ▾' if opened else 'Session details ▸'))
        self.session_toggle.toggled.connect(details.setVisible)
        layout.addWidget(self.session_toggle)
        details.setVisible(False)
        layout.addWidget(details)

        layout.addWidget(_text('EXPORT SETTINGS', 'sectionTitle'))
        self.export_settings_mount = QWidget()
        self.export_settings_mount.setObjectName('exportSettingsMount')
        self.export_settings_layout = QVBoxLayout(self.export_settings_mount)
        self.export_settings_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.export_settings_mount)
        layout.addWidget(_text('NATIVE 3MF EXPORT', 'sectionTitle'))
        self.export_actions_mount = QWidget()
        self.export_actions_mount.setObjectName('exportActionsMount')
        self.export_actions_layout = QVBoxLayout(self.export_actions_mount)
        self.export_actions_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.export_actions_mount)

        layout.addWidget(_text('VALIDATED OUTPUT', 'sectionTitle'))
        self.export_summary = _text('No validated export in this session.', 'bodyMuted')
        layout.addWidget(self.export_summary)
        output_buttons = QHBoxLayout()
        self.open_export_button = QPushButton('Open in Slicer')
        self.open_export_button.setEnabled(False)
        self.open_export_button.clicked.connect(lambda: self.open_export_requested.emit())
        output_buttons.addWidget(self.open_export_button)
        self.export_folder_button = QPushButton('Show Output Folder')
        self.export_folder_button.setEnabled(False)
        self.export_folder_button.clicked.connect(lambda: self.show_export_folder_requested.emit())
        output_buttons.addWidget(self.export_folder_button)
        layout.addLayout(output_buttons)
        layout.addWidget(_text('CURRENT ACTIVITY', 'sectionTitle'))
        self.activity_label = _text('Ready', 'helpText')
        layout.addWidget(self.activity_label)
        self.activity_progress = QProgressBar()
        self.activity_progress.setObjectName('activityProgress')
        self.activity_progress.setTextVisible(False)
        self.activity_progress.setRange(0, 0)  # Indeterminate only during a real UI job.
        self.activity_progress.setVisible(False)
        self.activity_progress.setMaximumHeight(8)
        layout.addWidget(self.activity_progress)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setObjectName('activityLog')
        self.activity_log.setReadOnly(True)
        self.activity_log.setStyleSheet(
            'QPlainTextEdit {background: #11171c; color: #d5e0e9; '
            'border: 1px solid #35414d; border-radius: 7px; '
            'font-family: Consolas, monospace; font-size: 11px; padding: 7px;}'
        )
        self.activity_log.setMinimumHeight(130)
        self.activity_log.setMaximumHeight(175)
        self.activity_toggle = QToolButton()
        self.activity_toggle.setObjectName('exportActivityToggle')
        self.activity_toggle.setText('Activity log ▸')
        self.activity_toggle.setCheckable(True)
        self.activity_toggle.setChecked(False)
        self.activity_toggle.toggled.connect(
            lambda opened: self.activity_toggle.setText('Activity log ▾' if opened else 'Activity log ▸'))
        self.activity_toggle.toggled.connect(self.activity_log.setVisible)
        layout.addWidget(self.activity_toggle)
        self.activity_log.setVisible(False)
        layout.addWidget(self.activity_log)
        event_buttons = QHBoxLayout()
        clear = QPushButton('Clear Activity')
        clear.clicked.connect(self.clear_events)
        event_buttons.addWidget(clear)
        copy = QPushButton('Copy Activity')
        copy.clicked.connect(self.copy_activity)
        event_buttons.addWidget(copy)
        layout.addLayout(event_buttons)

        layout.addWidget(_text('EXISTING / GENERATED REPORT', 'sectionTitle'))
        layout.addWidget(_text('Open an existing FullSpectrum or slicer validation report. '
                               'You can also inspect the report generated by a successful export.',
                               'bodyMuted'))
        report_buttons = QHBoxLayout()
        self.open_report_button = QPushButton('Open Report…')
        self.open_report_button.clicked.connect(self.browse_report)
        report_buttons.addWidget(self.open_report_button)
        self.copy_report_button = QPushButton('Copy Report')
        self.copy_report_button.setEnabled(False)
        self.copy_report_button.clicked.connect(self.copy_report)
        report_buttons.addWidget(self.copy_report_button)
        self.clear_report_button = QPushButton('Clear')
        self.clear_report_button.setEnabled(False)
        self.clear_report_button.clicked.connect(self.clear_report)
        report_buttons.addWidget(self.clear_report_button)
        layout.addLayout(report_buttons)
        self.report_hint = _text('No report selected.', 'bodyMuted')
        layout.addWidget(self.report_hint)
        self.report_view = QPlainTextEdit()
        self.report_view.setObjectName('reportViewer')
        self.report_view.setReadOnly(True)
        self.report_view.setStyleSheet(
            'QPlainTextEdit {background: #11171c; color: #d5e0e9; '
            'border: 1px solid #35414d; border-radius: 7px; '
            'font-family: Consolas, monospace; font-size: 11px; padding: 7px;}'
        )
        self.report_view.setPlaceholderText('Select an existing report to read it here.')
        self.report_view.setMinimumHeight(220)
        self.report_toggle = QToolButton()
        self.report_toggle.setObjectName('exportReportToggle')
        self.report_toggle.setText('Report viewer ▸')
        self.report_toggle.setCheckable(True)
        self.report_toggle.setChecked(False)
        self.report_toggle.toggled.connect(
            lambda opened: self.report_toggle.setText('Report viewer ▾' if opened else 'Report viewer ▸'))
        self.report_toggle.toggled.connect(self.report_view.setVisible)
        layout.addWidget(self.report_toggle)
        self.report_view.setVisible(False)
        layout.addWidget(self.report_view)
        layout.addWidget(_text('Engine validation checks structure, paint mapping and palette reconstruction. Confirm printer settings and slice in your chosen slicer before printing.', 'helpText'))
        layout.addStretch(1)

    def attach_export_panels(self, settings, actions):
        """Mount existing MainWindow widgets without duplicating preferences."""
        self.export_settings_layout.addWidget(settings)
        self.export_actions_layout.addWidget(actions)

    def set_context(self, model_path, template_path, slicer, dirty=False):
        for key, value in model_summary(model_path, template_path, slicer, dirty).items():
            self.fields[key].setText(value)
            self.fields[key].setToolTip(str(value))

    def set_export_result(self, result):
        '''Only call after the engine returned a fully validated result.'''
        output = Path(result['output'])
        self.fields['conversion'].setText(shorten(output.name, 70))
        self.fields['conversion'].setToolTip(str(output))
        self.fields['validation'].setText('Engine validated · 3MF archive checked')
        self.phase_label.setText('Validated native 3MF saved')
        self.export_summary.setText(f'{output.name} · {result.get("slicer", "Selected slicer")}')
        self.export_summary.setToolTip(str(output))
        self.open_export_button.setEnabled(True)
        self.export_folder_button.setEnabled(True)

    def record_event(self, title, detail, severity='info'):
        """Record a real UI event; callers must only emit success on completion."""
        if severity not in ('info', 'success', 'warning', 'error', 'busy'):
            severity = 'info'
        stamp = datetime.now().strftime('%H:%M:%S')
        entry = f'[{stamp}] {severity.upper()}: {shorten(title, 60)} — {shorten(detail, 180)}'
        self._events = event_tail([*self._events, entry])
        self.activity_log.setPlainText('\n'.join(self._events))
        bar = self.activity_log.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.activity_label.setText(shorten(detail, 100))
        self.activity_progress.setVisible(severity == 'busy')
        color = {'success':'#89d9c3', 'warning':'#f1b66d', 'error':'#f0929e',
                 'busy':'#67bfd1', 'info':'#b5c3ce'}[severity]
        self.activity_label.setStyleSheet(f'color: {color};')

    def clear_events(self):
        self._events = []
        self.activity_log.clear()
        self.activity_label.setText('Activity cleared')
        self.activity_progress.hide()

    def copy_activity(self):
        if self._events:
            QApplication.clipboard().setText('\n'.join(self._events))

    def browse_report(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Existing Report', '',
            'Text reports (*.txt *.md *.log *.csv)')
        if path:
            self.load_report(path)

    def load_report(self, path):
        """Exposed for GUI tests; an invalid file must not replace the last report."""
        try:
            content = read_existing_report(path)
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Unable to Open Report', str(exc))
            self.record_event('Report unavailable', str(exc), 'warning')
            return False
        self._report_path = Path(path)
        self._report_content = content
        self.report_view.setPlainText(content)
        self.report_toggle.setChecked(True)
        self.report_hint.setText(f'Viewing previously saved report: {shorten(self._report_path.name)}')
        self.report_hint.setToolTip(str(self._report_path))
        self.copy_report_button.setEnabled(True)
        self.clear_report_button.setEnabled(True)
        self.record_event('Report opened', f'Existing report {self._report_path.name} loaded (view-only)', 'success')
        return True

    def clear_report(self):
        self._report_path = None
        self._report_content = ''
        self.report_view.clear()
        self.report_hint.setText('No report selected.')
        self.copy_report_button.setEnabled(False)
        self.clear_report_button.setEnabled(False)

    def copy_report(self):
        if self._report_path is not None:
            QApplication.clipboard().setText(self._report_content)
