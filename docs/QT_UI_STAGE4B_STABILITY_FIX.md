# Qt Stage 4B stability and usability follow-up

Baseline: `af79043` after applying the Stage 4B package. The installer rejects unknown edits.

## Changes

- **Filament search/loading**: The All Bambu materials catalogue is loaded on a background worker, and the Qt table is populated in batches of 24 rows when more than 80 choices exist. Searching before the table is finished is deferred and applied at the end. Source changes cancel obsolete batches. No partial list is ever persisted as the current choices.
- **Progress indicators**: Indeterminate status while the source library loads, then `n / total` during GUI table creation. Plan-only optimizer forecasting additionally displays elapsed time and the most recently reported planning step (this is **not** an ETA).
- **Mixed recipes**: The Find in Filaments button is displayed only for **Physical Filaments**; recipe details explain that mixed outputs are combinations of physical slot numbers. No automatic pins are made.
- **Dropdown wheel**: Plan and Filaments `QComboBox` choices ignore closed-combobox wheel events, passing them to the containing scrolling view. Dropdown menus still scroll normally when opened; keyboard control is unchanged.
- **Outdated details**: A clear amber **OUTDATED FORECAST** label appears at the top of details during manual edits; automatic refresh instead shows a neutral-blue **UPDATING FORECAST** label. It disappears after successful recalculation. No duplicate refresh prompt is added.
- **Regressions**: Stage 4A behavior-harness tests no longer depend on Stage 4B UI widgets. Existing Stage 4B regression checks now validate the new indicator.

## Non-goals

- The engine is unchanged; Stage 4B uses the existing `convert(..., plan_only=True)` path. No native 3MF export, new optimizer, fake percentage, or new protected-color semantics.
- A Python/QThread CPU-bound optimization may still take significant real time, especially with a large catalogue and Best search. Elapsed time indicates ongoing work; it does not guarantee uninterrupted OS-level responsiveness for arbitrary expensive computations.

## Windows validation

1. Choose **All Bambu materials**, type into search during and after loading. There should be no error or prolonged all-gray window, and filtering should apply when preparation finishes.
2. Generate a forecast using Best planning; watch the elapsed clock and last planning step while the engine computes.
3. Open Optimization Details > Mixed Recipes. The Find in Filaments button should no longer appear there; it should still work on Physical Filaments.
4. Scroll the Plan form while hovering over Optimization strategy / Maximum palette size: selection must remain unchanged. Click the dropdown to select another value normally.
5. With Automatic forecast off, change a planning choice: the amber **OUTDATED FORECAST** banner must appear. Refresh: it should disappear.
6. Run `python -m unittest discover -s tests -v` and `git diff --check`.
