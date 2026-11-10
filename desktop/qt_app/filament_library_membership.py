"""UI-neutral profile membership helpers for the shared filament table.

Never mutates the catalog, saved profile, or caller-provided dictionaries.
"""
from __future__ import annotations


def merge_with_profile(catalog, entries):
    """Show imported profile-only colors while editing; do not add to All Filaments."""
    available = {str(item['id']): dict(item) for item in catalog}
    for item in entries:
        available.setdefault(str(item['id']), dict(item))
    return list(available.values())


def sorted_for_profile(records, selected_ids):
    """Pinned membership first, then stable alphabetical ordering."""
    keys = set(selected_ids)
    return sorted(records, key=lambda r: (
        0 if r['id'] in keys else 1,
        str(r.get('brand', '')).casefold(),
        str(r.get('series', '')).casefold(),
        str(r.get('name', '')).casefold(),
        str(r['id']),
    ))


def reconcile_membership(prior, records, selected_ids):
    """Retain embedded imported snapshots; append newly checked catalog filaments."""
    selected = set(selected_ids)
    by_id = {str(record['id']): record for record in records}
    result = []
    seen = set()
    for old in prior:
        identity = str(old['id'])
        if identity in selected and identity not in seen:
            result.append(dict(by_id.get(identity, old)))
            seen.add(identity)
    for record in records:
        identity = str(record['id'])
        if identity in selected and identity not in seen:
            result.append(dict(record))
            seen.add(identity)
    return result


def membership_signature(records):
    return frozenset(str(entry['id']) for entry in records)


def checked_visible_with_filters(record, selected_ids, profile_editing):
    """Checked profile entries are shown even when search/brand filters differ."""
    return bool(profile_editing and record['id'] in set(selected_ids))
