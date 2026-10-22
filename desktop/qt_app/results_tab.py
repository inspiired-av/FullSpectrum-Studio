"""Results and activity workspace for validated Qt 3MF export."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget, QToolButton, QStackedWidget, QGridLayout,
)

from desktop.qt_app.results_state import event_tail, model_summary, read_existing_report, shorten
from desktop.qt_app.export_ui_icons import export_icon, compact_icon_button


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
        self.record_event('Ready', 'Export session initialized.', 'info')

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName('resultsScroll')
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.content_scroll)
        page = QWidget()
        self.content_scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 13, 12, 12)
        layout.setSpacing(9)

        # One compact, always-visible session status row. Full technical details
        # are a disclosure next to the status rather than a full-width button.
        status = QHBoxLayout()
        self.status_icon = QLabel()
        self.status_icon.setObjectName('exportStatusIcon')
        self.status_icon.setPixmap(export_icon('info', '#90a5b4').pixmap(17, 17))
        self.status_icon.setFixedSize(18, 18)
        status.addWidget(self.status_icon)
        self.phase_label = _text('Export not started', 'resultsStatus')
        self.phase_label.setStyleSheet('color: #b5c3ce; font-weight: 600;')
        status.addWidget(self.phase_label, 1)
        self.stage_label = _text('', 'helpText')
        self.stage_label.hide()  # Development marker is not export metadata.
        self.session_toggle = QToolButton()
        self.session_toggle.setObjectName('exportSessionToggle')
        compact_icon_button(self.session_toggle, 'info', 'Show session details', side=28)
        self.session_toggle.setToolTip('Show or hide export session details')
        self.session_toggle.setAccessibleName('Session details')
        self.session_toggle.setCheckable(True)
        status.addWidget(self.session_toggle)
        layout.addLayout(status)

        details = QFrame()
        details.setObjectName('section')
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(8, 8, 8, 8)
        detail_layout.setSpacing(5)
        self.fields = {}
        for key, caption in (('model', 'Model'), ('template', 'Native template'),
                             ('slicer', 'Output slicer'), ('settings', 'Plan settings'),
                             ('conversion', 'Conversion'), ('validation', 'Validation')):
            row = QHBoxLayout()
            title = _text(caption, 'bodyMuted')
            title.setMinimumWidth(95)
            row.addWidget(title)
            val = _text('—', 'helpText')
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(val, 1)
            detail_layout.addLayout(row)
            self.fields[key] = val
        details.setVisible(False)
        self.session_toggle.toggled.connect(details.setVisible)
        layout.addWidget(details)

        # The validated artifact gets its own file glyph, not an anonymous
        # inline filename in the status row. Hide the whole row until success.
        self.export_summary_row = QWidget()
        artifact_row = QHBoxLayout(self.export_summary_row)
        artifact_row.setContentsMargins(0, 0, 0, 0)
        artifact_row.setSpacing(7)
        self.export_file_icon = QLabel()
        self.export_file_icon.setObjectName('exportFileIcon')
        self.export_file_icon.setPixmap(export_icon('file', '#89d9c3').pixmap(19, 19))
        self.export_file_icon.setFixedSize(20, 20)
        artifact_row.addWidget(self.export_file_icon)
        self.export_summary = _text('', 'bodyMuted')
        self.export_summary.setObjectName('exportSummary')
        self.export_summary.setVisible(False)
        artifact_row.addWidget(self.export_summary, 1)
        layout.addWidget(self.export_summary_row)
        self.export_summary_row.hide()

        self.export_settings_mount = QWidget()
        self.export_settings_mount.setObjectName('exportSettingsMount')
        self.export_settings_layout = QVBoxLayout(self.export_settings_mount)
        self.export_settings_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.export_settings_mount)

        # Keep export as the sole full-width primary action.
        self.export_actions_mount = QWidget()
        self.export_actions_mount.setObjectName('exportActionsMount')
        self.export_actions_layout = QVBoxLayout(self.export_actions_mount)
        self.export_actions_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.export_actions_mount)

        self.validated_output_panel = QWidget()
        validated = QVBoxLayout(self.validated_output_panel)
        validated.setContentsMargins(0, 0, 0, 0)
        validated.setSpacing(5)
        action_row = QHBoxLayout()
        self.open_export_button = QPushButton('Open in Slicer')
        self.open_export_button.setIcon(export_icon('open'))
        self.open_export_button.setMinimumHeight(34)
        self.open_export_button.setEnabled(False)
        self.open_export_button.clicked.connect(lambda: self.open_export_requested.emit())
        action_row.addWidget(self.open_export_button, 1)
        self.export_folder_button = QPushButton('Show Output Folder')
        self.export_folder_button.setIcon(export_icon('folder'))
        self.export_folder_button.setMinimumHeight(34)
        self.export_folder_button.setEnabled(False)
        self.export_folder_button.clicked.connect(lambda: self.show_export_folder_requested.emit())
        action_row.addWidget(self.export_folder_button, 1)
        validated.addLayout(action_row)
        layout.addWidget(self.validated_output_panel)
        self.validated_output_panel.hide()

        # Single shared, scrollable diagnostics viewer with in-header actions.
        # Center the mode switch in the VISIBLE sidebar viewport, not an
        # oversized scroll-page layout (which shifts it at narrow widths).
        self.diagnostics_header = QWidget()
        self.diagnostics_header.setObjectName('exportDiagnosticsHeader')
        self.diagnostics_header.setMinimumHeight(38)
        diagnostics_head = QHBoxLayout(self.diagnostics_header)
        diagnostics_head.setContentsMargins(0, 0, 0, 0)
        diagnostics_head.setSpacing(6)
        diagnostics_left = QWidget()
        diagnostics_left_row = QHBoxLayout(diagnostics_left)
        diagnostics_left_row.setContentsMargins(0, 0, 0, 0)
        diagnostics_left_row.addWidget(_text('DIAGNOSTICS', 'sectionTitle'))
        diagnostics_head.addWidget(diagnostics_left)
        diagnostics_head.addStretch(1)
        self.diagnostics_mode_group = QWidget(self)
        diagnostic_choices = QHBoxLayout(self.diagnostics_mode_group)
        diagnostic_choices.setContentsMargins(0, 0, 0, 0)
        diagnostic_choices.setSpacing(4)
        self.activity_toggle = QToolButton()
        self.activity_toggle.setObjectName('exportActivityToggle')
        self.activity_toggle.setText('Activity')
        self.activity_toggle.setMinimumHeight(32)
        self.activity_toggle.setMinimumWidth(58)
        self.activity_toggle.setCheckable(True)
        self.activity_toggle.setChecked(True)
        self.activity_toggle.setAutoExclusive(True)
        self.activity_toggle.setToolTip('Show activity log')
        diagnostic_choices.addWidget(self.activity_toggle)
        self.report_toggle = QToolButton()
        self.report_toggle.setObjectName('exportReportToggle')
        self.report_toggle.setText('Report')
        self.report_toggle.setMinimumHeight(32)
        self.report_toggle.setMinimumWidth(58)
        self.report_toggle.setCheckable(True)
        self.report_toggle.setAutoExclusive(True)
        self.report_toggle.setToolTip('Show saved or imported report')
        diagnostic_choices.addWidget(self.report_toggle)
        for choice in (self.activity_toggle, self.report_toggle):
            choice.setStyleSheet(
                'QToolButton { background-color: #202b35; color: #b7c7d5; '
                'border: 1px solid #384653; border-radius: 4px; padding: 3px 6px; }'
                'QToolButton:checked { background-color: #244f60; color: #f1faff; '
                'border-color: #69b7cc; font-weight: 600; }'
            )
        self.diagnostics_mode_group.adjustSize()
        self.diagnostics_mode_group.raise_()
        self.diagnostics_tools = QWidget()
        diagnostic_actions = QHBoxLayout(self.diagnostics_tools)
        diagnostic_actions.setContentsMargins(0, 0, 0, 0)
        diagnostic_actions.setSpacing(4)
        diagnostic_actions.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.open_report_button = QPushButton()
        compact_icon_button(self.open_report_button, 'folder', 'Open existing report', side=32)
        self.open_report_button.clicked.connect(self.browse_report)
        diagnostic_actions.addWidget(self.open_report_button)
        self.copy_activity_button = QToolButton()
        compact_icon_button(self.copy_activity_button, 'copy', 'Copy activity', side=32)
        self.copy_activity_button.setAccessibleName('Copy activity')
        self.copy_activity_button.setToolTip('Copy activity to clipboard')
        self.copy_activity_button.clicked.connect(self.copy_activity)
        diagnostic_actions.addWidget(self.copy_activity_button)
        self.clear_activity_button = QToolButton()
        compact_icon_button(self.clear_activity_button, 'trash', 'Clear activity', side=32)
        self.clear_activity_button.setAccessibleName('Clear activity')
        self.clear_activity_button.setToolTip('Clear activity log')
        self.clear_activity_button.clicked.connect(self.clear_events)
        diagnostic_actions.addWidget(self.clear_activity_button)
        self.copy_report_button = QToolButton()
        compact_icon_button(self.copy_report_button, 'copy', 'Copy report', side=32)
        self.copy_report_button.setToolTip('Copy report')
        self.copy_report_button.setAccessibleName('Copy report')
        self.copy_report_button.setEnabled(False)
        self.copy_report_button.clicked.connect(self.copy_report)
        diagnostic_actions.addWidget(self.copy_report_button)
        self.clear_report_button = QToolButton()
        compact_icon_button(self.clear_report_button, 'trash', 'Clear report', side=32)
        self.clear_report_button.setToolTip('Clear report')
        self.clear_report_button.setAccessibleName('Clear report')
        self.clear_report_button.setEnabled(False)
        self.clear_report_button.clicked.connect(self.clear_report)
        diagnostic_actions.addWidget(self.clear_report_button)
        self.diagnostics_collapse = QToolButton()
        self.diagnostics_collapse.setObjectName('diagnosticsCollapse')
        compact_icon_button(self.diagnostics_collapse, 'down', 'Collapse diagnostics', side=32)
        self.diagnostics_collapse.setToolTip('Collapse diagnostics')
        self.diagnostics_collapse.setCheckable(True)
        self.diagnostics_collapse.setChecked(True)
        diagnostic_actions.addWidget(self.diagnostics_collapse)
        diagnostics_head.addWidget(self.diagnostics_tools)
        layout.addWidget(self.diagnostics_header)
        self.diagnostics_header.installEventFilter(self)
        self.content_scroll.verticalScrollBar().valueChanged.connect(
            lambda _value: self._center_diagnostics_switch())
        self.installEventFilter(self)

        self.activity_label = _text('Ready', 'helpText')
        self.activity_label.hide()  # Status belongs to session state, not a separate row.
        self.activity_progress = QProgressBar()
        self.activity_progress.setObjectName('activityProgress')
        self.activity_progress.setTextVisible(False)
        self.activity_progress.setRange(0, 0)
        self.activity_progress.setMaximumHeight(5)
        self.activity_progress.setVisible(False)
        layout.addWidget(self.activity_progress)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setObjectName('activityLog')
        self.activity_log.setReadOnly(True)
        self.report_view = QPlainTextEdit()
        self.report_view.setObjectName('reportViewer')
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText('Open a report to inspect it here.')
        for viewer in (self.activity_log, self.report_view):
            viewer.setStyleSheet(
                'QPlainTextEdit {background: #11171c; color: #d5e0e9; '
                'border: 1px solid #35414d; border-radius: 7px; '
                'font-family: Consolas, monospace; font-size: 11px; padding: 7px;}')
            viewer.setMinimumHeight(150)
        self.diagnostics_stack = QStackedWidget()
        self.diagnostics_stack.setObjectName('exportDiagnosticsStack')
        self.diagnostics_stack.setFixedHeight(260)
        self.diagnostics_stack.addWidget(self.activity_log)
        self.diagnostics_stack.addWidget(self.report_view)
        layout.addWidget(self.diagnostics_stack)
        self.report_hint = _text('No report selected.', 'bodyMuted')
        self.report_hint.hide()
        layout.addWidget(self.report_hint)
        self.activity_toggle.toggled.connect(
            lambda checked: self._select_diagnostics('activity') if checked else None)
        self.report_toggle.toggled.connect(
            lambda checked: self._select_diagnostics('report') if checked else None)
        self.diagnostics_collapse.toggled.connect(self._toggle_diagnostics)
        self._select_diagnostics('activity')
        # Resize with the Export viewport instead of imposing a tiny maximum.
        self.content_scroll.viewport().installEventFilter(self)
        self._fit_diagnostics_height()
        self._center_diagnostics_switch()
        layout.addStretch(1)

    def _center_diagnostics_switch(self):
        """Overlay the diagnostics switch at the exact ResultsTab horizontal center.

        Parenting the switch to ResultsTab removes the scroll-content width
        dependency. Its y position tracks the real diagnostics header even when
        scrolling. Hide it when that header scrolls out of view.
        """
        if not hasattr(self, 'diagnostics_mode_group'):
            return
        group = self.diagnostics_mode_group
        header = self.diagnostics_header
        viewport = self.content_scroll.viewport()
        group.adjustSize()
        x = (self.width() - group.width()) // 2
        header_in_tab = header.mapTo(self, QPoint(0, 0))
        y = header_in_tab.y() + (header.height() - group.height()) // 2
        # Keep the selector truly centered; title and tools remain in the
        # underlying header layout and do not participate in positioning.
        group.move(x, y)
        in_view = header.mapTo(viewport, QPoint(0, 0)).y()
        visible = (header.isVisible() and in_view + header.height() > 0
                   and in_view < viewport.height())
        group.setVisible(visible)
        if visible:
            group.raise_()

    def _fit_diagnostics_height(self):
        viewport_height = self.content_scroll.viewport().height()
        target = max(190, min(440, int(viewport_height * 0.48)))
        self.diagnostics_stack.setFixedHeight(target)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            if watched is self.content_scroll.viewport() and hasattr(self, 'diagnostics_stack'):
                self._fit_diagnostics_height()
                self._center_diagnostics_switch()
            elif watched is self.diagnostics_header or watched is self:
                self._center_diagnostics_switch()
        return super().eventFilter(watched, event)

    def _select_diagnostics(self, mode):
        report = mode == 'report'
        self.activity_toggle.setChecked(not report)
        self.report_toggle.setChecked(report)
        self.diagnostics_stack.setCurrentIndex(1 if report else 0)
        self.open_report_button.setVisible(report)
        self.copy_activity_button.setVisible(not report)
        self.clear_activity_button.setVisible(not report)
        self.copy_report_button.setVisible(report)
        self.clear_report_button.setVisible(report)
        self.report_hint.setVisible(report and bool(self._report_path))
        self.activity_progress.setVisible(not report and getattr(self, '_activity_busy', False)
                                          and self.diagnostics_collapse.isChecked())
        self._center_diagnostics_switch()

    def _toggle_diagnostics(self, expanded):
        self.diagnostics_stack.setVisible(expanded)
        self.report_hint.setVisible(expanded and self.report_toggle.isChecked() and bool(self._report_path))
        self.diagnostics_collapse.setIcon(export_icon('down' if expanded else 'right'))
        self.diagnostics_collapse.setToolTip('Collapse diagnostics' if expanded else 'Expand diagnostics')
        self.activity_progress.setVisible(expanded and self.activity_toggle.isChecked()
                                          and getattr(self, '_activity_busy', False))

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
        self.phase_label.setText('Validated native 3MF')
        self.phase_label.setStyleSheet('color: #89d9c3; font-weight: 600;')
        self.status_icon.setPixmap(export_icon('check', '#89d9c3').pixmap(17, 17))
        self.export_summary.setText(f'{output.name} · {result.get("slicer", "Selected slicer")}')
        self.export_summary.setToolTip(str(output))
        self.export_summary.show()
        self.export_summary_row.show()
        self.validated_output_panel.show()
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
        if title == 'Native 3MF export' and severity in ('busy', 'warning', 'error'):
            state = ('Exporting native 3MF…' if severity == 'busy' else
                     'Export failed' if severity == 'error' else 'Export cancelled')
            tint = {'busy': '#67bfd1', 'warning': '#e9b66c', 'error': '#f0929e'}[severity]
            self.phase_label.setText(state)
            self.phase_label.setStyleSheet(f'color: {tint}; font-weight: 600;')
            self.status_icon.setPixmap(export_icon('alert-circle' if severity == 'error'
                else 'info', tint).pixmap(17, 17))
        self._activity_busy = severity == 'busy'
        self.activity_progress.setVisible(self._activity_busy and self.activity_toggle.isChecked()
                                          and self.diagnostics_collapse.isChecked())
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
        self._select_diagnostics('report')
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
        self.report_hint.hide()
        self.copy_report_button.setEnabled(False)
        self.clear_report_button.setEnabled(False)

    def copy_report(self):
        if self._report_path is not None:
            QApplication.clipboard().setText(self._report_content)
