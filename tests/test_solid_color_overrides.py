"""Tests for exact source color protection, separate from mixer calibration."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from standard_3mf_import import (
    UnsupportedColored3MF,
    import_colored_3mf_project,
    protected_import_palette,
    source_color_counts,
)
from solid_color_overrides import (
    normalize_solid_overrides,
    require_protected_slots,
    solid_anchor_choice,
)


def fake_palette(colors, limit):
    # Purposefully quantizes *all other* colors to first few available paint slots.
    unique = list(dict.fromkeys(colors))[:limit]
    return unique, {color: unique.index(color) + 1 if color in unique else 1 for color in colors}


def error(a, b):
    return sum(abs(int(a[i:i+2], 16) - int(b[i:i+2], 16)) for i in (1,3,5))


def fixture(source, faces=("#9098A8", "#000000", "#1C77DA", "#20AE32")):
    distinct = list(dict.fromkeys(faces))
    colors = "".join(f'<m:color color="{c}FF"/>' for c in distinct)
    triangles = "".join(
        f'<triangle v1="0" v2="1" v3="2" pid="1" p1="{distinct.index(color)}"/>'
        for color in faces
    )
    xml = (
        '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">'
        '<resources><m:colorgroup id="1">' + colors + '</m:colorgroup>'
        '<object id="2" type="model"><mesh><vertices>'
        '<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>'
        '<vertex x="0" y="1" z="0"/></vertices><triangles>'
        + triangles + '</triangles></mesh></object></resources>'
        '<build><item objectid="2"/></build></model>'
    )
    with ZipFile(source, "w") as zipfile:
        zipfile.writestr("3D/3dmodel.model", xml)


def import_fixture(source, destination, **kwargs):
    return import_colored_3mf_project(
        source, destination,
        kmeans_colors=fake_palette,
        paint_code_for_slot=lambda slot: f"{slot:X}",
        basic_project_settings=lambda colors: {"filament_colour": colors},
        color_distance=error,
        **kwargs,
    )


class SolidRulesTests(unittest.TestCase):
    def test_rules_normalize_hex_without_changing_anchor_key(self):
        key = "Panchroma Translucent PLA|#9199A4"
        self.assertEqual(normalize_solid_overrides({"#9098a8": key}), {"#9098A8": key})

    def test_no_guessing_nearby_source_colors(self):
        self.assertEqual(normalize_solid_overrides({"#9098A8": "Grey"}).get("#9199A4"), None)

    def test_invalid_rule_rejected(self):
        for mapping in ({"9098A8": "Grey"}, {"#9098A8": ""}, {"#123": "Grey"}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                normalize_solid_overrides(mapping)

    def test_too_many_rules_rejected(self):
        with self.assertRaisesRegex(ValueError, "31"):
            normalize_solid_overrides({f"#{i:06X}": "Grey" for i in range(32)})

    def test_dedicated_protected_source_slot_does_not_absorb_other_face_colors(self):
        palette, assignment, protected = protected_import_palette(
            ["#9098A8", "#9098A8", "#000000", "#1C77DA", "#20AE32"],
            ["#9098A8"], fake_palette, error, 3,
        )
        self.assertEqual(palette[0], "#9098A8")
        self.assertEqual(protected, {"#9098A8": 1})
        self.assertEqual(assignment["#9098A8"], 1)
        for color in ("#000000", "#1C77DA", "#20AE32"):
            self.assertNotEqual(assignment[color], 1)

    def test_import_preserves_protected_face_and_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td)/"source.3mf", Path(td)/"staged.3mf"
            fixture(source)
            result = import_fixture(source, target, protected_source_colors=["#9098A8"], max_paint_slots=3)
            self.assertEqual(result["protectedSlotMap"], {"#9098A8": 1})
            self.assertEqual(result["triangleCount"], 4)
            with ZipFile(target) as archive:
                obj = json.loads(archive.read("Metadata/project_settings.config"))
                self.assertEqual(obj["filament_colour"][0], "#9098A8")
                triangle_codes = [tri.get("paint_color") for tri in ET.fromstring(
                    archive.read("3D/Objects/object_1.model")).findall(".//{*}triangle")]
                self.assertEqual(triangle_codes[0], "1")
                self.assertTrue(all(code != "1" for code in triangle_codes[1:]))

    def test_missing_source_color_never_matched_approximately(self):
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td)/"source.3mf", Path(td)/"staged.3mf"
            fixture(source)
            with self.assertRaisesRegex(UnsupportedColored3MF, "not present"):
                import_fixture(source, target, protected_source_colors=["#9199A4"])
            self.assertFalse(target.exists())

    def test_source_color_picker_uses_exact_pre_quantized_face_colors(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"source.3mf"
            fixture(source, faces=["#9098A8", "#9098A8", "#9098A8", "#1C77DA"])
            self.assertEqual(source_color_counts(source), {"#9098A8": 3, "#1C77DA": 1})

    def test_require_protected_slots_reports_missing_mapping(self):
        with self.assertRaisesRegex(ValueError, "not present"):
            require_protected_slots({"protectedSlotMap": {}}, {"#9098A8": "Grey"})

    def test_protected_slot_resolves_correctly(self):
        self.assertEqual(
            require_protected_slots({"protectedSlotMap": {"#9098A8": 1}}, {"#9098A8": "Grey"}),
            {1: "Grey"},
        )

    def test_physical_anchor_enforced_not_nearest_mix(self):
        anchors = [
            {"key": "Panchroma|#08ABFB", "name": "Cyan", "color": "#08ABFB"},
            {"key": "Panchroma|#9199A4", "name": "Grey", "color": "#9199A4"},
        ]
        slot, row = solid_anchor_choice(
            "#9098A8", "Panchroma|#9199A4", anchors,
            lambda anchor, key: anchor["key"] == key,
            lambda anchor: anchor["color"],
            lambda anchor: anchor["name"], error,
        )
        self.assertEqual(slot, 2)
        self.assertEqual(row[3], "SOLID")
        self.assertEqual(row[7], "#9199A4")
        self.assertEqual(row[5:7], ["", ""])

    def test_missing_physical_filament_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not uniquely available"):
            solid_anchor_choice("#9098A8", "Grey", [], lambda a,k: False,
                                lambda a: a["color"], lambda a:a["name"], error)

    def test_full_engine_build_palette_skips_mix_for_protected_slot(self):
        # Run this integrated regression in the repository; the standalone patch
        # package also runs without requiring a copy of the entire engine.
        repo_root = Path(__file__).resolve().parents[1]
        if not (repo_root / "fullspectrum_engine.py").is_file():
            self.skipTest("Full engine only exists in the target repository")
        from unittest.mock import patch
        import fullspectrum_engine as engine
        anchors = [
            {"name": "Cyan", "series": "Panchroma", "color": "#08ABFB"},
            {"name": "Grey", "series": "Panchroma", "color": "#9199A4"},
        ]
        with patch.object(engine, "best_mix_recipe", side_effect=AssertionError("Mixer called for protected slot")):
            palette = engine.build_palette(
                ["#9098A8"], anchors, quality_bias=50,
                protected_slots={1: "Panchroma|#9199A4"},
            )
        rows = palette[-1]
        self.assertEqual(rows[0][1], 2)
        self.assertEqual(rows[0][3], "SOLID")
        self.assertEqual(rows[0][7], "#9199A4")
        self.assertEqual(palette[4], {1: 2})
        self.assertEqual(palette[1], ["0", "0"])

    def test_protect_every_face_handles_bambu_minimum_two_slots(self):
        palette, assignment, protected = protected_import_palette(
            ["#9098A8"], ["#9098A8"], fake_palette, error, 32)
        self.assertEqual(palette[0], "#9098A8")
        self.assertEqual(len(palette), 2)
        self.assertEqual(assignment["#9098A8"], 1)
        self.assertEqual(protected["#9098A8"], 1)


if __name__ == "__main__":
    unittest.main()
