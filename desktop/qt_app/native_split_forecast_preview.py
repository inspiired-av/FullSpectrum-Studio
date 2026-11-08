"""Read-only, lossless-facet native split-paint *forecast visualization*.

The native optimizer's plan-only OBJ approximation assigns ONE slot to each
source triangle, so complex Bambu split-face paint vanishes from Predicted,
Loss, and Influence overlays. This module instead recolors the already-decoded
Qt display facets with the optimizer's existing per-SOURCE-slot recipes.

Never modifies a source 3MF, planned output, paint tree, or export path.
Unsupported/ambiguous source provenance fails closed to the existing forecast.
Full paint-region AREA-aware planner weights are a separate future task.
"""
from __future__ import annotations

from array import array
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import struct
from zipfile import ZipFile

MAX_FORECAST_DISPLAY_FACES = 750_000
MAX_SNIFF_XML_BYTES = 90_000_000
PAINT_ATTR = re.compile(rb'\bpaint_color\s*=\s*[\"\']([0-9A-Fa-f]+)[\"\']')
RGB = re.compile(r'^#[0-9A-Fa-f]{6}$')


def enabled():
    """Experimental by explicit opt-in; diagnostic mode cannot change exports."""
    return os.environ.get('FULLSPECTRUM_NATIVE_SPLIT_FORECAST', '0').strip().lower() in (
        '1', 'true', 'yes', 'on')


def has_native_split_paint(path):
    """Cheap streaming probe; paint leaf nibble's lower two bits signal splitting.

    Scans only local 3MF object XML members, and never extracts paths to disk.
    Malformed or huge archives defer to the existing engine validations.
    """
    if Path(path).suffix.lower() != '.3mf':
        return False
    with ZipFile(path) as archive:
        names = [i for i in archive.infolist()
                 if i.filename.startswith('3D/Objects/') and i.filename.endswith('.model')]
        if len(names) > 512 or any(info.file_size > MAX_SNIFF_XML_BYTES for info in names):
            return False
        for info in names:
            with archive.open(info) as stream:
                for line in stream:
                    for m in PAINT_ATTR.finditer(line):
                        if int(m.group(1)[-1:], 16) & 0x03:
                            return True
    return False


def _read_unique_native_swatches(path, source_slots):
    with ZipFile(path) as archive:
        info = archive.getinfo('Metadata/project_settings.config')
        if info.file_size > 12_000_000:
            raise ValueError('Native filament settings exceed safety budget')
        data = json.loads(archive.read(info))
        # A standard 3MF color resource can take precedence over the slicer's
        # assigned physical slot. RGB equality would NOT prove slot identity.
        # This first implementation supports native slot paint only; reject
        # hybrid color-property models until explicit per-face IDs are carried.
        models = [item for item in archive.infolist() if
                  item.filename.startswith('3D/') and item.filename.endswith('.model')]
        if len(models) > 512 or any(item.file_size > MAX_SNIFF_XML_BYTES for item in models):
            raise ValueError('Native 3MF model resources exceed preview attribution limits')
        for item in models:
            with archive.open(item) as stream:
                for line in stream:
                    if (b'pid=' in line or b'<colorgroup' in line or
                            b'<basematerials' in line or b'<texture2dgroup' in line):
                        raise ValueError('Hybrid 3MF material/texture properties need explicit face provenance')
    if not isinstance(data, dict):
        raise ValueError('Native project settings must contain a JSON object')
    colors = data.get('filament_colour')
    if not isinstance(colors, list) or len(colors) != source_slots:
        raise ValueError('Native filament slots do not match the optimized plan')
    if not all(isinstance(c, str) and RGB.fullmatch(c) for c in colors):
        raise ValueError('Native swatches are not all unambiguous six-digit RGB colors')
    mixed = data.get('filament_is_mixed') or ()
    if mixed and (len(mixed) != len(colors) or any(str(v) != '0' for v in mixed)):
        raise ValueError('Native SOURCE mixed-filament slots require separate provenance handling')
    colors = [color.upper() for color in colors]
    if len(set(colors)) != len(colors):
        raise ValueError('Multiple source filament slots share an RGB swatch; cannot infer source slot from color')
    return colors


def _recipe_rows(output, count):
    recipes = output.get('recipes')
    if not isinstance(recipes, (list, tuple)):
        raise ValueError('Optimizer did not return per-source-slot recipes')
    rows = {}
    for recipe in recipes:
        if not isinstance(recipe, dict):
            raise ValueError('Malformed optimizer recipe')
        slot = recipe.get('oldSlot')
        if type(slot) is not int or slot in rows or not 1 <= slot <= count:
            raise ValueError('Duplicate or unavailable native source slot')
        try:
            row = (slot, recipe['newSlot'], recipe['targetColor'], recipe['kind'],
                   recipe['label'], recipe['components'], recipe['ratios'],
                   recipe['preview'], recipe['deltaE'], recipe['directDeltaE'],
                   recipe['visualGain'])
        except KeyError as exc:
            raise ValueError('Incomplete native source recipe') from exc
        if not isinstance(row[7], str) or not RGB.fullmatch(row[7]):
            raise ValueError('Optimizer predicted an invalid RGB swatch')
        rows[slot] = row
    if set(rows) != set(range(1, count + 1)):
        raise ValueError('Optimizer omitted at least one native source filament slot')
    return [rows[n] for n in range(1, count + 1)]


