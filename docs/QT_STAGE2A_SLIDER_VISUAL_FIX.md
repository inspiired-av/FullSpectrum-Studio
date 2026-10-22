# Stage 2A — Quality slider visual correction

Incremental follow-up after the Stage 2A Slider patch. No additional dependencies.

- Explicitly styles both sides of the slider's track and uses a transparent widget background to avoid Fusion/Windows drawing a bright grey rectangular strip.
- Uses proper Qt slider pseudo-state selectors for the disabled groove, track fill, and handle. Disabled styling is fully desaturated.
- Displays an enabled, legible `AUTO` status chip while Smart Quality is checked. The slider, its numeric value, and the field label remain disabled. It also explains how to reenable manual control in a tooltip.
- Preserves the existing `quality_bias` integer, its 0–100 range, Save Settings/Revert behavior, and all other UI/engine behavior.
- Installer checks Stage 2A Slider source hashes, refuses unknown modifications and conflicting files, and is safe to rerun.

After installing, launch `python -m desktop.qt_app`, expand Advanced Settings, and toggle Smart Quality. When enabled, the slider should have a muted dark track and grey handle, an `AUTO` chip, and a dimmed number. When disabled, the cyan progress line and bright handle reappear, with the previously chosen value.
