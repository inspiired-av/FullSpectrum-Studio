# Stage 3C — Interpolated gradients and protected-color preview

Baseline: `5253ead` on `feat/qt-ui-redesign`. This remains a **read-only** Qt viewport; it does not change the saved source or conversion engine.

## Included

- Exact 3MF color-group triangle `p1/p2/p3` corners are retained for interpolation in the vertex shader, rather than being flattened into a mean face swatch.
- Per-triangle averaged RGB remains the exact **preview selection key** for gradients; no RGB quantization or conversion outputs are rewritten.
- Shader overlay uses each triangle's flat source-color key and highlights a selected source color in amber or a protected source color in teal. Changing selection does not rebuild the GPU mesh.
- Clicking a Source Palette swatch selects the matching Filaments > Protect Solid Colors table row if scanned; selecting a row in that table updates the palette and preview. Scanning remains a separate, explicit action.
- Protecting / unprotecting a source color updates the overlay and swatch border. Changes are session-only until Stage 4.
- Overlays are not shown on separately imported saved Predicted OBJ previews because their material keys are unrelated.
- Existing orbit, pan, zoom, reset, native object and painted colors, and complete-surface geometry loading remain unchanged.

## Limitations

- Native Bambu/Orca complex split-region face painting is not interpolated. Supported single-filament faces are rendered as whole face colors.
- Color-group interpolation is performed in RGB as a visualization; the palette still groups colors by representative face key.
- Protection assignments are UI-only and do not alter output or mix recipes until Stage 4.
- Complete-surface rendering is limited to 750,000 triangles. Higher counts require a future topology-preserving preview LOD, not face skipping.
- OpenGL shader/Qt GUI validation requires testing on Windows; automated pure-Python tests do not verify GPU output.

## Test steps

1. Open a standard colored 3MF with p1/p2/p3 variations; compare gradients with reference viewer.
2. Load the 59-color VSLA model; click Source Palette swatches and inspect amber highlighted regions.
3. Open Filaments, press Scan Source Colors, select a table row and verify the swatch/model synchronize.
4. Protect a selected color using an enabled filament; verify teal overlay / marked swatch and undo protection.
5. Open a different model; verify old selections/protections disappear.
6. Switch among Original, Wireframe, and an existing saved Predicted OBJ; ensure model-source highlight doesn't appear on Predicted.
7. Run `python -m unittest discover -s tests -v` and `git diff --check`.
