# Qt UI redesign — Stage 1: foundation

This is a **separate experimental UI**, built with PySide6/Qt Widgets to approach
FullSpectrum Studio's Mac workspace layout. The existing Tkinter frontend and
conversion engine are untouched. No models, filament settings, or 3MF files
are written by the Qt prototype.

## Run on Windows

Use the `feat/qt-ui-redesign` branch of the FullSpectrum Studio checkout:

```powershell
python -m pip install -r requirements-qt.txt
python -m desktop.qt_app
```

For consistency with the existing Windows build workflow, Python 3.12 is a
reasonable choice. `requirements-qt.txt` is **optional** and separate from the
existing release requirements. The Qt shell is **not** included in release
builds yet.

## What works

- Resizable Mac-inspired split workspace, dark palette, preview area, and
  right-side Plan / Filaments / Results navigation.
- Working **Open Model** and **Reference** file pickers. These record only the
  selected paths in the live Qt process and display a filename; no parsing,
  model loading, or conversion occurs in Stage 1.
- File > Open Model / Open Reference / Exit, and View > Plan / Filaments /
  Results, including shortcuts: `Ctrl+O`, `Ctrl+Shift+R`, and `Ctrl+1/2/3`.
- Preview/forecast and conversion controls correctly appear **disabled** until
  the underlying systems are connected. No fabricated color-accuracy metrics.
- Responsive Qt splitter; users can drag to resize the preview and settings
  panel independently.

## What is deliberately not connected

- Stage 2: filament inventory, protected colors, planner settings, saved user
  preferences, and controls.
- Stage 3: existing mesh viewport integration, original/predicted color
  display, orbit/pan/zoom, source analysis, large-model optimizations.
- Stage 4: preview/compose background workers, live forecast, validation,
  error reports, and Bambu Studio/OrcaSlicer output launching.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p "test_qt_ui_stage1.py" -v
```

The Qt GUI smoke checks are skipped automatically if PySide6 is not installed.
For headless Linux CI, set `QT_QPA_PLATFORM=offscreen` before testing if you
want to execute the optional Qt smoke checks.

## Migration constraints

1. Preserve all existing engine/export modules and the Tkinter production entry
   point until full Qt parity and round-trip validation.
2. Do not place PySide6 in `requirements-windows.txt` or the release workflow
   until the Qt frontend is actually being packaged.
3. Do not simulate predicted accuracy, mixed recipes, or source color swatches
   without real engine data. The Stage 1 view is a visibly labelled shell.
4. Maintain readable, consistent labels; favor `Preview`, `Plan`, `Filaments`,
   `Results`, `Color Optimization`, `Maximum Palette Size`, and `Reference`.
5. Later stages should keep background conversion off the Qt GUI thread and
   preserve the existing cancellation, native 3MF validation, and privacy-safe
   error reporting.
