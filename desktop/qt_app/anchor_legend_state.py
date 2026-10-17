"""Truthful mapping between the native optimizer's anchor categories and filaments.

Stage 4D-A maps actual mixture percentages to the dominant physical slot.
Categorical colors are retained as an optional high-contrast display.
"""
import re

ANCHOR_OVERLAY_COLORS = ('#28B8D5','#E86C8C','#EDC949','#4E79A7','#59A14F','#B07AA1')
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def anchor_legend_rows(result):
    if not isinstance(result, dict):
        return ()
    details = result.get('planningDetails') or {}
    if not isinstance(details, dict):
        return ()
    anchors = details.get('anchors') or []
    try:
        n = int(details.get('realSlots'))
    except (ValueError, TypeError):
        return ()
    if not isinstance(anchors,(list,tuple)) or not 1 <= n <= 8 or len(anchors) != n:
        return ()
    pinned=set(details.get('pinnedAnchorKeys') or ())
    rows=[];seen=set()
    for a in anchors:
        if not isinstance(a,dict):
            return ()
        slot=a.get('slot');color=a.get('color');name=a.get('name')
        if (type(slot) is not int or not 1<=slot<=n or slot in seen or
                not isinstance(color,str) or not HEX.fullmatch(color) or
                not isinstance(name,str) or not name.strip()):
            return ()
        seen.add(slot)
        rows.append(dict(slot=slot,overlay=ANCHOR_OVERLAY_COLORS[(slot-1)%6],
                         filament=color.upper(),name=name.strip(),
                         pinned=isinstance(a.get('key'),str) and a['key'] in pinned))
    return tuple(sorted(rows,key=lambda r:r['slot']))
