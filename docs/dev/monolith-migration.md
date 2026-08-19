# Monolith migration

## The story so far

`hoi4_content_maker.py` started as a single ~21k-line file. It's down to about
6k lines. What moved, and when:

- **#8**: logging pulled into `hoi4cm.core.logger`, plus the packaging/tooling
  setup (`pyproject.toml`, ruff/black scoping, pytest config) that made an
  extracted package possible at all.
- **#12**: `Focus`, the effect tables, script marshalling helpers, and the
  splash screen extracted (`models/focus.py`, `data/effects.py`,
  `script/__init__.py`, `ui/splash.py`).
- **#10**: i18n support added directly in `hoi4cm.core.i18n`, plus the
  `locales/*.json` files.
- **#13**: the three separate parse/build/export code paths that had grown
  in the monolith de-duplicated into one pipeline: `focus_tree/parse.py`,
  `build.py`, `export.py`.
- **#14**: the big one: `ModContext`/`MOD`, all five wizards, and the three
  UI mixins (`CanvasMixin`, `EffectsMixin`, `ModLoadingMixin`) extracted.
  This is most of what's left in `src/hoi4cm/` today.
- **#17**: security hardening pass: `core/safe_path.py`, `core/safe_xml.py`,
  read/write caps on `core/paths.py` and `core/config.py`, and the O(F^2)
  fixes in `focus_tree/export.py` and the monolith's duplicate-name check.
- `_import_txt` converged onto `focus_tree/parse.py` + `build.py` (phase 3):
  the third tokenizer/parser copy is gone. `parse.py` picked up the fields
  and fallback behavior it was missing (`country_raw`, `allow_branch`,
  `text`, the per-focus brace-walk fallback); `hoi4cm.mod` picked up
  `detect_loc_file`. `_import_txt` is now an ~80-line Tk shell.
- `_import_drawio` extracted to `focus_tree/drawio.py` (phase 3): the mxGraph
  XML walk, label/coordinate cleanup, row/column clustering, and HOI4-grid
  collision resolution are now pure functions (`parse_drawio_graph`,
  `drawio_to_focus_data`, `build_drawio_focuses`). Unlike `_import_txt`, this
  wasn't a convergence — draw.io's format doesn't overlap with the HOI4
  script parser, so it got its own module. `_import_drawio` is now an
  ~615-line Tk shell (dialogs + wiring); most of that is still the two
  Toplevel dialogs (tree setup, preview), which are Tk-only and stay put.
- `_export` (phases 4 and 11): the main tree's export unified onto
  `focus_tree/export.py` (`export_main_tree`, alongside the existing
  `export_focus_tree` for shared/joint trees), and the loc-file writer
  extracted to `focus_tree/loc.py` (`build_loc_yml`). Issue #27 added
  `focus_tree/export_plan.py`, so the main, extra, and Save All paths share
  one Tk-free render/write pipeline. The Tk shell resolves paths and
  snapshots values before `run_bg`; the worker renders and atomically writes
  each tree, and `on_done` reports failures and updates the mod catalog. The
  e693a19 O(F^2) fix (a
  `name -> Focus` map built once instead of a `next()` scan per focus) is now
  also applied to `_build_focus_code`, the Code-tab preview.
- Undo (phase 7): `_push_undo`/`_undo` redesigned around `core/undo.py`'s
  `UndoStack`, a pure module with no tkinter import. Each call site now
  says which focus ids it's about to touch instead of the old
  `_snapshot` deep-copying every loaded focus on every push. `_undo` deletes
  canvas items only for the ids that came back changed or removed and does
  one `_redraw()`, replacing the old `cv.delete("all")` + full rebuild. See
  `performance.md`'s undo row for the design. `#48` later closed the
  remaining coverage holes: `_clear_all` and the four prereq/mutex
  link/unlink methods (`_make_prereq`, `_rm_prereq`, `_make_mutex`,
  `_rm_mutex`) now push undo, the canvas drag-move in
  `src/hoi4cm/ui/canvas.py:_foc_mv` snapshots its pre-move state on the
  first motion frame, and a paired redo stack (`_redo` in the monolith,
  `UndoStack.redo` in `core/undo.py`) plus `<Control-y>` /
  `<Control-Shift-Z>` bindings round-trip the recent history.
  `push()` clears the redo trail so a new edit branch invalidates redo,
  matching every other editor.
