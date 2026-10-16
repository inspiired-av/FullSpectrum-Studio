# Stage 2B — Windowed Filaments Tab Layout Fix

Fixes an overlap in short-height Windows Qt windows: filament action controls and the Protected Solid Colors section could be painted on top of the filament and protection tables.

Changes **only** `desktop/qt_app/filaments_tab.py`: places all Filaments controls inside a vertical `QScrollArea` with layout minimum-size enforcement. The filament table and protected-color table each have their own fixed viewport height and internal row scrolling. On smaller windows the outer tab scrolls vertically; no controls should overlap.

The patch does **not** alter persisted filament selections, source switching, color scanning, protected-color logic, the conversion engine, or Tkinter.

## Install

After extracting `FullSpectrum_Studio_Qt_UI_Stage2B_Layout_Fix.zip`, run from the Git repository root:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage2B_Layout_Fix"
python "$folder\install_stage2b_layout_fix.py" .
```

The installer checks the current branch and requires the previous Stage 2B paint/source fix. It does not overwrite unexpected local changes or create backup files in the working tree. The previous UI file is included in the patch test fixtures for recovery if needed.

## Test

```powershell
python -m unittest discover -s tests -v
git diff --check
python -m desktop.qt_app
```

In a normal (not maximized) window select the Filaments tab, load Custom filament library, click Scan Source Colors, and scroll the full tab down. The tables scroll independently. In particular, **Enable All**, **Clear Pins**, **Save Filaments**, **Revert**, and the Protected Solid Colors controls should all remain distinct, not overlap.
