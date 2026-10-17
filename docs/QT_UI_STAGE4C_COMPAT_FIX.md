# Stage 4C preview and test corrections

Checkpoint: `5502f6f` on `feat/qt-ui-redesign`, with the first Stage 4C patch already installed.

- `fullspectrum_engine.py`: **plan-only direct-source 3MF** analysis now emits original-slot-indexed Color Loss and Anchor Influence display OBJs alongside Predicted. The engine calculates the actual per-color Delta E and anchor identity using its existing `plan_analysis_preview_colors` method; the colors are not a Qt estimate.
- `desktop/qt_app/forecast_preview_assets.py`: raises the analysis-view bound from 250,000 to 750,000 triangles, matching the existing full-surface Qt model loader. Reuses smoothed render geometry when engine OBJs have identical vertices and face order. Validates each overlay path and its matching MTL as before.
- `desktop/qt_app/main_window.py`: Stage 4C badge/status text.
- `tests/test_qt_stage3c.py`: explicitly decode UTF-8 on Windows, and check the current preview selection logic.
- `tests/test_qt_stage4c.py`: tests the installed production paths without importing `stage4c_transform.py` from the ZIP.

## Memory and speed

A 450,992-triangle direct-color 3MF is within the matching 750,000-triangle geometry limit, but preparing and holding three full analysis overlays still uses significant RAM. All loading and smoothing are worker-only. The application will decline a larger input rather than puncture its geometry by skipping triangles. For very large models, a topology-preserving display simplifier may be added separately.

## Limitations

Only the visualization artifacts from plan-only forecasts change. No native 3MF export, profile, settings, pinning, or underlying optimization plan changes. Predicted 3D, Color Loss, and Anchor Influence are engine-generated estimates before slicing; the physical print may vary. Some sources can still lack analyzable color metadata, in which case the corresponding mode is correctly unavailable.

## Validation

Run `python -m unittest discover -s tests -v` and `git diff --check` in the repository. Test UI with VSLA v4_SOLID_NoFilter.3mf and 3D_Printing_Test_SOLID.3mf, switching forecast modes and model files; verify pin changes mark views OUTDATED. Tests with actual Windows OpenGL contexts cannot be performed from this build environment.
