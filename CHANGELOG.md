# HOI4 Content Maker — Changelog

---

## Session 5 — Shared Focus Tree Position and Viewport Fixes

### Focus Tree — `_raw_rewards` Regex Missing `shared_focus` Blocks

**[BUG FIX] `shared_focus = { }` blocks were silently skipped by the raw-block extractor**
- `_load_extra_tree` (line ~17629) and `_load_extra_tree_from_path` (line ~18341)
- The regex `r'\b(?:joint_focus|focus)\s*=\s*\{'` used a word-boundary `\b` before `focus`.
  In `shared_focus`, the preceding `_` is a word character, so `\bfocus` never matched inside it.
  As a result, `completion_reward`, `available`, `bypass`, and `cancel` blocks from all
  `shared_focus = { }` files were captured via the low-fidelity tokenizer reconstructor
  (`_blk_to_str`) instead of raw source text, causing effects and conditions to be silently dropped.
- Fixed both functions: regex changed to `r'\b(?:shared_focus|joint_focus|focus)\s*=\s*\{'`.

---

### Focus Tree — Shared/Joint Extra Trees Not Auto-Fitting Viewport After Load

**[BUG FIX] Loading a shared or joint tree via `+ Shared` / `+ Joint` buttons left the viewport unchanged, making the new focuses appear off-screen**
- `_load_extra_tree` (line ~17896) and `_load_extra_tree_from_path` (line ~18571)
- Both functions called `_redraw()` (throttled, preserves current zoom/pan) but not `_fit_all()`.
  The "Load All" batch dialog already called `_fit_all()` after loading; individual load buttons did not.
  If the loaded tree's focuses were at grid coordinates outside the current viewport (e.g. a shared
  tree at grid x=27 while the main tree was at x=0–15), the tree appeared to be missing or at the
  wrong position when it was simply off-screen.
- Fixed: added `self._fit_all()` call immediately after `self._redraw()` in both functions.

---

## Session 4 — Focus Tree Fixes and Dictionary Expansion

### Focus Tree — `tag =` → `original_tag =` (all remaining locations)

**[BUG FIX] Draw.io import wizard preview code still used `tag =` instead of `original_tag =`**
- Lines ~15436, ~15668, ~14904
- The `_export()` function was already correct (`original_tag =`) but three other locations still emitted
  the wrong field: the Draw.io wizard's live preview text, the code preview pane built after import,
  and the "New Tree" dialog preview label.
- Fixed all three to use `original_tag =`, so the preview output matches actual export output exactly.

---

### Focus Tree — Import Parser Reads Country Tag from File

**[BUG FIX] Importing a `.txt` focus tree reset country tag to placeholder `"TAG"` instead of reading from file**
- `_import_txt()`, around line ~15980
- When importing an existing HOI4 focus tree file, the parser read the `focus_tree` block's `id` field
  but ignored the `country = { modifier = { original_tag = X } }` block entirely.
  The tag was inferred only from focus ID prefixes via `_detect_and_apply_tag()`, which fails for
  small trees or trees whose focus IDs don't follow the `TAG_` prefix convention.
- Fix: after calling `parse_block()` on the `focus_tree` block, extract:
  ```
  block["country"]["modifier"]["original_tag"]  (preferred)
  block["country"]["modifier"]["tag"]            (backwards compat for old exports)
  ```
  Store the result as `self._tree_country_tag`. This value is used by `_export()` as the fallback
  tag when the tree ID doesn't match the `^TAG_` pattern.
- Also: after `_detect_and_apply_tag()`, if the prefix was not auto-detected from focus names but
  `_tree_country_tag` was set from the file, populate `_default_focus_prefix` so new focuses created
  after import auto-prefix with the correct tag.

---

### EFFECT_DEFS — Missing Scope Effects

**[ADDED] `every_hostile_country` and `random_hostile_country` scope effects**
- These country scopes iterate over / pick one of all countries currently at war with the current
  country. Commonly used in war-related focus completion rewards and event effects.
- Both placed in the "Scopes" category alongside the existing `every_enemy_country` entry.

---

### MODIFIER_DEFS — Missing Building-Specific Production Speed Modifiers

