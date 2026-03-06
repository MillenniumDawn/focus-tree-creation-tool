# HOI4 Content Maker — Changelog

---

## Session 5 — Focus Tree Editor UX Pass and Dictionary Expansion (Effects & Modifiers)

### EFFECT_DEFS — Bug Fixes

**[BUG FIX] `md_change_ruling_party` renderer never matched — key name mismatch**
- EFFECT_DEFS key was `"md_change_ruling_party"` but the `_render_effect` dispatch checked
  `if t == "md_ruling_party":` — the string never matched, so the effect always fell through
  to the generic fallback and produced broken output.
- Fixed: renderer check changed to `if t == "md_change_ruling_party":`.

**[BUG FIX] `md_economic_cycle` dropdown contained invalid and missing values**
- Old dropdown: `"stable_growth,recession,boom,depression"` — `boom` does not exist in the mod.
  Missing: `stagnation`, `fast_growth`, `economic_boom`.
- Fixed to: `"stable_growth,recession,stagnation,fast_growth,depression,economic_boom"`.

### EFFECT_DEFS — New Entries

**[ADDED] 3 MD Politics no-parameter effects**
- `set_party_index_to_ruling_party` — syncs `party_index` variable to the current ruling party index
- `recalculate_party` — recalculates coalition and party seat totals
- `add_own_ideology_drift` — drifts population toward current ruling ideology
- All three render as `effect_name = yes` via new `_DISPATCH` lambda entries.

**[ADDED] 2 MD Scripted no-parameter effects**
- `cyber_execute_operation` — triggers a cyber operation (requires cyber temp vars to be set beforehand)
- `modify_reform_expectance_effect` — modifies reform expectance
- Both render as `effect_name = yes` via new `_DISPATCH` lambda entries.

**[ADDED] `"MD Scripted"` added to `EFFECT_CATS` list**

---

### MODIFIER_DEFS — New Entries (~106 added)

**[ADDED] MD Energy — 23 new modifiers**
- Satellite production speeds: `gnss_production_speed_modifier`, `comsat_production_speed_modifier`,
  `killsat_production_speed_modifier`, `spysat_production_speed_modifier`, `olv_production_speed_modifier`
- Energy generation: `fossil_energy_gain`, `nuclear_energy_gain`, `hydroelectric_power_generation_modifier`,
  `geothermal_power_generation_modifier`, `state_renewable_energy_generation_modifier`,
  `nuclear_reactor_fuel_production`, `battery_park_storage_size_modifier`
- Energy use: `energy_use_modifier_civs`, `energy_use_modifier_mils`, `energy_use_modifier_offices`,
  `energy_use_modifier_agriculture_district`
- Tech building speeds: `production_speed_fossil_powerplant_factor`, `production_speed_internet_station_factor`,
  `production_speed_microchip_plant_factor`, `production_speed_offices_factor`,
  `production_speed_renewable_energy_infra_factor`
- Microchip/synth: `microchip_plant_productivity_modifier`, `local_resources_microchips_factor`, `synth_resources`

**[ADDED] MD Political — 10 new modifiers**
- Ideology drift: `democratic_drift`, `communism_drift`, `fascism_drift`, `nationalist_drift`, `neutrality_drift`
- Ideology acceptance: `democratic_acceptance`, `communism_acceptance`, `fascism_acceptance`,
  `nationalist_acceptance`, `neutrality_acceptance`

**[ADDED] MD Law — 5 new modifiers**
- `terror_threat_base_defense_modifier`, `border_control_multiplier_modifier`,
  `military_status_women_cost_factor`, `increase_graft_cost`, `dockyard_productivity`
- Note: `dockyard_productivity` is the correctly-spelled key (the tool also has the historical
  typo entry `dockyard_prodctivity` — both are now present).

**[ADDED] Country — 6 flat country resource modifiers**
- `country_resource_oil`, `country_resource_steel`, `country_resource_aluminium`,
  `country_resource_rubber`, `country_resource_tungsten`, `country_resource_chromium`

**[ADDED] Industry — 7 new modifiers**
- Production cost factors: `production_cost_arms_factory_factor`, `production_cost_bunker_factor`,
  `production_cost_infrastructure_factor`, `production_cost_nuclear_reactor_factor`,
  `production_cost_rail_way_factor`
- Repair speed factors: `repair_speed_nuclear_reactor_factor`, `repair_speed_rail_way_factor`

