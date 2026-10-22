# Stage 3C — Multi-select source-color protection

Built on the Stage 3C interaction refinement; conversion and filament persistence unchanged.

- Click a selected color in **Protect Solid Colors** again to deselect it.
- Ctrl+click rows or palette swatches to add/remove colors, Shift+click table rows for a range.
- A plain click selects one color; Escape/Clear clears both views.
- **Protect Selected** assigns the chosen enabled physical filament to **every selected exact source color**, explicitly; merely selecting does not write an assignment.
- **Remove Protection** removes mappings for the selected set. Selection survives table updates.
- Multiple distinct source colors mapped to one physical filament share its output color; a warning is displayed when multi-selecting.
- All assignments stay model-specific and preview-only until the exporter is integrated in Stage 4.
- The shader highlights all selected face-color identities without GPU mesh rebuild, retaining protected-color indicators.
- No source model, output 3MF, or persistent settings are changed by this patch.

Run tests: `python -m unittest discover -s tests -v` and `git diff --check`.