**[ADDED] 18 building-specific `production_speed_X_factor` modifiers (Country category)**
- `production_speed_industrial_complex_factor` — civilian factory
- `production_speed_arms_factory_factor` — military factory
- `production_speed_dockyard_factor`
- `production_speed_infrastructure_factor`
- `production_speed_air_base_factor`
- `production_speed_bunker_factor`
- `production_speed_coastal_bunker_factor`
- `production_speed_anti_air_building_factor`
- `production_speed_radar_station_factor`
- `production_speed_rocket_site_factor`
- `production_speed_nuclear_reactor_factor`
- `production_speed_synthetic_refinery_factor`
- `production_speed_fuel_silo_factor`
- `production_speed_rail_way_factor`
- `production_speed_agriculture_district_factor` (MD-specific building)
- These are all used heavily across the mod's idea files (1000+ occurrences in 74 files)
  but were absent from MODIFIER_DEFS, so users couldn't find them via the modifier picker.

---

### MODIFIER_DEFS — Missing Resource-Specific State Modifiers

**[ADDED] 6 `local_resources_X_factor` modifiers (State category)**
- `local_resources_oil_factor`
- `local_resources_steel_factor`
- `local_resources_aluminium_factor`
- `local_resources_rubber_factor`
- `local_resources_tungsten_factor`
- `local_resources_chromium_factor`
- These state-scoped modifiers apply a multiplier to that specific resource in a state.
  Used in many spirit files (340+ occurrences) but were absent from MODIFIER_DEFS.

---

## Session 1 — Output Correctness Fixes (Focus Tree)

### Focus Tree Maker (`_export` and `_build_focus_code`)

**[BUG FIX] `tag =` → `original_tag =` in focus_tree country block**
- File line ~17655
- The country selector block was emitting `tag = TAG`, which checks the current tag (can change
  during civil wars or puppeting). Changed to `original_tag = TAG`, which checks the permanent tag.
- Without this fix the focus tree could load for the wrong nation in certain scenarios.

**[BUG FIX] `search_filters = { FOCUS_FILTER_POLITICAL }` was silently dropped on export**
- Lines ~17718–17720 (`_export`) and ~14447 (`_build_focus_code` preview)
- The condition `if sf and sf != "FOCUS_FILTER_POLITICAL"` skipped writing the filter whenever
  it was set to the default political value. All political focuses were exported with no
  `search_filters` block, breaking the in-game focus search UI.
- Fixed by removing the exclusion: `if sf:` now always writes the filter when set.

**[BUG FIX] Focus log used wrong scope and missing "executed"**
- Line ~17765 (`_export`) and ~15661 (import scaffold code path)
- Was: `log = "[GetDateText]: [Root.GetName]: focus TAG_focus_name"`
- Fixed to: `log = "[GetDateText]: [This.GetName]: focus TAG_focus_name executed"`
- `[Root.GetName]` is incorrect in focus tree scope. `[This.GetName]` refers to the country
  completing the focus. "executed" matches the convention used in all existing MD focus files.

---

## Session 1 — Output Correctness Fixes (Decision Maker)

**[BUG FIX] `complete_effect` log — lowercase "decision" and extra " complete" suffix**
- Lines ~7034 and ~7043
- Was: `log = "[GetDateText]: [Root.GetName]: decision TAG_my_dec complete"`
- Fixed to: `log = "[GetDateText]: [Root.GetName]: Decision TAG_my_dec"`
- Matches the CLAUDE.md standard (capital D, no trailing word).

**[BUG FIX] `remove_effect` log — said "decision … removed" instead of the effect identifier**
- Line ~7053
- Was: `log = "[GetDateText]: [Root.GetName]: decision TAG_my_dec removed"`
- Fixed to: `log = "[GetDateText]: [Root.GetName]: remove_effect TAG_my_dec"`
- Matches actual MD decision files (e.g. `remove_effect COM_disband_the_presidential_guard_decision`).

---

## Session 1 — Output Correctness Fixes (Event Maker)

**[BUG FIX] Event wizard always emitted an empty `immediate` block**
- Lines ~9632–9636
- Even for `is_triggered_only = yes` events with no immediate effects, the wizard wrote:
  `immediate = { log = "..." }`. This adds unnecessary log I/O overhead on every trigger
  and is non-standard in MD.
- Fixed: removed the unconditional `else` branch. `immediate` is now only written when
  the user has provided content.

**[BUG FIX] Event option log was injected even when the option had no effects**
- Line ~9644
- CLAUDE.md rule: "Log only if there are actual effects in the option."
- Was injecting a log line unconditionally into every option.
- Fixed: log injection now only runs when `opt_effects` is non-empty.

