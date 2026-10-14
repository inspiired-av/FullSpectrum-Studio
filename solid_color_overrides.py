"""Strict per-source-color to physical filament assignments for standard colored 3MF.

Rules are scoped to a single imported model. They intentionally do not choose
nearby source colors or silently fall back to mixed print recipes.
"""

import re

COLOR = re.compile(r"#[0-9A-Fa-f]{6}\Z")


def normalize_solid_overrides(overrides):
    """Return canonical source HEX -> full physical anchor key mapping."""
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise ValueError("Solid filament overrides must map source HEX colors to filament keys")
    if len(overrides) > 31:
        raise ValueError("At most 31 source colors can be protected while leaving a paint slot for other colors")
    result = {}
    for color, filament in overrides.items():
        if not isinstance(color, str) or not COLOR.fullmatch(color):
            raise ValueError(f"Invalid protected source color {color!r}; expected #RRGGBB")
        if not isinstance(filament, str) or not filament.strip() or len(filament) > 512:
            raise ValueError(f"Missing or invalid physical filament key for {color}")
        key = color.upper()
        if key in result and result[key] != filament.strip():
            raise ValueError(f"Conflicting solid filament overrides for {key}")
        result[key] = filament.strip()
    return result


def require_protected_slots(import_metadata, overrides):
    """Resolve original source HEX selections to unquantized staged paint slots."""
    slot_map = import_metadata.get("protectedSlotMap", {}) if import_metadata else {}
    missing = sorted(set(overrides) - set(slot_map))
    if missing:
        raise ValueError("Protected source colors not present in this 3MF: " + ", ".join(missing))
    return {int(slot_map[color]): filament for color, filament in overrides.items()}


def solid_anchor_choice(source_color, filament_key, anchors, matches_key, anchor_color, anchor_name, dist):
    """Resolve to an already selected *real* slot, never a mixed slot."""
    matches = [(slot, item) for slot, item in enumerate(anchors, start=1) if matches_key(item, filament_key)]
    if len(matches) != 1:
        raise ValueError(
            f"Protected {source_color} filament {filament_key!r} is not uniquely available "
            "among selected physical anchors; enable/pin it and check Physical slots"
        )
    slot, anchor = matches[0]
    color = anchor_color(anchor)
    error = dist(source_color, color)
    return slot, [None, slot, source_color, "SOLID", anchor_name(anchor), "", "", color,
                  f"{error:.2f}", f"{error:.2f}", "0.00"]
