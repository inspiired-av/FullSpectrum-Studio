# Stage 4B — Contextual section help and pin-test compatibility

## What is included

- Fourteen contextual `?` controls beside headings in **Plan**, **Filaments**, **Model Preview/Source Palette**, and **Results**.
- Each `?` displays a short **hover tooltip** and an extended **click guide** in a scrollable, read-only, dismissible dialog. The guide text lives centrally in `section_help.py`.
- **About Templates** is removed. The **Native Project Template ?** includes the former procedure for making an empty slicer 3MF, plus requirements and limitations.
- Results' legacy Stage 2C placeholder wording is refreshed to Stage 4B terminology.
- `test_qt_stage4b_pin_forecast.py`: a missing `pinned_anchor_keys` entry in an untouched settings file is treated as an empty list. No production settings code is changed.

## Behavior and constraints

- Help controls do not save settings, start forecasts, pin filaments, modify a source file, open external links, or invoke conversion.
- Existing engine, forecast metrics, physical/mixed recipes, automatic refresh and 3D rendering behavior are unchanged.
- Native template explanations distinguish the eventual export requirement from Stage 4B's read-only forecasting.
- Hover summaries are available without clicking; modal guides can be dismissed via Close or Esc.

## Manual Windows check

1. Hover **Live Forecast ?** and confirm the short tooltip.
2. Click it and confirm the complete explanation is scrollable; dismiss using Close/Esc.
3. Check **Expected Palette**, **Optimization Details**, **Color Optimization**, **Native Project Template** and **Advanced Settings**.
4. Check the **Model Preview** and **Source Palette** headings and all three **Filaments** headings.
5. Open **Results** and check Current Session, Current Activity and Existing Report.
6. Confirm **About Templates** is gone and its instructions appear under Native Project Template `?`.
7. Confirm the pin/forecast test now passes when the settings file has no saved `pinned_anchor_keys` key.
8. Run `python -m unittest discover -s tests -v` and `git diff --check`.

The installer requires branch `feat/qt-ui-redesign` with the previously delivered Stage 4B Pin/Forecast Fix files. Existing files with unknown edits are rejected **before writing anything**.
