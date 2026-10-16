# Stage 4B — Help glyph visibility fix

**Scope:** Context help button presentation only; no model, planning, engine, or settings changes.

## Issue

On Windows with the Qt/Fusion dark theme, the small question-mark help controls were blank despite their background/border rendering. The global `QToolButton` rule provides 8px vertical and 12px horizontal padding, which is too much for a fixed 22×22 control. Its tool button text/icon policy could also hide the character.

## Fix

`SectionHelpButton` uses `ToolButtonTextOnly`, a 24×24 control, and an ID-specific zero-padding/zero-minimum override with an explicit font size. Hover summaries, click-to-open Markdown dialogs, tab navigation, and all existing help content are preserved.

## Windows checks

1. Launch Qt UI with no model and confirm each `?` glyph is visible beside the section headings (including Plan, Filaments, Results, Model Preview and Source Palette).
2. Hover: concise tooltip. Click: expanded help dialog with Close.
3. Verify Advanced Settings, combo boxes, and the rest of the theme are unchanged.
4. Run `python -m unittest discover -s tests -v` and `git diff --check`.
