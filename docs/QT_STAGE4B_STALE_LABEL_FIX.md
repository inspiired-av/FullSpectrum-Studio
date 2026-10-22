# Qt Stage 4B — Previous forecast label compatibility

Previous forecasts must remain visibly marked when a same-model planning setting changes.

The first-run filament configuration gate can block a new optimizer run, but must **not** intercept the display update of a previously successful result. `_present_forecast_pending` now updates the Expected Palette caption before testing the filament setup gate. It still blocks optimization until the filament source is ready and confirmed.

- Manual mode with a ready setup: `Previous forecast · N planned colors`, and the existing Refresh Forecast instruction.
- Automatic mode with a ready setup: the same previous palette caption, with the existing neutral updating status.
- Unconfirmed setup: previous palette caption preserved, with the setup-required status; no forecast is scheduled.
- No prior result: `No forecast yet` and no stale label.
- Different model: existing clear-inspection path discards the previous forecast entirely.

No gauge, engine, pin, library-loading, export, or persistence change.

Verification: run `python -m unittest discover -s tests -v` and `git diff --check` on Windows. The full Qt suite requires PySide6; the included targeted behavior tests work without it.
