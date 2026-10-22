# Stage 4B — first-run compatibility regression fix

This is a targeted follow-up to **Stage 4B First-Run Gate**. Install after the First-Run Gate patch on `feat/qt-ui-redesign`.

## Fixes

- `RingGauge.text()` now returns the same centered percentage string rendered by the painter, or `—` with no result. Existing Stage 4A tests that read `w.accuracy.text()` keep working, with no QLabel replacement or visual change.
- Forecast invalidation still resets RingGauge and WorstMatchPanel in a real window. The older Stage 4A `BehaviorHarness`, which substitutes a lightweight QLabel-style stub, can reset accuracy using `setText('—')` instead. Confidence and worst-match controls are only addressed when present.
- Automatic forecast toggle checks the first-run filament gate in real windows. The Stage 4A unit harness, which was written before the gate existed, can exercise scheduling without constructing that UI; its old behavior is retained.

## Non-changes

No optimizer, input/output file formats, persistence behavior, color visualization, model loading, forecast readiness rules, or first-run confirmation behavior has been changed.

## Verification

```powershell
python -m unittest discover -s tests -v
python -m desktop.qt_app
git diff --check
```

Check both first-run blocked state and returning user's saved-filament automatic forecast on Windows. Qt rendering-dependent tests require PySide6.
