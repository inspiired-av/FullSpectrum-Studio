"""Safe Stage 4C read-only forecast overlay loading; no Qt GUI or 3MF writes.

The engine owns color prediction and loss mapping. Load only its plan-only
analysis OBJ/MTL assets while its temporary workspace still exists.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from array import array

# Three meshes at this cap can already take hundreds of MB; don't silently
# downsample geometry, because skipping triangles damages closed surfaces.
MAX_PREVIEW_TRIANGLES = 750_000
MAX_OBJ_BYTES = 64 * 1024 * 1024
ASSETS = (
    ('predicted', 'predictedMesh'),
    ('loss', 'heatmapMesh'),
    ('influence', 'anchorInfluenceMesh'),
)


def recolor_buffer(previous_mesh, new_mesh):
    """Reuse prepared normals when the engine's OBJ variants share topology.

    Replaces per-face diffuse RGB and face tags only. Never mutates the
    previous mode's vertex buffer or source preview. Called on worker thread.
    """
    base=getattr(previous_mesh, 'render_buffer', None)
    if base is None or not isinstance(base, array) or base.typecode != 'f':
        return None
    if previous_mesh.vertices != new_mesh.vertices or previous_mesh.triangles != new_mesh.triangles:
        return None
    face_colors=new_mesh.face_colors
    if len(face_colors) != len(new_mesh.triangles) or len(base) != len(face_colors)*36:
        return None
    packed=array('f',base)
    for i,hex_color in enumerate(face_colors):
        if not isinstance(hex_color,str) or len(hex_color) != 7 or not hex_color.startswith('#'):
            return None
        try:
            rgb=tuple(int(hex_color[j:j+2],16)/255.0 for j in (1,3,5))
        except ValueError:
            return None
        start=i*36
        for vertex in range(3):
            offset=start+vertex*12
            packed[offset+6:offset+9]=array('f',rgb)
            packed[offset+9:offset+12]=array('f',rgb)
    return packed


def load_forecast_previews(analysis_assets, analysis_root, loader=None, flattener=None):
    """Return ({mode: PreviewMesh}, optional warning) from engine-authored assets.

    Only locally generated files beneath analysis_root are accepted. No URL,
    absolute path outside the temporary workspace or user-provided file is read.
    Geometry/normals are prepared on the worker, not the Qt UI thread.
    """
    if not isinstance(analysis_assets, dict):
        return {}, 'This forecast did not generate a predicted 3D analysis mesh.'
    if loader is None:
        from desktop.qt_app.mesh_loader import load_preview_mesh
        loader = load_preview_mesh
    if flattener is None:
        from desktop.qt_app.preview_shading import flatten_faces
        flattener = flatten_faces
    root = Path(analysis_root).resolve()
    preview_meshes = {}
    warnings = []
    for mode, key in ASSETS:
        source = analysis_assets.get(key)
        if not source:
            continue
        try:
            path = Path(source).resolve()
            path.relative_to(root)
            if path.suffix.lower() != '.obj':
                raise ValueError('engine preview is not an OBJ')
            if not path.is_file() or not path.with_suffix('.mtl').is_file():
                raise ValueError('matching OBJ/MTL preview pair is missing')
            if path.stat().st_size > MAX_OBJ_BYTES:
                raise ValueError('preview is too large for responsive display')
            mesh = loader(path)
            if not getattr(mesh, 'face_colors', ()) or not any(mesh.face_colors):
                raise ValueError('preview has no diffuse material colors')
            if len(mesh.triangles) > MAX_PREVIEW_TRIANGLES:
                raise ValueError('preview exceeds the safe interactive triangle limit')
            # All engine-generated overlays share a geometry source. A
            # prepared-buffer recolor avoids expensive repeated normal smoothing
            # on large painted models; fallback keeps unequal meshes correct.
            first=next(iter(preview_meshes.values()),None)
            prepared=recolor_buffer(first,mesh) if first is not None else None
            mesh = replace(mesh, render_buffer=prepared if prepared is not None else flattener(mesh))
            preview_meshes[mode] = mesh
        except (OSError, ValueError, TypeError, KeyError) as exc:
            warnings.append(f'{mode.title()} view unavailable: {exc}')
    if not preview_meshes:
        warnings.append('No compatible 3D analysis overlay was returned by the planner.')
    return preview_meshes, ' '.join(warnings)
