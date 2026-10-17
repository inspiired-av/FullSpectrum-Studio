# Stage 4C — Predicted 3D forecast and color-loss previews

Baseline: `feat/qt-ui-redesign` checkpoint `5502f6f`. Stage 4D still owns actual conversion, 3MF export and slicer integration.

## Implementation

- On a **valid** GUI read-only forecast, `ForecastRequest.visualization=True` requests the **existing engine** plan-only analysis assets under a `TemporaryDirectory`, with `analysis_dir` confined to that workspace. Existing API/test `SimpleNamespace` requests that do not opt in keep `analysis_dir=None`.
- The forecast worker loads available OBJ/MTL preview meshes and prepares their normal buffers **before** temporary files disappear. Only meshes within the analysis directory are accepted; any unreadable or oversized overlay is skipped without failing the successful numeric forecast.
- Existing QOpenGLWidget displays **Original, Predicted, Color Loss, Anchor Influence, Wireframe** via the same renderer. Camera orbit/pan/zoom is preserved while switching, rather than reset to defaults. Reset View remains explicit.
- Color-loss key follows the **engine's** current heatmap thresholds: ΔE ≤ 2 green, 2–6 yellow, >6 orange/red. These are estimated pre-slice errors, not calibrated printer measurements.
- Original source swatches, selection overlays and protected-color tint do not get improperly applied to predicted/loss/influence meshes.
- An older same-model forecast remains available but is labelled **OUTDATED** after Plan or Filaments settings change. Selecting a different model clears live analysis meshes. Late worker results remain guarded by Stage 4A's serial check.
- Manual **Load Predicted…** external OBJ compatibility remains; it is explicitly identified as external and cannot be misrepresented as the current optimizer's plan.

## Known limitations

- `direct_source_colors=True` standard material-colored 3MF analysis currently emits **only a predicted OBJ**. It does not generate a real color-loss or anchor-influence OBJ, so those options stay disabled (not synthesized from approximations). Native slicer project analysis may provide all three.
- Large analysis overlays above 250,000 triangles or 64 MiB OBJ are refused for memory safety, with a warning. Original model preview remains unaffected. This is a Stage 4C display bound; actual geometry is unchanged.
- The internal predicted and original display geometries need not be identical reduced preview meshes; split-screen or pixel-perfect side-by-side registration is not claimed here.

## Windows acceptance

1. Open a supported Bambu/Orca native `.3mf`, load filaments, run Refresh Forecast. Select **Predicted**, **Color Loss**, and **Anchor Influence** if present. Confirm source/original remains available and hover/camera behavior works.
2. Compare the same location while orbiting and switching views; switching should preserve the viewpoint.
3. Change a pin with Auto off: older predicted view should show **OUTDATED** until Refresh Forecast completes. With Auto on, new analysis should replace the old view only after a successful fresh result.
4. Open a new model while the previous forecast is running. Old data must never appear in the new model.
5. Open a standard material-colored 3MF such as VSLA. Predicted should load if generated; Color Loss and Anchor Influence should remain disabled if the engine has not supplied the corresponding assets.
6. Run `python -m unittest discover -s tests -v`, `git diff --check`. Keep testing output 3MF integrity separately in Stage 4D.
