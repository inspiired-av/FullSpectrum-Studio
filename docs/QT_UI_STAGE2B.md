# Qt UI Stage 2B — Filament Management

The **Filaments** tab now supports a searchable swatch table, enabling colors,
pinning physical filaments, and model-specific solid source-color assignments.
It uses the existing `desktop.filament_options.selectable_filament_options` adapter
and reads the same FullSpectrum settings as the Tkinter UI.

## Behavior

- Select the filament source (and custom JSON path, if applicable) on **Plan**.
- Open **Filaments** and press **Load / Refresh**. On first tab selection, loading starts automatically.
- Enable at least **two distinct** colors. Pinned colors must be enabled and
  must not exceed the selected physical slot limit (Auto defaults to six).
- **Save Filaments** persists enabled/pinned keys only. **Revert** reloads
  settings. Plan's independent unsaved edits are not overwritten.
- To protect a solid color, use **Open Model** to select an *original* standard
  material-colored `.3mf`, then **Scan Source Colors** on the Filaments tab.
  Select a source-color swatch and an enabled target filament, then click
  **Protect Selected**. The exact color/faces and mapped filament appear in
  the table. These rules are **in-memory, specific to that model** and clear
  when a different model is selected; they are not written to preferences.
- Actual model-preview face highlighting arrives in Stage 3; applying protected
  rules during conversion arrives in Stage 4. This is configuration only.
- Inventory and 3MF scanning run in background Qt threads, and stale scan
  results are discarded when a different file or source is selected.

## Testing

```powershell
python -m unittest discover -s tests -v
git diff --check
```

The original Tkinter GUI and native conversion engine are not modified.
The Stage 2A slider visual fix is a prerequisite.
