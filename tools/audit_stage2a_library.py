"""Read-only Stage 2A library migration preflight. Run from repository root.

python -m tools.audit_stage2a_library
python -m tools.audit_stage2a_library --json
python -m tools.audit_stage2a_library --include-catalog
"""
from __future__ import annotations

import argparse
import json
import sys

from desktop.qt_app.filament_migration_guard import (
    MigrationGuardError, audit_installed_library, selection_manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only FullSpectrum filament migration audit')
    parser.add_argument('--json', action='store_true', help='Print machine-readable audit summary')
    parser.add_argument('--include-catalog', action='store_true',
                        help='Load existing local/fallback Bambu catalog in addition to personal library')
    parser.add_argument('--selection', nargs='*', metavar='VARIANT_ID',
                        help='Optionally validate a variant-ID selection for future export integration')
    args = parser.parse_args(argv)
    try:
        catalog = ()
        if args.include_catalog:
            from desktop.qt_app.filament_library_store import bambu_catalog_filaments
            catalog = bambu_catalog_filaments()
        report = audit_installed_library(catalog=catalog)
        payload = {'status': 'PASS', 'summary': report.summary,
                   'notices': list(report.notices), 'writes_performed': 0}
        if args.selection:
            payload['selection'] = selection_manifest(report.document, args.selection)
    except (ValueError, OSError, TypeError, MigrationGuardError) as exc:
        if args.json:
            print(json.dumps({'status': 'FAIL', 'error': str(exc), 'writes_performed': 0}, indent=2))
        else:
            print('FAIL — ' + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print('Stage 2A read-only migration audit: PASS')
        for field, value in report.summary.items():
            print(f'  {field}: {value}')
        for note in report.notices:
            print('  NOTICE: ' + note)
        print('  No library, slicer profile, settings, or export files were modified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
