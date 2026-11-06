"""Presentation-only visibility and source choice for preview options."""
from __future__ import annotations


def preview_options_state(has_model, has_live, has_imported, using_imported):
    """Describe controls without changing forecast, import, or mesh state."""
    model = bool(has_model)
    live = model and bool(has_live)
    imported = model and bool(has_imported)
    both = live and imported
    return {
        'menu_visible': model,
        'import_enabled': model,
        'sources_visible': both,
        'live_enabled': live,
        'imported_enabled': imported,
        'live_checked': both and not bool(using_imported),
        'imported_checked': both and bool(using_imported),
    }
