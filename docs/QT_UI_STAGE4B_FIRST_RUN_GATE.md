# Stage 4B — First-run filament setup and forecast gating

Baseline: `feat/qt-ui-redesign`, after `FullSpectrum_Studio_Qt_UI_Stage4B_Circle_Help_Fix` (which incorporates Stage 4B parity, help polish and earlier pin synchronization fixes).

## Design rationale

Opening a model is natural, so geometry rendering, original colors and source inspection remain immediate. A read-only color optimization, however, must not run against unconfirmed defaults on a first launch. The UI now clearly separates a successfully **loaded** source from an **intentionally configured** source.

### First run

- With no saved `source` preference, opening a model does **not** start a forecast. Plan shows **Configure Filaments…** and a disabled **Use These Filaments** action.
- Click Configure Filaments, pick a source, load its options and review or change enabled/pinned colors. A matching **Use These Filaments for Forecast** action appears in Filaments. This requires at least two distinct enabled colors (except fixed CMYKW mode), a complete library load and valid pin selections.
- Selecting a different source explicitly, modifying valid filament checkboxes, or saving a valid filament selection also confirms the current session. If the default source is unchanged, the user can confirm via the dedicated button without saving.
- With Automatic forecast ON, an available model starts a debounced forecast after confirmation. With Automatic forecast OFF, press Refresh Forecast. Unsaved filaments still affect the current forecast; Save Filaments and Save Settings retain their existing persistence roles.

### Returning user

- An explicit, valid saved `source` preference is treated as configuration. On launch, the filament list begins loading in the existing background worker; the read-only forecast waits until the requested source completes successfully.
- A saved custom library must still be an existing file, and must load with enough enabled colors. Missing/invalid sources or unusable selections block forecast until corrected.
- A small **Filaments ready · saved configuration** / **current session** line makes the restored state visible.
- Model and source changes invalidate earlier forecasts. Previous results for the same model retain their existing stale treatment until refreshing, and a different model clears them.

## Architecture

- `forecast_setup_gate.py` is pure Python: no Qt, optimizer, file mutations, or mock color data. It only decides readiness based on current source, saved source, explicit consent, source load completion, enabled colors and validation.
- `MainWindow` applies this gate at both `_request_forecast` (manual and debounced automatic path) and the event-queue scheduling points. No planner, 3MF, export or persistent settings changes.
- The **Use These Filaments** confirmation is session-only. To make the source choice persist on future launches, use the existing **Save Settings**; **Save Filaments** persists enable/pin selections.
- Catalog loading uses the existing Filaments worker; no synchronous catalog load was added.

## Windows QA checklist

1. Fresh/empty settings: Open Model first. 3D preview appears, no forecast starts, configure actions visible.
2. Visit Filaments, load the source and choose **Use These Filaments for Forecast**. Automatic mode should start once ready; manual mode should await Refresh Forecast.
3. Save Settings with a valid source; relaunch. After asynchronous source loading, selecting a model should automatically forecast when Auto is ON.
4. Custom library path missing or invalid: both automatic and manual forecasting blocked with a clear action message.
5. Enable fewer than two colors or create an invalid pin set: both forecast paths blocked. Fix the selection: automatic mode resumes after debounce.
6. Change model while loading another source: old-source results must not be reused.
7. Ensure unsaved checkbox changes affect the session, while only existing Save buttons persist their respective preferences.
8. Run `python -m unittest discover -s tests -v` and `git diff --check`.

Qt UI integration requires testing on Windows. Pure logic and installer tests are runnable without PySide6.
