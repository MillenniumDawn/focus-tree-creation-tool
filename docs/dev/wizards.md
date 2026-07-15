# Wizards

`src/hoi4cm/wizards/` holds the five modal builder dialogs, each a single
`open_*_wizard(app)` entry point re-exported from `wizards/__init__.py`.

| Wizard | Entry point | Lines | Purpose |
|---|---|---|---|
| Decision | `open_decision_wizard(app)` | 5,405 | Build a decision or decision category |
| Event | `open_event_wizard(app)` | 3,445 | Build a HOI4 event |
| National Spirit | `open_national_spirit_wizard(app)` | 2,113 | Build a national spirit / idea |
| Dynamic Modifier | `open_dyn_mod_wizard(app)` | 1,662 | Build a dynamic modifier |
| Additional Income | `open_additional_income_wizard(app)` | 582 | Build an MD additional-income entry |

## `_shared.py`

31 lines holding state that used to be plain module-level globals in the
monolith's Tk-handling block:

- `_app_img_caches`: a registry list every wizard appends its own image
  caches to, so the App can clear all of them in one place on mod reload
  instead of reaching into each wizard module individually.
- `_ev_gfx_cache` / `_ev_imgsize_cache`: the event wizard's gfx-name to
  path and path to (width, height) caches, registered into
  `_app_img_caches` at import time.
- `_LOC_KEY_RE`: a pre-compiled regex the additional-income wizard uses to
  pull a localisation key out of a quoted HOI4 string.

Pulling these into one module keeps the wizards free of cross-wizard
coupling (no wizard imports another wizard's globals directly) while still
giving the App a single invalidation point.

## Verbatim-extraction convention

All five wizard files open with the same header instead of a module
docstring-first convention:

```python
# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.
```

These were lifted out of the monolith as-is (#14) to get them into
`src/hoi4cm/` without a rewrite blocking the extraction. The `noqa` covers
the specific lint categories the monolith's style trips (line length,
possibly-undefined names from forward references, old-style `%`
formatting, ambiguous single-letter names, loop-variable and mutable-default
lint, late-binding closures, and non-cryptographic random use) so ruff
still runs clean on the file without a style pass first.

Tests are still owed. None of the five wizard modules have coverage today
(see `testing.md`'s headless constraint): extracting a wizard did not come
with a test, unlike the pure modules in `focus_tree/`, `models/`, and
`core/`. Adding coverage means testing the non-Tk logic inside each wizard
(id/name validation, gfx lookups, dict-to-script conversion) separately
from the dialog construction itself, since the dialog construction can't
run in CI.
