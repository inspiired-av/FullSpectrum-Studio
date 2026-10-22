# Qt Stage 4A — Read-only source inspection and native palette forecast

Built on `feat/qt-ui-redesign` commit `dc4a8fc`. Stage 3C viewer, source palette, multi-selection and solid protection remain unchanged.

- Inspect project color slots using the existing engine's `inspect_project(..., metadata_only=True)`. 3D geometry remains rendered by Stage 3C.
- **Refresh Forecast** calls the real engine's `convert(..., plan_only=True)` in a Qt worker, with the current unsaved Plan settings, selected catalog/custom filament source, enabled and pinned physical filaments, and model-specific solid assignments.
- Forecast displays actual estimated quality, confidence, worst Delta E, physical/mixed slot counts and up to 32 output swatches. These are planning estimates, **not print/slicer verification**.
- **Automatic forecast** is opt-in and debounced; changing a model or relevant setting invalidates old results. Worker completion checks a generation token to avoid stale results. Cancel requests interruption on the next progress callback.
- Native-project solid-color overrides are explicitly **not** passed to the engine: the current engine accepts solid-color protection only for standard material-colored 3MFs. A descriptive warning is shown instead of claiming that those assignments were planned.
- The planning output directory is temporary and cleaned. No native 3MF, CSV report or settings are written by Stage 4A. The existing engine may use other internal temporary work and caches while planning.
- Predicted model geometry, loss visualization and source-model export are deferred to Stages 4C/4D. Existing historical report viewer is unchanged.

## Windows verification

1. Load a standard material-colored 3MF, check source slot inspection, and click **Refresh Forecast** on Plan.
2. Confirm accuracy, confidence, worst color mismatch and the planned palette populate only after the engine returns.
3. Adjust `Maximum palette size`, `Smart quality` and enabled/pinned filaments, then rerun and verify the display updates; with Auto forecast enabled, confirm it schedules automatically.
4. Change models while a forecast is in progress; confirm a stale result does not populate the new model.
5. Test a native slicer 3MF with model-specific protected assignments and confirm the unsupported protection combination is reported rather than silently ignored.
6. Run `python -m unittest discover -s tests -v` and `git diff --check`.

**Limitation:** Windows/PySide6 OpenGL and real-engine integration must be tested on a user's machine. The repository unit tests exercise the exact engine-call contract and safe output behavior with a fake engine.
