"""Stage 2A: pure-Python bridge to the existing FullSpectrum settings store.

Plan controls stage changes in memory and write only after an explicit Save.
Existing Tkinter-only preferences (pins, protected colors, etc.) are preserved.
No conversion engine or Qt dependency is imported here.
"""
from __future__ import annotations

from pathlib import Path

from desktop.settings_store import load_settings, save_settings, validated_settings

# Match the established Tkinter shell defaults, rather than introducing a
# second interpretation of optimization or source selection.
DEFAULTS = {
    "source": "inventory",
    "output_color_strategy": "maximum_fidelity",
    "max_output_colors": "32",
    "strategy": "official",
    "planner_mode": "best",
    "planning_sample": "preview",
    "catalog_region": "global",
    "real_slots": "auto",
    "quality_bias": 60,
    "smart_quality": True,
    "auto_preview": True,
    "auto_open": True,
    "output_application": "Bambu Studio",
    "custom": "",
    "native_project_template": "",
    "bambu_studio_executable": "",
    "orcaslicer_executable": "",
}
MANAGED_KEYS = frozenset(DEFAULTS)


def validate_plan_change(key: str, value):
    """Reject corrupted or unsupported values before modifying UI draft state."""
    if key not in MANAGED_KEYS:
        raise KeyError(f"Unsupported Plan field: {key}")
    accepted = validated_settings({key: value})
    if key not in accepted:
        raise ValueError(f"Invalid Plan setting for {key}: {value!r}")
    return accepted[key]


class PlanPreferences:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self.saved = load_settings(self.path)
        self.values = {**DEFAULTS, **{key: value for key, value in self.saved.items() if key in MANAGED_KEYS}}
        # Track only fields changed in this Qt session. Avoid overwriting
        # unrelated settings if the Tkinter app saves them meanwhile.
        self.dirty_keys: set[str] = set()

    def get(self, key: str):
        if key not in MANAGED_KEYS:
            raise KeyError(key)
        return self.values[key]

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_keys)

    def set(self, key: str, value) -> bool:
        value = validate_plan_change(key, value)
        if self.values[key] == value:
            return False
        self.values[key] = value
        if value == self.saved.get(key, DEFAULTS[key]):
            self.dirty_keys.discard(key)
        else:
            self.dirty_keys.add(key)
        return True

    def save(self):
        """Atomically merge only edited keys into the current settings file."""
        # Re-load to protect unrelated keys updated by the legacy frontend.
        existing = load_settings(self.path)
        merged = dict(existing)
        for key in self.dirty_keys:
            merged[key] = self.values[key]
        result = save_settings(merged, self.path)
        self.saved = load_settings(self.path)
        self.dirty_keys.clear()
        return result

    def revert(self):
        """Discard Qt edits and reload latest settings saved by either UI."""
        self.saved = load_settings(self.path)
        self.values = {**DEFAULTS, **{key: value for key, value in self.saved.items() if key in MANAGED_KEYS}}
        self.dirty_keys.clear()


PALETTE_STRATEGIES = (
    ("Balanced — fewer mixtures", "balanced"),
    ("Maximum fidelity (recommended)", "maximum_fidelity"),
    ("Fill palette — use available slots", "fill_palette"),
)
FILAMENT_SOURCES = (
    ("My inventory", "inventory"),
    ("Bambu catalog", "catalog"),
    ("All Bambu materials", "all-bambu"),
    ("Custom filament library", "custom"),
    ("CMYKW materials", "exact-cmykw"),
)
REGIONS = (
    ("Global", "global"), ("Europe", "eu"), ("US & Canada", "us-ca"),
    ("United Kingdom", "uk"), ("Australia & New Zealand", "au-nz"),
    ("Asia", "asia"),
)
PHYSICAL_SLOTS = (("Auto", "auto"),) + tuple((str(i), str(i)) for i in range(2, 9))
PLAN_EFFORT = (("Best", "best"), ("Fast", "fast"))
PLANNING_SAMPLES = (("Rendered preview", "preview"), ("Exact paint distribution", "paint"))
PALETTE_BASE = (("Bambu PLA", "official"), ("CMYKW", "cmykw"))
OUTPUT_SLICERS = (("Bambu Studio", "Bambu Studio"), ("OrcaSlicer", "OrcaSlicer"))
