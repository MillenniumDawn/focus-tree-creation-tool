# Testing

Run `pytest --collect-only -q` to list the tests under `tests/`.
`pyproject.toml`'s `[tool.pytest.ini_options]` puts `src/` on `pythonpath`
and scopes `testpaths` to `tests/`, so `pytest` from the repo root just
works. `tests/conftest.py` holds exactly one fixture, `tk_root` (see "The
headless constraint"); everything else lives in the file that uses it.

## Coverage

`pytest --cov` measures the whole `hoi4cm` package with branch coverage on
(`[tool.coverage.run]` in `pyproject.toml`), so no `--cov=` argument is
needed for the normal case. `pytest --cov --cov-report=term-missing` prints
the per-module gaps. The coverage source intentionally excludes
`hoi4_content_maker.py`, which is the Tk shell. Tests that call its seams are
still regression coverage, but they do not change this package percentage.

CI gates it twice:

- The full run carries `--cov-fail-under=50`, a backstop against a large
  untested addition. It's a floor, not a target: raise it as coverage
  climbs.
- `pytest tests/test_wizard_generators_*.py --cov=hoi4cm.wizards._generators
  --cov-fail-under=95` keeps the wizard script/loc renderers near-fully
  covered, and runs without Xvfb on purpose so they can't quietly grow a
  Tk dependency.

The package number (~53% with a display, via `xvfb-run -a`) is still
dominated by the large Tk dialog bodies, but construction is now
smoke-tested (`tests/test_wizard_smoke.py`,
`tests/test_ui_dialog_smoke.py`): `wizards/decision.py` 9%, `event.py` 26%,
`national_spirit.py` 20%, `dyn_mod.py` 15%, `additional_income.py` 56%,
`ui/gfx_browser.py` 48%, `ui/settings_dialog.py` 62%,
`ui/mod_loading.py` 31%, `ui/menubar.py` 75%, `ui/toolbar.py` 88% and
`ui/splash.py` 66%. Everything pure is 82-100%. Extracting logic out of
those closures (the `_generators.py` pattern) is what moves the number;
the smokes are a backstop against NameError regressions (see #45), not a
substitute for that extraction.

## Fixture / isolation patterns

Every module with import-time or process-lifetime state needs a fixture
that resets it, or state leaks between tests. Five patterns cover what's
here today:

- **Module-state snapshot/restore.** `tests/test_logger.py`'s `log_state`
  fixture saves `sys.excepthook`, the excepthook-installed flag, and the
  error callback before a test, yields, then restores all three and clears
  the error buffer. Use this shape for anything that mutates a module
  global as a side effect (see "Module-level singletons" in
  `architecture.md`).
- **Monkeypatch of module path constants.** `tests/test_config.py` points
  `config.CONFIG_PATH` at a `tmp_path` file via `monkeypatch.setattr`
  before calling `cfg_load`/`cfg_save`, so no test ever touches the real
  `~/.hoi4_focus_maker.json`. `tests/test_scan_cache.py`'s `cache` fixture
  does the same for `scan_cache.STATE_DIR`.
- **`tmp_path` mod trees.** `tests/test_mod_context.py`'s `mod_tree`
  fixture writes a small but realistic directory tree (`common/national_focus/...`,
  `gfx/interface/...`) under `tmp_path`, then scans it and asserts on the
  resulting `MOD.*` fields. It also carries an autouse `isolate_scan_cache`
  fixture so the scanner's SQLite cache never touches `~/.hoi4cm`.
- **Parametrized round-trips.** `tests/test_focus_tree_roundtrip.py` checks
  parse -> build -> export -> reparse stability: the exporter normalizes
  whitespace, so the guarantee it checks is that a second export equals the
  first, plus that structural fields and known content survive. Its
  `reset_counter` fixture saves and restores `Focus._next` around each test
  so ID assignment doesn't depend on test order.
- **The shared `tk_root` fixture.** `tests/conftest.py` builds a `tk.Tk()`
  and destroys it after the test, skipping when no display is reachable
  (see "The headless constraint" below). `tests/test_canvas_tk.py`
  overrides it to `withdraw()` the window, since it drives `CanvasMixin`
  against a bare `tk.Canvas` through a minimal fake host exposing only the
  attributes `_draw_focus` touches (`cv`, `focuses`, `offset`, `zoom`,
  `selected`, `_multi_sel`, `mutex_mode`, `mutex_src`, `_get_tree_badge`)
  rather than a real `App`, and never needs real geometry. The grid tests
  are the exception: `_draw_grid` clips to the viewport, and a withdrawn
  root's children never map, so `winfo_width/height` report 1 and there is
  no viewport to clip to. Those use the module's `mapped_canvas` fixture,
  which deiconifies and fails loudly (not skips) if the canvas still
  doesn't map — a silently unmapped canvas would make the clipping
  assertions vacuous. `test_unmapped_canvas_still_gets_a_grid_over_the_whole_extent`
  pins the other side of that: with no dimensions to clip to, the grid
  falls back to covering the canvas extent.

## Golden-fixture tests for the focus-tree pipeline

`tests/fixtures/focus_trees/*.txt` are small hand-written files, each one
isolating a single importer behavior: a `focus_tree = { }` wrapper with
prerequisite OR/AND groups and mutex, bare top-level `focus`/`shared_focus`
blocks with no wrapper, a `country` block with deliberately irregular
formatting (to check verbatim capture), a country-tag-matching `offset`
block, a file with a missing closing brace that only the per-focus
brace-walk fallback recovers, and `scanner_edge_cases.txt` — braces and
hashes inside quoted strings, an icon path ending in a backslash, and
comments in every position one can appear, which is what the regex scanners
in `script/syntax.py` have to get right (see the scanner rewrite note in
`performance.md`). `tests/test_focus_tree_fixtures.py` parses and builds
each one and compares the result against a committed golden JSON under
`tests/fixtures/focus_trees/golden/`.

The comparison normalizes before asserting: focuses are keyed by name
instead of numeric id (ids depend on `Focus._next`, a global counter), and
`prereqs`/`mutex` id-lists are remapped to names for the same reason. Group
structure and ordering are left alone since OR-group membership and AND
ordering are semantically meaningful.

To regenerate a golden after an intentional behavior change: write a small
script that parses+builds the fixture with `hoi4cm.focus_tree.parse_focus_tree`
/ `build_focuses`, dumps the same normalized shape `test_focus_tree_fixtures.py`
compares against, and overwrites the JSON. Only do this after confirming the
new output is actually correct: the golden is a regression guard, not a
source of truth.

`tests/test_focus_tree_roundtrip.py` extends the same fixtures through
`export_focus_tree` and back, checking export idempotence and structural
field survival. `country_raw` and `tree_extras` (unrecognized `focus_tree`
wrapper keys — `default`, `reset_on_civilwar`, `initial_show_position`, ...)
are both written verbatim by `export_focus_tree` and `export_main_tree`,
mirroring how `_script_extras` preserves unknown per-focus keys; dedicated
tests in `test_focus_tree_roundtrip.py` and `test_focus_tree_export_main.py`
cover both fields, falling back to the canned `country` block only when
`country_raw` is blank (a brand-new tree with nothing captured on import).
`country_raw` capture at parse time is checked directly in
`test_focus_tree_fixtures.py`; `tree_extras` capture is checked in
`test_focus_tree_parse.py` (it's not part of the golden-fixture `meta` shape).

## One-off comparison against a real mod

Some changes (e.g. converging a duplicated parser in the monolith onto
`focus_tree/parse.py` + `build.py`) need validation against real, large,
occasionally-malformed mod files before the old code path can be deleted;
the committed fixtures above are necessarily small and can't stand in for
that. The pattern used for the `_import_txt` convergence:

1. Import `hoi4_content_maker.py` headlessly via
   `importlib.util.spec_from_file_location` + `exec_module`, with both the
   repo root and `src/` on `sys.path`. This works with no display: nothing
   at module import time instantiates `tk.Tk()` (that only happens inside
   `if __name__ == "__main__":`).
2. Run the old code path and the new `parse_focus_tree` + `build_focuses`
   path over the same file, normalized the same way as the golden-fixture
   tests above (name-keyed, id-lists remapped to names).
3. Diff every field and report every divergence with a concrete example,
   rather than stopping at the first mismatch. Recurring root causes (e.g.
   one block type silently unsupported) usually explain many files at once.
4. Run it over the committed fixtures, then over every `.txt` file in a real
   mod's `common/national_focus/` (this machine keeps a Millennium Dawn
   checkout at `/mnt/Linux/Millennium-Dawn` for exactly this). Never modify
   files under that path; it's read-only reference material.

This script is a one-off and doesn't get committed. Write it under the
session scratchpad, or a local `/tmp` directory, and throw it away once the
divergences are resolved (either fixed in `parse.py`/`build.py`, or, if the
old code was buggy and the new behavior is a strict improvement, documented
in `monolith-migration.md` instead of "fixed"). The `_import_txt` run found
105/110 exact matches over Millennium Dawn's `national_focus/` directory;
the other 5 all traced back to one cause: the old importer never recognized
bare `joint_focus` blocks, so files that are joint-focus-only, meant to be
loaded via "Load Joint Tree" rather than "Import Focus Tree", either failed
to import at all or mis-resolved positions chained through an unrecognized
anchor. That's a pre-existing gap the new path closes rather than a
regression, so it was documented rather than reverted.

## The headless constraint

CI's `test` job (`.github/workflows/ci.yml`) runs the suite under
`xvfb-run -a`, so widget tests do get a display there. `tkinter` itself
imports fine on `actions/setup-python`'s CPython; the display was the only
thing missing, and Xvfb supplies it.

The job also sets `HOI4CM_REQUIRE_TK=1`, which turns `tk_root`'s "no
display" skip into a failure. Without that, a broken Xvfb would take every
widget test out of the run and still report green: before Xvfb landed, 18
tests skipped in CI and nobody saw it. Locally the variable is unset, so a
headless dev box still skips cleanly.

Widget tests are still the expensive kind, so the split stands: put logic
in a pure function and test it headlessly wherever that's possible. Every
pure module (`focus_tree/`, `models/`, `script/`, `mod/`, `data/`, all of
`core/`, plus `ui/viewport.py`) has real coverage, as does the wizard
script/loc generator module `wizards/_generators.py` (via
`tests/test_wizard_generators_*.py`, at 99%). The close-path dependencies
the wizards lean on are covered too: the daemon executor
(`core/concurrency.py`, `tests/test_concurrency.py`), the graphics snapshot
cache (`mod/workspace_cache.py`, `tests/test_workspace_cache.py`), and
`ui/widgets.py`'s `_safe_after`/`_safe_after_idle`
(`tests/test_safe_after.py`). The virtualized list sizing is split the same
way: `visible_row_range`/`row_pool_size` are pure and carry the
"pool always holds every visible row" property test, while the widget
behavior around them (`tests/test_checklist.py`,
`tests/test_focus_list.py`, `tests/test_thumbnail_grid.py`) needs a root.

Widget construction is smoke-tested: each `open_*_wizard` and each `ui/`
dialog builds a Toplevel against `tk_root` without raising (see
`tests/test_wizard_smoke.py` and `tests/test_ui_dialog_smoke.py`). Those
smokes catch the NameError-on-click class (#45); deeper interaction
(opening sub-browsers, confirming, file dialogs) remains manual-only, per
the checklists below.

## Manual verification

Run against the real Millennium Dawn mod (this machine keeps a checkout at
`/mnt/Linux/Millennium-Dawn`), not a synthetic small mod, since the scale
targets in `performance.md` only show up at MD's size:

- Cold load (no scan cache) and warm load (second load, cache hit) of the
  mod, comparing scan time and the summary counts.
- Import the largest tree (`usa.txt`, 776 focus blocks) standalone.
- "Load All Trees" across the full `common/national_focus` directory while
  interacting with the canvas (pan/zoom) during and after the batch.
- Repeat edit, move, and undo five times (`edit/move/undo x5`),
  watching for undo-stack correctness and canvas redraw glitches.
- Export to a scratch copy of a file and diff it against the original to
  confirm the round-trip didn't drop or reorder fields.
- Export into a **read-only directory** (`chmod 555` a scratch copy of
  `common/national_focus/`). The export must raise a "Write Failed" dialog
  naming the file, add one entry to the in-app error log, show no success
  dialog, and leave both the `.txt` and the loc `.yml` byte-identical. The
  atomic/rollback behaviour itself is covered headlessly
  (`tests/test_workspace_files.py`, `tests/test_monolith_export.py`); this
  checks the dialog actually reaches the user.

### Phase 8: viewport culling checklist

`test_canvas_tk.py` covers the culling logic itself against a bare canvas;
these need the real `App` and a loaded tree to catch anything the fake host
doesn't reproduce (event bindings, undo, mod reload, the minimap widget):

- Pan a focus off screen and back. No ghost position (it should redraw at
  its real coordinates, not a stale one), and its selection ring (if
  selected) is correct immediately, not one frame late.
- Drag a focus that's half on/half off screen across the edge.
- Create a mutex line to a partner that's off screen; confirm it draws (or
  correctly doesn't) as the partner crosses in and out of view.
- Right-click near each of the four viewport edges to place a new focus;
  confirm placement lands where clicked, not offset by a culling artifact.
- Cycle fit-all -> zoom in -> pan -> fit-all a few times.
- Load a >2,000-focus tree (or "Load All Trees" on Millennium Dawn) and
  check the minimap: dot positions still line up with the real canvas at
  that density, and the viewport rectangle tracks pan/zoom correctly.
- Reload the mod (File -> Load Mod again) while some focuses are panned
  off screen (culled), then pan back and confirm they redraw correctly
  with no stale `_culled`/`_items` state left over from before the reload.

### Issue #26: render-loop bookkeeping checklist

The unit tests cover each piece against a bare canvas. These need the real
`App`, since what changed is *when* per-frame work is skipped:

- Pan (middle-drag / Ctrl+drag) a full viewport in each direction without
  releasing. The grid is generated one screen beyond the viewport, so this
  is the case that runs off the generated lattice; releasing must snap a
  full grid back.
- Toggle the grid off and on at several zoom levels, and zoom past the
  point where lines would smear (the `stepx < 4` cutoff) and back.
- File -> New / Clear All with a tree loaded, then redraw: the grid pool's
  items were destroyed with `cv.delete("all")` and have to be rebuilt.
- Zoom all the way out on a big tree (so tens of thousands of edges draw),
  then zoom back in. No stale line segments should remain visible.
- Unload one extra tree from the middle of a Load All Trees session and
  confirm every remaining tree's badge letter and colour re-numbers — that
  is the badge table being invalidated rather than the old per-call scan.
- Move focuses through every path that isn't `move()`: paste, undo/redo,
  align/distribute, draw.io import, apply-code in the Code tab. Each has to
  leave the canvas showing the new geometry. If one doesn't, run with
  `HOI4CM_SCENE_INDEX_VALIDATE=1` — if that fixes it, the path mutated a
  focus without bumping `FocusDocument.revision`.

### Phases 9-10: settings, menu sweep, GFX browser parity

These modules can be imported in CI, and pure settings helpers have headless
tests. Widget construction still needs a live `App` against a loaded mod:

- **Settings walkthrough**: open Settings from the Tools menu, change the
  mod path, a GFX directory, MD detection, and a locale, then close and
  reopen the dialog to confirm every field reloads with what was just set.
  Confirm `relativize_to_mod_root` still normalizes an absolute GFX path
  typed into a browse field down to a mod-relative one.
- **Menu sweep**: click every File/Edit/View/Tools item at least once
  (including the "Recent" submenu with zero and with several mods loaded)
  and confirm each does what its tooltip says, the dropdown closes on
  outside click, and the accelerator shown next to each item still matches
  its bound keybind (`_build_keybinds`). Confirm the error-log button still
  turns red after a deliberately triggered error and the mod label updates
  on load/unload.
- **Toolbar sweep**: click every toolbar row 2 button (Prereq, Mutex,
  wizard shortcuts, Multi, Del Selected, Clear All, +Shared, +Joint, Load
  All, Save All) and confirm each still opens the right dialog or performs
  the right canvas action. Type into the Continuous Focus Position x/y
  fields, tab out, and confirm the value commits (`_cfp_commit`).
- **GFX browser parity**: from the sidebar's Icon GFX field, open the
  browser with a mod loaded (should show only `gfx/interface/goals/` and
  its subfolders) and with no mod loaded (should fall back to a folder
  picker, non-recursive listing). Confirm the Select button's dimmer
  highlight when re-picking the field's current value versus its brighter
  highlight on a new value. Separately, open the universal GFX browser from
  a wizard (e.g. the decision maker's icon browse button) and confirm its
  full folder list (decisions, ideas, goals, event pictures, flags,
  interface, custom) still all show up, unaffected by the sidebar picker's
  narrower scope.
