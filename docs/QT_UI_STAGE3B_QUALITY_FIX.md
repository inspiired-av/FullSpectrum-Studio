# Qt Stage 3B — Full-surface rendering and responsive palettes

This incremental patch follows Stage 3B on `feat/qt-ui-redesign`.

## Large mesh rendering

- Stop striding `triangles[::step]`: omitting alternate faces opens watertight surfaces and reveals interior/backside triangles. Full source geometry now renders for models through 750,000 triangles, including the reported 450,992-triangle project.
- For models above the full-surface budget, provide an actionable error instead of a visibly incorrect, perforated preview. Topology-preserving LOD for multi-million-triangle models remains Stage 3C work.
- Geometry parsing plus vertex normals/packing run on the existing loader QThread, before returning to the Qt UI. The 3MF source itself is never rewritten.

## UI layout

- Filament and protected source-color tables have minimum sizes but share surplus height at tall window sizes. The parent page still scrolls in a short window.
- Source palette is a responsive strip/grid of larger swatches, analogous to the Mac reference. Hex codes and full-model face counts remain accessible via tooltip, with a concise summary label. Rows adapt to splitter and window width.

## Out of scope

- No live color forecast, conversion, or additional texture sampling. Source vertex gradients remain limited by Stage 3B's per-face color treatment.
- No unsafe blind mesh decimation, no engine/Tkinter/preferences changes.