- Settings dialog (phase 9): `_open_settings`'s ~1,315-line body moved to
  `ui/settings_dialog.py` as `open_settings(app)`, the same one-line-delegate
  pattern the five wizards use. Lifted out along with it: `relativize_to_mod_root`
  (the mod-relative-path normalization every GFX-path browse button used
  inline), and two data constants that used to get rebuilt on every dialog
  open, `VANILLA_COUNTRY_TAGS` and `GFX_PATH_PRESETS`. The dead
  `_default_hoi4_mod_dir` alias is gone from the monolith too, so it and four
  other now-unused `hoi4cm.core` imports (`CONFIG_PATH`, `I18N_LANGS`,
  `get_language`, `set_language`) came out with it. `ui/settings_dialog.py`
  is wired in with a direct
  `from hoi4cm.ui.settings_dialog import open_settings`.
- GFX browser dedup + menubar/toolbar (phase 10, the last phase of this
  round): `_open_gfx_browser`/`_gfx_browse_files` audited against the
  already-extracted `ui/gfx_browser.py` (`open_universal_gfx_browser`,
  `open_gfx_placement_editor`) and found to serve a genuinely different
  contract, not a straight duplicate: the sidebar's focus-icon field only
  ever browses `gfx/interface/goals/`, always emits a `GFX_focus_`-prefixed
  key, commits straight to `App._fv_gfx`/`._set_gfx` instead of a generic
  `on_select(gfx_key, abs_path)` callback, and has an initial-value-aware
  Select button the universal browser doesn't. Folding it into
  `open_universal_gfx_browser` would have either broadened what the icon
  field can browse (every GFX category, not just goals) or bolted on
  several conditional parameters for a single caller, so it was extracted
  as-is instead, as a third function, `open_focus_icon_browser`, in the
  same `ui/gfx_browser.py`. It did pick up one thing from its sibling: the
  bounded `LRUCache` + pinned-thumbnail handling, replacing the old
  unbounded dict cache, matching the fix already applied to
  `open_universal_gfx_browser`. See "Migration status" below for the fuller
  rationale and what a future consolidation would need.
  `_build_menubar`/`_build_toolbar_row2` moved verbatim to `ui/menubar.py`/
  `ui/toolbar.py` as `build_menubar(app, toolbar)`/
  `build_toolbar_row2(app, toolbar)`. Neither kept a monolith delegator:
  `_build_ui` was their only caller, unlike `_open_settings`/
  `_open_gfx_browser`, which stay as one-line delegates because they're
  passed around as bound-method callbacks (menu items, a sidebar button).
  The `hoi4cm.ui` facade picked up four names this phase: `open_settings`
  (deferred from phase 9), `open_focus_icon_browser`, `build_menubar`, and
  `build_toolbar_row2`.
- **Application modernization (this round)**: the perf/threading/memory pass
  pulled a wave of infrastructure out of the monolith and firmed up the
  round-1 modules. New homes: `core/concurrency.py` (a daemon
  `ThreadPoolExecutor` so app close is a graceful lifecycle close, not
  `os._exit`), the document model (`models/document.py`: `FocusDocument`,
  `TreeDocument`, `EditorWorkspace`), focus-tree `codec.py` / `operations.py`,
  project save/load (`editor/project_codec.py`), the GFX catalog and its
  caches (`mod/graphics_catalog.py`, `mod/workspace_cache.py`,
  `mod/workspace_files.py`), effect/syntax marshalling (`script/effects.py`,
  `script/syntax.py`), the canvas image pipeline and lifecycle plumbing
  (`ui/image_broker.py`, `ui/lifecycle.py`, `ui/scene_index.py`,
  `ui/thumbnail_grid.py`, `ui/focus_list.py`, `ui/canvas_scheduler.py`), and
  the wizard GFX helpers (`wizards/_graphics.py`, `wizards/_image_loader.py`).
  See the status table for the module-by-module list, and
  `architecture.md`'s "Revision discipline" / executor-daemon notes for the
  two invariants these depend on.
