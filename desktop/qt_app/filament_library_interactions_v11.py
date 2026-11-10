"""Small, optional Qt-only Filament Library usability enhancements (v11).

The library catalog, saved profile records, filtering rules and forecasting are
not modified here. Call ``install_library_usability_v11(dialog)`` once after the
existing FilamentLibraryDialog widgets and model have been initialized.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QSignalBlocker
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLayout, QToolButton,
)

_SORT_RESET_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
width="24" height="24" fill="none" stroke-linecap="round" stroke-linejoin="round">
<path d="M4 6h9M4 11h7M4 16h5" stroke="#b4c5d3" stroke-width="1.8"/>
<path d="M15 9.5a6 6 0 1 1-2 11.2" stroke="#69bfd2" stroke-width="1.8"/>
<path d="m14.8 5.6.2 4.1 3.7-.8" stroke="#69bfd2" stroke-width="1.8"/>
</svg>"""


def _sort_reset_icon() -> QIcon:
    """Render a vector icon at 2x, with device pixel ratio for crisp Qt scaling."""
    renderer = QSvgRenderer(QByteArray(_SORT_RESET_SVG.encode('utf-8')))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter, QRectF(0, 0, 48, 48))
    finally:
        painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


def _filter_row_with(dialog, widget):
    """Return the existing filter-row layout; do not add a second filter row."""
    for layout in dialog.findChildren(QHBoxLayout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is not None and item.widget() is widget:
                return layout
    return None


def _sort_default(dialog):
    """Restore the source model's natural order, not alphabetical sort-by-header."""
    table = dialog.table
    header = table.horizontalHeader()
    model = table.model()
    # A column of -1 means "restore source-model order" in QSortFilterProxyModel.
    # Temporarily suppress the header notification so a previous header sort
    # isn't immediately reapplied on resetting the indicator.
    with QSignalBlocker(header):
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(False)
    model.sort(-1, Qt.SortOrder.AscendingOrder)


def _update_reset_visibility(dialog):
    button = getattr(dialog, 'library_reset_sort_button_v11', None)
    if button is None:
        return
    # All Filaments is the only screen with a global library sort reset.
    # Profile editing retains its checked-first ordering.
    on_all = getattr(dialog, '_profile_identity', None) is None
    button.setVisible(on_all)
    button.setEnabled(on_all)


def install_library_usability_v11(dialog) -> None:
    if getattr(dialog, '_library_usability_v11_installed', False):
        return
    required = ('table', 'sources', 'profiles', 'all_filaments_button', '_profile_identity')
    missing = [name for name in required if not hasattr(dialog, name)]
    if missing:
        raise RuntimeError('Filament Library v11 requires v10 widgets: ' + ', '.join(missing))
    table = dialog.table
    if not isinstance(table, QAbstractItemView):
        raise TypeError('Expected a Qt filament table view')
    # Extends the existing row selection; checked membership remains its own
    # model role. Modifier clicks do not write to the profile in this patch.
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    # The current SVG has substantial internal negative space. 22px provides
    # a readable mark within the existing sidebar row; no row-height increase.
    dialog.all_filaments_button.setIconSize(QSize(22, 22))

    row = _filter_row_with(dialog, dialog.sources)
    if row is None:
        raise RuntimeError('Filament Library v11 could not locate the source filter row')
    button = QToolButton(dialog)
    button.setObjectName('libraryResetSortButton')
    button.setIcon(_sort_reset_icon())
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(33, 33)
    button.setToolTip('Reset sorting to original library order (keeps filters and selections)')
    button.setAccessibleName('Reset filament sorting')
    button.setStyleSheet(
        'QToolButton#libraryResetSortButton { background: #222c37; '
        'border: 1px solid #3a4b59; border-radius: 6px; padding: 2px; }'
        'QToolButton#libraryResetSortButton:hover { background: #2b4452; '
        'border-color: #64b7ca; }'
    )
    row.addWidget(button, 0)
    button.clicked.connect(lambda: _sort_default(dialog))
    # Clicking a sortable column should reveal the sort indicator again.
    header = table.horizontalHeader()
    header.sectionClicked.connect(lambda _index: header.setSortIndicatorShown(True))
    # Defer visibility until the current profile selection handler has run.
    dialog.profiles.currentItemChanged.connect(
        lambda *_: _update_reset_visibility(dialog))
    dialog.all_filaments_button.clicked.connect(
        lambda *_: _update_reset_visibility(dialog))
    dialog.library_reset_sort_button_v11 = button
    dialog._library_usability_v11_installed = True
    _update_reset_visibility(dialog)
