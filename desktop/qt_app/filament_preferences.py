"""Stage 2B: UI-independent filament enable/pin and model-only solid choices.

Shares the same keys and settings document as the production Tkinter frontend.
No preview, print, or conversion is performed by this module.
"""
from __future__ import annotations

from pathlib import Path
import re

from desktop.settings_store import load_settings, save_settings

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class FilamentPreferences:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.saved = load_settings(self.path)
        self.disabled = set(self.saved.get('disabled_anchor_keys', []))
        self.pinned = set(self.saved.get('pinned_anchor_keys', []))
        self._dirty = False
        self.solid_assignments: dict[str, str] = {}  # model-only; never persisted
        self.model_path = ''

    @property
    def is_dirty(self):
        return self._dirty

    def selected(self, key):
        return key not in self.disabled

    def is_pinned(self, key):
        return key in self.pinned

    def apply(self, options, enabled_keys, pinned_keys, max_slots=6):
        """Validate changes, then merge only keys belonging to THIS source.

        Other source selections are not silently erased on source changes.
        """
        keys = {str(item['key']) for item in options}
        enabled = set(enabled_keys) & keys
        pinned = set(pinned_keys) & keys
        distinct = {str(item.get('color', '')).upper() for item in options
                    if item['key'] in enabled and _HEX.fullmatch(str(item.get('color', '')))}
        if len(distinct) < 2:
            raise ValueError('Use at least two distinct filament colors.')
        if not pinned <= enabled:
            raise ValueError('Required filaments must also have Use checked.')
        if len(pinned) > int(max_slots):
            count = int(max_slots)
            noun = 'filament' if count == 1 else 'filaments'
            raise ValueError(
                f'You can require at most {count} {noun} with the current Physical slots setting.'
            )
        new_disabled = (self.disabled - keys) | (keys - enabled)
        new_pinned = (self.pinned - keys) | pinned
        if len(new_disabled) > 1000 or len(new_pinned) > 1000:
            raise ValueError('Too many saved filament identities (1000 maximum).')
        if new_disabled != self.disabled or new_pinned != self.pinned:
            self.disabled, self.pinned = new_disabled, new_pinned
            self._dirty = (self.disabled != set(self.saved.get('disabled_anchor_keys', []))
                           or self.pinned != set(self.saved.get('pinned_anchor_keys', [])))
            # Protected mappings cannot target a now-disabled filament.
            self.solid_assignments = {
                color: key for color, key in self.solid_assignments.items()
                if key not in self.disabled
            }

    def save(self):
        """Re-read latest settings: edits by other windows are preserved."""
        current = load_settings(self.path)
        if self._dirty:
            current['disabled_anchor_keys'] = sorted(self.disabled)
            current['pinned_anchor_keys'] = sorted(self.pinned)
            save_settings(current, self.path)
        self.saved = load_settings(self.path)
        self._dirty = False

    def revert(self):
        self.saved = load_settings(self.path)
        self.disabled = set(self.saved.get('disabled_anchor_keys', []))
        self.pinned = set(self.saved.get('pinned_anchor_keys', []))
        self._dirty = False
        self.solid_assignments = {
            color: key for color, key in self.solid_assignments.items()
            if key not in self.disabled
        }

    def use_model(self, filename):
        """Solid source-color protection belongs to the specific source model."""
        filename = str(filename or '')
        if filename != self.model_path:
            self.model_path = filename
            self.solid_assignments.clear()

    def protect(self, source_color, filament_key, available_colors, options):
        source = str(source_color or '').upper()
        valid_sources = {str(c).upper() for c in available_colors}
        valid_keys = {o['key'] for o in options if o['key'] not in self.disabled}
        if not _HEX.fullmatch(source) or source not in valid_sources:
            raise ValueError('Select an exact color from the original 3MF source.')
        if filament_key not in valid_keys:
            raise ValueError('Choose an enabled physical filament.')
        self.solid_assignments[source] = filament_key

    def unprotect(self, source_color):
        self.solid_assignments.pop(str(source_color).upper(), None)


def load_filament_options(source, inventory_snapshot=None, custom_path=''):
    """Invoke the same engine and option normalizer used by Tkinter.

    Caller runs this in a worker thread; the module isn't imported at Qt startup.
    """
    import fullspectrum_engine as engine
    from desktop.filament_options import selectable_filament_options
    if source in ('inventory', 'catalog', 'all-bambu') and inventory_snapshot is None:
        inventory_snapshot = engine.read_bambu_inventory(required=False, minimum_colors=0)
    return selectable_filament_options(engine, source, inventory_snapshot, custom_path)


class SourceColorCounts(dict):
    """Source swatches with an explicit representation for UI messaging."""

    def __init__(self, counts, source_kind):
        super().__init__(counts)
        self.source_kind = source_kind


def scan_source_colors(filename):
    import fullspectrum_engine as engine
    path = Path(filename)
    if not path.is_file() or path.suffix.lower() != '.3mf':
        raise ValueError('Select a 3MF model containing source color assignments first.')
    if engine.is_standard_colored_3mf(path):
        return SourceColorCounts(engine.available_solid_source_colors(path), 'material_faces')
    from desktop.qt_app.native_object_colors import scan_native_object_colors
    try:
        counts = scan_native_object_colors(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            'No supported source colors were found. Standard material-colored 3MFs use '
            'face-level materials; Bambu/Orca projects can also assign a single '
            'physical filament to each object. Simple single-state Bambu facet '
            'paint is supported; complex split-region paint and mixed-filament '
            'states are not safely countable by this scanner. '
            f'Details: {exc}'
        ) from exc
    kind = 'native_painted_faces' if getattr(counts, 'has_painted_faces', False) else 'native_object_colors'
    return SourceColorCounts(counts, kind)
