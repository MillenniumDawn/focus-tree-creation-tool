# Monolith migration

## The story so far

`hoi4_content_maker.py` started as a single ~21k-line file. It's down to
8,754 lines. What moved, and when:

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

What's left in `hoi4_content_maker.py` today is essentially: the `sys.path`
shim and import block (lines ~62-148), two Windows-DPI helpers (~151-235),
and `class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk)`
(~240-8754, around 110 methods), plus the `__main__` entry point that calls
`show_splash(_launch)`.

## Wiring convention

New extractions plug into the `core` facade, not underscore aliases. See
`architecture.md`'s "core facade" section for the mechanics. Short version:
add the public name to the owning subpackage's `__all__`, then to
`core/__init__.py`'s import list and `__all__` if the monolith or a wizard
needs it via `hoi4cm.core`.

## Migration status

| Monolith function | Lines | Destination | Status |
|---|---|---|---|
| `_open_settings` | ~7179-8494 (~1,316) | `ui/settings_dialog.py` | in monolith (phase 9) |
| `_import_drawio` | ~4952-5567 (~616) | `focus_tree/drawio.py` | **done** (phase 3) |
| `_import_txt` | ~5777-5899 (~123) | converged onto `focus_tree/parse.py` + `build.py` | **done** (phase 3) |
| `_build_menubar` | ~399-934 | `ui/menubar.py` | in monolith (phase 10) |
| `_build_toolbar_row2` | ~935-1193 | `ui/toolbar.py` | in monolith (phase 10) |
| `_export` | ~9003-9443 | unify with `focus_tree/export.py` + new `focus_tree/loc.py` | in monolith (phase 4) |
| `_open_gfx_browser` | ~2614-3048 | dedup with `ui/gfx_browser.py` | in monolith (phase 10) |
| `_gfx_browse_files` | ~3049-3258 | dedup with `ui/gfx_browser.py` | in monolith (phase 10) |
| Sidebar builders (`_build_sidebar`, `_build_sidebar_props`, `_build_sidebar_conditions`, `_build_sidebar_code`, `_sb_*` helpers) | ~1629-2362 (~640) | n/a | deferred |
| Undo (`_snapshot`/`_push_undo`/`_undo`) | ~1546-1577 | `core/undo.py` (redesigned, see `performance.md`) | in monolith (phase 7) |

`_import_txt` was worth calling out: it had been a third, independent copy of
the tokenizer/parser logic that already existed in `focus_tree/parse.py`.
Phase 3 wasn't a straight cut-and-paste for it, it was converging three
implementations into one. `parse.py` and `build.py` picked up the handful
of behaviors the monolith copy had that they didn't (see the comparison
harness in `testing.md`), and only then did the monolith copy get deleted.
`_import_drawio`'s parser turned out not to need that treatment: it's the
only thing in the codebase that reads mxGraph XML, so there was nothing to
converge it with, just a straight lift into its own module.

`_open_gfx_browser`/`_gfx_browse_files` likely duplicate the already-extracted
`ui/gfx_browser.py` (`open_universal_gfx_browser`, `open_gfx_placement_editor`).
Phase 10 needs to confirm the overlap and delete whichever copy loses.

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
- **`_open_settings`**: the single largest remaining chunk (~1,316 lines).
  Deferred to phase 9 simply because of size and because it touches almost
  every config key the app has; wants its own careful pass rather than
  being folded into an earlier phase.
