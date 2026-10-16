"""Read-only Phase 4 audit of physical filament presets in slicer-native 3MFs.

This is *not* a filament calibration tool: matching a preset name does not
validate extrusion temperature, volumetric flow, cooling, or printed color.
Only physical slots are compared; generated mixed slots derive from them.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile, BadZipFile


class MaterialAuditError(ValueError):
    pass


def _base_preset(name):
    """Compare preset family while ignoring machine suffix after '@'."""
    tokens = re.sub(r"\s+", " ", str(name or "").split("@", 1)[0].strip()).casefold().split()
    # Panchroma product family alias: the generic planning catalog calls it
    # "Bambu Panchroma Translucent PLA" while a slicer-saved preset may be
    # "Panchroma PLA Translucent". Ignore token order and a catalog prefix,
    # but preserve all material qualifiers (e.g. silk vs translucent).
    if "panchroma" in tokens:
        tokens = [word for word in tokens if word != "bambu"]
        return "panchroma " + " ".join(sorted(word for word in tokens if word != "panchroma"))
    return " ".join(tokens)


def _color(value):
    value = str(value or "").strip().upper()
    return value if re.fullmatch(r"#[0-9A-F]{6}", value) else ""


def _slot_field(settings, key, i):
    items = settings.get(key, [])
    return str(items[i] or "") if isinstance(items, list) and len(items) > i else ""


def audit_material_profiles(settings, anchors, real_count=None):
    """Compare planned physical anchors with serialized native physical slots.

    anchors: ordered dicts with slot/name/color and optionally expected preset
    (the engine's real_profiles). Reports unknown identity as unverified rather
    than claiming a match. Does not make any mutations.
    """
    if not isinstance(settings, dict):
        raise MaterialAuditError("Expected a native project_settings dictionary")
    colors = settings.get("filament_colour")
    if not isinstance(colors, list) or not colors:
        raise MaterialAuditError("Native project has no filament_colour array")
    count = len(anchors) if real_count is None else int(real_count)
    if not 0 < count <= len(colors) or len(anchors) != count:
        raise MaterialAuditError("Physical anchor count does not match exported filament slots")
    output = []
    for i in range(count):
        anchor = anchors[i]
        if not isinstance(anchor, dict):
            raise MaterialAuditError("Physical anchor must be a dictionary")
        expected_name = str(anchor.get("name") or "").strip()
        expected_profile = str(anchor.get("preset") or "").strip()
        expected_color = _color(anchor.get("color"))
        actual_color = _color(colors[i])
        actual_profile = _slot_field(settings, "filament_settings_id", i).strip()
        actual_id = _slot_field(settings, "filament_ids", i).strip()
        actual_vendor = _slot_field(settings, "filament_vendor", i).strip()
        actual_type = _slot_field(settings, "filament_type", i).strip()
        is_mixed = _slot_field(settings, "filament_is_mixed", i).strip()
        problems = []
        if is_mixed == "1":
            problems.append("physical slot is marked as mixed")
        if expected_color and expected_color != actual_color:
            problems.append(f"color {actual_color or '(invalid)'} differs from intended {expected_color}")
        if not actual_profile:
            problems.append("no saved filament preset ID")
        elif expected_profile:
            if _base_preset(expected_profile) != _base_preset(actual_profile):
                problems.append(f"preset '{actual_profile}' differs from intended '{expected_profile}'")
        else:
            # A custom JSON color library generally defines no slicer preset.
            # Brand/series labels are hints only, never proof of preset identity.
            expected_series = str(anchor.get("series") or "").strip()
            if not expected_series and expected_name:
                if "panchroma" in expected_name.lower():
                    expected_series = "Panchroma"
                elif "pla basic" in expected_name.lower():
                    expected_series = "PLA Basic"
            if expected_series and expected_series.casefold() not in actual_profile.casefold():
                problems.append(f"preset '{actual_profile}' does not identify expected series '{expected_series}'")
        output.append({
            "slot": i + 1, "intended": expected_name or f"Physical filament {i+1}",
            "intended_color": expected_color, "exported_color": actual_color,
            "intended_preset": expected_profile, "exported_preset": actual_profile,
            "exported_filament_id": actual_id, "exported_vendor": actual_vendor,
            "exported_type": actual_type, "problems": problems,
            "status": "review" if problems else "matched" if expected_profile else "unverified",
        })
    return output


def warning_lines(audit):
    """Human-readable warnings for export report; safe with no verified presets."""
    flagged = [x for x in audit if x["status"] == "review"]
    unverified = [x for x in audit if x["status"] == "unverified"]
    lines = []
    if flagged:
        lines.append(
            f"Phase 4 material-profile review: {len(flagged)}/{len(audit)} physical slots "
            "have a preset/color mismatch or missing identity. "
            "The native template's material parameters were retained; filament HEX colors "
            "and mixed swatches do not validate actual print settings."
        )
        for row in flagged:
            lines.append(f"Physical slot {row['slot']} ({row['intended']}): " + "; ".join(row['problems']))
    if unverified:
        lines.append(
            f"Phase 4 material-profile review: {len(unverified)} physical slot(s) have no "
            "verified intended slicer preset; check their profiles before printing."
        )
    return lines


def _load_native_settings(path):
    try:
        with ZipFile(path) as z:
            if "Metadata/project_settings.config" not in z.namelist():
                raise MaterialAuditError("3MF has no native project settings")
            raw = z.read("Metadata/project_settings.config")
            if len(raw) > 12 * 1024 * 1024:
                raise MaterialAuditError("Project settings exceed audit safety limit")
            return json.loads(raw)
    except (OSError, BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterialAuditError(f"Cannot read project: {exc}") from exc


def audit_project(project, anchors, real_count=None):
    return audit_material_profiles(_load_native_settings(project), anchors, real_count)


def _anchors_from_library(settings, library):
    # Read-only offline convenience. Filament JSON describes colors, not validated
    # temperature/flow profiles. Use library colors only as identifying hints.
    raw = json.loads(Path(library).read_text(encoding="utf-8"))
    entries = raw.get("filaments", []) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise MaterialAuditError("Filament library must contain a filaments list")
    by_color = {}
    for entry in entries:
        if isinstance(entry, dict) and _color(entry.get("color")):
            by_color.setdefault(_color(entry["color"]), []).append(entry)
    mixed = settings.get("filament_is_mixed", [])
    count = next((i for i, flag in enumerate(mixed) if str(flag) == "1"), len(settings.get("filament_colour", [])))
    anchors = []
    for color in settings.get("filament_colour", [])[:count]:
        matches = by_color.get(_color(color), [])
        entry = matches[0] if len(matches) == 1 else {}
        anchors.append({"name": entry.get("name", "Unidentified filament"),
                        "series": entry.get("series", ""), "color": color})
    return anchors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only audit of native 3MF physical filament profiles")
    parser.add_argument("project", help="FullSpectrum exported native .3mf")
    parser.add_argument("--library", help="Optional FullSpectrum custom filament JSON for color/name hints")
    args = parser.parse_args(argv)
    try:
        settings = _load_native_settings(args.project)
        if args.library:
            anchors = _anchors_from_library(settings, args.library)
            audit = audit_material_profiles(settings, anchors)
        else:
            mixed = settings.get("filament_is_mixed", [])
            n = next((i for i,v in enumerate(mixed) if str(v)=="1"), len(settings["filament_colour"]))
            anchors = [{"name": f"Unverified physical filament {i+1}", "color": settings['filament_colour'][i]}
                       for i in range(n)]
            audit = audit_material_profiles(settings, anchors)
    except (MaterialAuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"Physical slots audited: {len(audit)} (this does not validate print parameters)")
    for row in audit:
        print(f"{row['slot']:>2}: {row['status'].upper():<10} {row['intended']} "
              f"{row['exported_color']} | {row['exported_preset']}")
        for problem in row['problems']:
            print(f"    ! {problem}")
    for warning in warning_lines(audit):
        print("WARNING: " + warning)
    if not warning_lines(audit):
        print("Preset names match known references, but nozzle/flow/temperature still require validation.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
