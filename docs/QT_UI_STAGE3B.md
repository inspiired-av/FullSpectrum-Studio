# Qt Stage 3B — Original color preview and smoother shading

This patch applies over **Stage 3A with the matrix-upload fix**, on `feat/qt-ui-redesign`.

- **Original** now reads explicit 3MF color groups (including base material groups), native Bambu/Orca per-object filament assignments, and unambiguous single-slot `paint_color` faces. Source palette is read-only and includes counts from the entire model, even if the preview is triangle-sampled. Faces with complex split paint remain neutral rather than claiming a false color; the status identifies them. Transparent 3MF colors are not guessed.
- **Shading** uses area-weighted vertex normals with a 53-degree crease threshold and softer studio lighting. Curved meshes are smoother, and sharp mechanical edges remain distinct. Source vertices/triangles are not modified.
- **Predicted** becomes available when the user explicitly selects **Load Predicted…** and opens a *previously generated* OBJ with a same-stem `.mtl` using `Kd` diffuse colors. It is labeled **Saved predicted OBJ**; live forecasts are still Stage 4 work. This action does not run the optimizer, validate a slicer project, or generate an export. Color Loss remains disabled.
- The original source and predicted files remain separate; switching back to Original/Wireframe restores the source mesh. New source selection invalidates earlier predicted previews.
- OBJ source preview supports local same-stem MTL diffuse colors. GLB remains geometry-only in this phase; glTF PBR/textures, intricate split-region paint, image texture sampling and live predictions are not implemented.
- The optional Qt requirements now include NumPy for reliable PyOpenGL array support, including Python 3.14.

## Install (PowerShell from repository root)

Extract the distribution ZIP, then:

```powershell
$folder = "$env:USERPROFILE\Downloads\FullSpectrum_Qt_UI_Stage3B"
python "$folder\install_qt_stage3b.py" .
python -m pip install -r requirements-qt.txt
python -m unittest discover -s tests -v
python -m desktop.qt_app
```

## Windows checks

1. Open `VSLA v4_SOLID_NoFilter.3mf`; expect **59** source colors across **1,304** triangles, with smooth curved surfaces and distinct lettering edges.
2. Open `Shapes Material-colored.3mf`; expect **5** object colors, **6,128** triangles.
3. Open `3D_Printing_Test.3mf`; expect **8** object/face colors across **17,844** triangles.
4. Original, Wireframe, orbit/pan/zoom, Reset View and sidebar tabs should still work. Source palette below the viewport should scroll without changing the model view.
5. Load an existing saved predicted OBJ with its same-stem MTL to activate Predicted. The application must never present this as a *new* live forecast.

**No changes** to Tkinter, the conversion engine, saved filament preferences, source 3MFs, or native project exports.