- **#31**: the "Load All Trees" checklist dialog's per-file row loop (~7 Tk
  widgets per candidate file, ~5,500 for a ~790-file mod) moved to
  `ui/checklist.py`'s `VirtualChecklist`, a pooled row list over a scrolling
  canvas. It reuses `_PooledList`, a base class factored out of
  `VirtualFocusList` (`ui/focus_list.py`) for this extraction. The
  filename-prefix convention, select-mode presets, and batch-load filter
  came out as plain functions alongside it: `default_tree_type`,
  `apply_select_mode`, `is_loadable`, plus the `ChecklistItem` row struct.
  `_load_all_trees` itself (the directory scan, file walk, and dialog
  wiring) stays a Tk shell in the monolith; only the row rendering and
  selection logic moved. See `performance.md`'s "Checklist dialog for Load
  All Trees" row for the perf fix this was.

What's left in `hoi4_content_maker.py` today is essentially: the `sys.path`
shim and import block (lines ~62-152), two Windows-DPI helpers (~155-207),
and `class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk)`
(~241-5929, 108 methods, most bodies much smaller now), plus the
`__main__` entry point that calls `show_splash(_launch)`. Those 108
methods group into:

- **Sidebar** (still deferred, see below): `_build_sidebar`,
  `_build_sidebar_props`, `_build_sidebar_conditions`, `_build_sidebar_code`,
  the dozen `_sb_*`/`_show_form`/`_hide_form`/`_flash_added` field-widget
  helpers, the offset editor (`_refresh_offsets`, `_add_offset`,
  `_del_offset`, `_save_offsets_to_focus`, `_focus_flag_label`), and the
  focus-icon field (`_sb_gfx_picker`, `_set_gfx`, `_update_gfx_preview`,
  `_open_gfx_browser`, now a delegate into `ui/gfx_browser.py`).
- **CRUD/selection**: `_select`, `_deselect`, `_populate`, `_add_focus`,
  `_new_focus_at`, `_apply`, `_delete_focus`, `_delete_selected`,
  `_key_delete`, `_clear_all`, `_toggle_multisel`, `_select_all_focuses`,
  `_duplicate_focus`, `_on_icon_change`.
- **Prereq/mutex picking**: `_pick_prereq`, `_toggle_connect`,
  `_make_prereq`, `_rm_prereq`, `_toggle_mutex`, `_end_mutex`, `_make_mutex`,
  `_rm_mutex`, `_refresh_prereqs`, `_refresh_mutex`.
- **View-code / Code-tab**: `_refresh_code_tab`, `_apply_focus_code`,
  `_build_focus_code`, `_view_code`, `_add_effect`.
- **Validation**: `_validate_tree`.
- **New-tree dialog**: `_new_tree_dialog`.
- **Bulk rename**: `_bulk_rename_dialog`.
- **Save/load (project + mod)**: `_save`, `_load`, `_detect_and_apply_tag`,
  `_apply_md_visibility`, `_update_title`.
- **Export**: `_export`.
- **Import**: `_import_drawio`, `_import_drawio_continue`, `_import_txt`
  (the Tk-shell wrappers described above; the parse/build logic itself
  already moved).
- **Multi-tree** (shared/joint trees loaded alongside the main one):
  `_get_tree_badge`, `_install_extra_tree`, `_load_extra_tree`,
  `_unload_extra_tree`, `_refresh_loaded_trees_panel`,
  `_export_extra_tree`, `_batch_load_trees_worker`, `_load_all_trees`,
  `_save_all_trees`.
- **Focus list panel**: `_refresh_focus_list_debounced`,
  `_refresh_focus_list`, `_update_focus_list_selection`,
  `_toggle_focus_list`.
