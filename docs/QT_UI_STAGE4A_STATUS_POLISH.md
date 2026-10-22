# Stage 4A — Automatic forecast status polish

- In **Automatic forecast** mode, a changed planning input starts the existing
  debounce timer and shows neutral blue `Updating forecast automatically…`
  instead of an amber *outdated* warning. The previous estimated palette and
  metrics remain visible during the update.
- In **manual** mode, the status line alone says
  `Previous forecast is outdated — select Refresh Forecast to update.`
  The palette heading only identifies `Previous forecast · N planned colors`.
- Before the first forecast, only the status line prompts the user to refresh;
  the palette heading says `No forecast yet`.
- Switching source models still clears the old forecast. Failures stay red.
  Toggling automatic refresh off cancels queued timer/pending refreshes; it does
  not discard an earlier result.
- Existing plan-only optimizer, backgrounds workers, debounce interval,
  renderer, protection controls, saved settings and export limitations are
  unchanged.

This is a UI behavior fix, not an optimizer speed improvement. The warning itself
was not doing expensive engine work; it was visually misleading while a refresh
was already queued.
