"""Import 3MF material-extension color groups into a Bambu paint-compatible stage.

This module intentionally does not reinterpret third-party ``paint_color`` or
PrusaSlicer segmentation attributes. 3MF color-group properties are the source
of truth. It preserves mesh vertices/faces and maps each face to an RGB target.
"""

from collections import Counter
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import re
import xml.etree.ElementTree as ET

CORE = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
MATERIAL = "{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}"
RELATIONSHIP_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
MAX_MODEL_XML_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_FACES = 2_000_000
UNITS_TO_MM = {
    "millimeter": 1.0,
    "micron": 0.001,
    "centimeter": 10.0,
    "meter": 1000.0,
    "inch": 25.4,
    "foot": 304.8,
}


class UnsupportedColored3MF(ValueError):
    """A valid 3MF uses features not yet supported by this importer."""


def _model_part(archive):
    """Find the 3D model relationship rather than assuming a fixed filename."""
    names = set(archive.namelist())
    if "_rels/.rels" in names:
        relationships = ET.fromstring(archive.read("_rels/.rels"))
        for rel in relationships:
            if rel.attrib.get("Type") != RELATIONSHIP_TYPE:
                continue
            target = rel.attrib.get("Target", "").replace("\\", "/")
            name = target.lstrip("/")
            if name not in names or ".." in Path(name).parts:
                raise UnsupportedColored3MF("3MF model relationship references a missing or unsafe part")
            return name
    if "3D/3dmodel.model" in names:
        return "3D/3dmodel.model"
    candidates = [name for name in names if name.lower().endswith(".model") and name.startswith("3D/")]
    if len(candidates) == 1:
        return candidates[0]
    raise UnsupportedColored3MF("Cannot identify the primary 3MF model part")


def _hex_color(value):
    if not re.fullmatch(r"#[\da-fA-F]{6}(?:[\da-fA-F]{2})?", value or ""):
        raise UnsupportedColored3MF(f"Invalid 3MF material color {value!r}")
    if len(value) == 9 and value[-2:].upper() != "FF":
        raise UnsupportedColored3MF("Transparent 3MF vertex colors are not yet supported")
    return value[:7].upper()


def _matrix(value):
    if not value:
        return None
    try:
        nums = [float(item) for item in value.split()]
    except ValueError as exc:
        raise UnsupportedColored3MF("Invalid build-item transformation") from exc
    if len(nums) != 12 or any(not (-1e9 < item < 1e9) for item in nums):
        raise UnsupportedColored3MF("Unsupported 3MF build-item transformation")
    return nums


def _transform(point, matrix, scale):
    x, y, z = point
    if matrix:
        a, b, c, d, e, f, g, h, i, j, k, l = matrix
        x, y, z = (a*x + d*y + g*z + j,
                   b*x + e*y + h*z + k,
                   c*x + f*y + i*z + l)
    return (x*scale, y*scale, z*scale)


def _read_colored_meshes(archive, max_faces):
    part = _model_part(archive)
    info = archive.getinfo(part)
    if info.file_size > MAX_MODEL_XML_BYTES:
        raise UnsupportedColored3MF("3MF model XML exceeds the safe import size")
    root = ET.fromstring(archive.read(part))
    if root.tag != CORE + "model":
        raise UnsupportedColored3MF("Primary 3MF part is not a core 3MF model")
    unit = root.get("unit", "millimeter")
    if unit not in UNITS_TO_MM:
        raise UnsupportedColored3MF(f"Unsupported 3MF model unit: {unit}")
    scale = UNITS_TO_MM[unit]
    resources = root.find(CORE + "resources")
    build = root.find(CORE + "build")
    if resources is None or build is None:
        raise UnsupportedColored3MF("3MF lacks resources or build items")
    color_groups = {}
    objects = {}
    for element in resources:
        if element.tag == MATERIAL + "colorgroup":
            group_id = element.get("id")
            if group_id in color_groups:
                raise UnsupportedColored3MF("Duplicate 3MF color-group ID")
            color_groups[group_id] = [_hex_color(item.get("color"))
                                      for item in element if item.tag == MATERIAL + "color"]
        elif element.tag == CORE + "object":
            objects[element.get("id")] = element
    if not color_groups:
        raise UnsupportedColored3MF("3MF has no material-extension color groups (m:colorgroup)")

    positions, faces, colors = [], [], []
    blended_corners = 0
    for instance in build.findall(CORE + "item"):
        obj = objects.get(instance.get("objectid"))
        if obj is None:
            raise UnsupportedColored3MF("3MF build item references an unavailable mesh object")
        mesh = obj.find(CORE + "mesh")
        if mesh is None:
            raise UnsupportedColored3MF("Component-based 3MF objects are not yet supported")
        vertices = mesh.find(CORE + "vertices")
        triangles = mesh.find(CORE + "triangles")
        if vertices is None or triangles is None:
            raise UnsupportedColored3MF("3MF mesh lacks vertices or triangles")
        matrix = _matrix(instance.get("transform"))
        offset = len(positions)
        for item in vertices.findall(CORE + "vertex"):
            try:
                point = tuple(float(item.get(axis)) for axis in ("x", "y", "z"))
            except (ValueError, TypeError) as exc:
                raise UnsupportedColored3MF("Invalid 3MF vertex coordinates") from exc
            positions.append(_transform(point, matrix, scale))
        vertex_count = len(positions) - offset
        for triangle in triangles.findall(CORE + "triangle"):
            if len(faces) >= max_faces:
                raise UnsupportedColored3MF(f"3MF exceeds {max_faces:,} triangles")
            try:
                vertices_idx = tuple(int(triangle.get(f"v{i}")) for i in (1,2,3))
            except (TypeError, ValueError) as exc:
                raise UnsupportedColored3MF("Invalid 3MF triangle vertex index") from exc
            if any(idx < 0 or idx >= vertex_count for idx in vertices_idx):
                raise UnsupportedColored3MF("3MF triangle references an invalid vertex")
            group = color_groups.get(triangle.get("pid", obj.get("pid")))
            if group is None:
                raise UnsupportedColored3MF("3MF triangle has no supported color-group assignment")
            try:
                first = int(triangle.get("p1", obj.get("pindex", "0")))
                ids = (first, int(triangle.get("p2", first)), int(triangle.get("p3", first)))
                corners = [group[idx] for idx in ids]
            except (TypeError, ValueError, IndexError) as exc:
                raise UnsupportedColored3MF("3MF triangle references an invalid color-group index") from exc
            if len(set(corners)) > 1:
                blended_corners += 1
                components = [tuple(int(color[i:i+2],16) for i in (1,3,5)) for color in corners]
                face_color = "#{:02X}{:02X}{:02X}".format(*(round(sum(c[j] for c in components)/3) for j in range(3)))
            else:
                face_color = corners[0]
            faces.append(tuple(offset + i for i in vertices_idx))
            colors.append(face_color)
    if not faces:
        raise UnsupportedColored3MF("3MF has no colored mesh triangles")
    return positions, faces, colors, blended_corners


