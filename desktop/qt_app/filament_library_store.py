"""Safe, PLA-first library and portable quick palettes for FullSpectrum Studio.

Catalog records are informational until the user selects them. No slicer files
are ever written. Active palettes deliberately use the existing engine's
custom-palette JSON interface; no new optimizer assumptions are introduced.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from desktop.settings_store import settings_path

SCHEMA = 1
HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
SAFE_NAME = re.compile(r'^[^\x00-\x1f\x7f]{1,100}$')
FAMILIES = (
    'PLA Basic', 'PLA Matte', 'PLA Silk', 'PLA Silk+', 'PLA Marble',
    'PLA Sparkle', 'PLA Tough', 'PLA Tough+', 'PLA Aero', 'PLA Glow',
    'PLA Dynamic', 'PLA Galaxy', 'PLA Wood', 'PLA Translucent',
    'PLA Lite', 'PLA Pure', 'PLA-CF', 'PLA Metal',
)
EXPERIMENTAL = ('PETG', 'ABS', 'ASA', 'TPU')
OPTICS = ('opaque', 'translucent', 'transparent')
MAX_RECORDS = 3500
MAX_BYTES = 2_000_000
MAX_PROFILES = 128
_ID_NAMESPACE = uuid.UUID('890d9374-6f23-4434-90cb-344932c9dd1b')


def library_root():
    return settings_path().parent / 'filaments'


def personal_file():
    return library_root() / 'personal.json'


def legacy_file():
    # Read only for migration; never edit the first-increment file.
    return settings_path().parent / 'my_filaments.json'


def active_file():
    return library_root() / 'active_palette.json'


def profile_root():
    return settings_path().parent / 'palettes'


def stable_id(namespace, *parts):
    key = '|'.join(str(p).strip().casefold() for p in parts)
    return namespace + ':' + str(uuid.uuid5(_ID_NAMESPACE, namespace + '|' + key))


def _text(value, field, length=100, *, default=None):
    if value is None and default is not None:
        value = default
    if not isinstance(value, str):
        raise ValueError(f'{field} must be text')
    value = value.strip()
    if not value or len(value) > length or not SAFE_NAME.fullmatch(value):
        raise ValueError(f'Invalid {field} (1–{length} printable characters)')
    return value


def normalize(entry, *, personal=False):
    if not isinstance(entry, dict):
        raise ValueError('Filament record must be a JSON object')
    material = _text(entry.get('material', 'PLA'), 'material', 20)
    if material not in ('PLA', *EXPERIMENTAL):
        raise ValueError('Unsupported material; PLA is the only production-supported material')
    series = _text(entry.get('series', 'PLA Basic'), 'profile', 40)
    if series not in FAMILIES:
        raise ValueError('Unknown PLA slicer profile')
    name = _text(entry.get('name'), 'filament name')
    brand = _text(entry.get('brand'), 'brand', 80, default='Generic')
    color = entry.get('color')
    if not isinstance(color, str) or not HEX.fullmatch(color):
        raise ValueError('Expected six-digit #RRGGBB HEX color')
    finish = _text(entry.get('finish', 'Standard'), 'finish', 40)
    optics = entry.get('optics', 'translucent' if series == 'PLA Translucent' else 'opaque')
    if optics not in OPTICS:
        raise ValueError('Unknown opacity classification')
    source = _text(entry.get('source', 'personal' if personal else 'generic'), 'source', 32)
    color_source = _text(entry.get('color_source', 'user-entered' if personal else 'approximate'), 'color provenance', 40)
    identity = entry.get('id')
    if identity is None and personal:
        identity = 'personal:' + str(uuid.uuid4())
    if not isinstance(identity, str) or len(identity) > 120 or not re.fullmatch(r'[A-Za-z0-9:_.-]+', identity):
        raise ValueError('Invalid stable filament ID')
    if personal and not identity.startswith('personal:'):
        raise ValueError('Only personal records may be edited')
    if not personal and source == 'personal' and not identity.startswith('personal:'):
        raise ValueError('Personal filament has invalid identity')
    result = dict(id=identity, name=name, brand=brand, material=material,
                  series=series, color=color.upper(), finish=finish,
                  optics=optics, source=source, color_source=color_source,
                  experimental=(material != 'PLA'))
    for key in ('sku', 'preset', 'filamentID', 'source_ref', 'product_series'):
        if key in entry and entry[key] is not None:
            result[key] = _text(entry[key], key, 200)
    # Stage 2A.2: retain explicitly validated v2 metadata alongside v1 fields.
    # The planner still receives the same series/HEX representation.
    from desktop.qt_app.filament_metadata_v2 import retain_optional_metadata
    return retain_optional_metadata(entry, result)


def _validate_records(items, *, personal=False):
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise ValueError('Invalid or oversized filament list')
    clean = [normalize(item, personal=personal) for item in items]
    ids = [item['id'] for item in clean]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate stable filament ID')
    return clean


def _read_json(path, maximum=MAX_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular JSON file (not a symlink)')
    if path.stat().st_size > maximum:
        raise ValueError('JSON file exceeds supported size')
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Unable to read JSON; existing data was not modified') from exc


def _atomic_json(path, data):
    path = Path(path)
    content = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(content) > MAX_BYTES:
        raise ValueError('Saved JSON exceeds supported size')
    # Reuse only app-owned paths, never an arbitrary passed-in destination.
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Refusing to write through a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.fs-library-', suffix='.tmp',
                                         delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return path


def file_revision(path=None):
    path = Path(path) if path is not None else personal_file()
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Unsafe personal library')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_personal():
    path = personal_file()
    if path.exists():
        obj = _read_json(path)
        if not isinstance(obj, dict) or obj.get('schema') != SCHEMA or set(obj) != {'schema', 'filaments'}:
            raise ValueError('Unsupported personal library format; refusing to overwrite')
        return _validate_records(obj['filaments'], personal=True), file_revision(path)
    # Do not edit/move previous app-generated library; import it in memory.
    old = legacy_file()
    if old.exists():
        obj = _read_json(old)
        if not isinstance(obj, dict) or set(obj) != {'filaments'} or not isinstance(obj['filaments'], list):
            raise ValueError('Existing my_filaments.json has an unfamiliar format')
        result = []
        for item in obj['filaments']:
            if not isinstance(item, dict):
                raise ValueError('Legacy filament record is invalid')
            record = dict(item)
            record['source'] = 'personal'
            record['id'] = stable_id('personal', 'legacy', item.get('brand'),
                                     item.get('series'), item.get('name'), item.get('color'))
            result.append(normalize(record, personal=True))
        return _validate_records(result, personal=True), None
    return [], None


def save_personal(entries, *, expected_revision=None):
    # Optimistic concurrency check prevents two open editors overwriting edits.
    path = personal_file()
    if file_revision(path) != expected_revision:
        raise ValueError('Personal library changed on disk; reopen the editor to avoid losing edits')
    clean = _validate_records(entries, personal=True)
    _atomic_json(path, {'schema': SCHEMA, 'filaments': clean})
    return file_revision(path)


_GENERIC = (
    ('Black', '#000000', 'PLA Basic', 'opaque'),
    ('White', '#FFFFFF', 'PLA Basic', 'opaque'),
    ('Cyan', '#00FFFF', 'PLA Basic', 'opaque'),
    ('Magenta', '#FF00FF', 'PLA Basic', 'opaque'),
    ('Yellow', '#FFFF00', 'PLA Basic', 'opaque'),
    ('Red', '#FF0000', 'PLA Basic', 'opaque'),
    ('Green', '#00FF00', 'PLA Basic', 'opaque'),
    ('Blue', '#0000FF', 'PLA Basic', 'opaque'),
    ('Black', '#000000', 'PLA Translucent', 'translucent'),
    ('Cyan', '#00FFFF', 'PLA Translucent', 'translucent'),
    ('Magenta', '#FF00FF', 'PLA Translucent', 'translucent'),
    ('Yellow', '#FFFF00', 'PLA Translucent', 'translucent'),
)


def generic_filaments():
    """Illustrative generic swatches, NOT manufacturer-measured print colors."""
    out=[]
    for name, color, series, optics in _GENERIC:
        out.append(normalize({
            'id':stable_id('generic', series, name, color), 'source':'generic',
            'name':f'Generic {name}', 'brand':'Generic', 'series':series,
            'color':color, 'optics':optics, 'color_source':'approximate',
            'finish':'Translucent' if optics == 'translucent' else 'Standard',
        }))
    return out


def bambu_catalog_filaments(engine=None):
    """Use the application's existing local/fallback catalog; never scrape or write slicer files."""
    if engine is None:
        import fullspectrum_engine as engine
    options = engine.catalog_palette('all')
    results=[]
    for item in options:
        if not isinstance(item, dict):
            continue
        try:
            details = engine.anchor_option_payload(item)
            name = details.get('name') or item.get('name')
            family = details.get('series') or item.get('series')
            if family not in FAMILIES:
                continue
            color = details.get('color')
            if not HEX.fullmatch(str(color)):
                continue
            brand = details.get('brand') or item.get('brand') or 'Bambu Lab'
            # Source independent identity allows future Bambu/Orca scans to merge
            # references for the same manufacturer SKU, not same HEX alone.
            sku = details.get('filamentID') or item.get('filamentID') or ''
            provenance = (details.get('catalogSource') or item.get('catalogSource')
                          or 'built-in fallback')
            record = {'id':stable_id('bambu', brand, sku, family, name, color),
                      'source':'bambu', 'name':str(name), 'brand':str(brand),
                      'series':str(family), 'color':str(color),
                      'color_source':('bundled-fallback' if provenance=='built-in fallback'
                                      else 'installed-slicer-catalog'),
                      'finish':'Translucent' if family=='PLA Translucent' else 'Standard',
                      'optics':'translucent' if family=='PLA Translucent' else 'opaque'}
            for key in ('filamentID', 'preset'):
                if details.get(key): record[key] = str(details[key])
            results.append(normalize(record))
        except (ValueError,TypeError):
            continue
    # Catalog may include alternate local profiles of the same physical product;
    # those have one stable ID and must not inflate repeated scans.
    return list({entry['id']:entry for entry in results}.values())


