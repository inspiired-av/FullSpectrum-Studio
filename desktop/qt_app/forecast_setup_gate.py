"""Explicit first-run material readiness for Stage 4B's read-only forecast.

No Qt, engine imports, persistence, or user prompts: pure gate decision logic.
An available library is not equivalent to a consciously selected library.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SetupDecision:
    ready: bool
    state: str
    message: str
    can_confirm: bool = False


def evaluate_setup(*, source, custom_path, saved_source, confirmed, loaded,
                   options, disabled=(), selection_valid=True, selection_error=''):
    """Return the action needed before the planner may use a filament source.

    `loaded` means the CURRENT source finished populating successfully; it
    must be explicitly cleared when source or custom file changes. Do not
    mistake default values in PlanPreferences for a saved configuration.
    """
    if source == 'custom' and (not custom_path or not Path(custom_path).is_file()):
        return SetupDecision(False, 'custom_missing',
                             'Choose an existing custom filament JSON library under Filaments.')
    if not loaded:
        return SetupDecision(False, 'loading',
                             'Load filament choices before generating the first forecast.')
    if not selection_valid:
        return SetupDecision(False, 'invalid',
                             str(selection_error or 'Correct the invalid filament selection under Filaments.'))
    if source != 'exact-cmykw':
        enabled = {str(o.get('color', '')).upper() for o in (options or ())
                   if str(o.get('key', '')) not in set(disabled) and o.get('color')}
        if len(enabled) < 2:
            return SetupDecision(False, 'insufficient',
                                 'Enable at least two distinct filament colors under Filaments.')
    configured = bool(confirmed) or bool(saved_source and saved_source == source)
    if not configured:
        return SetupDecision(False, 'needs_confirmation',
                             'Review the available filament colors, then choose Use These Filaments. '
                             'A default source is not a confirmed setup.', True)
    return SetupDecision(True, 'ready', 'Filament selection ready for forecasting.')