def source_color_counts(source, max_faces=DEFAULT_MAX_FACES):
    """List actual face colors before source-slot quantization, for the override UI."""
    with ZipFile(source) as archive:
        _, _, colors, _ = _read_colored_meshes(archive, max_faces)
    return dict(Counter(colors).most_common())


def protected_import_palette(colors, protected_colors, kmeans_colors, color_distance, max_paint_slots):
    """Keep protected colors in dedicated slots; never cluster unprotected faces into them."""
    distinct = set(colors)
    selected = []
    for color in protected_colors:
        normalized = str(color).upper()
        if normalized in selected:
            continue
        if normalized not in distinct:
            raise UnsupportedColored3MF(f"Protected source color {normalized} is not present in the 3MF")
        selected.append(normalized)
    unprotected = [color for color in colors if color not in set(selected)]
    if len(selected) + int(bool(unprotected)) > max_paint_slots:
        raise UnsupportedColored3MF("Too many solid-color overrides for the available 3MF paint slots")
    remaining = max_paint_slots - len(selected)
    other_palette, other_assignment = (kmeans_colors(unprotected, min(remaining, len(set(unprotected))))
                                       if unprotected else ([], {}))
    palette = selected + other_palette
    assignments = {color: index + 1 for index, color in enumerate(selected)}
    assignments.update({color: slot + len(selected) for color, slot in other_assignment.items()})
    if len(palette) == 1:
        # Existing Bambu importer requires at least two input slots.
        alternative = "#000000" if color_distance(palette[0], "#000000") > color_distance(palette[0], "#FFFFFF") else "#FFFFFF"
        palette.append(alternative)
    return palette, assignments, {color: index + 1 for index, color in enumerate(selected)}


def import_colored_3mf_project(source, destination, *, kmeans_colors,
                               paint_code_for_slot, basic_project_settings,
                               color_distance, max_paint_slots=32,
                               max_faces=DEFAULT_MAX_FACES, progress=None, protected_source_colors=()):
    """Convert material-colored 3MF into an intermediate Bambu paint-state 3MF.

    The converted project is the input to the unchanged FullSpectrum planner.
    Clustering is unavoidable for models with more than 32 distinct colors
    until the planner accepts RGB targets separately from paint slot IDs.
    """
    source, destination = Path(source), Path(destination)
    if progress:
        progress(0.05, "Reading standard colored 3MF face assignments")
    with ZipFile(source) as archive:
        positions, faces, raw_colors, blended = _read_colored_meshes(archive, max_faces)
    counts = Counter(raw_colors)
    palette, assignments, protected_slots = protected_import_palette(
        raw_colors, protected_source_colors, kmeans_colors, color_distance, max_paint_slots
    )
    if not palette:
        raise UnsupportedColored3MF("Could not build a source color palette")
    if progress:
        progress(0.10, f"Imported {len(faces):,} triangles, {len(counts)} RGB colors, {len(palette)} paint slots")

    vertex_xml = [f'<vertex x="{x:.17g}" y="{y:.17g}" z="{z:.17g}"/>' for x,y,z in positions]
    tri_xml = [f'<triangle v1="{a}" v2="{b}" v3="{c}" paint_color="{paint_code_for_slot(assignments[color])}"/>'
               for (a,b,c),color in zip(faces,raw_colors)]
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
             '<resources><object id="1" type="model"><mesh><vertices>\n'
             + '\n'.join(vertex_xml) + '\n</vertices><triangles>\n'
             + '\n'.join(tri_xml) + '\n</triangles></mesh></object></resources>\n'
             '<build><item objectid="1"/></build></model>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '<Default Extension="config" ContentType="application/octet-stream"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/Objects/object_1.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            '</Relationships>')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("Metadata/project_settings.config", json.dumps(basic_project_settings(palette)))
        archive.writestr("3D/Objects/object_1.model", model)
    return {
        "sourceType": "Standard colored 3MF",
        "vertexCount": len(positions),
        "triangleCount": len(faces),
        "internalColorCount": len(counts),
        "exportColorCount": len(palette),
        "compressedForBambu": len(counts) > len(palette),
        "perVertexColorFacesApproximated": blended,
        "protectedSlotMap": protected_slots,
    }
