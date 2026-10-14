"""Regression tests for standard 3MF color-group import (no printer needed)."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from standard_3mf_import import UnsupportedColored3MF, import_colored_3mf_project


def make_source(path, colors=("#000000FF", "#08ABFBFF"), pid="1", p1="0", p2=None,
                face_count=1, transform="", object_id="2"):
    p2attr = f' p2="{p2}"' if p2 is not None else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02" unit="millimeter">'
        '<resources><m:colorgroup id="1">'
        + ''.join(f'<m:color color="{c}"/>' for c in colors)
        + '</m:colorgroup><object id="2" type="model"><mesh><vertices>'
        '<vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>'
        '<vertex x="0" y="1" z="0"/></vertices><triangles>'
        + ''.join(f'<triangle v1="0" v2="1" v3="2" pid="{pid}" p1="{p1}"{p2attr}/>'
                  for _ in range(face_count))
        + '</triangles></mesh></object></resources>'
        + f'<build><item objectid="{object_id}" transform="{transform}"/></build></model>'
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", xml)


def fake_palette(colors, maximum):
    unique = list(dict.fromkeys(colors))[:maximum]
    return unique, {color: unique.index(color) + 1 if color in unique else 1 for color in colors}


def import_file(source, output, **kwargs):
    return import_colored_3mf_project(
        source, output, kmeans_colors=fake_palette,
        paint_code_for_slot=lambda slot: {1: "4", 2: "8", 3: "0C"}[slot],
        basic_project_settings=lambda colors: {"filament_colour": colors},
        color_distance=lambda a, b: sum((int(a[i:i+2], 16)-int(b[i:i+2],16))**2 for i in (1,3,5)),
        **kwargs
    )


class StandardColored3MFTests(unittest.TestCase):
    def test_import_preserves_geometry_and_translates_color_group(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td)/"source.3mf", Path(td)/"staged.3mf"
            make_source(source, p1="1")
            result = import_file(source, output)
            self.assertEqual(result["triangleCount"], 1)
            self.assertEqual(result["vertexCount"], 3)
            self.assertEqual(result["internalColorCount"], 1)
            with ZipFile(output) as archive:
                root = ET.fromstring(archive.read("3D/Objects/object_1.model"))
                self.assertEqual(len(root.findall(".//{*}triangle")), 1)
                self.assertEqual(root.find(".//{*}triangle").get("paint_color"), "4")
                self.assertEqual(json.loads(archive.read("Metadata/project_settings.config"))["filament_colour"][0], "#08ABFB")

    def test_instance_translation_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, transform="1 0 0 0 1 0 0 0 1 5 6 7")
            import_file(src, dst)
            with ZipFile(dst) as archive:
                root = ET.fromstring(archive.read("3D/Objects/object_1.model"))
                self.assertEqual(tuple(float(root.find(".//{*}vertex").get(a)) for a in ("x", "y", "z")), (5.,6.,7.))

    def test_vertex_color_variation_warns_and_averages(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, p1="0", p2="1")
            result = import_file(src, dst)
            self.assertEqual(result["perVertexColorFacesApproximated"], 1)

    def test_invalid_material_reference_does_not_silently_drop_color(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, pid="999")
            with self.assertRaisesRegex(UnsupportedColored3MF, "color-group"):
                import_file(src, dst)

    def test_invalid_index_fails(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, p1="99")
            with self.assertRaisesRegex(UnsupportedColored3MF, "color-group index"):
                import_file(src, dst)

    def test_transparent_color_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, colors=("#00000080", "#08ABFBFF"))
            with self.assertRaisesRegex(UnsupportedColored3MF, "Transparent"):
                import_file(src, dst)

    def test_build_missing_object_fails(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"a.3mf", Path(td)/"b.3mf"
            make_source(src, object_id="700")
            with self.assertRaisesRegex(UnsupportedColored3MF, "unavailable mesh"):
                import_file(src, dst)


if __name__ == "__main__":
    unittest.main()
