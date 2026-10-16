# Stage 3C — Source Color Selection & Protection UX

This incremental patch builds on Stage 3C (commit `5253ead` plus the Stage 3C installer). It is a read-only interface refinement. No conversion, 3MF writing, or settings persistence changes are made.

- Click a selected Source Palette swatch a second time to clear selection. Clicking empty palette space or clicking the model without dragging also clears it. **Clear** and **Esc** provide explicit alternatives. Orbit, pan and zoom remain unaffected.
- Clearing the selected color also clears the matching row selection in the Filaments tab, without changing any saved filament or model-specific protection assignments.
- Original mode now renders protected materials in their **original colors by default**. A teal marker on protected swatches and a teal indicator in the assignment table indicate their status without recoloring the model. Both amber selection and teal protection markers can coexist on the same swatch.
- Enable **Tint Protected** in the Source Palette to temporarily tint all protected regions teal in the viewport. A selected region takes amber precedence. Disabling the toggle restores original colors; no GPU vertex buffers are recreated.
- **Manage…** in the Source Palette navigates to the *Protect Solid Colors* controls in **Filaments**, which remain authoritative for material assignments. Use **Scan Source Colors** there if the source table has not yet been populated.
- Switching models retains neither the selection nor its protection assignments, consistent with the Stage 3C model-session design.

Test with `python -m unittest discover -s tests -v` and Windows Qt/OpenGL interaction. PySide6 GUI tests may be skipped in Python environments without Qt.
