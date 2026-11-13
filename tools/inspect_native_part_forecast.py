"""Read-only comparison of native 3MF source-part slots and forecast geometry.

Usage: python -m tools.inspect_native_part_forecast "C:\\...\\Minecraft_Frog(3).3mf"
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
from zipfile import ZipFile


def inspect(path):
    from fullspectrum_engine import reduced_preview_geometry
    from preview_world_geometry import model_instances
    source = Path(path)
    with ZipFile(source) as archive:
        project = json.loads(archive.read('Metadata/project_settings.config'))
        colors = project['filament_colour']
        instances = model_instances(archive, len(colors))
        vertices, faces = reduced_preview_geometry(archive, len(colors))
        counts = Counter(slot for _, slot in faces.values())
        print('Source file:', source.name)
        print('Embedded printer:', project.get('printer_model'), '/', project.get('printer_variant'))
        print('Native source slots:', len(colors))
        print('Part mesh instances:', len(instances[0]) if instances else 'unavailable')
        print('Forecast display vertices:', len(vertices))
        print('Forecast display faces:', len(faces))
        for index, color in enumerate(colors, 1):
            print(f'  source slot {index:2d}: {color.upper():8s}  {counts[index]:6d} faces')
        if source.name.startswith('Minecraft_Frog(') and len(colors) == 4:
            expected = Counter({1: 2, 2: 52, 3: 346, 4: 24})
            if counts != expected:
                raise ValueError(f'Original frog parity mismatch: expected {expected}, got {counts}')
            print('Original frog part-forecast parity: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    inspect(args.path)
