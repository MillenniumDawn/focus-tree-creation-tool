# Testing

Both CI and pre-release builds run the frozen executable with `--smoke-test`
before uploading it (60-second timeout; Xvfb on Linux). This creates and
destroys a hidden Tk root and a ttk widget without launching the editor.
It catches packaging failures that source tests cannot see, including the
Tcl/Tk 9 embedded-library incompatibility in PyInstaller 6.21. The check
lives in `src/hoi4cm/ui/startup_check.py`.

Run `pytest --collect-only -q` to list the tests under `tests/`.
`pyproject.toml`'s `[tool.pytest.ini_options]` puts `src/` on `pythonpath`
and scopes `testpaths` to `tests/`, so `pytest` from the repo root just
works. On import, `tests/conftest.py` replaces HOME with a temporary
per-run home before test modules are collected, then restores the original
environment and removes the temporary tree at session end. On Windows it also
sets USERPROFILE because that is what `expanduser("~")` prefers. The same
module forbids Tk construction (see "The headless rule"). Plain helpers
shared by several test files live in `tests/builders.py` (`make_focus`,
`default_decision`) and `tests/ui_fakes.py` (`AppFake`), imported by bare
name. Everything else lives in the file that uses it.

## Two suites

```sh
pytest                    # headless: logic, no display, about 5 seconds
xvfb-run -a pytest -m tk  # Tk smoke: tests/test_tk_smoke.py, about 2 seconds
```

