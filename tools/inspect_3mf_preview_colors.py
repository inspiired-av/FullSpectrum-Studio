#!/usr/bin/env python3
"""Read-only report of source colors displayed by the Qt 3MF loader."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from desktop.qt_app.mesh_loader import load_3mf


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('files',nargs='+',type=Path)
    args=parser.parse_args()
    for path in args.files:
        mesh=load_3mf(path)
        print(f'\n{path.name} | triangles: {len(mesh.triangles):,}')
        print(mesh.color_status)
        for color,count in mesh.palette_counts:
            print(f'  {color}  {count:,} faces')
        neutral=sum(color is None for color in mesh.face_colors)
        if neutral:print(f'  [unresolved/default]  {neutral:,} faces')


if __name__=='__main__':main()
