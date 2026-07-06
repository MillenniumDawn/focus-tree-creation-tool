# Testing

168 tests across 17 files under `tests/` (`pytest --collect-only -q`).
`pyproject.toml`'s `[tool.pytest.ini_options]` puts `src/` on `pythonpath`
and scopes `testpaths` to `tests/`, so `pytest` from the repo root just
works. No `conftest.py`; fixtures live in the file that uses them.

## Fixture / isolation patterns

Every module with import-time or process-lifetime state needs a fixture
that resets it, or state leaks between tests. Four patterns cover what's
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

## Golden-fixture tests for the focus-tree pipeline

`tests/fixtures/focus_trees/*.txt` are small hand-written files, each one
isolating a single importer behavior: a `focus_tree = { }` wrapper with
prerequisite OR/AND groups and mutex, bare top-level `focus`/`shared_focus`
blocks with no wrapper, a `country` block with deliberately irregular
formatting (to check verbatim capture), a country-tag-matching `offset`
block, and a file with a missing closing brace that only the per-focus
brace-walk fallback recovers. `tests/test_focus_tree_fixtures.py` parses and
builds each one and compares the result against a committed golden JSON
under `tests/fixtures/focus_trees/golden/`.

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
field survival. `country_raw` is excluded from that round-trip: `export.py`
still emits a canned `country` block rather than the captured verbatim text,
so there's nothing to round-trip yet (wiring `country_raw` into `export.py`
is a separate, later change). `country_raw` capture at parse time is
checked directly in `test_focus_tree_fixtures.py` instead.

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

CI's `test` job (`.github/workflows/ci.yml`) runs on plain `ubuntu-latest`
with no `python3-tk` install and no Xvfb, so it has neither a display nor a
guaranteed-working `tkinter` import. Nothing that opens a real Tk window
can run there. In practice: every pure
module (`focus_tree/`, `models/`, `script/`, `mod/`, `data/`, all of
`core/`) has real test coverage, and every wizard in `wizards/` plus most
of `ui/` has none. `tests/test_ui_smoke.py` is the exception that proves
the rule: it imports `hoi4cm.ui`/`hoi4cm.ui.theme` and asserts on plain
data (theme constants are hex strings, `BORDER` is exported) without ever
instantiating a `Tk()` root or starting a mainloop. That's the ceiling for
what a headless test can check on the UI side today. Anything that needs
a real widget, geometry, or event binding is manual-only.

## Manual verification

Run against the real Millennium Dawn mod (this machine keeps a checkout at
`/mnt/Linux/Millennium-Dawn`), not a synthetic small mod, since the scale
targets in `performance.md` only show up at MD's size:

- Cold load (no scan cache) and warm load (second load, cache hit) of the
  mod, comparing scan time and the summary counts.
- Import the largest tree (`usa.txt`, 776 focus blocks) standalone.
- "Load All Trees" across the full `common/national_focus` directory while
  interacting with the canvas (pan/zoom) during and after the batch.
- Edit and move a focus, undo, redo five times in a row (`edit/move/undo x5`),
  watching for undo-stack correctness and canvas redraw glitches.
- Export to a scratch copy of a file and diff it against the original to
  confirm the round-trip didn't drop or reorder fields.
