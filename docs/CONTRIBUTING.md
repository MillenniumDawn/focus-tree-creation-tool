# Contributing to HOI4 Content Maker

Thank you for your interest in contributing. This document covers how to report bugs, suggest features, and (if you have permission) submit code changes.

---

## Reporting Bugs

Please open a GitHub Issue with the following information:

1. **Python version** — `python --version`
2. **Operating system** — Windows / macOS / Linux + version
3. **What you did** — step-by-step reproduction steps
4. **What happened** — the actual behaviour (include the full traceback if there is one)
5. **What you expected** — the intended behaviour

If there is a traceback printed to the console, please paste the **full** traceback — partial tracebacks are hard to debug.

### Console output

The easiest way to capture tracebacks is to run the app from a terminal rather than double-clicking:

```bash
python hoi4_content_maker.py
```

Any exception tracebacks will appear in that terminal window.

---

## Suggesting Features

Open a GitHub Issue with the label **enhancement**. Please include:

- A clear description of what you want
- Why it would be useful (what mod workflow does it improve?)
- Any examples from HOI4's wiki or existing mods

---

## Code Style

If you have been granted permission to submit code:

- **Python 3.9+ compatible** — no walrus operator (`:=`) or match/case statements; the app targets 3.9–3.14.
- **Single file** — all application code lives in `hoi4_content_maker.py`. Do not split into modules.
- **tkinter only** — no additional GUI frameworks. Third-party packages are limited to optional image support (`Pillow`, `pillow-dds`).
- **Defensive field access** — always use the `_s()` helper (or `.get("key", "")`) when reading cat/dec fields in generator functions. Fields can be `bool`, `None`, or `str` depending on how they were set.
- **No forward references** — Python 3.14 is strict about closures. Always define functions before referencing them, or wrap deferred calls in `try/except`.
- **Autosave after changes** — any function that modifies `dm_cats` or `dm_decs` should call `_autosave()` and `_snapshot()` at appropriate points.

### Naming conventions

| Pattern | Use |
|---|---|
| `_build_*` | Functions that create/rebuild a UI panel |
| `_rebuild_*` | Functions that destroy and recreate a UI section |
| `_gen_*` | Functions that return a generated string (Paradox script or YAML) |
| `_collect()` | Save current editor form fields back to the data model |
| `_snapshot()` | Push current state onto the undo stack |
| `_s(v)` | Safe string coercion for generator output |
| `C_*` | Colour constants |
| `MOD` | Global `ModContext` instance |

---

## Licence Note

This project is **proprietary**. Submitting a contribution (pull request, patch, or otherwise) is taken as agreement that you grant the author (Blazer) full rights to use, modify, and distribute your contribution under the existing proprietary licence, with no obligation to credit contributors separately.

If you are not comfortable with these terms, please limit your participation to opening Issues.

---

## Contact

For questions not suited to a public Issue: **ThatGuyBlazer@gmail.com**
