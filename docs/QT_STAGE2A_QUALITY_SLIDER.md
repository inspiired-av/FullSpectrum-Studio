# Stage 2A polish — Quality vs. waste slider

Replaces the Quality vs. waste spin box in Qt **Advanced Settings** with a horizontally resizable slider and live numeric value (0–100).

- **Smart quality enabled:** slider, numeric value, and form label are dimmed; manual editing is disabled. The existing manual quality value remains stored.
- **Smart quality disabled:** slider becomes editable; the value label updates as the slider moves.
- **Save Settings:** persists the original `quality_bias` integer via the existing shared settings store.
- **Revert:** restores both Smart quality and slider position without writing preferences.
- Uses the same `quality_bias` and `smart_quality` keys as the Tkinter UI; engine and conversion logic are unchanged.

After installing, run `python -m desktop.qt_app`, expand Advanced Settings, and toggle Smart quality to verify the disabled/enabled appearance. Run `python -m unittest discover -s tests -v` for regression coverage.
