# Architecture

## Package map

`src/hoi4cm/`, one bullet per subpackage:

- **`core/`**: logging, config, paths, i18n, image gating, path/XML
  sanitizing. Re-exported flat through `core/__init__.py` (the "facade",
  see below). Everything else in the package can depend on `core`; `core`
  depends on nothing else in `hoi4cm`.
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
  (`Tooltip`, `_safe_after`).

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

## Threading model (stub, expanded in phase 5)

Today only two things run off the Tk main thread: the mod scan
(`ui/mod_loading.py`, a daemon `threading.Thread` running `MOD.scan`) and
image loads that go through the same worker. Both marshal results back to
the Tk thread via `_safe_after`/`_safe_after_idle` (`ui/widgets.py`), which
guard against scheduling a callback on a destroyed widget. Nothing else in
`hoi4cm` is thread-aware: parsing, building, and export all run
synchronously on whichever thread calls them (currently always the Tk
thread). Import parsing moving off the Tk thread, and the concurrency
rules for it, are `performance.md`'s phase 5 item, not implemented yet.