`pyproject.toml` deselects the `tk` marker by default, so plain `pytest` never
runs the smoke. The two never share a process. Tk objects that a worker
thread garbage-collects abort the interpreter (#319), and the headless suite
uses worker threads.

## The headless rule

`tests/conftest.py` replaces `tk.Tk.__init__` for every test not marked `tk`.
A test that builds a root fails with "Tk construction is forbidden". This is
the point of the suite: put logic in a pure function and test that. Three
shapes cover what is here:

- **Pure modules** (`focus_tree/`, `models/`, `script/`, `mod/`, `data/`,
  `core/`, `editor/`, `wizards/_generators.py`) are called directly.
- **Pure helpers inside a widget module** are imported and called without
  building the widget: `visible_row_range` and `row_pool_size` in
  `ui/focus_list.py`, `is_loadable` in `ui/checklist.py`,
  `relativize_to_mod_root` in `ui/settings_dialog.py`.
- **App and mixin methods** run unbound against a fake host. `AppFake` in
  `tests/ui_fakes.py` hosts the canvas, effects and mod-loading mixins with
  mocked widgets; monolith methods are called as `App._save(fake)`.
  `hoi4cm.ui.app_contracts` checks the real `App` against the mixin protocols.

`tests/test_tk_smoke.py` is the one file marked `tk`. It builds the real `App`
once and calls each command that opens a dialog, asserting a non-empty
Toplevel appears. That catches the NameError-on-click class (#45). The same
file holds the focus-callback and wheel-zoom regressions, which need a real
canvas and must not share a process with the headless suite. Add a dialog to
its parameter list when you add one. Do not add click-through tests.

## Coverage

`pytest --cov` measures both the `hoi4cm` package and the root-level
`hoi4_content_maker.py` Tk shell, with branch coverage on. The source list is
in `[tool.coverage.run]` in `pyproject.toml`; `--cov` without a value uses
that list. `pytest --cov --cov-report=term-missing` prints per-file gaps.
CI follows the headless run with two filtered reports so the sources have
independent floors rather than one blended percentage:

```sh
coverage report --include='src/hoi4cm/*' --fail-under=91
coverage report --include='hoi4_content_maker.py' --fail-under=34
```

Measured on the headless suite: 92% for the package and 35% for the monolith.
Each floor sits one point below. These are floors, not targets: raise them as
coverage climbs. The package and monolith must stay separately included in
`pyproject.toml` so a future change cannot silently stop measuring either
source.

The package floor leaves out the modules that build Tk widgets. They are
listed under `omit` in `[tool.coverage.report]`: the wizard dialogs, the
canvas, the browsers, the menubar and toolbar, and the other widget modules.
The headless suite reaches 2% to 77% of each, so including them would turn
the floor back into a number nobody can move. `tests/test_coverage_gates.py`
fails if an omitted module does not import tkinter, so a pure module cannot
be hidden there. A new pure module is gated automatically. A new widget
module drags the floor down until it is added to `omit`.

The way to raise real coverage is extraction: move logic out of a dialog
closure into a pure module (the `_generators.py` pattern), where it is gated
at once. Without the omit list the headless package figure is 47%. The Tk
tests removed in the headless cut brought that to 75%, but added only 9
statements across the non-widget modules.

To see the widget modules too, override the list with a pattern that matches
nothing: `coverage report --omit=none --include='src/hoi4cm/*'`.

The additional gate
`pytest tests/test_wizard_generators_*.py --cov=hoi4cm.wizards._generators
--cov-fail-under=95` keeps the wizard script/loc renderers near-fully
covered.

## UI translations

Every `locales/*.json` file is a language. `hoi4cm.core.i18n.discover_languages()`
builds `I18N_LANGS` from the directory at import, English first, and each file
names itself in Settings through `_meta.display_name`. To add a language, copy
`locales/en.json`, translate the values, and set `_meta.display_name`. A file
with no display name is listed under its code. A file that cannot be read is
skipped with a warning. `_meta` is never a translation: `tr()` cannot return it.

`tr(key, default)` falls back to the inline English default, so a missing key
never fails at run time. `tests/test_i18n_keys.py` is the guard. It reads every
`tr()` call in `src/hoi4cm` and `hoi4_content_maker.py` with `ast` and checks
that:

- every literal key is in `locales/en.json`, and every key in `en.json` is used
  by some call (orphans fail);
- every locale file has exactly the keys of `en.json`, apart from `_meta`, with
  the same named placeholders;
- every call supplies the placeholders its English text names, and none passes
  `key=` or `default=`, which collide with the parameters of `tr()`.

A call whose key is built at run time (an f-string or a variable) is invisible
to the scan. Each one is listed in `DYNAMIC_KEYS` in the test with every key it
can produce, and a new or changed dynamic call fails until it is listed. Undo
labels work the same way: the stack keeps English identifiers, and
`hoi4cm.ui.undo_labels` maps them to keys when the toast is shown.

## Fixture / isolation patterns

Every module with import-time or process-lifetime state needs isolation, or
state leaks between tests. Six patterns cover what's here today:

- **Pytest-startup HOME isolation.** `tests/conftest.py` installs a temporary
  HOME while the conftest is imported, before collection imports application
  modules. This keeps import-time logging, config reads, scan-cache paths, and
  autosave paths out of the real user home for the entire run. A subprocess
  regression test (`tests/test_home_isolation.py`) proves that sentinel files
  in the initial HOME are not changed.

- **Module-state snapshot/restore.** `tests/test_logger.py`'s `log_state`
  fixture saves `sys.excepthook`, the excepthook-installed flag, and the
  error callback before a test, yields, then restores all three and clears
  the error buffer. Use this shape for anything that mutates a module
  global as a side effect (see "Module-level singletons" in
  `architecture.md`).
- **MOD singleton isolation.** Tests that mutate the process-wide `MOD`
  context opt in to `mod_state_isolation` from `tests/conftest.py`. It restores
  added/removed attributes and nested built-in containers, `GraphicsCatalog`
  state, scan diagnostics, and the `sprite_imgs` LRU while retaining the
  catalog, cache, and cached image object identities. It is deliberately not
  autouse: modules opt in where needed and keep scenario-specific setup.
  Tests that only use `monkeypatch.setattr` on MOD have their changes restored
  by monkeypatch teardown and do not need this fixture.
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
  related builds reuse a `BuildContext` allocator, while standalone builds use
  their own context, so IDs stay local and independent of test order.

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
instead of numeric id (IDs belong to the document), and
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

## Platforms

The Tk smoke needs a display. On Linux run it under `xvfb-run -a` so nothing
opens on your desktop (`sudo apt-get install xvfb xauth` on Debian/Ubuntu).
That is the only way it is run and checked. CI runs it on Linux only, so a
pass says nothing about Windows or macOS.

The separate `windows-permissions` job runs `tests/test_cache_permissions.py`
on native Windows. Both new-cache and existing-cache cases inspect real directory
and database DACLs. Executable builds depend on this job as well as lint and the
Linux test job, so a cache-permission failure blocks release artifacts.

## What is not automated

Widget behavior has no automated test: canvas drawing and culling, the
virtualized list and thumbnail pools, dialog flows (confirm, browse, the
button press that starts a save), keyboard focus, grabs, and the tutorial
walk. The smoke proves each window builds. The checklists below cover the
rest by hand, and each one is a candidate for extraction into a pure function
with a headless test.

What a wizard save writes is the worked example: the four "Save to Mod" paths
live in `wizards/_saves.py` and `tests/test_wizard_saves.py` checks them
against `tmp_path` trees (see `wizards.md`).

No test starts the editor's main loop. The entry point is checked with
`--smoke-test`, both in the Tk smoke and against the frozen executable.

## Manual verification

Run against the real Millennium Dawn mod (this machine keeps a checkout at
`/mnt/Linux/Millennium-Dawn`), not a synthetic small mod, since the scale
targets in `performance.md` only show up at MD's size:

- Cold load (no scan cache) and warm load (second load, cache hit) of the
  mod, comparing scan time and the summary counts.
- Import the largest tree (`usa.txt`, 776 focus blocks) standalone.
- "Load All Trees" across the full `common/national_focus` directory while
  interacting with the canvas (pan/zoom) during and after the batch.
- Cancel a Load All Trees batch mid-run. The modal stays up until the
  current file finishes, then already-parsed trees stay loaded and the
  summary says it was cancelled.
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

`tests/test_viewport.py` and `tests/test_scene_index.py` cover the culling
math. Applying it to a canvas has no automated test, so these need the real
`App` and a loaded tree (event bindings, undo, mod reload, the minimap widget):

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

None of this has an automated test. These need the real
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
- **Menu sweep**: click every File/Edit/View/Tools/Help item at least once
  (including the "Recent" submenu with zero and with several mods loaded)
  and confirm each does what its tooltip says, the dropdown closes on
  outside click, and the accelerator shown next to each item still matches
  its bound keybind (`_build_keybinds`). With a focus selected, press each
  arrow key and confirm it moves one grid cell; repeat with a multi-selection
  and confirm the group moves together, then press an arrow toward an occupied
  cell and confirm nothing moves. Confirm Escape closes New Focus Tree, Load
  All Trees, and Set Edit Targets, and F1 restarts the tutorial. Confirm the
  error-log button still turns red after a deliberately triggered error and
  the mod label updates on load/unload.
- **First-launch tutorial**: start with `tutorial_disabled` absent, dismiss any
  autosave-recovery prompt, and confirm all eight translated steps appear in
  order. The Tools/File steps must pin the real dropdown open, highlight the
  intended rows, and leave those commands non-interactive. Resize or move the
  app between steps, finish with "Don't show this again" selected, restart to
  confirm it stays hidden, then use Help > Start Tutorial to relaunch it.
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

## Sidebar phase 2 verification (2026-10-22)

On Windows / Python 3.14.7, the real application was launched with the existing
`project_roundtrip.txt` fixture for before/after, empty, narrow (760×640), and
simulated 200% DPI captures. The supplied sidebar icons were checked byte-for-byte
against their originals. The Spotlight renderer and its six action assets are unchanged.

- 35 Tk smoke tests passed, including explorer keyboard navigation without moving
  nodes, selection synchronization, search expansion restoration, multiple trees,
  long labels, invalid drafts, resource discovery caching/reveal, resizing/collapse,
  simulated DPI, Spotlight and recovery regressions.
- 40 focused headless tests passed. The full headless run had 1,651 passed,
  7 skipped and 7 failures. Each failure also reproduced on the starting commit:
  three graphics-catalog path assertions, one graphics-browser search assertion,
  one image-broker path assertion, one settings path assertion and a CRLF assertion.
- Ruff, Black's library formatting check (233 Python files), mypy and pylint on
  changed modules/tests passed. The full pylint invocation retains existing
  canvas return-consistency and character-editor maxsplit messages.
- A cached query over 20,000 synthetic focus records took 3.3 ms on this machine;
  this measures filtering and ancestor retention, not drawing 20,000 canvas nodes.

Physical monitor-to-monitor DPI transitions, macOS/Linux folder-viewer launches,
and full-scale interactive mod inventories were not manually tested. Source-folder
launches are mocked in the Tk regression test; source discovery and real script
import are exercised. Save/export/undo/recovery checks remain in the existing suites.

### All-tree catalog follow-up

The application was launched against the configured Millennium Dawn source folder:
114 tree-definition files were listed, with the styles-only file excluded. Search
for Germany was captured in the real application. The follow-up passed 36 Tk smoke
tests, 12 focused catalog/import tests, Ruff, mypy and changed-module pylint. Tests
cover recursive discovery, utility/comment/string exclusion, tolerant reads, read
failures, loaded-file deduplication, explicit file opening, cancellation before reads,
import undo recording, and opening the existing New Focus Tree dialog. Catalog
selection/search do not mutate the workspace. The full headless suite was not rerun
for this follow-up; the prior full-run baseline is recorded above.

### Validation theme regression

Opening Validate previously called `ttk.Style.theme_use("clam")`, replacing the
application-wide Windows `vista` theme and losing the Project.Treeview's named
styles. A real Tk regression reproduced this theme change before the fix. Validate
now configures only Val.Treeview in the current theme. All 37 Tk smoke tests pass,
including validation refresh, explorer colors/row height, scrollbar colors and
Spotlight behavior. Existing running processes need restarting to load the fix.