def _flat_slots(mesh, swatches):
    faces = mesh.triangles
    colors = mesh.face_colors
    if (not getattr(mesh, 'split_painted_faces', 0) or
            mesh.source_triangles >= len(faces) or
            len(faces) > MAX_FORECAST_DISPLAY_FACES or
            len(colors) != len(faces)):
        raise ValueError('No supported complete native split-paint display mesh')
    if 'unsupported/unknown faces' in mesh.color_status.lower():
        raise ValueError('The native preview has unresolved paint regions')
    lookup = {c: i for i, c in enumerate(swatches, 1)}
    slots = []
    corners = mesh.corner_colors
    if len(corners) == len(faces):
        for c, triple in zip(colors, corners):
            if triple != (c, c, c):
                raise ValueError('Vertex gradients need distinct source-slot provenance')
    for color in colors:
        if not isinstance(color, str) or color.upper() not in lookup:
            raise ValueError('A displayed face color does not uniquely identify a source filament slot')
        slots.append(lookup[color.upper()])
    return slots


def _paint_rgb(packed, colors, source_slots):
    """Change display RGB only (float indices 6:9); keep ORIGINAL source tags.

    The influence pathway separately overwrites tag.r with the exact 1-based
    source slot from the generated face map. Every overlay is a detached array.
    """
    if len(packed) != len(source_slots) * 36:
        raise ValueError('Packed vertices do not align with split-paint facets')
    out = array('f', packed)
    rgb = [tuple(int(color[j:j+2], 16)/255 for j in (1, 3, 5)) for color in colors]
    triplets = [array('f', color) for color in rgb]
    for i, slot in enumerate(source_slots):
        color = triplets[slot - 1]
        start = i * 36
        for off in (6, 18, 30):
            out[start + off:start + off + 3] = color
    return out


def _write_slots(analysis_root, slots):
    """Version-compatible per-facet u32 provenance for existing Anchor Influence."""
    root = Path(analysis_root).resolve()
    if not root.is_dir():
        raise ValueError('Missing private forecast analysis directory')
    dest = root / 'source-face-slots-split.bin'
    tmp = dest.with_suffix('.bin.tmp')
    try:
        with tmp.open('wb') as target:
            for i in range(0, len(slots), 8192):
                part = slots[i:i+8192]
                target.write(struct.pack(f'<{len(part)}I', *part))
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return str(dest)


def build_overlays(path, output, analysis_root, *, loader=None, flattener=None,
                   indexer=None, color_plan=None):
    """Return ({mode: PreviewMesh}, sourceSlotMap path) for *valid* native splits.

    Caller must first check has_native_split_paint(). All work happens on the
    forecast worker, before its TemporaryDirectory is removed. Substitutions
    are atomic from the caller's perspective: any error preserves old overlays.
    """
    if loader is None:
        from desktop.qt_app.mesh_loader import load_preview_mesh
        loader = load_preview_mesh
    if flattener is None:
        from desktop.qt_app.preview_shading import flatten_faces
        flattener = flatten_faces
    if indexer is None:
        from desktop.qt_app.preview_indexed_mode import prepare_indexed_preview
        indexer = prepare_indexed_preview
    if color_plan is None:
        import fullspectrum_engine as engine
        color_plan = engine.plan_analysis_preview_colors

    if output.get('type') != 'planPreview':
        raise ValueError('Native paint overlay requires a read-only plan forecast')
    count = output.get('sourceSlots')
    if type(count) is not int or count < 1 or count > 2047:
        raise ValueError('Unsupported number of native source slots')
    swatches = _read_unique_native_swatches(path, count)
    rows = _recipe_rows(output, count)
    real_slots = output.get('realSlots')
    if type(real_slots) is not int or real_slots < 1 or real_slots > 8:
        raise ValueError('Invalid physical slot count')
    color_sets = color_plan(swatches, rows, real_slots)
    if len(color_sets) != 3 or any(len(values) != count for values in color_sets):
        raise ValueError('Engine forecast overlays do not align to source slots')
    if any(not all(isinstance(v, str) and RGB.fullmatch(v) for v in values)
           for values in color_sets):
        raise ValueError('Engine returned invalid overlay colors')

    source = loader(path)
    slots = _flat_slots(source, swatches)
    expanded = flattener(source)
    if not isinstance(expanded, array) or expanded.typecode != 'f':
        raise ValueError('Source preview flattener produced an incompatible GPU buffer')
    overlays = {}
    for mode, palette in zip(('predicted', 'loss', 'influence'), color_sets):
        colors = tuple(palette[slot-1].upper() for slot in slots)
        prepared = _paint_rgb(expanded, palette, slots)
        # Influence replaces GPU source tags with slot IDs downstream. Index
        # only AFTER those tags have been patched, or the indexed VBO would
        # retain stale RGB tags and interactive influence would be incorrect.
        candidate = indexer(prepared) if mode != 'influence' else None
        overlays[mode] = replace(
            source, face_colors=colors,
            corner_colors=tuple((color,) * 3 for color in colors),
            render_buffer=prepared, render_indexed=candidate,
            load_profile=None,
            color_status='Native split-paint display facets · read-only forecast')
    slot_path = _write_slots(analysis_root, slots)
    return overlays, slot_path
