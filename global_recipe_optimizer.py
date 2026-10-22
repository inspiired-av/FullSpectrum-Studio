"""Experimental Phase 3 global mix recipe allocation.

Optimize source-face color error over all selected physical and mixed slots.
Keep the physical anchors and protected (SOLID) face mappings unchanged. This
module does not read or modify printer/project metadata or 3MF resources.
"""
from collections import Counter
from math import isfinite


def optimize_direct_palette(source_colors, usage, palette, anchors, protected_slots,
                            distance, anchor_name, candidate_recipes,
                            max_output_colors, minimum_improvement=0.005):
    """Try a global palette optimization; never return worse mean/worst dE.

    `candidate_recipes`: iterable of (component slot tuple, ratio tuple, Bambu
    reconstructed #RRGGBB). Recipes must reference physical anchors only.
    `usage`: nonnegative source-face weights by 1-based original color ID.
    """
    colors, flags, comps, ratios, mapping, rows = palette
    physical = len(anchors)
    if not 2 <= physical <= len(colors) <= 32:
        raise ValueError("Invalid palette physical/output slot counts")
    if len(rows) != len(source_colors) or len(mapping) != len(source_colors):
        raise ValueError("Source color rows do not match original targets")
    if max_output_colors < physical or max_output_colors > 32:
        raise ValueError("Invalid maximum output color count")
    if not (len(colors)==len(flags)==len(comps)==len(ratios)):
        raise ValueError("Inconsistent filament array lengths")
    protected_slots = protected_slots or {}
    for index,source in enumerate(source_colors,1):
        if rows[index-1][0] != index or rows[index-1][2] != source:
            raise ValueError("Original target mapping is inconsistent")
        if index in protected_slots:
            slot = mapping[index]
            if slot > physical or rows[index-1][3] != "SOLID":
                raise ValueError("Protected source colors must remain physically assigned")

    # Use the actual Bambu reconstructed colors. Keep existing mixture recipes
    # in the candidate pool even if planner-specific ratio families differ.
    candidates = {}  # preview color -> (component_ids, ratio_text, color)
    for i in range(physical,len(colors)):
        if flags[i] != "1":
            raise ValueError("Non-physical slot lacks a valid mixed recipe")
        candidates[colors[i]] = (comps[i],ratios[i],colors[i])
    for comp_slots, fraction, color in candidate_recipes:
        if not isinstance(color,str) or len(color) != 7 or color[0] != '#':
            raise ValueError("Invalid reconstructed candidate color")
        if color in colors[:physical] or color in candidates:
            continue
        slots=tuple(comp_slots)
        if len(slots) not in (2,3) or len(set(slots)) != len(slots) or any(
            not 1 <= k <= physical for k in slots
        ):
            raise ValueError("Mixed candidate references a nonphysical filament")
        if len(fraction) != len(slots):
            raise ValueError("Mixed candidate component/ratio mismatch")
        parsed=tuple(float(v) for v in fraction)
        if any(not isfinite(v) or v<=0 or v>=1 for v in parsed) or abs(sum(parsed)-1)>0.015:
            raise ValueError("Mixed candidate has invalid component ratios")
        candidates[color]=(",".join(str(i) for i in slots),
                           ",".join(f"{v:.4f}" for v in parsed),color)

    target_indices = [i for i in range(len(source_colors)) if i+1 not in protected_slots]
    weights = [max(0.0,float(usage.get(i+1,0))) for i in target_indices]
    if not any(weights):
        weights = [1.0 for _ in target_indices]
    if not target_indices:
        return palette, {"accepted":False,"reason":"All source colors protected","meanBefore":0,"meanAfter":0,"worstBefore":0,"worstAfter":0}
    physical_dists=[]
    for i in target_indices:
        physical_dists.append(tuple(distance(source_colors[i], col) for col in colors[:physical]))
    base_best=[min(ds) for ds in physical_dists]
    # v2 reassigned all source colors to nearest existing color. The exact
    # baseline comparison here nevertheless scans all physical/mixed colors.
    before=[min(distance(source_colors[i], color) for color in colors) for i in target_indices]
    weight_sum=sum(weights)
    base_mean=sum(w*d for w,d in zip(weights,before))/weight_sum
    base_worst=max(before)
    allowed=max_output_colors-physical
    if allowed<=0 or not candidates:
        return palette, {"accepted":False,"reason":"No mix slots available","meanBefore":round(base_mean,4),"meanAfter":round(base_mean,4),"worstBefore":round(base_worst,4),"worstAfter":round(base_worst,4)}

    pool=list(candidates.values())
    distances=[tuple(distance(source_colors[i],item[2]) for i in target_indices)
               for item in pool]
    # Greedy weighted reduction. Each added mixture must improve at least one
    # color and never worsens nearest-palette color accuracy.
    chosen=[]
    remaining=set(range(len(pool)))
    current=list(base_best)
    threshold=1e-7*weight_sum
    for _ in range(allowed):
        candidate_id=None
        candidate_gain=threshold
        for j in sorted(remaining):
            gain=sum(w*max(0.0,b-d) for w,b,d in zip(weights,current,distances[j]))
            if gain>candidate_gain+1e-10:
                candidate_id=j
                candidate_gain=gain
        if candidate_id is None:
            break
        chosen.append(candidate_id)
        remaining.remove(candidate_id)
        current=[min(b,d) for b,d in zip(current,distances[candidate_id])]

    # Pairwise local exchange corrects greedy allocation errors with bounded
    # work (max 32 slots, a few hundred candidates, at most five exchanges).
    for _ in range(5):
        best_improvement=1e-6*weight_sum
        swap=None
        for place, old_id in enumerate(chosen):
            others=[physical_dists[t] for t in range(len(target_indices))]
            without=[min([min(others[t])] + [distances[j][t] for j in chosen if j!=old_id])
                     for t in range(len(target_indices))]
            baseline=sum(w*min(b,distances[old_id][t]) for t,(w,b) in enumerate(zip(weights,without)))
            for j in sorted(remaining):
                score=sum(w*min(b,distances[j][t]) for t,(w,b) in enumerate(zip(weights,without)))
                improvement=baseline-score
                if improvement>best_improvement:
                    best_improvement=improvement
                    swap=(place,old_id,j)
        if swap is None:
            break
        place,old_id,j=swap
        chosen[place]=j
        remaining.remove(j)
        remaining.add(old_id)

    final_colors=colors[:physical]+[pool[j][2] for j in chosen]
    after=[]
    assignments={}
    for index,source in enumerate(source_colors,1):
        if index in protected_slots:
            assignments[index]=mapping[index]
            continue
        slot=min(range(1,len(final_colors)+1),
                 key=lambda k:(distance(source,final_colors[k-1]),k>physical,k))
        assignments[index]=slot
        after.append(distance(source,final_colors[slot-1]))
    new_mean=sum(w*d for w,d in zip(weights,after))/weight_sum
    new_worst=max(after)
    info={"accepted":False,"meanBefore":round(base_mean,4),"meanAfter":round(new_mean,4),
          "worstBefore":round(base_worst,4),"worstAfter":round(new_worst,4),
          "candidateRecipes":len(pool),"outputSlots":len(final_colors)}
    # Keep v2 plan if global selection fails to improve both weighted fidelity
    # and rare worst-case source colors. A higher slot count alone is not gain.
    if new_mean>base_mean-minimum_improvement or new_worst>base_worst+1e-7:
        info["reason"]="Retained earlier palette: no safe global improvement"
        return palette,info
    revised_rows=[]
    mixed_flags=flags[:physical]+["1"]*len(chosen)
    new_components=comps[:physical]+[pool[j][0] for j in chosen]
    new_ratios=ratios[:physical]+[pool[j][1] for j in chosen]
    for index,source in enumerate(source_colors,1):
        slot=assignments[index]
        if index in protected_slots:
            row=rows[index-1][:]
            if row[1] != slot:
                raise ValueError("Protected solid assignment changed")
            revised_rows.append(row)
            continue
        direct_slot=min(range(1,physical+1),
                        key=lambda i:(distance(source,final_colors[i-1]),i))
        direct_error=distance(source,final_colors[direct_slot-1])
        err=distance(source,final_colors[slot-1])
        if slot<=physical:
            kind="ANCHOR"
            label=anchor_name(anchors[slot-1])
            components=""
            fractions=""
        else:
            kind="MIX"
            label=""
            components=new_components[slot-1]
            fractions=new_ratios[slot-1]
        revised_rows.append([index,slot,source,kind,label,components,fractions,
                             final_colors[slot-1],f"{err:.2f}",f"{direct_error:.2f}",
                             f"{direct_error-err:.2f}"])
    info["accepted"]=True
    info["reason"]="Global recipe selection improved mean and maintained worst error"
    return (final_colors,mixed_flags,new_components,new_ratios,assignments,revised_rows),info
