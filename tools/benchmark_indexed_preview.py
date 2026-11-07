"""Offline, read-only indexed rendering feasibility benchmark.

Run from repo root: python tools/benchmark_indexed_preview.py path/to/model.3mf
No OpenGL context, Qt app launch, source mutation, or export takes place.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Allow direct execution from any working directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import argparse
from time import perf_counter
from desktop.qt_app.mesh_loader import load_preview_mesh
from desktop.qt_app.preview_shading import flatten_faces
from desktop.qt_app.preview_indexing import make_indexed_candidate

MIB = 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', help='Supported source .3mf/.obj/.glb within existing preview limits')
    parser.add_argument('--minimum-savings', type=float, default=10.0,
                        help='Percent net GPU buffer reduction required to recommend indexing')
    args = parser.parse_args()
    begin = perf_counter()
    mesh = load_preview_mesh(args.model)
    parse_ms = (perf_counter() - begin) * 1000
    begin = perf_counter()
    expanded = flatten_faces(mesh)
    prep_ms = (perf_counter() - begin) * 1000
    candidate = make_indexed_candidate(expanded)
    exact = candidate.matches_source_bytes(expanded)
    print(f'Model: {mesh.name}')
    print(f'Source triangles: {mesh.source_triangles:,} | Preview triangles: {len(mesh.triangles):,}')
    print(f'Parsing: {parse_ms:,.1f} ms | CPU packing: {prep_ms:,.1f} ms')
    print(f'Indexing construction: {candidate.elapsed_ms:,.1f} ms')
    print(f'Expanded vertices: {candidate.source_vertex_count:,} | Unique complete vertices: {candidate.unique_vertex_count:,}')
    print(f'Current unindexed VBO: {candidate.source_bytes / MIB:,.2f} MiB')
    print(f'Indexed VBO+EBO: {candidate.indexed_bytes / MIB:,.2f} MiB ({candidate.percent_saved:+.1f}% saved)')
    print('Exact float32 bitwise reconstruction:', 'PASS' if exact else 'FAIL')
    print(f'GPU indexing recommendation (>= {args.minimum_savings:g}% net savings):',
          'YES' if candidate.worth_uploading(minimum_savings_percent=args.minimum_savings) else 'NO — retain direct upload')
    if not exact:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