def merged_filaments(catalog=(), personal=()):
    # Distinct manufacturers are not merged by HEX; only exact stable IDs are.
    result={item['id']:item for item in generic_filaments()}
    for item in catalog:
        normalized=normalize(item)
        result[normalized['id']]=normalized
    for item in personal:
        normalized=normalize(item,personal=True)
        result[normalized['id']]=normalized
    return sorted(result.values(), key=lambda x:(x['brand'].casefold(),x['series'],x['name'].casefold(),x['id']))


def _active_entries(records):
    clean=_validate_records(records)
    if any(item['material'] != 'PLA' for item in clean):
        raise ValueError('Non-PLA filaments are experimental and cannot be exported by this PLA optimizer')
    # Stage 2A.3: a palette contains selectable *variants*, not unique
    # (family, HEX) pairs. Each normalized record already has a unique ID.
    # The engine will treat colliding colors as alternative physical choices,
    # not incorrectly count them as distinct colors or mixture anchors.
    if len(clean) < 2 or len({entry['color'] for entry in clean}) < 2:
        raise ValueError('Active palette needs at least two different colors')
    if len(clean) > 32:
        raise ValueError('An active palette cannot exceed 32 candidates')
    result=[]
    for item in clean:
        entry={key:item[key] for key in ('id','name','brand','series','color')}
        for optional in ('preset','filamentID'):
            if item.get(optional): entry[optional]=item[optional]
        result.append(entry)
    return result


