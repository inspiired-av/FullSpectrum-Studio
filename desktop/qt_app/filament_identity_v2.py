"""Stage 2A: lossless, read-only projection of v1 filament data into schema v2.

This module never edits slicer or legacy library files. A color variant is not
its product, a native preset is not its color, and profile membership is not a
copy of a slicer configuration. The legacy snapshot remains available for exact
v1 interoperability until the optimizer becomes variant-ID aware.

The derived product-group IDs are PROVISIONAL when no manufacturer product ID
exists; they never imply identical optical/print behavior.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

SCHEMA = 2
KIND = 'filament_library_index'
NAMESPACE = uuid.UUID('e77939d8-ea3c-448c-b73d-42d6dc235fa9')
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
IDENTITY = re.compile(r'^[A-Za-z0-9_.:+-]{1,160}$')
MAX_RECORDS = 3500
MAX_BYTES = 12_000_000
VALID_OPTICS = frozenset(('opaque', 'translucent', 'transparent'))
VALID_SLICERS = frozenset(('bambu_studio', 'orcaslicer', 'unknown'))


def _text(value, label, limit=200, *, allow_empty=False):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ValueError(f'{label} must be a short text value')
    if not value.strip() and not allow_empty:
        raise ValueError(f'{label} must not be empty')
    return value.strip()


def _identifier(value, label='identity'):
    if not isinstance(value, str) or not IDENTITY.fullmatch(value):
        raise ValueError(f'Invalid {label}')
    return value


def _canonical_id(prefix, *components):
    key = '\x1f'.join(str(part).strip().casefold() for part in components)
    return f'{prefix}:' + str(uuid.uuid5(NAMESPACE, f'{prefix}\x1f{key}'))


def _record(record):
    if not isinstance(record, dict):
        raise ValueError('Expected a legacy filament record')
    for attr in ('id', 'name', 'brand', 'series', 'color'):
        _text(record.get(attr), attr, 160)
    _identifier(record['id'], 'legacy filament ID')
    color = record['color']
    if not HEX.fullmatch(color):
        raise ValueError('Expected #RRGGBB HEX color')
    material = _text(record.get('material', 'PLA'), 'material', 32)
    optics = record.get('optics', 'translucent' if record['series'] == 'PLA Translucent' else 'opaque')
    if optics not in VALID_OPTICS:
        raise ValueError('Invalid optical classification')
    clean = dict(record)
    clean['color'] = color.upper()
    clean['material'] = material
    clean['optics'] = optics
    # This projection should never silently serialize arbitrary object types.
    try:
        json.dumps(clean, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Non-JSON filament metadata') from exc
    return clean


def _product_from_record(record):
    # An explicit manufacturer product ID is future-proof. Legacy category
    # fields alone are not proof that colors share calibrated optics.
    explicit = record.get('product_id')
    family = _text(record.get('product_series') or record['series'], 'product family')
    finish = _text(record.get('finish', 'Standard'), 'finish', 80)
    if explicit is not None:
        product_id = _identifier(explicit, 'product ID')
        provisional = False
    else:
        product_id = _canonical_id('product', record['brand'], record['material'], family, finish)
        provisional = True
    return {
        'id': product_id,
        'brand': record['brand'],
        'material': record['material'],
        'family': family,
        'finish': finish,
        'identity_status': 'provisional-family' if provisional else 'explicit',
    }


def _preset_ref(ref, *, is_legacy=False):
    if not isinstance(ref, dict):
        raise ValueError('Preset reference must be an object')
    slicer = ref.get('slicer', 'unknown')
    if slicer not in VALID_SLICERS:
        raise ValueError('Unsupported slicer reference')
    fields = ('preset_name', 'filament_id', 'setting_id', 'printer_model',
              'nozzle_mm', 'source_id', 'inherits')
    values = {field: (None if ref.get(field) is None else _text(
        str(ref[field]), field, 300)) for field in fields}
    if not any(values.get(key) for key in ('preset_name', 'filament_id', 'setting_id')):
        raise ValueError('Preset reference needs a preset or filament identifier')
    # Include printer/nozzle/source in identity: distinct compatible configurations
    # are not collapsed merely because they have the same material color.
    identity = _canonical_id('preset', slicer, *(values[field] or '' for field in fields))
    return dict(id=identity, slicer=slicer, **values,
                verification='legacy-unverified' if is_legacy else
                _text(ref.get('verification', 'unverified'), 'verification', 80))


def _references_for_record(record):
    references = []
    refs = record.get('preset_refs', ())
    if not isinstance(refs, (tuple, list)):
        raise ValueError('preset_refs must be a list')
    for ref in refs:
        references.append(_preset_ref(ref))
    if record.get('preset') or record.get('filamentID'):
        # Previous code stores derived fallback names as well as genuine native
        # metadata. No unverified legacy reference is labeled slicer-native.
        references.append(_preset_ref({
            'preset_name': record.get('preset'), 'filament_id': record.get('filamentID'),
            'source_id': record.get('source_ref'),
        }, is_legacy=True))
    return {item['id']: item for item in references}


def _variant_from_record(record, product_id, preset_ids):
    # Critical: preserve the v1 stable ID. HEX, display name and catalog
    # order never participate in a migrated variant identity.
    return {
        'id': record['id'], 'product_id': product_id,
        'name': record['name'], 'sku': record.get('sku'),
        'color': {
            'hex': record['color'],
            'provenance': record.get('color_source', 'unknown'),
            'manufacturer_url': record.get('manufacturer_url'),
            'last_verified': record.get('last_verified'),
            'measured_lab': record.get('measured_lab'),
        },
        'optical': {
            'class': record['optics'],
            'transmission_distance_mm': record.get('transmission_distance_mm'),
            'calibration': record.get('optical_calibration'),
        },
        'preset_refs': sorted(preset_ids),
        'origin': record.get('source', 'unknown'),
        'legacy_record': record,
    }


def project_legacy_state(*, generic=(), catalog=(), personal=(), profiles=()):
    """Project legacy records without changing their IDs, order, files or contents.

    Profiles may embed records no longer present in the active catalog. Those
    are retained as snapshot-only variants rather than losing membership.
    More recent primary library records take priority over embedded snapshots;
    the profile's own exact v1 snapshot is kept separately for round trips.
    """
    products = {}
    variants = {}
    presets = {}
    profile_docs = []

    def register(item, *, snapshot_only=False):
        row = _record(item)
        key = row['id']
        if key in variants:
            return key
        product = _product_from_record(row)
        prior = products.get(product['id'])
        if prior is not None and prior != product:
            raise ValueError('Conflicting product identity metadata')
        products[product['id']] = product
        refs = _references_for_record(row)
        for identity, ref in refs.items():
            if identity in presets and presets[identity] != ref:
                raise ValueError('Conflicting native-preset reference')
            presets[identity] = ref
        variant = _variant_from_record(row, product['id'], refs)
        variant['origin'] = 'profile-snapshot' if snapshot_only else variant['origin']
        variants[key] = variant
        return key

    for source in (generic, catalog, personal):
        for row in source:
            register(row)
            if len(variants) > MAX_RECORDS:
                raise ValueError('Too many filament variants')

    seen_profiles = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError('Invalid saved profile')
        pid = _identifier(profile.get('id'), 'profile ID')
        if pid in seen_profiles:
            raise ValueError('Duplicate profile identity')
        seen_profiles.add(pid)
        title = _text(profile.get('name'), 'profile name', 100)
        snapshots = [_record(row) for row in profile.get('filaments', ())]
        ids = [register(item, snapshot_only=True) for item in snapshots]
        if len(ids) != len(set(ids)):
            raise ValueError('A profile contains duplicate variant IDs')
        profile_docs.append({
            'id': pid, 'name': title, 'member_variant_ids': ids,
            'legacy_filaments': snapshots,
        })
    document = {
        'schema': SCHEMA, 'kind': KIND,
        'products': sorted(products.values(), key=lambda p: p['id']),
        'variants': sorted(variants.values(), key=lambda v: v['id']),
        'preset_references': sorted(presets.values(), key=lambda p: p['id']),
        'profiles': sorted(profile_docs, key=lambda p: p['id']),
    }
    validate_document(document)
    return document


def validate_document(document):
    if not isinstance(document, dict) or set(document) != {
            'schema', 'kind', 'products', 'variants', 'preset_references', 'profiles'}:
        raise ValueError('Unrecognized schema v2 document')
    if document['schema'] != SCHEMA or document['kind'] != KIND:
        raise ValueError('Unrecognized filament library schema')
    tables = ('products', 'variants', 'preset_references', 'profiles')
    for name in tables:
        entries = document[name]
        if not isinstance(entries, list) or len(entries) > MAX_RECORDS:
            raise ValueError('Invalid v2 collection: '+name)
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('Expected object in '+name)
        ids = [_identifier(entry.get('id'), name+' ID') for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate v2 identity in '+name)
    product_ids = {item['id'] for item in document['products']}
    variant_ids = {item['id'] for item in document['variants']}
    preset_ids = {item['id'] for item in document['preset_references']}
    for ref in document['preset_references']:
        calculated = _preset_ref(ref, is_legacy=(ref.get('verification') == 'legacy-unverified'))
        if calculated['id'] != ref['id']:
            raise ValueError('Preset identity mismatch')
        if ref.get('slicer') not in VALID_SLICERS:
            raise ValueError('Invalid slicer reference')
    for item in document['variants']:
        if item.get('product_id') not in product_ids:
            raise ValueError('Orphan color variant')
        if not isinstance(item.get('preset_refs'), list) or any(
                ref not in preset_ids for ref in item['preset_refs']):
            raise ValueError('Unresolved preset reference')
        if not isinstance(item.get('color'), dict) or not HEX.fullmatch(
                str(item['color'].get('hex', ''))):
            raise ValueError('Invalid color variant')
        if not isinstance(item.get('optical'), dict) or item['optical'].get('class') not in VALID_OPTICS:
            raise ValueError('Invalid optical data')
        _record(item.get('legacy_record'))
        if item['legacy_record']['id'] != item['id']:
            raise ValueError('Legacy identity drift')
    for item in document['profiles']:
        members = item.get('member_variant_ids')
        snapshots = item.get('legacy_filaments')
        if not isinstance(members, list) or not isinstance(snapshots, list) or len(members) != len(snapshots):
            raise ValueError('Invalid profile membership')
        if len(members) != len(set(members)) or any(key not in variant_ids for key in members):
            raise ValueError('Missing profile member')
        if [record['id'] for record in snapshots] != members:
            raise ValueError('Profile snapshot/identity mismatch')
        for row in snapshots:
            _record(row)
    try:
        payload = json.dumps(document, allow_nan=False, ensure_ascii=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid JSON in v2 catalog') from exc
    if len(payload) > MAX_BYTES:
        raise ValueError('v2 catalog exceeds size limit')
    return document


def legacy_profile_from_document(document, profile_id):
    """Return exact v1-compatible profile contents, preserving embedded records."""
    validate_document(document)
    matches = [p for p in document['profiles'] if p['id'] == profile_id]
    if len(matches) != 1:
        raise ValueError('Unknown profile')
    p = matches[0]
    return {'schema': 1, 'kind': 'palette', 'name': p['name'],
            'filaments': [dict(row) for row in p['legacy_filaments']]}


def index_revision(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Unsafe schema v2 index')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_index(document, *, path, expected_revision=None):
    """Explicit opt-in only. Never edit v1 files, user-selected paths or slicers.

    A caller must supply the app-owned index path. Atomic writes include an
    optimistic revision check; a normal library load never invokes this.
    """
    validate_document(document)
    path = Path(path)
    if path.name != 'catalog_index_v2.json' or path.parent.name != 'filaments':
        raise ValueError('Refusing to write outside the v2 index location')
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Unsafe v2 index path')
    if index_revision(path) != expected_revision:
        raise ValueError('Schema v2 index changed; refresh before writing')
    content = (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    if len(content) > MAX_BYTES:
        raise ValueError('v2 index too large')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.fss-v2-',
                                         suffix='.tmp', delete=False) as stream:
            temp = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return index_revision(path)


def read_index(path):
    if index_revision(path) is None:
        raise ValueError('No schema v2 index exists')
    try:
        document = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid schema v2 index') from exc
    return validate_document(document)
