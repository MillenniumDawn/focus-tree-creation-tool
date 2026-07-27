# AGENTS.md

Guidance for AI coding agents (opencode, Claude Code, etc.) working in this repo. `CLAUDE.md` is a symlink to this file.

## What this is

A standalone Python/Tkinter desktop app for authoring Hearts of Iron IV mod content (focus trees, decisions, events, ideas, dynamic modifiers). It parses existing Paradox script, edits it visually, and exports wiki-accurate `.txt`/`.yml` files. Stdlib + tkinter only at runtime; Pillow and PyInstaller are optional extras.

## The one rule that shapes everything

**New code goes in `src/hoi4cm/`. Do not grow the monolith.**

`hoi4_content_maker.py` is down to ~6k lines from its original ~21k. What's left is essentially `class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk)` plus the importers and exporters that haven't been extracted yet (see `docs/dev/monolith-migration.md` for the full status table). When adding or refactoring, extract into a `src/hoi4cm/` module and pair it with a test — don't add features to the monolith. Edits to the monolith should be confined to bug fixes and the wiring needed to call into newly-extracted modules.

## Commands

```bash
python hoi4_content_maker.py    # run the app (needs a display + tkinter)

pip install ".[dev]"            # tests + linters
pytest                          # full suite (src/ is on the path via pyproject)
pytest tests/test_config.py::test_cfg_save_merges_existing_keys   # single test
ruff check .                    # lint
black --check .                 # formatting

python build/build.py           # standalone exe (after pip install ".[build]")
```

CI runs ruff + black and pytest, all on 3.14 (the project's floor).

## Layout

- **`hoi4_content_maker.py`** — the launch point and (still) most of the app: `App(tk.Tk)` and its remaining importers/exporters/settings. Entry point at the bottom calls `show_splash(_launch)`.
- **`src/hoi4cm/core/`** — the extracted package: `logger.py`, `config.py`, `paths.py`, re-exported flat from `hoi4cm.core`. This is where new modules land.
- **`hoi4_logger.py`** — back-compat shim re-exporting from `hoi4cm.core.logger`. No logic here.
- **`docs/dev/`**: developer docs, architecture, migration status, performance, testing, wizards. Start at `docs/dev/README.md`.

The monolith inserts `src/` onto `sys.path` at startup and imports canonical names straight from the `hoi4cm.core` facade (`from hoi4cm.core import (...)`). There's no more underscore-aliasing layer; the one survivor is `_default_hoi4_mod_dir = default_hoi4_mod_dir`, kept because a couple of call sites still use the old name. When you extract a new module, add the public name to the owning subpackage's `__all__`, and to `core/__init__.py`'s import and `__all__` if the monolith needs it from there. Details in `docs/dev/architecture.md`.

## Conventions

- **Lint scope:** ruff (`E,F,W,I,UP,B`) and black (line-length 88) cover `src/hoi4cm/` and `tests/` only — the monolith and `build/` are excluded. Packaged code must pass both; in the monolith, match the existing style by hand.
- **Logging, not print.** `get_logger("name")` for a `HOI4CM.<name>` child. User-facing errors go through `add_error()` so they reach the in-app error log.
- **Tolerant file reads.** Mod files have mixed encodings — read them via `read_file`, never bare `open(...).read()`.
- **Preserve user data on round-trips.** Parse→export of an existing file must not drop fields. Test round-trips when touching the parser or exporters.
- **Frozen paths.** `~/.hoi4_focus_maker.json` (config) and `~/.hoi4cm/` (logs) are unchanged from the monolith so existing users keep their settings. Don't rename them.
- New modules ship with a test under `tests/` (see `test_logger.py`/`test_config.py` for the isolation-fixture style) — only packaged code is covered.

## Releases

Pushing a tag matching `v*` triggers `release.yml`: the version is the tag name (`github.ref_name`), it builds Win/macOS/Linux executables, and publishes a Release with them attached. Executables are never committed.
