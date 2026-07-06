# Testing

146 tests across 16 files under `tests/` (`pytest --collect-only -q`).
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
