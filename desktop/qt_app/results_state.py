"""Source-of-truth labels and safe, read-only report loading for Qt Stage 2C.

These functions never infer that a conversion, a slicer round trip, or print
validation has passed from the mere existence of a report file.
"""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

MAX_REPORT_BYTES = 2 * 1024 * 1024
REPORT_EXTENSIONS = frozenset({'.txt', '.log', '.md', '.csv'})
MAX_EVENTS = 100


def read_existing_report(filename):
    """Return decoded text of a small local report; never modify the file."""
    path = Path(filename).expanduser()
    if path.suffix.lower() not in REPORT_EXTENSIONS:
        raise ValueError('Select an existing .txt, .log, .md, or .csv report.')
    if not path.is_file():
        raise ValueError('Report file not found.')
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError('Report exceeds the 2 MiB display limit.')
    with path.open('rb') as stream:
        data = stream.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError('Report exceeds the 2 MiB display limit.')
    for encoding in ('utf-8-sig', 'utf-16'):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise ValueError('Report must be UTF-8 or UTF-16 text; binary files are unsupported.')


def shorten(value, max_chars=96):
    """Restrict long paths and untrusted strings in visible status and activity."""
    string = str(value or '').replace('\r', ' ').replace('\n', ' ').strip()
    if len(string) <= max_chars:
        return string
    return string[:max_chars - 1] + '…'


def _filename(value):
    if not value:
        return ""
    return PureWindowsPath(value).name if "\\" in str(value) else Path(value).name


def model_summary(model_path, template_path, slicer, dirty=False):
    """Describe configuration state, not engine execution state."""
    model = _filename(model_path) if model_path else 'No model selected'
    template = _filename(template_path) if template_path else 'Not selected'
    return {
        'model': shorten(model),
        'template': shorten(template),
        'slicer': shorten(slicer or 'Not selected'),
        'settings': 'Unsaved changes' if dirty else 'Saved or unchanged',
        'conversion': 'Not run in Qt (Stage 4)',
        'validation': 'Not run in Qt (Stage 4)',
    }


def event_tail(events, limit=MAX_EVENTS):
    """Bound memory growth in a long-running UI session."""
    return list(events)[-max(1, min(int(limit), MAX_EVENTS)):]
