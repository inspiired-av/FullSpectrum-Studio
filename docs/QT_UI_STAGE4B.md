# Qt Stage 4B — Palette Planning Details

Based on `feat/qt-ui-redesign` checkpoint `af79043`.

## Workflow

1. Open a model and run **Refresh Forecast**, or enable Automatic forecast.
2. Expand **Optimization Details** beneath Expected Palette in Plan.
3. **Physical Filaments** lists the optimizer's chosen physical slots, HEX colors, material names, saved preset and pinned/optimized status.
4. **Mixed Recipes** lists one row per unique mixed output slot. Component numbers refer to physical slots in the first table; ratios are the Bambu FilamentMixer fractions displayed as percentages. The Source states column shows how many source states use the recipe; Worst dE is the highest recorded color error of those source states.
5. To review a physical material, select a row and use **Find in Filaments…**. This searches and focuses the existing Filaments list without changing any pinned or enabled states. Change constraints there, then refresh (or let Automatic forecast update).

The section starts collapsed and is enabled after a successful forecast. It can be collapsed independently of Plan's Advanced Settings.

## State and safety

- Only the existing `fullspectrum_engine.convert(..., plan_only=True)` computes the result. No second optimizer or inferred mixtures.
- Main-thread Qt only displays a small subset of returned source-slot, physical-anchor and mixed-recipe data. The engine is never imported inside the presentation widget.
- Old same-model estimates, including the detail rows, remain visible and marked **Outdated** while settings change and a new estimate is pending. A different model clears them.
- No 3MF export, filament enable/pin mutation, physical inventory write, or slicing occurs in Stage 4B.
- Unsupported or absent engine fields are displayed as unavailable rather than invented.
- Stage 4C covers generated 3D predicted colors and color-loss visualization. Stage 4D covers conversion, export, and slicer integration.
