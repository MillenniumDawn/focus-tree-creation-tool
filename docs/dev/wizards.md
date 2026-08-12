# Wizards

`src/hoi4cm/wizards/` holds the five modal builder dialogs, each a single
`open_*_wizard(app)` entry point re-exported from `wizards/__init__.py`.

| Wizard | Entry point | Lines | Purpose |
|---|---|---|---|
| Decision | `open_decision_wizard(app)` | 4,958 | Build a decision or decision category |
| Event | `open_event_wizard(app)` | 2,849 | Build a HOI4 event |
| National Spirit | `open_national_spirit_wizard(app)` | 2,113 | Build a national spirit / idea |
| Dynamic Modifier | `open_dyn_mod_wizard(app)` | 1,662 | Build a dynamic modifier |
| Additional Income | `open_additional_income_wizard(app)` | 582 | Build an MD additional-income entry |

Event dropped from its original 3,445 lines when `_open_effect_picker`
moved into `_shared.py` as `open_effect_picker` (issue #45) — decision.py
had no picker of its own (the bug: its button called a name that was never
defined anywhere), so it now imports the shared one instead of growing a
second copy.

## `_shared.py`

State that used to be plain module-level globals in the monolith's
Tk-handling block, plus one popup shared across wizards:

- `_app_img_caches`: a registry list every wizard appends its own image
  caches to, so the App can clear all of them in one place on mod reload
  instead of reaching into each wizard module individually.
- `_ev_gfx_cache` / `_ev_imgsize_cache`: the event wizard's gfx-name to
  path and path to (width, height) caches, registered into
  `_app_img_caches` at import time.
- `_LOC_KEY_RE`: a pre-compiled regex the additional-income wizard uses to
  pull a localisation key out of a quoted HOI4 string.
- `open_effect_picker(parent, target_text, on_insert=None)`: the popup
  effect selector, extracted verbatim from the event wizard's own
  `_open_effect_picker` (issue #45) and parameterized so the decision
  wizard can call it too. Renders a snippet into `target_text`; `on_insert`
  is an optional no-arg callback fired after a successful insert (the event
  wizard passes its `_schedule_preview`, decision passes nothing).

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

## The generators module

`_generators.py` holds the script/loc renderers that used to live inside
the `open_*_wizard` closures. Each wizard now resolves only its Tk-widget
knobs (StringVar/Text reads) and delegates to a module-level pure function
there, so the rendering logic is testable headlessly (see `testing.md`):

- event: `render_event_txt`, `generate_events_txt`, `generate_event_loc_yml`,
  `build_event_scripted_loc_blocks`
- decision: `generate_decision_block`, `generate_decisions_file`,
  `generate_decision_categories_file`, `generate_decision_scripted_loc`,
  `generate_decision_loc_yml`
- national spirit: `build_national_spirit_output`
- dynamic modifier: `parse_dyn_mod_lines`, `build_dyn_mod_output`
- additional income: `build_income_spirit_snippet`

These are the extraction target the original "Tests are still owed" note
pointed at. They have dedicated headless tests under
`tests/test_wizard_generators_*.py`, and CI enforces a 95% floor on
`hoi4cm.wizards._generators` (see `pyproject.toml`'s `[tool.coverage]` and
`.github/workflows/ci.yml`). New script/loc generation should go into
`_generators.py` with a test, not back into the closures.

Each generator carries a golden test that asserts the whole rendered block,
not just that a field appears somewhere in it. Field order is load-bearing
in a few places (`icon` sits between `allowed` and `visible`; the blank
line before an event's `immediate` block matches the MD file convention),
and substring assertions can't see any of it. Add fields to the golden when
you add them to a generator.

Tests are still owed for the rest of the wizard logic (id/name validation,
gfx lookups, dialog state wiring). Those are Tk-coupled: testing them means
exercising the non-Tk logic separately from the dialog construction itself.
The script/loc generators, which carry the loc-export and mod-file writing
risk the extraction was meant to de-risk, are now covered.
