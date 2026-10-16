# Qt Stage 3A — Interactive 3D geometry viewport

Stage 3A adds a **depth-tested OpenGL 3.3 Core** model viewer to the independent Qt frontend (`python -m desktop.qt_app`). The Tkinter production interface and FullSpectrum conversion engine are unchanged.

## Capabilities

- Reads 3MF build geometry, parts and nested components, applying slicer-saved 3MF affine transformations in an XYZ / Z-up coordinate system. Preserves mesh handedness (no mirrored 3D Builder-style preview).
- Imports triangle geometry from OBJ and embedded GLB (simple glTF 2.0 triangle primitives) and rotates glTF's Y-up coordinate system to Z-up without reflecting the mesh.
- GPU depth testing, double-sided flat-shaded geometry, wireframe mode, automatic framing, camera reset, left-drag orbit, right-drag/Shift-drag pan, scroll zoom and keyboard `R` reset.
- Reads model files on a worker thread and ignores stale results after a new model is selected; archive parser enforces conservative memory and triangle limits. Does **not** modify the source.
- Keeps Predictive, Color Loss, palette and conversion features disabled until Stages 3B and 4. **The cyan/gray model color is a neutral preview shade, not original filament color.**

## Limitations

- Requires a Windows GPU/driver exposing OpenGL 3.3 or a compatible Qt/software OpenGL implementation and the `PyOpenGL` package; error message is shown when the graphics context is unavailable. It does not silently replace the OpenGL viewport with an inaccurate painter's-order renderer.
- More than 250,000 triangles are deterministically sampled for display; the viewport says when the model has been sampled. **Neither geometry nor print data is modified.**
- glTF: external buffers, sparse attributes and non-triangle primitive modes are unsupported in the Stage 3A preview. Advanced texture/material rendering is deferred.
- Material-colored and face-painted 3MF source colors are not rendered until Stage 3B. Printed-color predictions are not inferred.
- This is a source-viewer milestone, not new slicer compatibility or printer validation. Stage 2 report/Filaments features remain unchanged.

## Install and test (PowerShell, from the repo root)

Extract the distributed ZIP in Downloads, then:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage3A"
python "$folder\install_qt_stage3a.py" .
python -m pip install -r requirements-qt.txt
python -m unittest discover -s tests -v
python -m desktop.qt_app
```

## Manual smoke tests

1. Open an original 3MF, such as a colored gradient model, and check that the geometry is correctly oriented (not mirrored). Try orbit/pan/zoom and Reset View.
2. Open `Shapes Material-colored.3mf`; expect 5 objects and 6,128 triangles, but neutral model shading until Stage 3B.
3. Open `3D_Printing_Test.3mf`; expect 17,844 triangles. Compare placement and orientation against Bambu Studio/3D Builder.
4. Select Original / Wireframe; Predicted and Color Loss remain unavailable.
5. Switch models while an earlier model is loading; only the newest model should display. Check Filaments and Results remain usable.

The automated geometry tests do not require Qt; OpenGL window tests need a Windows display and functional graphics context.
