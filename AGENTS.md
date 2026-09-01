# AGENTS.md

Guidance for AI coding agents (opencode, Claude Code, etc.) working in this repo. `CLAUDE.md` is a symlink to this file.

## What this is

A standalone Python/Tkinter desktop app for authoring Hearts of Iron IV mod content (focus trees, decisions, events, ideas, dynamic modifiers). It parses existing Paradox script, edits it visually, and exports wiki-accurate `.txt`/`.yml` files. Stdlib + tkinter only at runtime; Pillow and PyInstaller are optional extras.

## The one rule that shapes everything

**New code goes in `src/hoi4cm/`. Do not grow the monolith.**

`hoi4_content_maker.py` is down to ~5.7k lines from its original ~21k. What's left is essentially `class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk)` holding the Tk shells: dialogs, wiring, event bindings, and the one-line delegates into extracted modules. The sidebar form is the last big chunk still in the monolith and is deliberately deferred (see `docs/dev/monolith-migration.md` for the full status table and why). When adding or refactoring, extract into a `src/hoi4cm/` module and pair it with a test — don't add features to the monolith. Edits to the monolith should be confined to bug fixes and the wiring needed to call into newly-extracted modules.

## Commands

```bash
python hoi4_content_maker.py    # run the app (needs a display + tkinter)

pip install ".[dev]"            # tests + linters
pytest                          # full suite (src/ is on the path via pyproject)
pytest tests/test_config.py::test_cfg_save_merges_existing_keys   # single test
ruff check .                    # lint
black --check .                 # formatting
mypy                            # type check (src/hoi4cm + tests)
pylint src/hoi4cm tests         # lint (light gate on top of ruff/black)
pre-commit run --all-files      # run all hooks once
pre-commit install              # run hooks on every commit

python build/build.py           # standalone exe (after pip install ".[build]")
```

CI runs ruff, black, mypy, pylint and pytest, all on 3.14 (the project's floor).

## Layout

- **`hoi4_content_maker.py`** — the launch point and (still) most of the app: `App(tk.Tk)`, its Tk-shell methods and one-line delegates into extracted modules, and the deferred sidebar form. Entry point at the bottom calls `show_splash(_launch)`.
- **`src/hoi4cm/`** — the extracted package, organized by domain: `core/` (logger, config, paths, undo, i18n, concurrency, safe file/xml helpers), `models/` (`Focus`, `FocusDocument`, `EditorWorkspace`), `focus_tree/` (parse/build/export, codec, operations, drawio, loc), `ui/` (canvas, splash, menubar, toolbar, settings dialog, gfx browser, image pipeline), `wizards/` (the five authoring wizards + shared helpers), `mod/` (mod context, GFX catalog, scan/workspace caches), `script/` (effects + syntax), `editor/` (project save/load), `data/` (effect/modifier tables). New modules land in the owning subpackage, not a catch-all.
- **`docs/dev/`**: developer docs, architecture, migration status, performance, testing, wizards. Start at `docs/dev/README.md`. They carry a maintenance rule: any PR that changes architecture, hot paths, or migration status updates the matching doc in the same PR.

The monolith inserts `src/` onto `sys.path` at startup and imports canonical names straight from the `hoi4cm.core` facade (`from hoi4cm.core import (...)`), which re-exports the public names of every subpackage (data, focus_tree, models, ui, ...). There's no underscore-aliasing layer left. When you extract a new module, add the public name to the owning subpackage's `__all__`, and to `core/__init__.py`'s import list and `__all__` if the monolith or a wizard needs it via the facade. Details in `docs/dev/architecture.md`.

## Conventions

- **Lint scope:** Ruff (`E,F,W,I,UP,B`) and Black (line-length 88) cover all Python except `build/`; mypy and pylint cover `src/hoi4cm/` and `tests/` only. Packaged code must pass all four; the monolith must pass Ruff and Black. Config lives in `pyproject.toml` (`[tool.ruff]`, `[tool.black]`, `[tool.mypy]`, `[tool.pylint]`); `.pre-commit-config.yaml` wires them into pre-commit. Pylint's `disable` list is deliberate: it drops checks Ruff/Black already cover and false positives on Tk/dataclass/mixin patterns, so it stays a light gate.
- **Logging, not print.** `get_logger("name")` for a `HOI4CM.<name>` child. User-facing errors go through `add_error()` so they reach the in-app error log.
- **Tolerant file reads.** Mod files have mixed encodings — read them via `read_file`, never bare `open(...).read()`.
- **Preserve user data on round-trips.** Parse→export of an existing file must not drop fields. Test round-trips when touching the parser or exporters.
- **Frozen paths.** `~/.hoi4_focus_maker.json` (config) and `~/.hoi4cm/` (logs) are unchanged from the monolith so existing users keep their settings. Don't rename them.
- New modules ship with a test under `tests/` (see `test_logger.py`/`test_config.py` for the isolation-fixture style) — only packaged code is covered.

## Releases

`ci.yml` is the only workflow. Every push and PR runs lint, test, then the Win/macOS/Linux build matrix. Pushing a tag matching `v*` runs that same gate and adds the `release` job, which publishes a Release with the three binaries and a `SHA256SUMS.txt` attached; the version is the tag name (`github.ref_name`). Executables are never committed. Build deps are hash-pinned in `build/requirements.txt`, regenerated with `uv pip compile --generate-hashes --universal --extra build pyproject.toml -o build/requirements.txt`.
