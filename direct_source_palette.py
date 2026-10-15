"""Direct 3MF source-color targets for FullSpectrum Studio phase 3.

The preexisting standard-3MF importer remains responsible for geometry. This
module supplies unquantized source targets and repaints their original facets
after the engine has selected <=32 final output filament slots.
"""
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import re

from standard_3mf_import import _read_colored_meshes

_TRIANGLE_PAINT = re.compile(rb'(<triangle\b[^>]*?\bpaint_color=")([^"]*)(")')


def load_exact_color_targets(source, max_faces=2_000_000):
    """Return ordered, exact face-color targets and source weighting by face count.

    This follows the very same validated importer used for intermediate geometry
    generation; neither 32-state quantization nor mixture prediction is involved.
    """
    with ZipFile(source) as archive:
        vertices, faces, face_colors, approximated = _read_colored_meshes(archive, max_faces)
    if len(faces) != len(face_colors):
        raise RuntimeError("Exact color importer returned inconsistent face assignments")
    colors = list(dict.fromkeys(face_colors))
    if not colors or len(colors) > max_faces:
        raise RuntimeError("No valid source face-color targets")
    source_slots = {color: i for i, color in enumerate(colors, 1)}
    usage = Counter(source_slots[color] for color in face_colors)
    return {
        "colors": colors,
        "vertices": vertices,
        "faces": faces,
        "face_colors": face_colors,
        "usage": usage,
        "source_slots": source_slots,
        "triangle_count": len(face_colors),
        "approximate_vertex_blends": approximated,
    }


def mapped_source_paint_colors(source_data, source_slot_mapping, encode_slot, output_slots):
    """Make a final Bambu paint state for every original face, in importer order."""
    slot_by_color = {}
    for color, old_slot in source_data["source_slots"].items():
        output_slot = source_slot_mapping.get(old_slot)
        if type(output_slot) is not int or not 1 <= output_slot <= output_slots:
            raise RuntimeError(f"Exact source color {color} lacks a printable output slot")
        slot_by_color[color] = encode_slot(output_slot)
    return [slot_by_color[color] for color in source_data["face_colors"]]


def rewrite_staged_faces(directory, encoded_face_colors):
    """Replace just the imported facet paint states, preserving all mesh geometry.

    Only standard material-colored 3MF imports use the single deterministic mesh
    part emitted by import_colored_3mf_project. Never run on arbitrary native 3MF.
    """
    source = Path(directory) / "3D" / "Objects" / "object_1.model"
    if not source.is_file():
        raise RuntimeError("The intermediate colored 3MF does not contain its expected mesh part")
    xml = source.read_bytes()
    count = 0

    def replace(match):
        nonlocal count
        if count >= len(encoded_face_colors):
            raise RuntimeError("Intermediate 3MF has more painted triangles than the original")
        paint = encoded_face_colors[count]
        if not isinstance(paint, str) or not re.fullmatch("[0-9A-Fa-f]+", paint):
            raise RuntimeError("Generated an invalid 3MF paint state")
        count += 1
        return match.group(1) + paint.encode("ascii") + match.group(3)

    patched = _TRIANGLE_PAINT.sub(replace, xml)
    if count != len(encoded_face_colors):
        raise RuntimeError(
            f"Triangle mismatch while restoring source colors: {count} intermediate, "
            f"{len(encoded_face_colors)} source"
        )
    # Atomic replacement to avoid partially rewritten geometry if disk I/O fails.
    temporary = source.with_suffix(".model.phase3.tmp")
    try:
        temporary.write_bytes(patched)
        temporary.replace(source)
    finally:
        temporary.unlink(missing_ok=True)
    return [source.relative_to(directory).as_posix()], Counter(encoded_face_colors)


def fallback_representatives(staged_colors, output_colors, distance):
    """Map each physical/mixed slot onto an existing staging property block.

    The original 32-color stage only supplies baseline material settings. Its
    nearest property representative is *not* used for color planning or paint.
    """
    if not staged_colors:
        raise RuntimeError("No source material-property templates are available")
    return [min(range(1, len(staged_colors) + 1),
                key=lambda slot: distance(staged_colors[slot-1], color))
            for color in output_colors]


