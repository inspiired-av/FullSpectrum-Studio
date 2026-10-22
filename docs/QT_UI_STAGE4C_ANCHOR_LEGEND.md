# Qt Stage 4C — Anchor Influence legend

The final Stage 4C change adds a lower-left, mouse-transparent legend inside
`ModelViewport` while `Anchor Influence` is selected. The legend displays two
swatches per selected physical anchor: a categorical overlay color and the
actual HEX filament color, followed by slot and filament name. Saved pins are
labeled. The categories reflect the native engine's first contributing MIX
component and are not a numeric measure of influence. The six display colors
repeat for slots 7–8; the legend explains that if applicable.

Rows come directly from the last successful forecast's `planningDetails.anchors`.
Invalid/incomplete metadata never produces an invented legend. It disappears
when the forecast becomes stale, upon model change, and when switching to
another preview mode. The existing Color Loss legend remains unchanged.

## Windows validation

1. Forecast `3D_Printing_Test_SOLID.3mf`; select `Anchor Influence` and compare
   the slot names/colors with Optimization Details.
2. Switch to Color Loss and back, then Original. Only the appropriate analysis
   legend should appear.
3. Change a pin (manual forecast): old anchor key hides on stale prediction;
   refresh and verify current anchors reappear.
4. Load another model and ensure old anchors are not shown.
5. Resize/orbit/pan/zoom. The legend must stay within the viewport and not
   capture mouse interaction.
6. Run all tests and `git diff --check` before checkpoint commit.

No engine planning, geometry, or export behavior was altered.
