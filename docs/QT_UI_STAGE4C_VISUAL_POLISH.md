# Stage 4C — View Mode Help, Color-Loss Key, and Worst-Match Cleanup

Baseline: `feat/qt-ui-redesign` at `5502f6f` with the **Stage 4C Compatibility Fix** already applied. No conversion/export pipeline changes.

## Preview modes help

The new `?` beside the mode selector explains Original, Predicted, Color Loss, Anchor Influence and Wireframe. It reuses the existing circular SectionHelpButton and click dialog, rather than reintroducing a glyph next to the Model Preview heading. In particular, the influence colors are **labels for anchor regions**, not actual filament colors.

## Color-loss map legend

A compact lower-left overlay appears **inside the OpenGL viewport** only in Color Loss mode, with three large colored segments and labels:

- green `#37C977` — estimated ΔE ≤ 2 (low)
- yellow `#F5D725` — estimated ΔE 2–6 (moderate)
- orange-red `#F54A1F` — estimated ΔE > 6 (higher)

These are engine heatmap endpoints and threshold categories, not measured print calibration. The actual engine heatmap interpolates colors between the endpoints. The legend follows the viewport size, ignores mouse input, and does not change mesh data.

## Worst visible match

The single target → predicted swatch row is now the sole presentation of the **worst visible match** and its maximum ΔE. The upper metric row shows the *engine-authored* **mean ΔE** instead, or an em dash if unavailable. A separate hint below the palette shows only an actionable filament suggestion or an independent warning; it never repeats the target, predicted HEX and maximum ΔE paragraph.

## Excluding objects and plates (proposed Stage 4D)

**Not part of this visual-only patch.** The correct export-time feature needs an object/instance selector with an initial **all included** state, plus an optional **exclude entire plate** action for native slicer projects. Exclusion must remove only selected build instances and update any relevant slicer object/plate metadata, paint links, model settings, and derived preview/cache state **in a staged output copy**. Original input 3MF files must never be edited. If source contains a single grouped object, it may not be independently separable into printable objects without additional decomposition. Require at least one printable object, revalidate archive references and build tree, and show excluded instances in an export summary.

## Manual Windows checks

Launch Qt, run a real forecast, switch through all available modes. Confirm the `?` dialog describes all five modes; the Color Loss key appears over the viewport and stays visible on resize; the mean ΔE is distinct from worst ΔE; worst-match HEX and ΔE occur only once; and all previous stale/refresh behavior remains. Run `python -m unittest discover -s tests -v` and `git diff --check`.
