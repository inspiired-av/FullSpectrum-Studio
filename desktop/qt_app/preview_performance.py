"""Conservative preview memory budget and CPU/GL-submission telemetry.

This module is intentionally pure Python. It does not inspect or alter native
project geometry, rendering colors, export settings, or filament assignments.
GPU timings measure the *CPU call* into glBufferData, not completed GPU work.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

MIB = 1024 * 1024
BYTES_PER_DISPLAY_TRIANGLE = 3 * 12 * 4  # 3 corners x 12 float32 attributes
# These are guardrails for future LOD work, NOT a higher mesh import limit.
MAX_PREVIEW_BUFFER_BYTES = 512 * MIB
MAX_ESTIMATED_PEAK_BYTES = 2 * 1024 * MIB


@dataclass(frozen=True)
class PreviewResourceEstimate:
    vertices: int
    triangles: int
    source_triangles: int
    cpu_mesh_bytes: int
    render_buffer_bytes: int
    gpu_buffer_bytes: int
    estimated_peak_bytes: int


@dataclass(frozen=True)
class PreviewLoadProfile:
    resources: PreviewResourceEstimate
    parse_ms: float
    prepare_ms: float


def preview_resource_estimate(mesh) -> PreviewResourceEstimate:
    """Cheap, conservative *estimates*, not actual RSS/VRAM measurements.

    Counts are O(1) and deliberately avoid walking the model. Container sizes
    include approximate CPython object/tuple/float and reference overhead.
    The estimate is a budget indicator, not a benchmark of allocator usage.
    """
    vertices = len(mesh.vertices)
    triangles = len(mesh.triangles)
    source = int(mesh.source_triangles)
    if vertices < 0 or triangles < 0 or source < triangles:
        raise ValueError('Invalid preview triangle/vertex counts')
    colors = len(getattr(mesh, 'face_colors', ()) or ())
    corner_colors = len(getattr(mesh, 'corner_colors', ()) or ())
    # Float coordinate tuples, int-index tuples, optional source color refs.
    cpu_bytes = (vertices * 160 + triangles * 192 + colors * 24 +
                 corner_colors * 40)
    packed = triangles * BYTES_PER_DISPLAY_TRIANGLE
    # Model+packed CPU buffer+driver-upload budget+GPU resident allocation.
    peak = cpu_bytes + packed + packed + packed
    return PreviewResourceEstimate(vertices, triangles, source, cpu_bytes,
                                   packed, packed, peak)


def require_preview_budget(estimate: PreviewResourceEstimate, *,
                           max_buffer_bytes: int = MAX_PREVIEW_BUFFER_BYTES,
                           max_estimated_peak_bytes: int = MAX_ESTIMATED_PEAK_BYTES):
    """Preflight guard; existing source/draw triangle limits remain authoritative."""
    if estimate.render_buffer_bytes > max_buffer_bytes:
        raise ValueError(
            'Preview vertex buffer would require ' +
            _format_mib(estimate.render_buffer_bytes) + ' (limit ' +
            _format_mib(max_buffer_bytes) + '). A reduced or adaptive preview '
            'representation is required; source geometry was not modified.')
    if estimate.estimated_peak_bytes > max_estimated_peak_bytes:
        raise ValueError(
            'Estimated preview peak memory would require ' +
            _format_mib(estimate.estimated_peak_bytes) + ' (budget ' +
            _format_mib(max_estimated_peak_bytes) + '). A reduced preview '
            'representation is required; source geometry was not modified.')
    return estimate


def require_upload_budget(byte_size: int, *,
                          max_buffer_bytes: int = MAX_PREVIEW_BUFFER_BYTES):
    """Reject unsupported allocation before asking the OpenGL driver for it."""
    if not isinstance(byte_size, int) or byte_size < 0:
        raise ValueError('Invalid GPU upload buffer size')
    if byte_size > max_buffer_bytes:
        raise ValueError('Preview GPU vertex buffer exceeds the configured safety budget')
    return byte_size


def _format_mib(byte_count: int) -> str:
    return f'{byte_count / MIB:,.1f} MiB'


def _format_ms(value) -> str:
    if value is None:
        return 'Pending'
    value = float(value)
    if not isfinite(value) or value < 0:
        return 'Unavailable'
    return f'{value:,.1f} ms'


def preview_performance_snapshot(mesh, *, upload_submit_ms=None,
                                 upload_bytes=0, fallback_prepare_ms=None):
    """Stable, JSON-friendly presentation snapshot for the current viewport."""
    if mesh is None:
        return None
    profile = getattr(mesh, 'load_profile', None)
    estimate = profile.resources if profile else preview_resource_estimate(mesh)
    return {
        'vertices': estimate.vertices,
        'triangles': estimate.triangles,
        'source_triangles': estimate.source_triangles,
        'cpu_mesh_bytes': estimate.cpu_mesh_bytes,
        'render_buffer_bytes': estimate.render_buffer_bytes,
        'estimated_peak_bytes': estimate.estimated_peak_bytes,
        'gpu_buffer_bytes': int(upload_bytes),
        'parse_ms': profile.parse_ms if profile else None,
        'prepare_ms': profile.prepare_ms if profile else fallback_prepare_ms,
        'upload_submit_ms': upload_submit_ms,
    }


def format_preview_performance(snapshot) -> str:
    if not snapshot:
        return 'Open a model to view preview performance information.'
    return (
        f"Source triangles: {snapshot['source_triangles']:,}\n"
        f"Drawn triangles: {snapshot['triangles']:,}\n"
        f"Vertices: {snapshot['vertices']:,}\n\n"
        f"Model parsing: {_format_ms(snapshot['parse_ms'])}\n"
        f"CPU geometry preparation: {_format_ms(snapshot['prepare_ms'])}\n"
        f"GPU upload submission: {_format_ms(snapshot['upload_submit_ms'])}\n\n"
        f"Estimated decoded mesh: {_format_mib(snapshot['cpu_mesh_bytes'])}\n"
        f"Expanded CPU vertex buffer: {_format_mib(snapshot['render_buffer_bytes'])}\n"
        f"Allocated model GPU vertex buffer: {_format_mib(snapshot['gpu_buffer_bytes'])}\n"
        f"Conservative peak estimate: {_format_mib(snapshot['estimated_peak_bytes'])}\n\n"
        'Memory figures are estimates, not process RSS or VRAM readings. '
        'GPU upload submission time is CPU call duration, not GPU completion. '
        'Grid, plate and analysis texture allocations are not included.'
    )
