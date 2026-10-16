# FullSpectrum Studio — Qt Stage 2C: Results and UI activity

Stage 2C adds an actual **Results** tab without running the conversion engine. It
builds on the completed Stage 2B Filaments scroll-layout fix on
`feat/qt-ui-redesign` and leaves the Tkinter UI in place.

## What is enabled

- Current session overview: model name, native project template, output slicer,
  unsaved Plan settings, and honest "not run in Qt" states for conversion and validation
- Recent application activity from real UI operations: selecting source models and
  references, saving/reverting Plan settings, loading filament libraries, saving
  filament selection, scanning source colors, and changing model-specific protection
- A small indeterminate progress indicator **only during actual filament loading or
  source-color scanning**, never during idle and never for a simulated conversion
- Read-only, copyable view of an existing `.txt`, `.md`, `.log`, or `.csv` report
  (up to 2 MiB); loading a report does not run or validate a conversion
- File > Open Existing Report… (`Ctrl+Shift+O`), View > Results (`Ctrl+3`)
- Dark read-only text viewer and consistent "Stage 2C" labels

## Install

Extract the ZIP under Downloads. From your FullSpectrum repository:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2C"
python "$folder\install_qt_stage2c.py" .
```

To launch and test:

```powershell
python -m desktop.qt_app
python -m unittest discover -s tests -v
git diff --check
```

## Validate on Windows

1. Open Qt; the Results tab should say conversion and validation **Not run in Qt**.
2. Open a model from the header; Results should show the filename and an activity entry.
3. On Filaments, Load/Refresh, then Scan Source Colors; Results should record actual completion or failure.
4. Open an existing report from Results, verify text, Copy Report and Clear.
5. Resize the app smaller; Results and Filaments scroll independently, without overlap.
6. Save Plan settings and confirm the Results status changes to "Saved or unchanged".

**Deliberate limits:** source geometry preview remains Stage 3, engine conversion,
progress/forecast integration, output file creation, and slicer launch remain Stage 4.
Protection selections remain session-only and are not applied to exports.
