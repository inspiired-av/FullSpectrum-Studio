# Qt Stage 3C — Windows encoding and stage-label cleanup

- Explicitly decode UTF-8 when regression tests read Qt Python source files. Avoid dependence on Windows' locale-default `cp1252`, which fails on some Unicode code points.
- Show **Stage 3C** in the UI prototype badge and startup status after the interactive multi-select/protection refinements.
- Add a small regression check to keep all file reads in this test explicitly UTF-8.
- No model import, prediction, filament preferences, multi-selection, shader, or OpenGL logic changes.

## Verify on Windows

```
python -m unittest discover -s tests -v
python -m desktop.qt_app
```

`git diff --check` may emit Windows line-ending conversion warnings; they are distinct from test failures.
