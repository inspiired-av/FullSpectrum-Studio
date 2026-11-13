"""Inspect/migrate the Stage 2A v2 identity projection without changing v1 files.

Run: python -m tools.inspect_filament_identity_v2
Optional: --include-bambu (slow) / --write-index (explicit, app-owned only)
"""
from __future__ import annotations

import argparse
from collections import Counter
from desktop.qt_app import filament_library_store as store
from desktop.qt_app.filament_identity_v2 import index_revision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-bambu', action='store_true',
                        help='Read the local Bambu catalog synchronously (never modify slicer directories)')
    parser.add_argument('--write-index', action='store_true',
                        help='Explicitly save the derived index to app-owned filaments/catalog_index_v2.json')
    options = parser.parse_args(argv)
    catalog = store.bambu_catalog_filaments() if options.include_bambu else []
    snapshot = store.build_identity_index_v2(catalog=catalog)
    optical = Counter(item['optical']['class'] for item in snapshot['variants'])
    status = Counter(item['verification'] for item in snapshot['preset_references'])
    print('Stage 2A - Filament identities (read-only v1 projection)')
    print('Products:', len(snapshot['products']), '(provisional groupings are NOT calibrated material equivalence)')
    print('Color variants:', len(snapshot['variants']))
    print('Slicer preset references:', len(snapshot['preset_references']))
    print('Saved/built-in profiles:', len(snapshot['profiles']))
    print('Optical classifications:', dict(sorted(optical.items())))
    print('Preset verification:', dict(sorted(status.items())))
    print('Source catalog:', 'local Bambu catalog loaded' if options.include_bambu else 'not scanned (add --include-bambu)')
    for profile in snapshot['profiles']:
        print('  Profile:', profile['name'], '| members:', len(profile['member_variant_ids']))
    if options.write_index:
        path = store.library_root() / 'catalog_index_v2.json'
        revision = index_revision(path)
        result = store.export_identity_index_v2(catalog=catalog, expected_revision=revision)
        print('v2 index saved:', path)
        print('Revision:', result)
        print('v1 personal/profile files and slicer configurations unchanged.')
    else:
        print('No files written. Add --write-index to persist only the v2 index.')


if __name__ == '__main__':
    main()
