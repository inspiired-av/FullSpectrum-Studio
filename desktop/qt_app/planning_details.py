"""Read-only, deterministic interpretation of FullSpectrum's plan-only optimizer data.

No new optimizer logic, local file writes, or inferred source/print metrics.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _integer(value, fallback=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback


def _number(value):
    try:
        n = float(value)
        return n if isfinite(n) else None
    except (ValueError, TypeError):
        return None


def _hex(value):
    value = str(value or '').upper()
    return value if len(value) == 7 and value.startswith('#') and all(c in '0123456789ABCDEF' for c in value[1:]) else ''


def _components(slots, ratios):
    """Render physical slot references and normalized mixer weights accurately."""
    try:
        numbers = [int(x.strip()) for x in str(slots).split(',') if x.strip()]
        weights = [float(x.strip()) for x in str(ratios).split(',') if x.strip()]
    except (ValueError, TypeError):
        return ''
    if not numbers or len(numbers) != len(weights) or any(n <= 0 for n in numbers):
        return ''
    if any(not isfinite(w) or w < 0 for w in weights):
        return ''
    # Values are serialized fractions by the engine, NOT percentages.
    return ' + '.join(f'{n} ({w * 100:.0f}%)' for n, w in zip(numbers, weights))


@dataclass(frozen=True)
class PlanDetails:
    physical: tuple[dict, ...]
    mixed: tuple[dict, ...]
    real_slots: int
    output_slots: int
    source_slots: int | None
    total_cap: int | None
    planner: str
    quality_bias: str
    printability: str
    pin_count: int
    recommendation: dict | None

    @property
    def slot_summary(self):
        cap = f' / {self.total_cap} allowed' if self.total_cap is not None else ' / Auto cap'
        return (f'{self.output_slots}{cap} · {self.real_slots} physical + '
                f'{max(0, self.output_slots-self.real_slots)} mixed')


def build_details(result):
    """The engine supplies the facts; this function formats and groups them only.

    Recipes are source-state assignments. Several source states can reference
    the SAME output slot, so deduplicate per output slot for the mix table.
    """
    real = max(0, _integer(result.get('realSlots')))
    output = max(real, _integer(result.get('outputSlots')))
    requested = result.get('maxOutputColors')
    cap = _integer(requested) if str(requested).isdigit() else None
    pins = set(result.get('pinnedAnchorKeys') or ())
    physical = []
    for anchor in result.get('anchors') or ():
        if not isinstance(anchor, dict):
            continue
        slot = _integer(anchor.get('slot'))
        if slot <= 0 or slot > real:
            continue
        physical.append({
            'slot': slot,
            'name': str(anchor.get('name') or anchor.get('series') or f'Filament {slot}'),
            'key': str(anchor.get('key') or ''),
            'color': _hex(anchor.get('color')),
            'preset': str(anchor.get('preset') or ''),
            'pinned': str(anchor.get('key') or '') in pins,
            'remainingGrams': _number(anchor.get('remainingGrams')),
        })
    physical.sort(key=lambda x: x['slot'])
    mixes = {}
    for entry in result.get('recipes') or ():
        if not isinstance(entry, dict) or entry.get('kind') != 'MIX':
            continue
        slot = _integer(entry.get('newSlot'))
        if slot <= real or slot > output:
            continue
        if slot not in mixes:
            mixes[slot] = {
                'slot': slot, 'color': _hex(entry.get('preview')),
                'components': _components(entry.get('components'), entry.get('ratios')),
                'states': 0, 'maxDeltaE': None,
            }
        mixes[slot]['states'] += 1
        error = _number(entry.get('deltaE'))
        if error is not None:
            prior = mixes[slot]['maxDeltaE']
            mixes[slot]['maxDeltaE'] = error if prior is None else max(prior, error)
    quality_mode = result.get('qualityBiasMode')
    quality = result.get('qualityBias')
    quality_label = (f'Smart ({quality}/100)' if quality_mode == 'auto'
                     else f'{quality}/100' if quality is not None else '—')
    recommend = result.get('recommendation')
    if not isinstance(recommend, dict):
        recommend = None
    src = result.get('sourceSlots')
    return PlanDetails(
        physical=tuple(physical), mixed=tuple(mixes[k] for k in sorted(mixes)),
        real_slots=real, output_slots=output,
        source_slots=_integer(src) if src is not None else None,
        total_cap=cap, planner=str(result.get('plannerMode') or '—'),
        quality_bias=quality_label,
        printability=str((result.get('printability') or {}).get('difficulty') or 'Not estimated'),
        pin_count=sum(1 for a in physical if a['pinned']),
        recommendation=recommend,
    )