- **Wizard/dialog delegates**: `_open_settings`, `_additional_income_wizard`,
  `_national_spirit_wizard`, `_dyn_mod_wizard`, `_decision_wizard`,
  `_event_wizard`, one-line calls into their `hoi4cm` modules.
- **Error log**: `_init_error_log`, `_log_error`, `_on_error_logged`,
  `_show_error_log`.
- **Undo shell**: `_push_undo`, `_undo`, `_redo` (the Tk-facing half of
  `core/undo.py`'s `UndoStack`, including the redo stack that pairs with
  undo).
- **Autocomplete / mod-aware suggestions**: `_attach_autocomplete`,
  `_get_mod_suggestions`.
- **Widget factories / low-level helpers**: `_mk_btn`, `_mk_lbl`,
  `_mk_entry`, `_mk_hsep`, `_hint`, `_sash_pr`/`_sash_mv`/`_sash_rl`
  (sidebar-splitter drag), `_update_statusbar`,
  `_refresh_tree_meta_panel`.
- **Bootstrap**: `__init__`, `_on_app_close`, `_build_ui`, `_build_keybinds`,
  `_build_layout`, plus the two module-level DPI helpers
  (`_enable_windows_dpi_awareness`, `_apply_tk_dpi_scaling`).

## Wiring convention

New extractions plug into the `core` facade, not underscore aliases. See
`architecture.md`'s "core facade" section for the mechanics. Short version:
add the public name to the owning subpackage's `__all__`, then to
`core/__init__.py`'s import list and `__all__` if the monolith or a wizard
needs it via `hoi4cm.core`.

## Migration status

