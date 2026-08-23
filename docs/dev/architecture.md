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
  matching configured-language localisation text (`build_loc_yml`).
  `loc.py` also owns `LocTarget`, the explicit HOI4 language table used to
  resolve each header, directory, and filename suffix,
  `drawio.py` walks a draw.io mxGraph XML export into the same `Focus`
  shape (`parse_drawio_graph`, `drawio_to_focus_data`,
  `build_drawio_focuses`), and `batch_load.py` walks a file list into
  parsed trees (`batch_load_trees`, `make_cancel_handle`).
- **`mod/`**: `ModContext` (the `MOD` singleton): walks a mod's directory
  tree once and indexes sprites, focus/event/idea/decision/dyn-mod IDs,
  country tags, and MD money-system paths. `scan_cache.py` is the SQLite
  per-file cache backing warm reloads. `workspace_files.py` is the single
  writer every mod-file save goes through (see "Writing mod files" below).
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
  -> loc export                             (id -> configured-language YML entries)
```

The selected HOI4 localisation language is persisted as `loc_language` on
`ModContext`. UI code snapshots that string into export plans and pure wizard
generators; worker code does not read mutable global settings. Existing edit
targets remain explicit overrides, while automatic discovery recursively
filters `localisation/` for the configured language.

Parsing and export are pure and tested without a display. Everything from
`App.focuses` onward touches Tk and is exercised manually (see
`testing.md`).

## Writing mod files

Every write that lands in a user's mod goes through one class:
`hoi4cm.mod.workspace_files.WorkspaceFiles`. Nothing outside it may call
`open(path, "w")` on a mod file, a project `.json`, or a localisation
`.yml` — the target is usually a **tracked file the user already has**, and a
truncate-in-place write destroys it if the process dies mid-write (issue #46).

- **`write_text(path, text, encoding=...)`** — temp file in the target's own
  directory, `flush` + `fsync`, then `os.replace`. Creates missing parents
  and preserves the target's existing mode.
- **`write_texts([(path, text, encoding), ...])`** — the same, for a *group*
  of files that must land together. Every temp file is staged and fsynced
  before the first swap, so an encoding error or a full disk aborts while all
  targets still hold their old contents; if a swap fails part-way anyway, the
  already-swapped targets are restored from snapshots taken just before the
  swap. This is what the focus-tree `.txt` + loc `.yml` pair uses, so an
  export is never half-applied.
- **`append_text(...)`** — a plain append (nothing to truncate), used by the
  loc/scripted-loc paths that only ever add entries.

`notifying_workspace_files(MOD, mod_root)` (same module, re-exported from
`hoi4cm.wizards._shared` for the wizards) builds a writer whose `on_written`
hook pokes the graphics catalog — but only when the save target is the
currently loaded mod, so writing elsewhere never touches live state.

The other half of the contract is that a failure is **reported**, not
swallowed or raised as a traceback: `hoi4cm.ui.file_errors`'s
`report_write_failure(parent, path, error)` records it via `add_error()` (so
it reaches the in-app error log) and raises a dialog naming the file. The
monolith's `_export`, `_export_extra_tree` and `_save` all return `None`
through it rather than showing a success dialog for an export that never
landed.

`report_write_failure` delegates to the generic `hoi4cm.ui.error_report`'s
`report_error(msg, exc=None, *, parent=None, title=None)`, which is the one
place a handled error turns into a log entry (with the traceback when an
exception is given) plus a dialog. Synchronous import/parse/export failures
across the monolith and the wizards go through it (issue #52), so the
in-app error log sees what used to be dialog-only errors; background-task
failures were already covered by `run_bg` in `ui/tasks.py`.

One deliberate consequence: an atomic write needs write permission on the
target's **directory**, not just on the file. A read-only mod folder that used
to accept an in-place overwrite now fails with a clear dialog. That is the
intended trade — the alternative is truncating the user's tree and hoping.

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
`_safe_after`, in call order. `progress_modal(parent, title, *, determinate=True,
cancellable=False)` opens a small `Toplevel` with a status label and a bar,
`grab_set()`, and `WM_DELETE_WINDOW` blocked: the same shape as the inline
dialog in `_load_mod`, factored out. The handle always exposes `cancelled`
(a `threading.Event`) and `request_cancel()`. Import, export, and Save All
leave `cancellable` off.

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

Cancel is cooperative, not a kill. `make_cancel_handle` and
`batch_load_trees` live in `focus_tree/batch_load.py` with no Tk objects.
`cancellable=True` (Load All Trees) adds a Cancel button and routes
window-close to that handle. Neither destroys the window nor drops the grab;
they set `cancelled` so the worker can stop between files. The in-flight
file finishes, `batch_load_trees` returns the results it already built, and
`on_done` still runs on the Tk thread and applies that partial load. `run_bg`
does not take a cancel token: `work` stays a zero-arg callable that closes over
the event. `Future.cancel()`
only drops queued jobs, and skipping `on_done` would throw away the partial
result.

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
off the Tk thread for `_load_all_trees`, `_import_txt`, `_import_drawio`, and
all focus-tree exports. `focus_tree/export_plan.py` owns the plain-data export
plans and sequential worker execution. The Tk shell resolves dialogs and
snapshots its state before submission, then reports results and calls
`MOD.note_file_written` on the Tk thread after each successful atomic write.
`performance.md`'s GIL guidance still applies: threads here buy UI
responsiveness, not parse concurrency, which is why multi-file work processes
files sequentially rather than fanning out across workers.
