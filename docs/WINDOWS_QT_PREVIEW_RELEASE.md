# FullSpectrum Studio — Windows Qt Preview

This is a **community-built, noncommercial Windows preview** published from
[`inspiired-av/FullSpectrum-Studio`](https://github.com/inspiired-av/FullSpectrum-Studio),
not an official release from the [upstream author](https://github.com/Gr33k3D/FullSpectrum-Studio).

It includes the Qt redesign through commit `73917cd190a339316c1f905615abad96b54d79f4`,
plus packaging-only changes on `release/windows-qt-preview`.

## What's included

- PySide6 **Plan**, **Filaments** and **Export** workspace (not the earlier Tkinter Windows UI).
- Original, Predicted, Color Loss, Anchor Influence and Wireframe preview modes.
- Filament **Use** and **Require** selection; source-color **Assign Filament** workflow.
- Live forecast controls and native 3MF export for OrcaSlicer and Bambu Studio.
- Per-slicer executable preferences, export activity/report diagnostics, progress and cancellation.

## Downloads

- **Portable ZIP** (`FullSpectrum-Studio-Windows-Qt-Preview-Portable-*.zip`): extract the whole
  `FullSpectrumStudioQt` folder; run `FullSpectrumStudioQt.exe` inside it. Do not move only the EXE
  out of the extracted folder; it needs the bundled runtime files.
- **Setup EXE** (`FullSpectrum-Studio-Windows-Qt-Preview-Setup-*.exe`): per-user installer
  in a separate *FullSpectrum Studio Qt Preview* folder, with a separate uninstall entry.
- **SHA256SUMS.txt**: checksums for the portable and installer downloads.

The runtime is bundled; users do **not** need to install Python. An installed compatible
Bambu Studio or OrcaSlicer may be needed for native-template selection and opening results.

## Compatibility and cautions

- Preview release for **Windows x64**; it is not code-signed. Windows SmartScreen may warn
  about an unsigned community executable. Obtain downloads from this repository's own Releases
  page and verify checksums before running; never disable antivirus protection globally.
- The Qt preview currently has finite mesh and OpenGL safety limits; high-polygon-quality
  presets and drag-and-drop model loading are not included in this release.
- This installer is separate from the original Windows installer, but both frontends read
  and write `%LOCALAPPDATA%\FullSpectrumStudio\settings.json`. Back up that file before
  experimenting, and avoid running the two versions concurrently.
- Templates are user-provided native 3MF projects. Verify generated 3MFs in the selected
  slicer and inspect filament assignments before printing.
- Reports, error logs and model files stay local unless the user chooses to share them.

## Upstream contributions

The ongoing upstream contribution work remains in the **draft pull request stack**;
this preview release is **not** a substitute for upstream review or merge.
Packaging-specific commits belong only on `release/windows-qt-preview`.

## License and notices

Source and binaries are provided under the repository's **PolyForm Noncommercial 1.0.0**
license. Retain `LICENSE` and `THIRD_PARTY_NOTICES.md` when redistributing.
Original required notice: Copyright 2026 Gr33k and FullSpectrum Studio contributors.
