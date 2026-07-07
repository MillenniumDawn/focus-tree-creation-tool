# Architecture

## Package map

`src/hoi4cm/`, one bullet per subpackage:

- **`core/`**: logging, config, paths, i18n, image gating, path/XML
  sanitizing, and the sparse undo stack (`undo.py`, `UndoStack`). Re-exported
  flat through `core/__init__.py` (the "facade", see below). Everything else
  in the package can depend on `core`; `core` depends on nothing else in
  `hoi4cm`.
- **`data/`**: static tables: `EFFECT_DEFS`/`MODIFIER_DEFS` and the MD
  building/resource cost tables. No logic beyond lookup helpers.
- **`models/`**: `Focus`, the plain-data class behind every canvas item.
  `to_dict`/`from_dict` for JSON round-trips (autosave, tree files).
- **`script/`**: low-level HOI4 script marshalling: `dict_to_raw`,
  `normalize_effect_fields`, `append_scripted_loc`. Pure string/dict work.
- **`focus_tree/`**: the parse/build/export pipeline for focus-tree script
  text. Pure, no tkinter: `parse.py` tokenizes and parses, `build.py` turns
  a `ParsedFocusTree` into `Focus` objects, `export.py` renders focuses back
  to script text given a caller-supplied effect renderer.
- **`mod/`**: `ModContext` (the `MOD` singleton): walks a mod's directory
  tree once and indexes sprites, focus/event/idea/decision/dyn-mod IDs,
  country tags, and MD money-system paths. `scan_cache.py` is the SQLite
  per-file cache backing warm reloads.
- **`wizards/`**: the five `open_*_wizard(app)` entry points (decision,
  event, national spirit, dynamic modifier, additional income) plus
  `_shared.py` for cross-wizard state. See `wizards.md`.
- **`ui/`**: Tk-facing code: `CanvasMixin`, `EffectsMixin`,
  `ModLoadingMixin` (the three mixins `App` is built from), the GFX
  browser/placement editor, theme constants, and small shared widgets
  (`Tooltip`, `_safe_after`). One exception to "Tk-facing": `viewport.py`
  is pure, no-tkinter viewport-culling math (`visible_world_rect`,
  `focus_visible`, `edge_visible`) that `CanvasMixin` calls into — kept
  separate so it has real headless test coverage like `focus_tree/`,
  instead of joining the rest of `ui/`'s manual-only surface (see
  `testing.md`).

## Dataflow

```
file text
  -> focus_tree.parse.parse_focus_tree      (tokenize + parse into ParsedFocusTree)
  -> focus_tree.build.build_focuses         (ParsedFocusTree -> list[Focus])
  -> App.focuses                            (App owns the live list, keyed by tree)
  -> CanvasMixin draw                       (Focus -> canvas items, dirty-key redraw)
  -> focus_tree.export.export_focus_tree    (Focus -> script text, on save/export)
  -> loc export                             (id -> l_english.yml entries)
```

Parsing and export are pure and tested without a display. Everything from
`App.focuses` onward touches Tk and is exercised manually (see
`testing.md`).

## The core facade

The monolith does not import individual `hoi4cm.core.foo` submodules. It
imports canonical names from `hoi4cm.core` itself:

```python
from hoi4cm.core import (
    CONFIG_PATH, EFFECT_DEFS, Focus, add_error, build_focuses,
    export_focus_tree, parse_focus_tree, sanitize_component, tr, ...
)
```

`core/__init__.py` re-exports from its own submodules (`config.py`,
`i18n.py`, `logger.py`, `paths.py`, `safe_path.py`, `safe_xml.py`) and also
re-exports from sibling subpackages (`data`, `focus_tree`, `models`,
`script`, `ui`) so the monolith has one import line to maintain. When you
extract a new module, add the public name to the owning subpackage's
`__all__`, then add it to `core/__init__.py`'s import and `__all__` if the
monolith (or a wizard) needs it from there.

The old underscore-aliasing story (`_cfg_load = cfg_load`, etc.) is gone.
The one survivor is `_default_hoi4_mod_dir = default_hoi4_mod_dir` at
`hoi4_content_maker.py:97`, kept because `_load_mod` and `_open_settings`
still reference the underscore name.

## Module-level singletons

A handful of modules hold process-lifetime state instead of being
instantiated per use. Know these before writing a test that touches them,
or state leaks across tests:

- **`MOD`** (`hoi4cm.mod.context.ModContext`, instantiated once in
  `mod/__init__.py`): the discovered-mod-assets object every wizard and
  the App read from. Rebuilt in place by `MOD.scan(root)` on mod load, not
  replaced.
