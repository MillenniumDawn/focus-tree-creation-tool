# Developer docs

Dev docs, terse, rationale first. These describe the `hoi4cm` package and
the migration off the monolith, for anyone extending or auditing the code.
Not user-facing (see the repo root `README.md`/`BUILD_INSTRUCTIONS.md` for
that).

- **[architecture.md](architecture.md)**: package map, dataflow, the core
  facade convention, module-level singletons, threading model.
- **[monolith-migration.md](monolith-migration.md)**: the extraction story
  so far, the wiring convention, the migration status table, the extraction
  recipe, what's still deferred and why.
- **[performance.md](performance.md)**: scale targets, the hot-path ledger,
  GIL guidance, cache inventory.
- **[testing.md](testing.md)**: fixture/isolation patterns, the headless
  constraint, manual verification checklist.
- **[wizards.md](wizards.md)**: the five wizard modules, `_shared.py`
  caches, the verbatim-extraction convention.

Maintenance rule: any PR that changes architecture, hot paths, or migration
status updates the matching doc in the same PR.
