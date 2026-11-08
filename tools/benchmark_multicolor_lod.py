"""Compare experimental source-paint-preserving display LOD on a local mesh.

Run from any directory: python tools/benchmark_multicolor_lod.py FILE.3mf
No output 3MF, model colors, or export pipeline is modified.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from desktop.qt_app.mesh_loader import load_preview_mesh
from desktop.qt_app.preview_multicolor_lod import build_adaptive_multicolor_lod


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model',type=Path)
    parser.add_argument('--seconds',type=float,default=12.0,
                        help='maximum preparation budget per quality mode')
    args=parser.parse_args()
    if args.seconds<=0 or args.seconds>30:
        parser.error('--seconds must be between 0 and 30')
    start=perf_counter()
    mesh=load_preview_mesh(str(args.model))
    print('Model:',args.model)
    print('Parsing:',round((perf_counter()-start)*1000,1),'ms')
    print('Source triangles:',mesh.source_triangles)
    print('Available original preview:',len(mesh.triangles))
    print('Note: this is a display-only approximation; paint/export remain untouched.')
    for mode in ('balanced','performance'):
        r=build_adaptive_multicolor_lod(mesh,mode,max_seconds=args.seconds)
        print('\n',mode.title(),sep='')
        print('Preview triangles:',r.draw_faces)
        print('Reduction: %.2f%%' % (100*(1-r.draw_faces/max(r.source_faces,1))))
        print('LOD preparation: %.1f ms' % r.duration_ms)
        print('Total surface-area change: %.3f%%' % (100*r.area_relative_error))
        print('Worst significant color-area change: %.3f%%' % (100*r.worst_color_area_error))
        print('Lost source-color identities:',r.dropped_colors)
        print('Decision:',r.reason)

if __name__=='__main__':main()
