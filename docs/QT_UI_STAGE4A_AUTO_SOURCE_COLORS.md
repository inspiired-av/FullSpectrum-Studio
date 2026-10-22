# Stage 4A — Automatic Source Color Loading

- **Source Palette** renders colors from the read-only mesh preview. For standard 3MF this can include interpolated vertex colors. It is for inspection and interactive highlighting.
- **Protect Solid Colors** reads an independent, authoritative scan of *assignable* source colors. On native slicer projects, the scanner may only recognize single-state painted faces/object colors; unsupported split-region paint is not silently treated as assignable.
- The manual **Scan Source Colors** button is removed. After the preview loads a `.3mf`, the Filaments tab scans source colors in the background once, then populates the table and its counts automatically.
- Preview parsing and the authoritative scan are sequenced to avoid opening a large file twice simultaneously. The scanner does not write back to the model.
- A source swatch selected while the scan is running remains selected when the table is populated. Assign Filament… reuses the table without rescanning.
- Unsupported/invalid source assignments show an **inline** explanation under Protect Solid Colors; no automatic modal error appears. OBJ and GLB source-color previews are still supported, but exact physical-filament protection continues to require supported 3MF data.
- Filament assignment is still an explicit **Protect Selected** action. No palette optimizer, source geometry, global filament preferences, or conversion code changes are made.

## Tests

`python -m unittest discover -s tests -v`

Check the VSLA material-colored 3MF (automatic 59-color table), Shapes material-colored 3MF (5 colors), a native Bambu/Orca project (authoritative scanner limitations), and opening a second model while the first scan is in progress.
