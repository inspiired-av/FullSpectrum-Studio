# Stage 4B — Help and Forecast Visual Polish

Baseline: Stage 4B contextual-help and forecast parity patches on `feat/qt-ui-redesign`.

## Help system

- Removed every question-mark control from **Results**, leaving its original section labels and actions.
- Removed the decorative help control alongside **Optimization Details**.
- Retained concise contextual help only for Preview, Source Palette, Live Forecast, Expected Palette, Color Optimization, Native Project Template, Advanced Settings, Filament Source, Filament Colors, and Protect Solid Colors.
- Switched help controls to a **QPainter-drawn 18 × 18 px circle with a centered ?**, unaffected by the application-wide Qt button padding. Accessibility, keyboard focus, hover tooltip, click modal remain.
- **Filament Source** explains how to build a local `filaments` JSON library with `name`, `brand`, `series`, `color`, links to the [Custom Brands README section](https://github.com/inspiired-av/FullSpectrum-Studio/blob/feat/qt-ui-redesign/README.md#custom-brands) and its [JSON example](https://github.com/inspiired-av/FullSpectrum-Studio/blob/feat/qt-ui-redesign/examples/custom-palette.example.json). Dialog links are clickable.

## Live Forecast layout

- Adds breathing room above/below Accuracy and Confidence captions.
- Places **Worst visible match** directly beneath the Expected Palette swatches as a compact target → predicted swatch row with HEX and real ΔE. No duplicate large banner.
- Missing optimizer data remains visibly unavailable; no fake color or ΔE is generated.
- No changes to planning, engine, persistence, export, paint/protection logic or rendering algorithms.

## Windows acceptance checks

1. Open a model, get a forecast, compare rings and worst-match swatches with the Mac layout, including narrow windowed mode.
2. Click **Filaments → Filament Source (?)**; the dialog must contain clickable README/example links and practical JSON steps. Hover shows a short summary.
3. Verify all help controls are small circles with visible, centered `?`, including at Windows display scaling; hover/click still work.
4. Verify **Results** has zero help glyphs; **Optimization Details** has none. Other appropriate headings retain the glyph.
5. Automatic/manual forecast invalidation and **Find in Filaments…** behavior must remain unchanged.
6. Run `python -m unittest discover -s tests -v`, followed by `git diff --check`.
