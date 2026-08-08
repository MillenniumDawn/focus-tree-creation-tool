# Architecture

## Package map

`src/hoi4cm/`, one bullet per subpackage:

- **`core/`**: logging, config, paths, i18n, image gating, path/XML
  sanitizing, the sparse undo stack (`undo.py`, `UndoStack`), and a bounded
  LRU mapping (`lru.py`, `LRUCache`) backing the in-memory `PhotoImage`
  caches. Re-exported flat through `core/__init__.py` (the "facade", see
  below). Everything else in the package can depend on `core`; core submodules
  other than the facade depend on nothing else in `hoi4cm`.
- **`data/`**: static tables: `EFFECT_DEFS`/`MODIFIER_DEFS` and the MD
  building/resource cost tables. No logic beyond lookup helpers.
- **`models/`**: `Focus`, the plain-data class behind every canvas item.
  `to_dict`/`from_dict` for JSON round-trips (autosave, tree files).
- **`script/`**: low-level HOI4 script marshalling: `dict_to_raw`,
  `normalize_effect_fields`, `append_scripted_loc`. Pure string/dict work.
- **`focus_tree/`**: the parse/build/export pipeline for focus-tree script
  text. Pure, no tkinter: `parse.py` tokenizes and parses, `build.py` turns
  a `ParsedFocusTree` into `Focus` objects, `export.py` renders focuses back
  to script text given a caller-supplied effect renderer, `loc.py` builds
  the matching `l_english.yml` localisation text (`build_loc_yml`), and
  `drawio.py` walks a draw.io mxGraph XML export into the same `Focus`
  shape (`parse_drawio_graph`, `drawio_to_focus_data`,
  `build_drawio_focuses`).
- **`mod/`**: `ModContext` (the `MOD` singleton): walks a mod's directory
  tree once and indexes sprites, focus/event/idea/decision/dyn-mod IDs,
  country tags, and MD money-system paths. `scan_cache.py` is the SQLite
  per-file cache backing warm reloads.
- **`wizards/`**: the five `open_*_wizard(app)` entry points (decision,
  event, national spirit, dynamic modifier, additional income) plus
  `_shared.py` for cross-wizard state. The package `__init__` resolves the
  five names through a module-level `__getattr__`, so importing one wizard
  doesn't load the other four; keep it that way when adding a sixth. See
  `wizards.md`.
- **`ui/`**: Tk-facing code: `CanvasMixin`, `EffectsMixin`,
  `ModLoadingMixin` (the three mixins `App` is built from), `gfx_browser.py`
  (the universal GFX picker, the drag-to-place GFX editor, and the
  sidebar's narrower focus-icon picker, see `monolith-migration.md` for why
  there are two GFX browsers instead of one), `settings_dialog.py`
  (`open_settings`), `menubar.py`/`toolbar.py` (`build_menubar`/
  `build_toolbar_row2`, the one-shot builders behind `App`'s top bar),
  `tasks.py` (the `run_bg`/`progress_modal` background-worker plumbing, see
  "Threading model" below), theme constants, and small shared widgets
  (`Tooltip`, `_safe_after`). One exception to "Tk-facing": `viewport.py`
  is pure, no-tkinter viewport-culling math (`visible_world_rect`,
  `focus_visible`, `edge_visible`) that `CanvasMixin` calls into, kept
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

The old underscore-aliasing story (`_cfg_load = cfg_load`, etc.) is gone
from the monolith. One survivor remains, but it moved with its only caller:
`_default_hoi4_mod_dir = default_hoi4_mod_dir` now lives in
`hoi4cm/ui/mod_loading.py`, kept because `_load_mod` (same module) still
references the underscore name. `settings_dialog.py`'s `open_settings`
calls `default_hoi4_mod_dir()` directly and never needed the alias.

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

## Revision discipline

`FocusDocument` owns focus geometry and bumps a `geometry_revision` counter
whenever a focus moves (its mutating methods, or an explicit `touch()`).
UI that caches against that counter recomputes only when it changes:
`SceneIndex` (canvas hit-testing and culling) rebuilds when
`FocusDocument.revision` moves, and the minimap's world-bounds cache is keyed
on `SceneIndex.revision`. The rule: never mutate a focus's coordinates in
place without going through `FocusDocument` / `touch()`. Skip it and those
caches keep stale coordinates, so hit-testing and the minimap disagree with
what's actually drawn until something else forces a rebuild.

## Threading model (phase 5)

Two things run off the Tk main thread on their own bespoke plumbing: the mod
scan (`ui/mod_loading.py`, a daemon `threading.Thread` running `MOD.scan`)
and image loads that go through the same worker. Everything else that needs
a background thread (batch tree loading, `.txt`/`.drawio` import parsing)
goes through `ui/tasks.py`, which generalizes that same
worker-thread-plus-`_safe_after` shape into `run_bg`.

### The `run_bg` contract

`run_bg(widget, work, on_done, on_error=None)` submits
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
destroyed-widget `AttributeError` and `TclError`, not arbitrary exceptions
from the scheduled callback. A bare
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
cancel_futures=True`; `cancel_futures` needs Python 3.9+, well under this
project's 3.14 floor) is wired into `_on_app_close` so pending background
work doesn't block process exit; it's idempotent and safe to call from
tests.

The background pool the modernized UI uses (the mod scan and image decoding)
is `core/concurrency.py`'s `DaemonThreadPoolExecutor`, handed out through
`ApplicationLifecycle.executor`. Its workers start as **daemon** threads on
purpose (`core/concurrency.py:58`). App close is now a graceful lifecycle
close (resources released through `ui/lifecycle.py`), not the old
`os._exit`, so a non-daemon worker still draining its queue would keep the
process alive after the window is gone.

Parsing, building, and export remain thread-agnostic pure functions with no
opinion on which thread calls them. `run_bg` is what decides that they run
off the Tk thread for `_load_all_trees`, `_import_txt`, and `_import_drawio`
today. `performance.md`'s GIL guidance still applies: threads here buy UI
responsiveness, not parse concurrency, which is why multi-file batch loads
process files sequentially rather than fanning out across workers.