**[ADDED] Naval — 33 new modifiers**
- Ship design cost factors (13): `attack_submarine_design_cost_factor`, `missile_submarine_design_cost_factor`,
  `corvette_design_cost_factor`, `destroyer_design_cost_factor`, `frigate_design_cost_factor`,
  `cruiser_design_cost_factor`, `battle_cruiser_design_cost_factor`, `carrier_design_cost_factor`,
  `patrol_boat_design_cost_factor`, `helicopter_operator_design_cost_factor`,
  `stealth_corvette_design_cost_factor`, `stealth_destroyer_design_cost_factor`, `stealth_frigate_design_cost_factor`
- Max production cost caps (10): `production_cost_max_attack_submarine`, `production_cost_max_missile_submarine`,
  `production_cost_max_corvette`, `production_cost_max_destroyer`, `production_cost_max_frigate`,
  `production_cost_max_cruiser`, `production_cost_max_battle_cruiser`, `production_cost_max_carrier`,
  `production_cost_max_stealth_destroyer`, `production_cost_max_helicopter_operator`
- Doctrine: `naval_doctrine_cost_factor`
- Naval leader trait XP factors (9): `trait_blockade_runner_xp_gain_factor`, `trait_blue_water_expert_xp_gain_factor`,
  `trait_green_water_expert_xp_gain_factor`, `trait_inshore_fighter_xp_gain_factor`,
  `trait_ironside_xp_gain_factor`, `trait_fleet_protector_xp_gain_factor`,
  `trait_fly_swatter_xp_gain_factor`, `trait_naval_invader_xp_gain_factor`, `trait_seawolf_xp_gain_factor`

**[ADDED] Army — 6 new modifiers**
- Mastery gain: `blue_water_mastery_gain_factor`, `leadership_track_mastery_gain_factor`,
  `special_elite_forces_mastery_gain_factor`
- Tactic preferences: `tactic_ambush_preferred_weight_factor`, `tactic_breakthrough_preferred_weight_factor`,
  `tactic_delay_preferred_weight_factor`

**[ADDED] Unit Leader — 15 new trait XP gain modifiers**
- `trait_infantry_leader_xp_gain_factor`, `trait_armoured_cavalry_leader_xp_gain_factor`,
  `trait_artillery_leader_xp_gain_factor`, `trait_air_cavalry_leader_xp_gain_factor`,
  `trait_air_controller_xp_gain_factor`, `trait_commando_xp_gain_factor`,
  `trait_mountaineer_xp_gain_factor`, `trait_engineer_xp_gain_factor`,
  `trait_guerrilla_leader_trait_xp_gain_factor`, `trait_organizer_xp_gain_factor`,
  `trait_panzer_leader_xp_gain_factor`, `trait_desperate_defender_xp_gain_factor`,
  `trait_superior_tactician_xp_gain_factor`, `trait_trickster_xp_gain_factor`,
  `trait_spotter_xp_gain_factor`

**[ADDED] Intelligence — 1 new modifier**
- `operation_risk` — modifies risk of intelligence operations

---

### Focus Tree Editor — Prerequisite Selector (FIX 1)

