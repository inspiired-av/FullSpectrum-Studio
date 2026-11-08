"""Read-only before/after usage-weight diagnostics for native 3MF projects.

Run with `python -m tools.benchmark_native_paint_weights model.3mf`.
Does not optimize or export; measures original leaf/part counts and true area.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from time import perf_counter
import argparse
import json
from zipfile import ZipFile

from desktop.qt_app.native_area_planning import native_surface_slot_weights


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model',type=Path)
    args=parser.parse_args()
    from fullspectrum_engine import (collect_archive_paint_codes,
        paint_slot_usage, archive_model_setting_extruder_slots,
        include_model_extruder_usage)
    with ZipFile(args.model) as archive:
        colors=json.loads(archive.read('Metadata/project_settings.config'))['filament_colour']
        _,codes=collect_archive_paint_codes(archive)
        old=paint_slot_usage(codes,len(colors))
        old=include_model_extruder_usage(old,archive_model_setting_extruder_slots(archive,len(colors)))
    start=perf_counter()
    area=native_surface_slot_weights(args.model,colors)
    duration=(perf_counter()-start)*1000
    old_total=sum(old.values()) or 1
    area_total=sum(area.values()) or 1
    print(f'Source: {args.model.name} | surface calculation: {duration:,.1f} ms')
    print(f'Total verified area: {area_total:,.5f} mm²')
    print('Slot   Hex       Previous weight share    Geometric area share    Area (mm²)')
    for slot,c in enumerate(colors,1):
        print(f'{slot:4d}   {c[:7].upper()}       {100*old.get(slot,0)/old_total:7.3f}%  '
              f'              {100*area.get(slot,0)/area_total:7.3f}%   '
              f'{area.get(slot,0):12,.5f}')
    print('No optimizer or exporter run; this is not a filament-volume estimate.')

if __name__=='__main__':
    main()
