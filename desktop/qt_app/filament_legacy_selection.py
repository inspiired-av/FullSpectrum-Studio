"""Read-only detection and explicit reconciliation of ambiguous legacy selector keys.

Legacy selectors used ``series|HEX``; newer custom palettes distinguish actual
filament variants by stable IDs when that selector would match multiple rows.
A saved legacy Require/Exclude cannot be safely mapped to one such row.

This module never reads settings or writes anything.  The caller must obtain
explicit user approval before using ``keys_to_retire`` to retire a legacy key.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


@dataclass(frozen=True)
class LegacySelectionConflict:
    legacy_key: str
    variants: tuple[tuple[str, str], ...]  # (stable selector key, label)
    disabled_keys: tuple[str, ...]  # exact saved spellings, not normalized replacements
    pinned_keys: tuple[str, ...]

    @property
    def kinds(self):
        return tuple(name for name, values in (
            ('Excluded', self.disabled_keys), ('Required', self.pinned_keys)) if values)


def find_legacy_selection_conflicts(options, disabled=(), pinned=()):
    """Return only legacy selectors that collide in the CURRENT option set.

    - No inference is made from the HEX alone; the material family must match.
    - Unambiguous legacy palettes and settings from unrelated sources are kept.
    - The returned exact keys can be removed after an explicit user decision.
    """
    grouped = {}
    for item in options:
        if not isinstance(item, dict):
            continue
        color = str(item.get('color') or '').upper()
        family = str(item.get('series') or '').strip()
        identity = str(item.get('key') or '').strip()
        if not family or not identity or not _HEX.fullmatch(color):
            continue
        legacy = f'{family}|{color}'
        grouped.setdefault(legacy.casefold(), (legacy, {}))[1].setdefault(
            identity, str(item.get('name') or identity))
    disabled = {str(key) for key in disabled}
    pinned = {str(key) for key in pinned}
    result = []
    for canonical, (legacy, variants) in grouped.items():
        if len(variants) < 2:
            continue
        # It is a collision only when more than one selectable key exists.
        # A stable ID is never silently inferred from a legacy color alias.
        old_disabled = tuple(sorted(key for key in disabled if key.casefold() == canonical))
        old_pinned = tuple(sorted(key for key in pinned if key.casefold() == canonical))
        if not old_disabled and not old_pinned:
            continue
        result.append(LegacySelectionConflict(
            legacy, tuple(sorted(variants.items())), old_disabled, old_pinned))
    return tuple(sorted(result, key=lambda item: item.legacy_key.casefold()))


def keys_to_retire(conflicts):
    """Exact keys to retire from saved preferences *after* explicit approval."""
    return frozenset(key for conflict in conflicts
                     for key in (*conflict.disabled_keys, *conflict.pinned_keys))


def unresolved_message(conflicts):
    if not conflicts:
        return ''
    keys = ', '.join(conflict.legacy_key for conflict in conflicts[:3])
    more = f' (+{len(conflicts) - 3} more)' if len(conflicts) > 3 else ''
    return (f'Saved filament preference(s) {keys}{more} match multiple physical variants. '
            'Review Use/Require selections on the Filaments tab and choose Save Filaments. '
            'No physical variant has been chosen automatically.')


def review_text(conflicts, enabled, pinned, *, limit=12):
    """Describe the ACTUAL checked rows before confirmation, including clearing pins."""
    enabled, pinned = set(enabled), set(pinned)
    lines = [
        'These saved filament keys no longer identify one physical filament.',
        'The previous legacy selections will be retired, and the checkboxes you',
        'currently see will become authoritative. Other saved keys stay unchanged.',
        'This can also change matching selections in other filament sources.',
        '',
    ]
    total = 0
    for conflict in conflicts:
        lines.append(f'{conflict.legacy_key} · {", ".join(conflict.kinds)}')
        for identity, name in conflict.variants:
            if total >= limit:
                lines.append('  …additional variants not shown')
                break
            lines.append(f'  {name} [{identity}]: '
                         f'Use {"Yes" if identity in enabled else "No"}; '
                         f'Require {"Yes" if identity in pinned else "No"}')
            total += 1
        if conflict.pinned_keys and not any(ident in pinned for ident, _ in conflict.variants):
            lines.append('  NOTE: Saving will CLEAR the old Required selection.')
        if total >= limit:
            break
    lines += ['', 'Proceed with this explicit reconciliation?']
    return '\n'.join(lines)