def activate_palette(records):
    """Create the ordinary engine custom library; do not change saved Plan preferences."""
    entries = _active_entries(records)
    _atomic_json(active_file(), {'filaments':entries,
                                'fullspectrum_selection':[r['id'] for r in records]})
    return active_file()


def active_ids():
    path=active_file()
    if not path.exists():return set()
    obj=_read_json(path)
    if not isinstance(obj,dict):return set()
    ids=obj.get('fullspectrum_selection',[])
    if not isinstance(ids,list):return set()
    return {value for value in ids if isinstance(value,str) and len(value)<=120}


def _check_profile(obj):
    if not isinstance(obj,dict) or obj.get('schema')!=SCHEMA or obj.get('kind')!='palette':
        raise ValueError('Unsupported palette profile format')
    name=_text(obj.get('name'),'profile name')
    entries=_validate_records(obj.get('filaments'))
    _active_entries(entries)
    return {'schema':SCHEMA,'kind':'palette','name':name,'filaments':entries}


def save_profile(name, records, *, profile_id=None):
    name=_text(name,'profile name')
    items=_validate_records(records)
    _active_entries(items)
    root=profile_root()
    existing = list_profiles()
    if len(existing)>=MAX_PROFILES and profile_id is None:
        raise ValueError('Too many saved palette profiles')
    if any(p['name'].casefold()==name.casefold() and p['id'] != profile_id for p in existing):
        raise ValueError('A profile with this name already exists')
    if profile_id is None:
        profile_id=str(uuid.uuid4())
    try:
        profile_id=str(uuid.UUID(profile_id))
    except (ValueError,AttributeError) as exc:
        raise ValueError('Invalid profile ID') from exc
    data=_check_profile({'schema':SCHEMA,'kind':'palette','name':name,'filaments':items})
    _atomic_json(root / (profile_id+'.json'),data)
    return profile_id


