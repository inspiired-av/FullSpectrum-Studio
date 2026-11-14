"""Stage 2A.2: ID-authoritative profile membership for existing v1 profiles.

A filament color or slicer family is a property, not its identity.  Different
physical variants may have the same displayed HEX and still be available in a
saved palette.  No disk writes, Qt dependencies, or slicer interactions here.

This does not change the engine's established rule that a print needs at least
two distinct colors and cannot REQUIRE two same-HEX physical anchors.
"""
from __future__ import annotations


def _id(record):
    if not isinstance(record, dict):
        raise ValueError('Filament record must be an object')
    identity = record.get('id')
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError('Filament variant needs a stable ID')
    return identity


def available_profile_variants(candidates, existing):
    """Return addable PLA variants, excluding ONLY selected/repeated stable IDs.

    The candidate order is authoritative: live library first, then any
    profile-only snapshots.  Do not replace or modify frozen profile records.
    """
    current_ids = {_id(record) for record in existing}
    seen = set(current_ids)
    available = []
    for record in candidates:
        key = _id(record)
        if key in seen:
            continue
        seen.add(key)
        if record.get('material') == 'PLA':
            available.append(record)
    return available


def append_profile_variants(existing, requested):
    """Append by stable variant identity, preserving every existing snapshot.

    Exact duplicate IDs are ignored; conflicting IDs in the same request
    fail rather than selecting one arbitrarily.  Same color/family with two
    different IDs is fully supported.
    """
    output = list(existing)
    by_id = {_id(record): record for record in output}
    seen_new = {}
    for record in requested:
        key = _id(record)
        if record.get('material') != 'PLA':
            raise ValueError('Only PLA filaments may be added to an active palette')
        if key in seen_new:
            if seen_new[key] != record:
                raise ValueError('Conflicting candidate rows share filament ID ' + key)
            continue
        seen_new[key] = record
        if key not in by_id:
            output.append(record)
            by_id[key] = record
        # A saved profile may intentionally have a frozen snapshot for this ID.
        # Re-adding a live record never silently overwrites that snapshot.
    return output
