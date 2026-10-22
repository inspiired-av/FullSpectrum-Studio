# Qt Stage 4A — Assign Filament shortcut

Fix the Source Palette's former `Manage…` shortcut, which navigated to the
Filaments tab but left its **Protect Solid Colors** table empty until the user
clicked **Scan Source Colors** manually.

- Label the shortcut **Assign Filament…**, enabled only with source colors selected.
- Switch to Filaments, scroll to the assignment controls, and scan the source
  asynchronously **only when it has not been scanned for the selected model**.
- Preserve all selected source HEX keys through the scan and select their rows
  after the result arrives. Reuse existing loaded colors on subsequent clicks.
- Ignore stale scan results after model changes and prevent duplicate scans.
- Focus the target filament selector once matching rows are selected.
- Never implicitly protect source colors or mutate any source model, output,
  engine preferences, or physical filament assignments.
- On unsupported native paint files, show the existing source scan warning;
  keep Source Palette selection intact so it can be inspected or retried.

The new regression checks cover both preloaded and lazy-scanned selection paths.
Run `python -m unittest discover -s tests -v` after installing.