def list_profiles():
    root=profile_root()
    if not root.exists():return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Unsafe palette profile folder')
    entries=list(root.glob('*.json'))
    if len(entries)>MAX_PROFILES:
        raise ValueError('Palette profile folder has too many files')
    records=[]
    for path in entries:
        try:
            identity=str(uuid.UUID(path.stem))
        except ValueError:
            # Never read unrelated JSON files in this folder.
            continue
        profile=_check_profile(_read_json(path))
        records.append({'id':identity,'name':profile['name'], 'filaments':profile['filaments']})
    return sorted(records,key=lambda x:x['name'].casefold())


def builtin_profiles():
    entries=generic_filaments()
    def by(series, color):
        return next(item for item in entries if item['series']==series and item['color']==color)
    return [{'id':'builtin:generic-cmykw','name':'Generic CMYKW · uncalibrated',
             'filaments':[by('PLA Basic',col) for col in ('#00FFFF','#FF00FF','#FFFF00','#000000','#FFFFFF')],
             'note':'Illustrative HEX values, not validated for Bambu PLA Palette CMYKW or translucent mixing.'}]


def profile_choices():
    return builtin_profiles() + list_profiles()


def get_profile(profile_id):
    for profile in profile_choices():
        if profile['id'] == profile_id:
            return profile
    raise ValueError('Palette profile was not found')


