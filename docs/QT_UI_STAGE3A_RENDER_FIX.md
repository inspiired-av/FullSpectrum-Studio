# Stage 3A — OpenGL camera matrix orientation fix

The Stage 3A preview correctly loaded triangles but sent Qt `QMatrix4x4.copyDataTo()`'s
**row-major** result to OpenGL using `GL_FALSE` (which expects column-major input).
This effectively transposed the projection-view matrix and rendered just a distorted
wedge of a model. On OpenGL 3.3 Core, use `GL_TRUE` to transpose the copied
row-major float array during `glUniformMatrix4fv` upload. The added
`_upload_projection_view` helper keeps the representation explicit.

This patch does not change geometry, model scaling, mesh winding, GL shaders,
mouse controls, the optimization engine, or user settings. It requires the
Stage 3A installation on `feat/qt-ui-redesign` and refuses unexpected edits.

Test on Windows using `3D_Printing_Test.3mf`, then `Shapes Material-colored.3mf`:
all intended geometry should now be visible, with orbit, zoom, and wireframe.
If unexpected clipping remains, capture screenshots from reset view and after orbit.

Regression test: `python -m unittest tests.test_qt_stage3a_matrix_upload -v`
Full regression: `python -m unittest discover -s tests -v`
