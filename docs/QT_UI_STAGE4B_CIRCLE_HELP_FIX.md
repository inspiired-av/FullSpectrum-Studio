# Stage 4B — Circular contextual help glyphs

- Removed contextual help controls from **Model Preview** and **Source Palette**. Their labels and functionality are unchanged.
- Retained the existing relevant Plan/Filaments help topics, including custom JSON filament library links; Results still has no help glyphs.
- Help widgets use a 20×20 logical pixel fixed-size button, fixed layout policy and zero stylesheet padding.
- The outline is painted from one **common radius** centered in the widget, instead of drawing an ellipse using the full widget bounds. It remains a circle even when some Windows style changes widget geometry.
- The `?` is still painted explicitly in the same square centered on the circle. Tooltip and click dialog remain operational.

## Validate on Windows

Run `python -m unittest discover -s tests -v` and `git diff --check`. Visually check the glyphs next to Live Forecast, Expected Palette, Color Optimization, Native Project Template, Advanced Settings, and Filament Source/Filament Colors. Confirm the `?` characters remain visible and hover/click help works at ordinary and high DPI scale. Model Preview and Source Palette must have **no** glyphs.
