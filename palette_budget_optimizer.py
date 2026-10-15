"""Phase 3: palette budget policies for original source-color planning.

Only the *final* palette changes. The caller handles source triangles and native
3MF export; protected source colors stay pinned to their original physical slot.
A candidate is a recipe of 2-3 physical filaments and a Bambu swatch.
"""
from math import isfinite

STRATEGIES = ("balanced", "maximum_fidelity", "fill_palette")
DISPLAY_NAMES = {
    "balanced": "Balanced",
    "maximum_fidelity": "Maximum fidelity",
    "fill_palette": "Fill palette",
}


def normalize_output_color_strategy(value):
    if value not in STRATEGIES:
        raise ValueError(f"Output color strategy must be one of: {', '.join(STRATEGIES)}")
    return value


def _signed_stats(distances, weights):
    total = sum(weights) or 1.0
    return sum(w*d for w,d in zip(weights, distances))/total, max(distances,default=0.0)


def allocate_palette(source_colors, usage, palette, anchors, protected_slots,
                     distance, anchor_name, candidate_recipes, max_output_colors,
                     strategy="maximum_fidelity", minimum_gain=0.0001):
    """Globally allocate mixed slots and return (palette, diagnostic dictionary).

    Balanced keeps only mixtures with a meaningful gain per added slot.
    Maximum fidelity prefers weighted mean improvement and large outlier relief;
    it doesn't use slots that cannot measurably improve the model.
    Fill palette uses every allowed slot when there are sufficient distinct,
    printable recipes, even if some added recipes aren't mapped to triangles.

    Designed for <=32 slots, 59+ source colors, and a few thousand candidates.
    The CIEDE2000 distance and exact Bambu mix colors are supplied by the engine.
    """
    strategy = normalize_output_color_strategy(strategy)
    colors, flags, components, ratios, mapping, rows = palette
    physical = len(anchors)
    if not (2 <= physical <= len(colors) <= 32 and
            len(colors)==len(flags)==len(components)==len(ratios)):
        raise ValueError("Invalid original palette lengths")
    if len(rows)!=len(source_colors) or len(mapping)!=len(source_colors):
        raise ValueError("Palette rows/source-color count mismatch")
    if not physical <= max_output_colors <= 32:
        raise ValueError("Max output colors must accommodate physical filaments, up to 32")
    protected_slots = protected_slots or {}
    for index,color in enumerate(source_colors,1):
        if rows[index-1][0]!=index or rows[index-1][2]!=color:
            raise ValueError("Palette rows do not match source order")
        if index in protected_slots and (mapping[index] > physical or rows[index-1][3] != "SOLID"):
            raise ValueError("Protected source color is not mapped to a physical filament")
    if len(colors)>max_output_colors:
        raise ValueError("Existing palette exceeds requested max output colors")

    active = [i for i in range(len(source_colors)) if i+1 not in protected_slots]
    weights = [max(0.,float(usage.get(i+1,0.))) for i in active]
    if any(not isfinite(w) for w in weights):
        raise ValueError("Non-finite source weight")
    if active and not any(weights):
        weights=[1.] * len(active)
    original_errors = [min(distance(source_colors[i],col) for col in colors) for i in active]
    before_mean,before_worst = _signed_stats(original_errors,weights)

    def information(accepted,reason,mean_after=before_mean,worst_after=before_worst,
                    after_slots=None,candidates=0):
        return {
            "accepted":accepted,"strategy":strategy,"reason":reason,
            "meanBefore":round(before_mean,4),"meanAfter":round(mean_after,4),
            "worstBefore":round(before_worst,4),"worstAfter":round(worst_after,4),
            "outputSlotsBefore":len(colors),
            "outputSlots":len(colors) if after_slots is None else after_slots,
            "candidateRecipes":candidates,
        }

    if not active or max_output_colors==physical:
        return palette, information(False,"No unprotected targets or available mixed slots")

    # Preserve existing valid recipes, then add new ones. Deduplicate by their
    # *Bambu reconstructed hex*, not only by ratio: recipes can render identically.
    fixed = list(colors[:physical])
    pool_by_color = {}
    for j in range(physical,len(colors)):
        if flags[j] != "1":
            raise ValueError("Output mix slot must have a mixed recipe")
        pool_by_color.setdefault(colors[j].upper(), (components[j],ratios[j],colors[j].upper()))
    for cs,rs,preview in candidate_recipes:
        slots=tuple(int(v) for v in cs)
        frac=tuple(float(v) for v in rs)
        if len(slots) not in (2,3) or len(slots)!=len(frac) or len(set(slots))!=len(slots):
            raise ValueError("Invalid mixed recipe components")
        if any(v<1 or v>physical for v in slots):
            raise ValueError("Mix recipe uses an invalid physical slot")
        if any(not isfinite(v) or v<=0 or v>=1 for v in frac) or abs(sum(frac)-1.)>0.015:
            raise ValueError("Invalid mixed recipe ratios")
        swatch=str(preview).upper()
        if len(swatch)!=7 or swatch[0]!='#' or any(ch not in '0123456789ABCDEF' for ch in swatch[1:]):
            raise ValueError("Invalid mixture swatch")
        if swatch not in {x.upper() for x in fixed}:
            pool_by_color.setdefault(swatch, (
                ','.join(str(v) for v in slots),
                ','.join(f'{v:.4f}' for v in frac),swatch))
    pool=list(pool_by_color.values())
    budget=min(max_output_colors-physical,len(pool))
    if not budget:
        return palette, information(False,"No distinct printable mixtures available")

    # Standard-library-only implementation. Building a column-oriented
    # distance table makes each trial cheap without forcing NumPy into a
    # Windows installation or a packaged application.
    target = [source_colors[i] for i in active]
    physical_d = [tuple(float(distance(t, c)) for c in fixed) for t in target]
    columns = [tuple(float(distance(t, recipe[2])) for t in target)
               for recipe in pool]
    weight_total = sum(weights) or 1.0
    weight = [w / weight_total for w in weights]
    best = [min(row) for row in physical_d]
    candidates = list(range(len(pool)))
    selected = []

    def objective(errors):
        return sum(w*e for w,e in zip(weight,errors)) + 0.35*max(errors,default=0.)

    for _ in range(budget):
        current_worst = max(best)
        top = None
        highest_gain = float('-inf')
        for candidate in candidates:
            column = columns[candidate]
            mean_improvement = 0.0
            new_worst = 0.0
            for w,prior,d in zip(weight,best,column):
                updated = min(prior,d)
                mean_improvement += w*(prior-updated)
                if updated>new_worst:
                    new_worst=updated
            gain = mean_improvement + 0.35*(current_worst-new_worst)
            if gain>highest_gain:
                top,highest_gain=candidate,gain

        required_gain = 0.08 if strategy=='balanced' else minimum_gain
        if strategy != 'fill_palette' and highest_gain <= required_gain:
            break
        if strategy=='fill_palette' and highest_gain<=minimum_gain:
            # Extra recipes are allowed but must be valid, unique printable
            # colors. Prefer candidates close to important source colors.
            top = max(candidates,key=lambda idx: (
                sum(w/(1.0+d) for w,d in zip(weight,columns[idx]))-
                0.00001*min(columns[idx]), -idx))
        candidates.remove(top)
        selected.append(top)
        col = columns[top]
        best = [min(prior,d) for prior,d in zip(best,col)]

    # Refinement: swap a chosen mix with any unused candidate only when the
    # same objective improves. All source distances are precomputed above.
    if strategy=='maximum_fidelity' and selected:
        for _ in range(3):
            improved=False
            selected_set=set(selected)
            unused=[i for i in range(len(pool)) if i not in selected_set]
            if not unused:
                break
            for place,old_id in enumerate(selected):
                others=[j for j in selected if j!=old_id]
                without=[min(row) for row in physical_d]
                for j in others:
                    without=[min(prior,d) for prior,d in zip(without,columns[j])]
                old_errors=[min(prior,d) for prior,d in zip(without,columns[old_id])]
                old_score=objective(old_errors)
                replacement=None
                replacement_score=old_score
                for idx in unused:
                    candidate_errors=[min(prior,d) for prior,d in zip(without,columns[idx])]
                    candidate_score=objective(candidate_errors)
                    if candidate_score+1e-6<replacement_score:
                        replacement,replacement_score=idx,candidate_score
                if replacement is not None:
                    selected[place]=replacement
                    improved=True
                    break
            if not improved:
                break

    final_colors=fixed+[pool[i][2] for i in selected]
    assignments={}
    matched_errors=[]
    active_row=0
    for i,source in enumerate(source_colors,1):
        if i in protected_slots:
            assignments[i]=mapping[i]
            continue
        physical_errors=physical_d[active_row]
        # On exact ties, preserve lower slot ID, including physical slots.
        physical_slot=min(range(physical),key=lambda j:(physical_errors[j],j))
        chosen_slot=physical_slot+1
        error=physical_errors[physical_slot]
        for offset,recipe_idx in enumerate(selected,start=physical+1):
            candidate_error=columns[recipe_idx][active_row]
            if candidate_error<error:
                chosen_slot,error=offset,candidate_error
        assignments[i]=chosen_slot
        matched_errors.append(error)
        active_row+=1
    after_mean,after_worst=_signed_stats(matched_errors,weights)

    # Maximum fidelity must never silently make the existing plan worse.
    # Fill palette may include extra valid swatches that have no painted uses.
    if strategy=='maximum_fidelity' and (
        after_mean > before_mean+0.00001 or after_worst > before_worst+0.00001 or
        (before_mean-after_mean < 0.0001 and before_worst-after_worst < 0.0001)
    ):
        return palette,information(False,'Maximum fidelity: retained existing palette (no safe gain)',
                                   after_mean,after_worst,len(final_colors),len(pool))
    if strategy=='balanced':
        reason='Balanced: retained only mixtures with a meaningful net benefit'
    elif strategy=='fill_palette' and len(final_colors)<max_output_colors:
        reason=f'Fill palette: only {len(final_colors)} distinct printable swatches available'
    else:
        reason=('Maximum fidelity: optimized mixed recipes' if strategy=='maximum_fidelity'
                else 'Fill palette: allocated all requested distinct mixed slots')

    newflags=flags[:physical]+['1']*len(selected)
    newcomps=components[:physical]+[pool[i][0] for i in selected]
    newratios=ratios[:physical]+[pool[i][1] for i in selected]
    newrows=[]
    for i,source in enumerate(source_colors,1):
        if i in protected_slots:
            newrows.append(rows[i-1][:])
            continue
        slot=assignments[i]
        direct_slot=min(range(1,physical+1),key=lambda k:(distance(source,final_colors[k-1]),k))
        direct_err=distance(source,final_colors[direct_slot-1])
        err=distance(source,final_colors[slot-1])
        kind='ANCHOR' if slot<=physical else 'MIX'
        label=anchor_name(anchors[slot-1]) if kind=='ANCHOR' else ''
        newrows.append([i,slot,source,kind,label,
                        '' if kind=='ANCHOR' else newcomps[slot-1],
                        '' if kind=='ANCHOR' else newratios[slot-1],
                        final_colors[slot-1],f'{err:.2f}',f'{direct_err:.2f}',
                        f'{direct_err-err:.2f}'])
    return (final_colors,newflags,newcomps,newratios,assignments,newrows),information(
        True,reason,after_mean,after_worst,len(final_colors),len(pool))