- **i18n state** (`hoi4cm.core.i18n`): `I18N_LANG`/`I18N_STRINGS` are
  module globals, loaded once at import time and reassigned by
  `set_language()`. Read them through `get_language()`/`tr()`, not by
  importing the globals directly (an imported name goes stale after a
  language switch).
- **Logger state** (`hoi4cm.core.logger`): the error buffer, the
  registered error callback, and whether the excepthook is installed are
  all module globals. `test_logger.py`'s `log_state` fixture snapshots and
  restores all three around each test.
- **`Focus._next`** (`hoi4cm.models.focus.Focus`): a class-level counter
  used to assign IDs. `Focus.from_dict` bumps it past any ID it loads, so
  freshly created focuses never collide with imported ones. Tests that
  create focuses reset it in a fixture (see `test_focus_tree_roundtrip.py`).

## Threading model (phase 5)

Two things run off the Tk main thread on their own bespoke plumbing: the mod
scan (`ui/mod_loading.py`, a daemon `threading.Thread` running `MOD.scan`)
and image loads that go through the same worker. Everything else that needs
a background thread (batch tree loading, `.txt`/`.drawio` import parsing)
goes through `ui/tasks.py`, which generalizes that same
worker-thread-plus-`_safe_after` shape into `run_bg`.

### The `run_bg` contract

`run_bg(widget, work, on_done, on_error=None, progress_cb=None)` submits
`work` (a zero-arg callable) to a shared `ThreadPoolExecutor`
(`get_executor()`, lazily created, `max_workers=2`,
`thread_name_prefix="hoi4cm-bg"`). On success, `on_done(result)` runs on the
Tk thread via `_safe_after`. On any exception from `work`, it's logged
(`log.exception`) and recorded via `add_error` so it reaches the in-app
error log, then `on_error(exc)` runs on the Tk thread if given.

The hard rule for anything inside `work`: **never touch Tk** (widgets,
`StringVar`/`BooleanVar`, canvas items, dialogs; Tkinter isn't
thread-safe), **never call `MOD.get_image`** (`PhotoImage` construction is
Tk-thread-only), and **never mutate `App` state** (`self.focuses`,
`self._extra_trees`, ...). The pattern every call site follows: take a
snapshot of whatever `self` state the computation needs *on the Tk thread*
before calling `run_bg`, compute against that snapshot inside `work`, and
apply the result to `self` inside `on_done`, which always runs on the Tk
thread, so it's the only place mutation happens. A worker is free to
construct plain-data results (`Focus` instances, `ParsedFocusTree`s) since
`App` doesn't adopt them until `on_done` inserts them into its own
dicts/lists.

`make_progress(widget, fn)` returns a callable safe to invoke from a worker;
calling it marshals `fn(*args, **kwargs)` onto the Tk thread via
`_safe_after`, in call order. `progress_modal(parent, title)` opens a small
`Toplevel` with a status label and a bar, `grab_set()`, and
`WM_DELETE_WINDOW` blocked: the same shape as the inline dialog in
`_load_mod`, factored out.

`_safe_after`/`_safe_after_idle` (`ui/widgets.py`) only swallow
`AttributeError` (the documented Python 3.14 `_tclCommands` destroyed-widget
bug), not arbitrary exceptions from the scheduled callback. A bare
`except Exception` there would silently eat bugs inside `on_done`/`on_error`
instead of surfacing them.

### The modal-grab invariant

`progress_modal`'s `grab_set()` isn't just UX polish: it's what makes it
safe for a worker to read a snapshot of `self.focuses` (or build `Focus`
objects) without the user mutating the live dict concurrently on the Tk
thread. Every `run_bg` call site that reads or builds against `self.focuses`
holds a `progress_modal` (or an equivalent grab) for the duration.

That grab is also why building `Focus` objects on a worker thread is safe
despite `Focus.__init__` bumping the shared `Focus._next` class counter:
there's only ever one thread creating focuses at a time, because the modal
grab blocks the user from triggering focus creation on the Tk thread while
the worker runs.

### Executor lifecycle

`get_executor()` creates the pool on first use and returns the same
instance after that. `shutdown_executor()` (`wait=False,
cancel_futures=True`; `cancel_futures` needs Python 3.9+, this project's
floor) is wired into `_on_app_close` so pending background work doesn't
block process exit; it's idempotent and safe to call from tests.

Parsing, building, and export remain thread-agnostic pure functions with no
opinion on which thread calls them. `run_bg` is what decides that they run
off the Tk thread for `_load_all_trees`, `_import_txt`, and `_import_drawio`
today. `performance.md`'s GIL guidance still applies: threads here buy UI
responsiveness, not parse concurrency, which is why multi-file batch loads
process files sequentially rather than fanning out across workers.