def write_predicted_obj(source_data, source_slot_mapping, output_colors, destination):
    """Create an honest direct-source predicted preview without intermediate colors.

    OBJ/MTL files are display-only. This never alters the exported 3MF mesh.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mtl_path = destination.with_suffix(".mtl")
    vertices = source_data["vertices"]
    faces = source_data["faces"]
    face_colors = source_data["face_colors"]
    if not (len(faces) == len(face_colors)):
        raise RuntimeError("Direct preview has inconsistent face counts")
    with mtl_path.open("w", encoding="utf-8", newline="\n") as material:
        for index, color in enumerate(output_colors, 1):
            channel = tuple(int(color[p:p+2], 16) / 255 for p in (1,3,5))
            material.write(
                f"newmtl predicted_{index}\n"
                f"Kd {channel[0]:.6f} {channel[1]:.6f} {channel[2]:.6f}\n"
                "Ka 0 0 0\nNs 20\n\n"
            )
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        output.write(f"mtllib {mtl_path.name}\n")
        for x, y, z in vertices:
            output.write(f"v {x:.17g} {y:.17g} {z:.17g}\n")
        previous = None
        for face, color in zip(faces, face_colors):
            old_slot = source_data["source_slots"][color]
            slot = source_slot_mapping[old_slot]
            if slot != previous:
                output.write(f"usemtl predicted_{slot}\n")
                previous = slot
            a, b, c = face
            output.write(f"f {a+1} {b+1} {c+1}\n")
    return destination


def globally_reassign_colors(source_colors, palette, anchors, protected_slots, distance,
                             anchor_name, anchor_color):
    """Map each unprotected *original* color to its closest available output slot.

    Phase 3 v1 chose the best independent recipe for a color, but discarded it
    if that recipe was excluded by the 32-slot budget. It then retained the
    nearest PHYSICAL filament, even when an existing mixed output color was a
    far better approximation. That can produce extreme green->grey fallbacks.

    This safe reassignment does not add/rearrange/rewrite recipes. It only
    corrects the face-to-output-slot mapping and row metrics. Thus no unlocked
    source color can have a higher Delta E afterwards, the output slot count is
    unchanged, and protected source colors keep their physical assignments.
    """
    newc, is_mixed, components, ratios, old_map, rows = palette
    real_count = len(anchors)
    if not 1 <= real_count <= len(newc) <= 32:
        raise RuntimeError("Direct palette slot counts are inconsistent")
    if not (len(newc)==len(is_mixed)==len(components)==len(ratios)):
        raise RuntimeError("Direct palette filament arrays have mismatched lengths")
    if len(rows) != len(source_colors) or len(old_map) != len(source_colors):
        raise RuntimeError("Direct palette has lost original source-color references")
    protected_slots = protected_slots or {}
    out_map = dict(old_map)
    updated_rows=[]
    revised=0
    improved=0
    old_worst=0.0
    new_worst=0.0
    for old_slot, color in enumerate(source_colors, 1):
        row = rows[old_slot-1]
        if row[0]!=old_slot or row[2]!=color:
            raise RuntimeError("Direct palette rows are not aligned with original color order")
        current=old_map.get(old_slot)
        if type(current) is not int or not 1 <= current <= len(newc):
            raise RuntimeError(f"Direct source slot {old_slot} lacks a valid existing output mapping")
        before=distance(color,newc[current-1])
        if old_slot in protected_slots:
            if current>real_count or row[3]!="SOLID":
                raise RuntimeError("Protected exact source color was not assigned to a solid filament")
            # Keep solid protection authoritative even if a mixture is closer.
            updated_rows.append(row[:])
            out_map[old_slot]=current
            continue
        direct_slot=min(range(1,real_count+1),key=lambda slot:(distance(color,newc[slot-1]),slot))
        direct_error=distance(color,newc[direct_slot-1])
        closest=min(range(1,len(newc)+1),
                    key=lambda slot:(distance(color,newc[slot-1]),slot>real_count,slot))
        after=distance(color,newc[closest-1])
        if after>before+1.e-7:
            raise RuntimeError("Global color assignment unexpectedly increased an error")
        if closest!=current:
            revised+=1
        if after+1.e-7<before:
            improved+=1
        old_worst=max(old_worst,before)
        new_worst=max(new_worst,after)
        out_map[old_slot]=closest
        color_preview=newc[closest-1]
        if closest<=real_count:
            kind="ANCHOR"
            label=anchor_name(anchors[closest-1])
            comp=""
            fraction=""
        else:
            if is_mixed[closest-1]!="1" or not components[closest-1] or not ratios[closest-1]:
                raise RuntimeError(f"Slot {closest} has no valid mixed filament recipe")
            kind="MIX"
            label=""
            comp=components[closest-1]
            fraction=ratios[closest-1]
        updated_rows.append([old_slot,closest,color,kind,label,comp,fraction,
                             color_preview,f"{after:.2f}",f"{direct_error:.2f}",
                             f"{direct_error-after:.2f}"])
    return (newc,is_mixed,components,ratios,out_map,updated_rows), {
        "reassigned": revised, "improved": improved,
        "worstBefore": round(old_worst,2), "worstAfter":round(new_worst,2),
    }
