# Qt UI Stage 2A — Functional Plan Preferences

Incremental patch for `feat/qt-ui-redesign`, following Stage 1. Does not replace Tkinter, change the conversion engine, or add Qt to release builds.

## Functions

- Connects Qt Plan controls to the **existing** `desktop/settings_store.py` file. Loading and editing preferences are read-only until **Save Settings** is clicked. Revert discards unsaved edits and reloads the latest preferences.
- Shares configuration with Tkinter without changing its storage format. Saves only modified Plan fields, reloading before committing so pinned filament selections and slicer paths are not overwritten.
- Supports Balanced / Maximum fidelity / Fill palette, 2–32 colors and Auto, selectable filament source, and custom JSON library browsing.
- Adds native 3MF template selector with validation and parsed printer/nozzle/process information; never changes the template.
- Provides Advanced Settings for base palette, planning effort, planning sample, physical slots, catalog region, smart quality, quality vs. waste, and slicer preferences.
- Improves wording consistency. **Compose Palette remains disabled**. The 3D viewport and forecast remain placeholder-only until Stages 3/4.

## Install

From the repository root, with Stage 1 already installed and branch `feat/qt-ui-redesign` checked out:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2A"
python "$folder\install_qt_stage2a.py" .
```

## Run and test

```powershell
python -m desktop.qt_app
python -m unittest discover -s tests -v
python -m unittest discover -s "$folder\tests" -v
```

In the Qt window, choose Maximum fidelity, set palette size to 24, select a valid native 3MF, click **Save Settings**, and close/restart. The values should be restored. Change them again and click **Revert** to confirm no changes are persisted. The old Tkinter frontend should see the same stored settings the next time it starts.

## Limitations

- No engine conversions, file parsing, background processing, protected solid colors, filament pinning, or preview rendering are connected yet.
- A `QFileDialog` selection validates the template through the existing `native_project_template.inspect_template` API. Invalid templates are rejected; a previously saved but now missing template is displayed as unavailable without a blocking pop-up.
- The legacy Tkinter settings format remains the source of truth. When both apps are open simultaneously, only explicitly modified Qt fields are saved. If another app edits the **same** field concurrently, the most recent save wins.
- Existing per-user settings are not modified by installing Stage 2A, only when **Save Settings** is clicked.