---

## Session 2 — Full Diagnostic Pass

### Effect System — `_normalize_effect_fields`

**[BUG FIX] `set_variable` import stored field under wrong key `"var_name"`**
- Lines ~10808–10815
- When importing a file containing `set_variable = { TAG_my_var = 0.05 }`, the parsed dict
  was stored as `{"var_name": "TAG_my_var", "value": "0.05"}`.
- `_render_effect` reads `g("var", ...)` (matching EFFECT_DEFS field name `"var"`), so the
  variable name was always discarded on re-export and replaced with the fallback `my_var`.
- Fixed: normalized dict now uses `{"var": ..., "value": ...}`.

**[BUG FIX] `add_to_variable` import stored fields under wrong keys `"variable"` / `"amount"`**
- Lines ~10788–10794
- Same class of bug. Imported `add_to_variable` effects always re-exported with the placeholder
  variable name `AM_my_stat_var` and default amount `0.05` regardless of actual content.
- `_render_effect` reads `g("var", ...)` and `g("value", ...)`.
- Fixed: normalized dict now uses `{"var": ..., "value": ..., "tooltip": ...}`.

---

### MD Additional Income Wizard

**[BUG FIX] `localization_key` value in scripted_localisation block was double-quoted**
- Line ~16575
- Was generating: `localization_key = "my_tooltip_key"`
- HOI4 scripted localisation expects bare (unquoted) keys for `localization_key`.
- Fixed: now generates `localization_key = my_tooltip_key`.

**[REMOVED] Dead empty fallback `text` block in scripted_loc output**
- The block `text = { trigger = { NOT = { has_idea = X } } localization_key = "" }` was
  being appended after the main text block. An empty `localization_key` is invalid in HOI4.
- Removed entirely. The `defined_text` block now only contains the active case.

**[BUG FIX] Spirit snippet used `name = "Literal String"` instead of a loc key**
- Line ~8685
- Was: `name = "Free Trade Bonus"` (inline literal, bypasses the localisation system)
- Fixed to: `name = {idea_id}` (bare localisation key reference, per CLAUDE.md convention)

**[BUG FIX] Spirit snippet missing `allowed_civil_war = { always = yes }`**
- CLAUDE.md requires this for all national ideas/spirits so the spirit persists through civil wars.
- Added as the second field in the generated spirit block (after `name`).

---

### Event Maker

**[BUG FIX] No `WM_DELETE_WINDOW` handler — all events lost silently on window close**
- The Event Maker had no close protocol and no autosave, unlike all other wizards.
- Added `_ev_save_state()` and `_ev_load_state()` backed by a temp JSON file
  (`hoi4_cm_event_autosave.json` in the system temp directory).
- `WM_DELETE_WINDOW` now calls `_ev_save_state()` before destroying the window.
- On next open, the autosave is restored automatically instead of starting blank.

---

### National Spirit Wizard

**[BUG FIX] `_save_raw` loc regex only matched obsolete `key:0 "value"` format**
- Line ~3616
- Was: `r'^\s*(\S+?):0\s+"(.*)"'` — required a `:0` version suffix that the wizard's own
  output no longer emits (current format is `key: "value"`).
- When the user edited the raw preview and saved back, loc key changes were never
  round-tripped to the form fields.
- Fixed to: `r'^\s+(\S+?)(?::\d+)?\s+"(.*)"'` — matches both `key: "value"` and `key:0 "value"`.

**[DEAD CODE] Duplicate `_edit_btn.config(...)` call on consecutive lines**
- Lines ~3601–3602
- `_edit_btn.config(text="✎ Edit", fg=TEXT_DIM, bg=BG_CARD)` appeared twice in a row with
  no code between them. The second call had no effect.
- Removed the duplicate.

---

### Dynamic Modifier Generator

**[BUG FIX] `read_existing()` used `encoding="utf-8"` instead of `"utf-8-sig"`**
- Line ~8192 inside `_save_file()`
- HOI4 `.txt` files are written with BOM (`utf-8-sig`). Reading with plain `utf-8` causes the
  BOM byte sequence (`\ufeff`) to appear in the parsed string, corrupting regex matches on the
  first line of the file (block-replacement search would fail to match a block whose ID had a
  BOM prefix).
- Fixed: default encoding changed to `"utf-8-sig"`.

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
