"""Optional, lossless, background-only GPU indexing of preview float32 vertices.

No source geometry, painted metadata, forecast or export paths are modified.
Import NumPy only when the opt-in is set; the production Direct path is intact.
"""
from __future__ import annotations

import os

MAX_INDEX_SOURCE_BYTES = 128 * 1024 * 1024
MIN_NET_SAVINGS_PERCENT = 10.0


def enabled() -> bool:
    """Indexed Direct by default; opt out with FULLSPECTRUM_PREVIEW_INDEXED=0.

    Diagnostic raw/split GL upload modes always bypass indexing.
    """
    choice = os.environ.get('FULLSPECTRUM_PREVIEW_INDEXED', 'auto').strip().lower()
    return (choice in ('', 'auto', '1', 'true', 'on', 'yes')
            and os.environ.get('FULLSPECTRUM_PREVIEW_UPLOAD', 'direct').strip().lower()
            in ('', 'direct'))


def prepare_indexed_preview(render_buffer, *, cancelled=None):
    """Return a byte-exact candidate, or None for the current Direct path.

    Called ONLY on ModelLoadWorker's background thread after flatten_faces.
    Cancellation is checked before and after numpy.unique (not during it).
    """
    if not enabled():
        return None
    if cancelled is not None and cancelled():
        return None
    source_bytes = len(render_buffer) * render_buffer.itemsize
    if not source_bytes or source_bytes > MAX_INDEX_SOURCE_BYTES:
        return None
    try:
        from desktop.qt_app.preview_indexing import make_indexed_candidate
        candidate = make_indexed_candidate(render_buffer)
    except Exception:
        # Any indexing failure must leave the authoritative Direct renderer usable.
        return None
    if cancelled is not None and cancelled():
        return None
    return candidate if candidate.worth_uploading(
        minimum_savings_percent=MIN_NET_SAVINGS_PERCENT) else None
