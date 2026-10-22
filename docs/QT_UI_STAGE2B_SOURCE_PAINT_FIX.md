# Qt Stage 2B — Filament Source Switching and Painted Native 3MF Scan

This incremental patch requires the Stage 2B **Source Fix** (object colors + source selector moved to Filaments) to already be installed on `feat/qt-ui-redesign`.

## Changes

- Switching between *My inventory*, *All Bambu materials*, custom libraries, etc. no longer attempts to **save/validate the old table** as a navigation prerequisite. It safely stages valid changes and discards invalid draft selections when switching sources. **Save Filaments** and **Protect Selected** still require at least two distinct enabled filament colors.
- Source-refresh also cannot be blocked by a one-color library.
- Native Bambu/Orca 3MF scanning supports (a) whole-object physical-filament assignments and (b) one physical filament per face represented with unambiguous single-state `paint_color` codes. Unpainted faces use their object's default extruder. Scanner links each native object ID to its external mesh path using explicit component relationships and validates coverage.
- Explicitly rejects split-region facet paint, unsupported mixed-filament recipes, invalid references, missing meshes, and incomplete object coverage rather than guessing colors.
- UI now distinguishes **native face-painted models** from **native object-colored models**. Both still carry UI-only protected assignments until Stage 4 export integration.

## Install

Extract the ZIP under Downloads, then run from the FullSpectrum Studio repository:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2B_Filament_Source_Paint_Fix"
python "$folder\install_stage2b_filament_paint_fix.py" .
```

This installer updates only three Stage 2B Qt files and adds one test, this document, and three small installer-test fixtures. It checks the branch and exact hashes of prerequisite files, refuses to overwrite conflicting local edits, and supports re-running without changes. It does not alter installed printer presets, settings.json, Tkinter code, engine code or source 3MFs.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Optional private fixture checks:

```powershell
$env:FULLSPECTRUM_QT_SHAPES_3MF = "$env:USERPROFILE\Downloads\Shapes Material-colored.3mf"
$env:FULLSPECTRUM_QT_PAINTED_3MF = "$env:USERPROFILE\Downloads\3D_Printing_Test.3mf"
python -m unittest discover -s tests -p test_qt_source_switch_and_painted_colors_v3.py -v
```

Expected painted fixture: eight source colors, 17,844 total triangles; the Shapes fixture contains five source colors, 6,128 triangles.

## Manual checks

1. Select My inventory with one color. Confirm **Save Filaments** rejects it (two distinct colors required).
2. Without Revert, switch to All Bambu materials. Confirm no modal warning and that rows reload for the new source. Repeat with Custom.
3. Open the original `Shapes Material-colored.3mf` and Scan Source Colors. Five object colors should appear.
4. Open `3D_Printing_Test.3mf` and Scan Source Colors. Eight combined painted/object colors should appear, total 17,844 faces.
5. Choose protection rules only for UI testing; Stage 4 export does not yet apply protection to Bambu facet-painted native sources.

**Important:** Native Bambu paint can encode sub-triangle, split-region colors. A single triangle may represent multiple colors. This Stage 2B scanner deliberately handles only one unambiguous filament state per triangle and rejects unsupported split states rather than reporting an incorrect face count. It is a read-only source-color display, not a conversion guarantee.
