# Stage 4B Pin and Forecast Synchronization Fix

Baseline: Stage 4B Stability Fix installed over the Stage 4A checkpoint `af79043`.

- Pin and Use checkbox edits are staged in memory immediately, and emit `planning_changed`.
- A valid change invalidates the current forecast; Automatic forecast uses the existing debounce to re-plan. Manual forecasting preserves the old results as outdated.
- Changing pin/enable state does **not** persist it. Click **Save Filaments** to save to disk.
- Invalid states (too many pins, fewer than two different colors) do not run an optimizer with a stale, previously valid selection. They display a correction message.
- Revoking an enabled filament clears source-color protections tied to that filament and notifies the 3D preview.
- Revert invalidates the current forecast as restored preferences may change planner choices.
- Replaces stale Stage 2B source-code assertion with wheel-safe source control assertion. `WheelSafeComboBox` is still a `QComboBox` subclass.

No optimizer modifications or 3MF export.
