# Stage 4B: Live Forecast Visual Parity

This patch follows the Stage 4B contextual-help patch and optional Help Glyph Fix.

- Introduces QPainter antialiased circular **Accuracy** and **Confidence** indicators using only computed engine percentage fields.
- Introduces side-by-side worst-match **Target** and **Predicted** color swatches. These use the HEX values in the existing engine-generated `gapMessage` string; missing values result in neutral swatches, never invented colors.
- Retains exact engine Delta E field and physical/mixed filament counts.
- Preserves the last computed metrics when a same-model forecast becomes outdated; clears gauges and swatches on model removal/change.
- Reduces every contextual-help `?` control to a consistent **22×22 circular** button with zero interior padding and a centered text glyph; click/hover help is unchanged.
- Does not touch any engine modules, persist any extra state, or trigger forecast calculations.

## Windows QA

1. Open a model and run Refresh Forecast. Check that gauge percentages match the text values and that a pair of HEX swatches appears when worst-match data is available.
2. Confirm that changing planning settings with automatic forecast disabled preserves the last shown gauges/swatches and marks that forecast outdated.
3. Open a different model; all stale gauges and swatches should clear.
4. Hover and click several help `?` controls, including Live Forecast and Native Project Template. They should be circular and launch their original help dialogs.
5. Resize the app horizontally, including narrow windowed mode, and scroll over plan inputs to confirm the wheel-safe controls still work.
6. Run `python -m unittest discover -s tests -v` and `git diff --check`.
