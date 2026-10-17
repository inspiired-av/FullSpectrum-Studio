# Stage 4D-A1 — Dominant and Interactive Anchor Influence

**Base commit:** `5121c4c` (`feat/qt-ui-redesign`). This is Stage 4D-A (advanced analysis), **not Stage 4D export**.

## User-facing behavior

1. Open a model and complete a read-only forecast.
2. Select **Anchor Influence**. The lower-left legend shows physical anchors using **actual physical filament colors by default**.
3. Change **Physical colors** to **Distinct colors** for high-contrast categories. These artificial colors are available only as a display option.
4. Click any physical anchor in the lower-left legend. The model switches to a **0–100% contribution heatmap** for that anchor. The visualization includes every source region where that filament appears in the optimizer's physical-component recipe, including secondary/tertiary components.
5. Click the same anchor to return to the dominant-anchor display. Changing the color-display dropdown does not re-run the optimizer or reset the camera.

A mixed region's **dominant** anchor is its highest-ratio component, ties resolved to the smallest physical slot. The percentage heatmap depicts **planner recipe proportions**, not measured printer usage, mass, opacity, transparency, physical influence of colorants, or sliced/toolpath volume. FullSpectrum cannot measure those without actual slicing and material calibration.

## Data integrity and performance

The engine emits a temporary **source-face slot map** (uint32, little-endian) in plan-only analysis. This map corresponds to each triangle of the engine-generated preview OBJ. For standard material-colored 3MFs it derives from original RGB face-color slots. For native painted projects, it is parsed from the source-slot `usemtl slot_N` in the reduced preview OBJ. This is **not** inferred by comparing visually similar colors and does not modify the original model. Geometry sampling rules are unchanged.

The Qt forecast worker validates the slot map and recipes and tags only the influence overlay's prepared GPU buffer. One small OpenGL 3.3 `RGBA32F` texture stores up to eight physical-component percentages per original source slot; clicking/choosing display colors only changes shader uniforms. Predicted and Color Loss buffers and source geometry are not mutated. Rendering does not re-run the planner or CPU face smoothing.

If the map/recipe data is absent, out-of-bounds, or inconsistent, the interactive influence view is disabled rather than inventing a dominant anchor. Existing Original/Predicted/Color Loss remain available. Limits: maximum 750,000 preview faces and 2,047 source colors for this GPU analysis path.

The legend is intentionally **clickable** in Stage 4D-A (Stage 4C's transparent non-interactive legend no longer applies). The Color Loss legend remains mouse-transparent. The legend is hidden on stale forecasts or model changes. No native 3MF export is done.

## Planned later Stage 4D phases

- **4D-B:** object/plate include/exclude selection with consistent preview/optimizer/export scoping.
- **4D-C:** native 3MF project export, profile preservation, validation and slicer handoff.

## Verification on Windows

Run `python -m unittest discover -s tests -v` and `git diff --check`. Visually test VSLA (59 source colors) and `3D_Printing_Test_SOLID.3mf` (450,992 source triangles). Confirm dominant physical filament swatches, categorical optional mode, mixed contributions including minority filaments, accurate stale warnings, unchanged camera, and no extra export files. For mixed recipes with 20:80 ratios, verify the **80%** component is the dominant physical color.
