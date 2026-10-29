# Issue #331: sidebar-only autosave recovery

## Reproduction

On current `main` at `5b925bc`, apply a focus cost change from `10` to `35`
through `App._apply`, then run the deterministic autosave callback. The value
changes in memory, but both recovery files still contain `10` after the next
and repeated timer ticks. Repeating with a description edit leaves the old
description in both files. The frozen base `6fb6afa` writes each edit to both
files on the next tick.

The cause was that the dirty check and autosave deduplication token both used
the scene revision. Sidebar content edits that leave name and coordinates
unchanged did not advance that revision.

## Regression coverage

`tests/test_workspace_dirty.py::test_autosave_timer_persists_sidebar_cost_and_description_edits`
uses the real `App._apply` and select-away (`App._select` → `_autosave`) paths,
with deterministic timer callbacks and temporary primary and sibling recovery
files. It reads the files back through `read_project` and verifies that:

- cost and description edits reach both files on the next tick;
- edits after marking the workspace clean transition back to dirty;
- geometry revision and name/position index identities remain unchanged;
- repeated unchanged ticks do not rewrite the recovery files.

## Verification

Python 3.14.7, headless environment:

```text
.venv/bin/python -m pytest -q                 1608 passed, 4 skipped, 19 deselected
.venv/bin/ruff check .                        passed
.venv/bin/black --check .                     passed
.venv/bin/mypy                                passed (217 source files)
.venv/bin/pylint src/hoi4cm tests scripts     passed, 10/10
git diff --check                              passed
```

Pylint reports existing warnings in `src/hoi4cm/wizards/character.py` and
`src/hoi4cm/wizards/decision.py`; it also cannot write its cache in this
environment. No interactive desktop or large-mod workflow was run.
