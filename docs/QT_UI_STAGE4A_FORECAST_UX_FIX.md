# Qt Stage 4A — Forecast state and warning display

Stage 4A runs `fullspectrum_engine.convert(..., plan_only=True)` in a background worker. This update only refines **presentation and scheduling**, not planner logic.

- A successful forecast is retained in memory for its source model. If relevant inputs change, the UI keeps the last accuracy, confidence, worst match and output swatches, but marks them **Previous forecast / Outdated**. They are never treated as a current plan.
- When Automatic forecast is off, input changes **do not** queue a new forecast. **Refresh Forecast** replaces the previous results with a new, current snapshot.
- When Automatic forecast is on, new input changes queue a debounced request. The old result stays visibly outdated while it runs. Stale or cancelled worker results are still rejected.
- Turning Automatic forecast on or off does not by itself invalidate a valid result. Slicer launch and auto-open preferences also do not affect the forecast.
- Failed requests use an explicitly red-colored, readable `Forecast unavailable` status. If the model has a previous result, its swatches remain displayed as **outdated**. If not, the UI shows an unavailable empty state.
- Selecting another model clears the old snapshot and prevents cross-model results from appearing.
- The Stage 3C encoding regression test now asserts that the displayed stage is **3C or newer** and the startup status uses the same stage, rather than freezing an obsolete version string.

No 3MF is written or altered. This patch does not change the optimizer, source geometry, physical filament protection, preview shading, or saved preferences.

## Windows verification

1. Get a successful forecast; turn off Automatic forecast.
2. Change Maximum palette size. Previous metrics and swatches should remain but say *Outdated*.
3. Set an impossible palette cap (e.g. fewer slots than pinned physical colors); press Refresh. The error should be red, and the previous results should still say *Outdated*.
4. Restore a valid setting; refresh successfully and check that the *Outdated* label clears.
5. Select a different 3MF; the previous palette and metrics should disappear.
6. Run `python -m unittest discover -s tests -v` and `git diff --check`.
