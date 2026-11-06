"""Pure, platform-independent policy for responsive preview toolbar rows."""
from __future__ import annotations


def compact_preview_rows(available_width: int, wide_required: int,
                         was_compact: bool = False) -> bool:
    """Wrap when the real viewport is too narrow, with 16 px hysteresis.

    A cache of *wide* required width prevents oscillating when moving widgets
    to a compact row reduces the current layout's own sizeHint.
    """
    width = max(0, int(available_width))
    needed = max(0, int(wide_required))
    if width == 0:
        return bool(was_compact)
    return width < needed + (16 if was_compact else 0)