| Monolith function | Lines | Destination | Status |
|---|---|---|---|
| `_open_settings` | was ~6685-7999 (~1,315) | `ui/settings_dialog.py` (`open_settings`) | **done** (phase 9) |
| `_import_drawio` | ~4952-5567 (~616) | `focus_tree/drawio.py` | **done** (phase 3) |
| `_import_txt` | ~5777-5899 (~123) | converged onto `focus_tree/parse.py` + `build.py` | **done** (phase 3) |
| `_build_menubar` | was ~408-943 (~536) | `ui/menubar.py` (`build_menubar`) | **done** (phase 10) |
| `_build_toolbar_row2` | was ~944-1202 (~259) | `ui/toolbar.py` (`build_toolbar_row2`) | **done** (phase 10) |
| `_export` | ~8297-8463 (~167, was ~9003-9443/440) | `focus_tree/export.py` (`export_main_tree`) + `focus_tree/loc.py` (`build_loc_yml`) + `focus_tree/export_plan.py` (shared worker pipeline) | **done** (phases 4 and 11, #27) |
| `_open_gfx_browser` | was ~2624-3058 (~435) | `ui/gfx_browser.py` (`open_focus_icon_browser`), extracted as-is, not merged, see below | **done** (phase 10) |
| `_gfx_browse_files` | was ~3059-3267 (~209) | folded into `open_focus_icon_browser`'s `_browse_flat_folder` helper | **done** (phase 10) |
| Sidebar builders (`_build_sidebar`, `_build_sidebar_props`, `_build_sidebar_conditions`, `_build_sidebar_code`, `_sb_*` helpers) | ~846-1817 (~970) | n/a | deferred |
| Undo (`_push_undo`/`_undo`/`_redo`) | ~1561-1608 | `core/undo.py` (`UndoStack` with redo stack, see `performance.md`) | **done** (phase 7; redo + call-site coverage in #48) |
| Background threads / executor | n/a | `core/concurrency.py` (`DaemonThreadPoolExecutor`) | **done** (modernization) |
| Workspace / focus document model | n/a | `models/document.py` (`FocusDocument`, `TreeDocument`, `EditorWorkspace`) | **done** (modernization) |
| Focus-tree codec + focus operations | n/a | `focus_tree/codec.py`, `focus_tree/operations.py` | **done** (modernization) |
| Project `.json` save/load | n/a | `editor/project_codec.py` | **done** (modernization) |
| GFX catalog + scan/workspace caches + atomic writes | n/a | `mod/graphics_catalog.py`, `mod/workspace_cache.py`, `mod/workspace_files.py` | **done** (modernization) |
| Effect rendering + Paradox script syntax | n/a | `script/effects.py`, `script/syntax.py` | **done** (modernization) |
| Canvas image pipeline + lifecycle / scene index / scheduler | n/a | `ui/image_broker.py`, `ui/lifecycle.py`, `ui/scene_index.py`, `ui/thumbnail_grid.py`, `ui/focus_list.py`, `ui/canvas_scheduler.py` | **done** (modernization) |
| Wizard GFX helpers + async image loader | n/a | `wizards/_graphics.py`, `wizards/_image_loader.py` | **done** (modernization) |
| `_load_all_trees` row-building loop | ~4327-4638 (~312, was ~4349-4755/407) | `ui/checklist.py` (`VirtualChecklist`, `ChecklistItem`, `apply_select_mode`, `default_tree_type`, `is_loadable`), reusing `_PooledList` factored out of `ui/focus_list.py` | **done** (#31), dialog shell stays in `_load_all_trees` |

`_import_txt` was worth calling out: it had been a third, independent copy of
the tokenizer/parser logic that already existed in `focus_tree/parse.py`.
Phase 3 wasn't a straight cut-and-paste for it, it was converging three
implementations into one. `parse.py` and `build.py` picked up the handful
of behaviors the monolith copy had that they didn't (see the comparison
harness in `testing.md`), and only then did the monolith copy get deleted.
`_import_drawio`'s parser turned out not to need that treatment: it's the
only thing in the codebase that reads mxGraph XML, so there was nothing to
converge it with, just a straight lift into its own module.

`_open_gfx_browser`/`_gfx_browse_files` turned out not to duplicate
`ui/gfx_browser.py`'s `open_universal_gfx_browser`, despite looking like the
same feature (both browse mod GFX folders in a lazy-loaded tile grid with a
Select button). The contracts differ in ways that matter: the sidebar's
Icon GFX field only ever wants `gfx/interface/goals/` (never decisions,
ideas, event pictures, etc.), always wants a `GFX_focus_`-prefixed key even
when no mod is loaded and the user is browsing an arbitrary folder, and
commits its result straight into `App._fv_gfx`/`.selected.gfx` rather than
going through a generic `on_select(gfx_key, abs_path)` callback. Routing the
sidebar button through `open_universal_gfx_browser` would have let the icon
field browse every GFX category (scope creep on a deliberately narrow
picker) and, in the no-mod-loaded fallback, generated a plain `GFX_`-prefixed
key instead of `GFX_focus_`, a real behavior change, not just cosmetics,
since that prefix is what the exported script needs. So the pair was
extracted as-is into a third function, `open_focus_icon_browser`, in the
same `ui/gfx_browser.py` module, rather than merged. It did inherit the one
improvement that carries over cleanly: the bounded `LRUCache` +
pinned-thumbnail image cache the sibling browser already had, in place of
  the old unbounded dict.

## Extraction recipe

1. Extract the pure logic (parsing, building, computing) into a
   `src/hoi4cm/` module. Keep the Tk shell (widget creation, event
   bindings) in `App` or the wizard, calling into the extracted function.
2. Pair it with a test under `tests/`. Pure modules get real coverage;
   Tk-touching code at minimum gets an import smoke test (see
   `testing.md`).
3. Add the new public name to the owning subpackage's `__all__`.
4. If the monolith (or another subpackage) needs the name via
   `hoi4cm.core`, add it to `core/__init__.py`'s import list and `__all__`.
5. Update `hoi4_content_maker.py`'s import block to pull the name from
   `hoi4cm.core` (or the owning subpackage) instead of defining it locally.

## Deferred, and why

- **Sidebar builders**: tightly coupled to `App`'s live form state (the
  selected `Focus`, the current sidebar widgets, in-place mutation on
  every keystroke). Extracting them cleanly needs a form-state redesign
  first, not just a lift-and-shift.
