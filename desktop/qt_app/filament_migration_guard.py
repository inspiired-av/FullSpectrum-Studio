"""Stage 2A: non-destructive migration audit and variant-based selection bridge.

No filesystem I/O occurs in this module. The v1 store remains authoritative;
identity_v2 is a read-only projection. This module intentionally does NOT
resolve native slicer presets or change the export engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class MigrationGuardError(ValueError):
    """A legacy-to-v2 conversion would lose or ambiguously merge identity."""


# No two primary records may quietly share an identity with conflicting
# metadata. Stage 2B will explicitly reconcile references from separate
# slicers; first-wins merging is not acceptable in a migration preflight.


@dataclass(frozen=True)
class MigrationAudit:
    """Read-only diagnostics; document is suitable for opt-in v2 index export."""
    document: dict[str, Any]
    summary: dict[str, int]
    notices: tuple[str, ...]


def _copy_rows(rows: Iterable[dict], source: str) -> list[dict]:
    if not isinstance(rows, (list, tuple)):
        raise MigrationGuardError(f'{source} records must be a list or tuple')
    out = []
    for index, entry in enumerate(rows):
        if not isinstance(entry, dict):
            raise MigrationGuardError(f'{source}[{index}] is not a filament object')
        out.append(dict(entry))
    return out


def _core_signature(entry: dict) -> str:
    """Compare complete records so optional metadata is never discarded."""
    from json import dumps
    try:
        return dumps(entry, sort_keys=True, ensure_ascii=False,
                     allow_nan=False, separators=(',', ':'))
    except (ValueError, TypeError) as exc:
        raise MigrationGuardError('Invalid non-JSON filament identity metadata') from exc


def _check_primary_collisions(generic: list[dict], catalog: list[dict],
                              personal: list[dict]) -> None:
    """Prevent v2's current first-wins projection from hiding a data conflict.

    Saved profile *snapshots* are deliberately excluded. They preserve the old
    contents of an individual palette even when a library variant changes.
    """
    seen: dict[str, tuple[str, tuple]] = {}
    cased: dict[str, str] = {}
    for source_name, source in (('generic', generic), ('catalog', catalog),
                                ('personal', personal)):
        for row in source:
            identity = row.get('id')
            if not isinstance(identity, str) or not identity.strip():
                raise MigrationGuardError(f'{source_name}: missing variant ID')
            folded = identity.casefold()
            if folded in cased and cased[folded] != identity:
                raise MigrationGuardError('Variant IDs differ only by case: '
                                          + cased[folded] + ' / ' + identity)
            cased[folded] = identity
            signature = _core_signature(row)
            old = seen.get(identity)
            if old is not None and old[1] != signature:
                raise MigrationGuardError(
                    f'Variant ID {identity!r} has conflicting primary records '
                    f'({old[0]} and {source_name}). Resolve metadata before migration; '
                    'do not merge by HEX or silently take the first record.')
            seen[identity] = (source_name, signature)


def audit_legacy_sources(*, generic=(), catalog=(), personal=(), profiles=(),
                         identity_module=None) -> MigrationAudit:
    """Validate and project the actual v1 data, without writing any files.

    Important: this intentionally does not convert v1 profile snapshots into
    live references. Their saved records and order survive in v2 separately.
    """
    if identity_module is None:
        from desktop.qt_app import filament_identity_v2 as identity_module
    generic = _copy_rows(generic, 'generic')
    catalog = _copy_rows(catalog, 'catalog')
    personal = _copy_rows(personal, 'personal')
    if not isinstance(profiles, (list, tuple)):
        raise MigrationGuardError('Saved profiles must be a list or tuple')
    profile_copies = []
    seen_profile_ids = {}
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise MigrationGuardError(f'Profile {index} is not an object')
        item = dict(profile)
        profile_id = item.get('id')
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise MigrationGuardError(f'Profile {index} has no valid stable ID')
        profile_fold = profile_id.casefold()
        if profile_fold in seen_profile_ids:
            raise MigrationGuardError(
                'Profile identity collision (including case-only differences): '
                + repr(seen_profile_ids[profile_fold]) + ' / ' + repr(profile_id))
        seen_profile_ids[profile_fold] = profile_id
        item['filaments'] = _copy_rows(profile.get('filaments', ()),
                                        f'profile {index} filaments')
        profile_copies.append(item)

    _check_primary_collisions(generic, catalog, personal)
    try:
        doc = identity_module.project_legacy_state(
            generic=generic, catalog=catalog, personal=personal,
            profiles=profile_copies)
        identity_module.validate_document(doc)
    except ValueError as exc:
        raise MigrationGuardError(f'v1 → v2 projection failed: {exc}') from exc

    # Validate profile order and *exact* stored snapshots; a collection of
    # variant references alone would lose intentionally frozen palette colors.
    by_id = {p['id']: p for p in doc['profiles']}
    for profile in profile_copies:
        pid = profile.get('id')
        if pid not in by_id:
            raise MigrationGuardError(f'Saved profile {pid!r} disappeared')
        restored = identity_module.legacy_profile_from_document(doc, pid)
        if (restored.get('name') != profile.get('name') or
                restored.get('filaments') != profile['filaments']):
            raise MigrationGuardError(
                f'Saved profile {pid!r} does not round-trip exactly. '
                'Refusing lossy migration; original v1 files are unchanged.')

    primary_records = {r['id']: r for r in (*generic, *catalog, *personal)}
    primary_ids = set(primary_records)
    changed_snapshot_rows = sum(
        row['id'] in primary_records and row != primary_records[row['id']]
        for p in profile_copies for row in p['filaments'])
    variants = doc['variants']
    products = doc['products']
    presets = doc['preset_references']
    snapshot_only = sum(v['id'] not in primary_ids for v in variants)
    provisional = sum(p['identity_status'] == 'provisional-family'
                      for p in products)
    legacy_preset = sum(p.get('verification') == 'legacy-unverified'
                        for p in presets)
    summary = {
        'primary_variants': len(primary_ids),
        'products': len(products),
        'variants': len(variants),
        'preset_references': len(presets),
        'saved_profiles': len(profile_copies),
        'snapshot_only_variants': snapshot_only,
        'historical_profile_snapshot_rows': changed_snapshot_rows,
        'provisional_products': provisional,
        'legacy_unverified_presets': legacy_preset,
    }
    notices = []
    if provisional:
        notices.append(f'{provisional} product grouping(s) are provisional; '
                       'similar names do not establish identical physical products.')
    if legacy_preset:
        notices.append(f'{legacy_preset} legacy preset reference(s) are unverified; '
                       'do not treat their names as printer compatibility evidence.')
    if changed_snapshot_rows:
        notices.append(f'{changed_snapshot_rows} saved palette row(s) differ from the current '
                       'library version; the historical snapshots remain intact.')
    if snapshot_only:
        notices.append(f'{snapshot_only} historical variant(s) exist only in saved '
                       'palette snapshots; they were preserved, not discarded.')
    return MigrationAudit(doc, summary, tuple(notices))


def selection_manifest(document: dict, variant_ids: Iterable[str], *,
                       identity_module=None) -> dict:
    """Resolve selected variant IDs without conflating color, product and preset.

    Read-only adapter for later Stage 2B/2C code. It does not invent a printer
    preset from a product name or select a substitute by nearest HEX.
    """
    if identity_module is None:
        from desktop.qt_app import filament_identity_v2 as identity_module
    identity_module.validate_document(document)
    ids = list(variant_ids)
    if not 1 <= len(ids) <= 32 or any(not isinstance(x, str) for x in ids):
        raise MigrationGuardError('Select 1–32 valid filament variant IDs')
    if len(ids) != len(set(ids)):
        raise MigrationGuardError('Selection contains duplicate filament variant IDs')
    variants = {item['id']: item for item in document['variants']}
    products = {item['id']: item for item in document['products']}
    native = {item['id']: item for item in document['preset_references']}
    result = []
    for slot, identity in enumerate(ids, 1):
        variant = variants.get(identity)
        if variant is None:
            raise MigrationGuardError(f'Unknown filament variant {identity!r}')
        product = products[variant['product_id']]
        result.append({
            'slot': slot,
            'variant_id': identity,
            'product_id': product['id'],
            'product_identity_status': product['identity_status'],
            'material': product['material'],
            'brand': product['brand'],
            'name': variant['name'],
            'series': variant['legacy_record']['series'],
            'finish': variant['legacy_record'].get('finish'),
            'sku': variant['legacy_record'].get('sku'),
            'source': variant['legacy_record'].get('source'),
            'color': variant['color']['hex'],
            'color_provenance': variant['color'].get('provenance'),
            'optical_class': variant['optical']['class'],
            'preset_references': [dict(native[key])
                                  for key in variant['preset_refs']],
        })
    return {
        'schema': 1, 'kind': 'fullspectrum_selection_manifest',
        'filaments': result,
        'distinct_colors': len({r['color'] for r in result}),
        'can_forecast_pla': (len(result) >= 2 and
                             len({r['color'] for r in result}) >= 2 and
                             all(r['material'] == 'PLA' for r in result)),
    }


def audit_installed_library(*, catalog=(), store=None, identity_module=None):
    """App-owned read-only adapter. Catalog discovery is supplied by caller.

    Stage 2B will supply collected catalog records after its own safe scan;
    no automatic reads of installed slicer folders occur in this method.
    """
    if store is None:
        from desktop.qt_app import filament_library_store as store
    personal, _revision = store.read_personal()
    return audit_legacy_sources(
        generic=store.generic_filaments(), catalog=catalog,
        personal=personal, profiles=store.profile_choices(),
        identity_module=identity_module)
