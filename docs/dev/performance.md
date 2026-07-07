# Performance

## Scale targets

The reference mod is Millennium Dawn: ~790 `.txt` files scanned under
`common/national_focus`, 1.05M total lines across them, the largest single
tree (`usa.txt`) at 40,790 lines / 776 focus blocks, 23,524 focus blocks
across all trees, and ~64k GFX image files under `gfx/`. Anything added
here should be checked against this scale, not a small test mod: a fix
that helps a 50-focus tree and does nothing for a 23,524-focus load is not
the target.

## Hot-path ledger

| Finding | Location | Fix | Status | Measured delta |
|---|---|---|---|---|
| Checklist dialog for "Load All Trees" builds one Tk widget row per file before it can show; on ~790 files that's ~790 synchronous widget constructions | `hoi4_content_maker.py:6856` (`_load_all_trees`) | Virtualize the row list or paginate | identified, unscheduled | TBD |
| Batch load ran a full panel refresh + `_redraw()` + `_fit_all()` per file, N times for N trees, all on the Tk thread | `hoi4_content_maker.py:6490` (`_install_extra_tree`), `_do_load` in `_load_all_trees` | `defer_redraw=True` per file; one refresh + redraw + fit-all after the whole batch | fixed in phase 2 | TBD |
| Cross-tree `relative_position_id` resolution in `build_focuses` scanned the whole `existing_focuses` list per focus, O(T*F) across a batch load. Import-side twin of the e693a19 export fix | `focus_tree/build.py` (`resolve_abs`) | `existing_by_name` map built once, first-match-wins preserved | fixed in phase 2 | TBD |
| The single end-of-batch redraw still walks every loaded focus with no viewport culling | `ui/canvas.py:150` (`_do_redraw`) | Viewport culling | tied to phase 8 | TBD |
| Main-tree export and the Code-tab preview resolve each focus's `relative_position_id` parent with `next(foc for foc in self.focuses.values() if foc.name == rel_id)`, an O(F) scan per focus, so O(F^2) overall. This is the same shape of bug e693a19 already fixed in `focus_tree/export.py` (used only for extra shared/joint trees) with a name-to-focus map built once; the fix was never ported to the monolith's own main-tree path | `focus_tree/export.py` (`export_main_tree`, the main-tree path `_export` now delegates to), `hoi4_content_maker.py:3686` (`_build_focus_code`) | Build a `name -> Focus` map once per call, same pattern as `focus_tree/export.py` | fixed in phase 4 | TBD |
| `_import_txt`/`_import_drawio` parse synchronously on the Tk thread; a large import blocks the UI for the parse duration | `hoi4_content_maker.py:5774`, `hoi4_content_maker.py:4948` | Move parse off the Tk thread, marshal the result back via `_safe_after` | identified, fix planned in phase 5 | TBD |
| GFX interface tree walked 3x per mod scan (`_scan_gfx` and `_scan_idea_gfx` each call `_scan_interface_gfx`, a top-level `os.listdir` over `interface/`; `_scan_decision_gfx` does its own recursive `os.walk`). Only the decision walk is cached | `mod/context.py:552` (`_scan_gfx_unified`) | One recursive `interface/` walk (`_index_interface_gfx`) and one `gfx/` walk feed all three dicts (`_derive_sprites`, `_derive_idea_sprites_core`, `_derive_decision_sprites`); same merge order/precedence as the three original scanners, pinned down by a characterization test before the rewrite | fixed in phase 6 | TBD |
| `_scan_files_cached` reads cache-miss files in parallel, then extracts them serially in a follow-up loop | `mod/context.py:341` | Read+extract submitted together per file to one `ThreadPoolExecutor`, so a file's read (GIL released) overlaps another file's extraction; cache put/prune/commit stay on the calling thread since the sqlite connection isn't thread-safe | fixed in phase 6 | TBD |
| Undo deep-copies every loaded focus (`copy.deepcopy` of the whole `self.focuses` dict) on every `_push_undo`, 60 entries retained (`deque(maxlen=60)`) | `hoi4_content_maker.py:1547` (`_snapshot`), `hoi4_content_maker.py:380` (`_undo_max`) | Redesign around per-edit diffs instead of full snapshots | identified, fix planned in phase 7 | TBD |
| No canvas viewport culling: `_do_redraw` iterates every loaded `Focus` regardless of what's on screen; loading all trees puts ~329k items on the canvas | `ui/canvas.py:150`, noted in a comment at `ui/canvas.py:443` explaining the `_draw_key` cache is what keeps this affordable today | Add viewport-based culling on top of the existing `_draw_key` skip-if-unchanged cache | identified, fix planned in phase 8 | TBD |

The `_draw_key`/state-key check in `_draw_focus` (`ui/canvas.py:486`) already
makes an unchanged focus close to free to redraw, but every `_redraw()` call
still iterates the full focus dict to find that out. The cost is O(total
loaded focuses), not O(what changed).

## GIL guidance

Threads in this codebase buy UI responsiveness and I/O overlap, not
parse concurrency. `read_file` releases the GIL during actual disk access
(`hoi4cm/core/paths.py`), so `_scan_files_cached`'s thread pool
(`min(8, cpu_count, len(paths))` workers) genuinely speeds up a cold scan.
Since phase 6, that pool runs each cache-miss file's read *and* extract
together, not read-all-then-extract-all: while one file is blocked on disk
I/O with the GIL released, another file's extraction can run. That's an
overlap win between files, not parse concurrency within one file. Parsing
itself is still pure Python (tokenizing, building `ParsedFocusTree`,
walking dict trees) and does not release the GIL, so N threads all doing
extraction at once still serializes on the GIL; the win is entirely from
interleaving with I/O waits. The identified fix for import-blocking-the-UI
(phase 5) is to move work off the Tk thread for responsiveness, not to
parallelize the parse itself.

Multiprocessing was considered and rejected: pickling `MOD` and parsed
focus trees across process boundaries costs more than the parse itself at
this scale, PyInstaller-frozen builds have their own multiprocessing
quirks per platform, and `MOD` is a shared singleton that every wizard
reads from. Splitting it across processes would need a much bigger
redesign than the performance problem justifies.

## Cache inventory

| Cache | Scope | Keyed by | Eviction |
|---|---|---|---|
| `ScanCache` (SQLite, `~/.hoi4cm/scan_cache/<hash>.db`) | per-file scan contribution, per domain | `(mtime, size)` | none, though `prune()` drops rows for paths no longer in the mod (no size/age cap) |
| `.hoi4cm_gfx_cache.json` (sidecar in the mod root) | unified GFX index: `sprites`, `idea_sprites`, and `decision_sprites` together (since phase 6, was decision-only before); schema-versioned (`"version"` key) so an old sidecar is discarded instead of misread | `interface/` directory mtime, recursive (within 2s) | none |
| `MOD.sprite_imgs` (in-memory `PhotoImage` cache) | one process's lifetime | gfx name | none, unbounded, and memoizes `None` on load failure so a failed load is never retried |
| GFX browser `_st["img_cache"]` (`ui/gfx_browser.py:280`) | one browser dialog's lifetime | file path | none, unbounded, cleared only when the dialog closes |

No cache here has an eviction policy today beyond `ScanCache.prune`'s
stale-path removal. Bounding the two unbounded in-memory caches is a phase
8 item, alongside viewport culling.