**[IMPROVED] Full UX rewrite of the prerequisite picker dialog**
- Dialog width increased from 360 to 580px, height from 360 to 520px.
- Added live counter showing how many focuses are selected (`3 selected`).
- Added hover tooltip on each focus row showing its position and cost.
- Added `Escape` key binding to cancel, `Ctrl+A` to select all.
- **Fixed prerequisite OR vs AND semantics** — the old "Add as AND group" button was
  actually creating OR groups (one `prerequisite = { focus = A focus = B }` block means
  "any one of A or B is required"). Now two distinct buttons exist:
  - **Add as OR group** — adds one `prerequisite { }` block listing all selected focuses
    (player needs any one of them — HOI4's native OR logic within a single block)
  - **Add as AND group** — adds separate `prerequisite { }` blocks, one per focus
    (all must be completed independently — HOI4's AND logic across multiple blocks)
- Explanation text above each button clarifies the HOI4 semantics.

---

### Focus Tree Editor — `continuous_focus_position` Preservation (FIX 2)

**[BUG FIX] `continuous_focus_position` was recalculated on every import/export instead of preserved**
- Previously, importing a focus tree file discarded the original `continuous_focus_position`
  and recalculated it from focus grid positions on export (usually producing the wrong value).
- Fix: `_import_txt()` now reads `continuous_focus_position { x = ... y = ... }` from the
  parsed block dict and stores the values as `self._cfp_x` / `self._cfp_y`.
- `_export()` now writes the stored values as-is, falling back to calculation only if no
  imported value exists (i.e., a newly created tree with no prior CFP).
- Added x/y entry fields in the toolbar row so the user can manually override the value.

---

### Focus Tree Editor — `shared_focus` / `joint_focus` Preservation (FIX 3 & 4)

**[BUG FIX] `shared_focus` and `joint_focus` references were silently stripped on import**
- The tokenizer-based block parser consumed the `focus_tree` block but did not extract
  `shared_focus` or `joint_focus` keys, so these references were lost and never re-exported.
- Fix: `_import_txt()` now performs a regex scan on the raw file text before tokenization
  to extract all `shared_focus` and `joint_focus` lines into `self._shared_focuses` and
  `self._joint_focuses` lists.
- `_export()` now writes all shared/joint focus lines immediately before the focus blocks.
- Added a **TREE REFERENCES** read-only panel in the sidebar (above the focus list) that
  displays the imported shared/joint focus references. Panel is shown only when references exist.

---

### Focus Tree Editor — Canvas Zoom Reset and Phantom Lines (FIX 5)

**[BUG FIX] Typing `0`, `g`, `m`, or `f` in any text field reset the canvas zoom/view**
- Single-key canvas shortcuts (`0` = fit all, `g` = toggle grid, `m` = toggle minimap,
  `f` = find focus) were bound globally on the root window.
- When the user typed in an Entry or Text widget, these keys fired anyway, causing the
  canvas to reset its zoom level unexpectedly.
- Fix: added a `_guard()` wrapper that checks `isinstance(e.widget, (tk.Text, tk.Entry))`
  and returns early without executing the shortcut if a text input has focus.

**[BUG FIX] Prerequisite lines turned phantom (duplicated/orphaned) after editing focus code**
- `_apply_focus_code()` called `self._redraw()` (throttled, fires 16ms later), but the
  viewport (zoom level and pan offset) was being reset during the redraw because the throttle
  scheduled the draw after the caller had already returned.
- Stale `_lines` canvas items from the previous draw were not cleared, causing ghost lines.
- Fix: zoom and offset are saved before the redraw call and restored 30ms later (after the
  throttled redraw fires) via `cv.after(30, _restore_vp)`, which also redraws lines and focuses.

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
  `block["country"]["modifier"]["original_tag"]` (preferred) or `block["country"]["modifier"]["tag"]` (backwards compat).
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
- `production_speed_industrial_complex_factor`, `production_speed_arms_factory_factor`,
  `production_speed_dockyard_factor`, `production_speed_infrastructure_factor`,
  `production_speed_air_base_factor`, `production_speed_bunker_factor`,
  `production_speed_coastal_bunker_factor`, `production_speed_anti_air_building_factor`,
  `production_speed_radar_station_factor`, `production_speed_rocket_site_factor`,
  `production_speed_nuclear_reactor_factor`, `production_speed_synthetic_refinery_factor`,
  `production_speed_fuel_silo_factor`, `production_speed_rail_way_factor`,
  `production_speed_agriculture_district_factor` (MD-specific building)

---

### MODIFIER_DEFS — Missing Resource-Specific State Modifiers

**[ADDED] 6 `local_resources_X_factor` modifiers (State category)**
- `local_resources_oil_factor`, `local_resources_steel_factor`, `local_resources_aluminium_factor`,
  `local_resources_rubber_factor`, `local_resources_tungsten_factor`, `local_resources_chromium_factor`
- State-scoped modifiers that apply a multiplier to a specific resource in a state.

---

## Session 3 — Focus Tree Fixes and Expansion

### Focus Tree — `tag =` → `original_tag =` (all remaining locations)

**[BUG FIX] Draw.io import wizard preview code still used `tag =` instead of `original_tag =`**
- Lines ~15436, ~15668, ~14904
- Fixed all three remaining locations to use `original_tag =` to match actual export output.

---

### Focus Tree — Import Parser Reads Country Tag from File

**[BUG FIX] Importing a `.txt` focus tree reset country tag to placeholder `"TAG"`**
- Parser now extracts `original_tag` from `country = { modifier = { original_tag = X } }` block
  and stores it as `self._tree_country_tag` for use in export and prefix auto-detection.

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
