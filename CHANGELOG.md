# Changelog

All notable changes to HOI4 Content Maker are documented here.

---

## [2.0] — 2025

### Decision Maker — New Features
- Full Decision Maker wizard with three-panel layout (tree / editor / preview)
- Live HOI4-themed preview canvas rendering decisions as they appear in-game
- GFX icon picker with inline image grid browser
- Category visibility toggles — hide/show individual categories with eye buttons
- **Solo** button — isolate one category in the preview for focused editing
- **👁 All / 🚫 All** quick visibility buttons
- Country tag name mapping system (Settings → Country Tag Names)
  - Map TAG codes to display names (`SOV` → `Soviet Union`)
  - One-click "Load Vanilla Tags" presets ~45 common HOI4 country codes
- Loc token style selector (colon-style vs dot-style)
- HOI4 localisation token rendering in preview:
  - `[SOV:NameWithFlag]` → resolved country name
  - `[NKO]Korea` bare-tag syntax → resolved name
  - `§Y...§!` colour codes rendered with correct colours
  - `§2` number colour codes stripped cleanly
  - `$var$` scripted variables with leading digit stripping
- GFX icons shown in tree rows (with emoji fallback when PIL unavailable)
- Decision names in tree strip loc codes for clean display
- Import existing `.txt` decision files with full field parsing
- **Apply Edits** — edit raw code in the Code tab and sync back to the data model
- Export to decisions `.txt`, categories `.txt`, localisation `.yml`, and scripted loc `.txt`
- Undo/redo support in Decision Maker
- Autosave with session restore prompt on reopen

### Decision Maker — Bug Fixes
- Fixed `NameError: name 'h' is not defined` in `_gen_decisions_file` (orphaned cache stub removed)
- Fixed `AttributeError: 'bool' object has no attribute 'strip'` in generator functions — added `_s()` safe string coercion wrapper applied to all 84 field accesses
- Fixed Apply Edits not saving: replaced fragile filedialog monkeypatch with a direct inline parser
- Fixed autosave restore not populating the tree — rebuild now fires after data loads, not before
- Fixed category duplication on restore/apply — added `_dedup_cats()` deduplication pass
- Fixed Solo button not working when a decision (not a category) was selected
- Fixed Solo, 👁 All, 🚫 All, and eye toggle buttons calling `_build_preview()` directly instead of `_rebuild_right()`, causing active tab to not refresh
- Fixed stale editor data being written back to the model when toggling visibility
- Fixed Code tab crash (`TclError: window isn't packed`) on scrollbar pack order
- Fixed Python 3.14 forward-reference errors in `_snap_then()` / `_on_dec_win_close`

### Focus Tree Editor
- Drag-and-drop focus canvas with zoom, pan, multi-select
- Prerequisite and mutex connection drawing
- Per-focus properties panel with GFX browser
- Inline code view
- Export to `national_focus/*.txt` and localisation `.yml`

### National Spirit Wizard
- Ideas/spirit block generator with GFX browser
- Slot, modifier, trigger field support

### Dynamic Modifier Wizard
- Dynamic modifier block generator with modifier picker

### Event Maker
- Full event authoring with option builder, effect picker
- Scripted localisation support
- Live event preview
- GFX background picker

### General
- Single-file distribution (`hoi4_content_maker.py`) — no pip install required for core features
- Persistent config saved to `~/.hoi4_focus_maker.json`
- Mod folder scanner: auto-discovers sprites, focus IDs, event IDs, decision IDs, country tags
- Recent mods list
- Settings panel: GFX paths, extra GFX directories, event dimension profiles
- Window geometry saved and restored between sessions
- Splash screen on launch

---

## [1.x] — Earlier

- Initial Focus Tree Editor release
- National Spirit Wizard
- Basic event support
