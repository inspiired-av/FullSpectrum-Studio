# Stage 3B Palette Interaction and Resizing Fix

## Problem
Qt native tooltip display for 31px `QLabel` swatches was unreliable on some Windows systems. The small fixed chips left unused horizontal space; the previous width regression test resized a child managed by a parent layout, so Qt restored the child width and the test failed (`16 not less than 16`).

## Fix
- `PaletteSwatch`: fixed-height, horizontally expanding swatch. The color's HEX and exact face count are also written to a persistent details line on hover. Click/Enter/Space locks the selection, while tooltip and accessible name remain available.
- `responsive_columns`: deterministic, bounded layout function; number of columns responds to the actual viewport resize event width. Swatches share available row width instead of remaining fixed 31px.
- Draggable vertical `QSplitter` between the OpenGL model and Source Palette. The user can enlarge the palette to see additional rows and collapse it back without changing the main left/right layout; the palette scrolls internally for many colors.
- Corrected the Stage 3B width-change regression test to vary the reflow width explicitly instead of requesting a child-widget resize that Qt's parent layout overrides.

No conversion behavior, model geometry, color import, or saved filament preferences are changed. Rendering inaccuracies at per-vertex gradients/material boundaries are a separate Stage 3C fidelity concern.
