"""Lossless, *experimental* indexed preview feasibility measurement.

Not part of the production renderer. Every vertex's entire packed 48-byte
attribute record is compared byte-for-byte (position, normal, color, tag).
This is an original NumPy-based implementation; no third-party optimizer code
is copied or bundled. Requires NumPy (already in requirements-qt.txt).
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
from time import perf_counter
import sys

import numpy as np

FLOATS_PER_VERTEX = 12
BYTES_PER_VERTEX = 48
BYTES_PER_INDEX = 4


@dataclass(frozen=True)
class IndexedPreviewCandidate:
    """Detached GPU-ready candidate; source float32 array is never modified."""
    vertices: np.ndarray  # one 48-byte void record per unique vertex
    indices: np.ndarray   # one uint32 index per original vertex, original order
    source_vertex_count: int
    elapsed_ms: float

    @property
    def unique_vertex_count(self) -> int:
        return int(self.vertices.size)

    @property
    def source_bytes(self) -> int:
        return self.source_vertex_count * BYTES_PER_VERTEX

    @property
    def indexed_bytes(self) -> int:
        return int(self.vertices.nbytes + self.indices.nbytes)

    @property
    def saved_bytes(self) -> int:
        return self.source_bytes - self.indexed_bytes

    @property
    def percent_saved(self) -> float:
        return 100.0 * self.saved_bytes / self.source_bytes if self.source_bytes else 0.0

    def worth_uploading(self, *, minimum_savings_percent: float = 10.0) -> bool:
        """Include index buffer overhead before accepting a candidate."""
        return self.source_vertex_count > 0 and self.percent_saved >= minimum_savings_percent

    def matches_source_bytes(self, packed_float32: array) -> bool:
        """Compare original expanded triangles to reconstructed index stream."""
        if len(packed_float32) != self.source_vertex_count * FLOATS_PER_VERTEX:
            return False
        source = np.frombuffer(packed_float32, dtype=f'V{BYTES_PER_VERTEX}')
        # Small bounded pieces avoid materializing a full second vertex buffer.
        chunk = 65536
        for start in range(0, self.source_vertex_count, chunk):
            stop = min(self.source_vertex_count, start + chunk)
            if not np.array_equal(self.vertices[self.indices[start:stop]], source[start:stop]):
                return False
        return True


def make_indexed_candidate(packed_float32: array) -> IndexedPreviewCandidate:
    """Deduplicate identical full vertex records without altering any float bits.

    Buffer order is the original flattened triangle order. In particular,
    different flat source tags, normals, or per-corner colors MUST stay separate.
    Sorting unique records changes the index/vertex order but not triangle order.
    """
    if not isinstance(packed_float32, array) or packed_float32.typecode != 'f' \
            or packed_float32.itemsize != 4:
        raise ValueError('Expected an array of float32 preview attributes')
    if sys.byteorder != 'little':
        raise RuntimeError('This benchmarking prototype requires a little-endian host')
    if len(packed_float32) % FLOATS_PER_VERTEX:
        raise ValueError('Packed preview buffer is not 12 float32 values per vertex')
    count = len(packed_float32) // FLOATS_PER_VERTEX
    if count > np.iinfo(np.uint32).max:
        raise ValueError('Vertex count exceeds OpenGL uint32 index range')
    start = perf_counter()
    records = np.frombuffer(packed_float32, dtype=f'V{BYTES_PER_VERTEX}')
    unique, inverse = np.unique(records, return_inverse=True)
    indices = inverse.astype(np.uint32, copy=False)
    # Ensure candidate owns no view into the original mutable input.
    vertices = unique.copy()
    indices = indices.copy()
    return IndexedPreviewCandidate(vertices, indices, count, (perf_counter() - start) * 1000)
