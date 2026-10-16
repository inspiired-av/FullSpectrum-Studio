# Stage 2A UI polish: template indicators + selectable slicer executables

This incremental patch preserves the Stage 2A Qt UI and the existing Tkinter frontend.

- Native slicer template information appears in teal when valid, muted when no template is selected, and red when invalid.
- Incompatible slicer/version warnings appear in amber, independently of the valid template information.
- Advanced Settings now has `Choose EXE…` and `Auto` buttons for the selected output slicer.
- The chosen `.exe` path is saved separately for Bambu Studio and OrcaSlicer, preserving portable/nightly executable selections when switching slicers.
- Clearing to **Auto** removes only the selected slicer's custom path; automatic executable discovery and launching remain part of Stage 4.
- Settings are committed only when **Save Settings** is clicked. Revert discards unsaved changes.

## Install

Extract the ZIP to Downloads. From your FullSpectrum Studio repository on `feat/qt-ui-redesign`:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2A_Polish"
python "$folder\install_qt_stage2a_polish.py" .
```

## Test

```powershell
python -m unittest discover -s tests -v
python -m desktop.qt_app
```

The installer requires the unmodified Stage 2A source files. It refuses unexpected modifications rather than overwriting work. Existing user preferences and saved templates are not edited during installation.
