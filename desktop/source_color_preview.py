"""Exact-color display geometry for small standard colored 3MF models.

This is a display-only path. It never changes the engine's source mesh or
filament assignments. Large models continue using the existing bounded OBJ
preview rather than loading millions of faces into a GUI.
"""
from pathlib import Path
from zipfile import ZipFile

PREVIEW_FACE_LIMIT = 16_000
PREVIEW_VERTEX_LIMIT = 85_000


def normalized_vertices(vertices, faces):
    used = {idx for face in faces for idx in face[:3]}
    if not used:
        raise ValueError("Preview contains no visible triangles")
    low = [min(vertices[i][a] for i in used) for a in range(3)]
    high = [max(vertices[i][a] for i in used) for a in range(3)]
    center = [(a+b)/2 for a,b in zip(low, high)]
    size = max(b-a for a,b in zip(low,high)) or 1.0
    return [tuple((p[a]-center[a])/size for a in range(3)) for p in vertices]


def read_standard_color_mesh(path):
    """Keep original triangles and per-face HEX identities for UI highlighting."""
    from standard_3mf_import import _read_colored_meshes, _model_part

    with ZipFile(path) as archive:
        model = _model_part(archive)
        # Avoid loading huge model XML for an optional visualization.
        if archive.getinfo(model).file_size > 15 * 1024 * 1024:
            raise ValueError("Standard 3MF is too large for an exact-color viewport")
        positions, triangles, hexes, _ = _read_colored_meshes(
            archive, PREVIEW_FACE_LIMIT + 1
        )
    if len(triangles) > PREVIEW_FACE_LIMIT or len(positions) > PREVIEW_VERTEX_LIMIT:
        raise ValueError("Model exceeds the exact-color viewport budget")
    if not positions or not triangles:
        raise ValueError("Model does not contain colored triangle faces")
    faces = [(a,b,c,tuple(int(color[i:i+2],16) for i in (1,3,5)),color)
             for (a,b,c),color in zip(triangles, hexes)]
    return normalized_vertices(positions, faces),faces
