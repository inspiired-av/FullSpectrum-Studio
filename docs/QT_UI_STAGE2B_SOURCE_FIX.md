# Qt Stage 2B — Filament-source layout and native solid-object scan

This is an incremental update to Stage 2B; it doesn't change the Tkinter app, engine, conversion rules, or native template exporter.

## Changes

- Moves the **Filament Source** dropdown and **Custom Filament Library** picker from Plan to **Filaments**, leaving a **Manage Filament Colors…** shortcut on Plan. The single shared `source` and `custom` settings keys are unchanged.
- **Save Filaments** saves the filament source/library and anchor enabled/pinned selections, without saving unrelated unsaved Plan controls.
- Adds read-only inspection of Bambu Studio or OrcaSlicer projects whose **entire objects** are assigned to one physical filament color. Displays color swatches and mesh-face counts from actual native project metadata.
- Retains existing standard material-colored 3MF face-color scanning. Projects with mixed filaments, incomplete object assignment metadata, or painted faces are rejected with a more specific explanation.
- Marks native object-color counts with an amber notice explaining that protection assignments are **UI only until Stage 4**. The scanner does not modify 3MF files, convert models, or claim that object-level protection is supported by the current exporter.

## Installation

Extract the zip and run from `feat/qt-ui-redesign`:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2B_Source_Fix"
python "$folder\install_qt_stage2b_source_fix.py" .
```

## Validation

```powershell
python -m unittest discover -s tests -v
python -m desktop.qt_app
git diff --check
```

Use **Open Model** with an original standard material-colored 3MF or the Bambu Studio `Shapes Material-colored.3mf` (solid objects assigned distinct physical colors), then open **Filaments** → **Scan Source Colors**. For the Shapes test sample, the scan should show **five source colors** and **6,128 faces** across the five objects. No model painting or viewport highlighting occurs yet.

For nonstandard native 3MFs with mixed recipes or face-painted regions, use a suitable original material-colored 3MF input instead or wait for later engine support. These source types are deliberately not misclassified as simple object-level colors.