def _managed_profile_path(profile_id):
    """Never accept arbitrary paths for saved palette mutations."""
    try:
        identity = str(uuid.UUID(str(profile_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError('Only saved user profiles can be modified') from exc
    root = profile_root()
    if root.is_symlink():
        raise ValueError('Unsafe palette profile folder')
    path = root / (identity + '.json')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Saved profile was not found')
    return path


def saved_profile_revision(profile_id):
    return file_revision(_managed_profile_path(profile_id))


def update_saved_profile(profile_id, records, *, expected_revision):
    """Edit only an existing managed profile, preserving its identity and name."""
    path = _managed_profile_path(profile_id)
    if file_revision(path) != expected_revision:
        raise ValueError('Profile changed on disk; reopen it before saving')
    original = _check_profile(_read_json(path))
    changed = _check_profile({'schema':SCHEMA, 'kind':'palette',
                              'name':original['name'], 'filaments':records})
    _atomic_json(path, changed)
    return file_revision(path)



def rename_saved_profile(profile_id, name, *, expected_revision):
    """Rename a managed profile with optimistic concurrency; never change its ID."""
    name = _text(name, 'profile name')
    path = _managed_profile_path(profile_id)
    if file_revision(path) != expected_revision:
        raise ValueError('Profile changed on disk; reopen it before renaming')
    existing = _check_profile(_read_json(path))
    if any(p['name'].casefold() == name.casefold() and p['id'] != str(profile_id)
           for p in list_profiles()):
        raise ValueError('A profile with this name already exists')
    _atomic_json(path, _check_profile({
        'schema': SCHEMA, 'kind': 'palette', 'name': name,
        'filaments': existing['filaments'],
    }))
    return file_revision(path)


def delete_saved_profile(profile_id, *, expected_revision):
    """Delete a saved quick profile, NOT the filaments it references."""
    path = _managed_profile_path(profile_id)
    if file_revision(path) != expected_revision:
        raise ValueError('Profile changed on disk; reopen it before deleting')
    _check_profile(_read_json(path))
    path.unlink()


# Product/manufacturer descriptors are NOT slicer preset family names.
# Keep the original series for display and select an explicit compatible
# engine family instead. Never silently guess an unrelated material profile.
_LEGACY_PROFILE_FAMILIES = {
    'Panchroma Translucent PLA': 'PLA Translucent',
    'Generic PLA': 'PLA Basic',
    'Generic PLA Basic': 'PLA Basic',
}


def parse_import_profile(path, *, name=None):
    """Read/validate the portable or legacy format without modifying its source."""
    obj = _read_json(path)
    if isinstance(obj, dict) and obj.get('kind') == 'palette':
        profile = _check_profile(obj)
        return _text(name or profile['name'], 'profile name'), profile['filaments']
    raw = obj.get('filaments') if isinstance(obj, dict) else obj
    if not isinstance(raw, list):
        raise ValueError('Imported JSON needs a filaments list')
    items = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError('Invalid entry in imported custom palette')
        series = entry.get('series', 'PLA Basic')
        if not isinstance(series, str):
            raise ValueError('Imported filament series must be text')
        fields = dict(entry)
        if series not in FAMILIES:
            family = _LEGACY_PROFILE_FAMILIES.get(series.strip())
            if family is None:
                raise ValueError(
                    f'Unknown PLA slicer profile for {entry.get("name", "filament")!r}: '
                    f'{series!r}. Choose a supported PLA profile before import.')
            fields['product_series'] = series.strip()
            fields['series'] = family
        fields.update(source='imported',
                      id=stable_id('imported', Path(path).name, i,
                                   entry.get('series'), entry.get('color')),
                      color_source='user-entered')
        if fields.get('product_series'):
            fields['product_series'] = _text(fields['product_series'], 'product series')
        items.append(normalize(fields))
    _active_entries(items)  # Validate before any managed-file mutation.
    return _text(name or Path(path).stem, 'profile name'), items


def import_profile(path, *, name=None, replace_profile_id=None,
                   expected_revision=None):
    """Import legacy/portable JSON; optional replacement is revision-checked."""
    title, items = parse_import_profile(path, name=name)
    if replace_profile_id is not None:
        old = next((p for p in list_profiles() if p['id'] == replace_profile_id), None)
        if old is None or old['name'].casefold() != title.casefold():
            raise ValueError('Replacement must target the existing profile with the same name')
        update_saved_profile(replace_profile_id, items,
                             expected_revision=expected_revision)
        return replace_profile_id
    return save_profile(title, items)


# Stage 2A: read-only schema v2 projection; v1 remains the active optimizer
# and saved palette format until native preset/variant resolution is validated.
def build_identity_index_v2(*, catalog):
    """Project loaded Bambu/Orca catalog results and app-owned v1 data to v2.

    Pass catalog explicitly: the UI worker should provide its already-scanned
    results rather than triggering an expensive synchronous scan here.
    """
    from desktop.qt_app.filament_identity_v2 import project_legacy_state
    personal, _ = read_personal()
    return project_legacy_state(generic=generic_filaments(), catalog=catalog,
                                personal=personal, profiles=profile_choices())


def export_identity_index_v2(*, catalog, expected_revision=None):
    """Opt-in schema v2 index write; does not modify v1 or slicer files."""
    from desktop.qt_app.filament_identity_v2 import write_index
    return write_index(build_identity_index_v2(catalog=catalog),
                       path=library_root() / 'catalog_index_v2.json',
                       expected_revision=expected_revision)
