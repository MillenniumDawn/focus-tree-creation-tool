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
| Checklist dialog for "Load All Trees" built one Tk widget row per file before it could show; on ~790 files that's ~5,500 synchronous widget constructions | `hoi4_content_maker.py` (`_load_all_trees`), formerly the inline row loop | Pooled row list over a scrolling canvas: `ui/checklist.py`'s `VirtualChecklist` reuses the `_PooledList` machinery extracted from `VirtualFocusList` (`ui/focus_list.py`), so the dialog builds only the visible rows (~2 dozen) and recycles them as it scrolls | fixed in phase 9 | not yet measured, needs a display session against the real mod |
| Batch load ran a full panel refresh + `_redraw()` + `_fit_all()` per file, N times for N trees, all on the Tk thread | `hoi4_content_maker.py:6490` (`_install_extra_tree`), `_do_load` in `_load_all_trees` | `defer_redraw=True` per file; one refresh + redraw + fit-all after the whole batch | fixed in phase 2 | not yet measured, needs a display session against the real mod |
| Cross-tree `relative_position_id` resolution in `build_focuses` scanned the whole `existing_focuses` list per focus, O(T*F) across a batch load. Import-side twin of the e693a19 export fix | `focus_tree/build.py` (`resolve_abs`) | `existing_by_name` map built once, first-match-wins preserved | fixed in phase 2 | not yet measured, needs a display session against the real mod |
| The single end-of-batch redraw still walks every loaded focus with no viewport culling | `ui/canvas.py:150` (`_do_redraw`) | Viewport culling | fixed in phase 8 (see the viewport-culling row below for what is/isn't fixed) | not yet measured, needs a display session against the real mod |
| Main-tree export and the Code-tab preview resolve each focus's `relative_position_id` parent with `next(foc for foc in self.focuses.values() if foc.name == rel_id)`, an O(F) scan per focus, so O(F^2) overall. This is the same shape of bug e693a19 already fixed in `focus_tree/export.py` (used only for extra shared/joint trees) with a name-to-focus map built once; the fix was never ported to the monolith's own main-tree path | `focus_tree/export.py` (`export_main_tree`, the main-tree path `_export` now delegates to), `hoi4_content_maker.py:3686` (`_build_focus_code`) | Build a `name -> Focus` map once per call, same pattern as `focus_tree/export.py` | fixed in phase 4 | not yet measured, needs a display session against the real mod |
| `_import_txt`/`_import_drawio` parse synchronously on the Tk thread; a large import blocks the UI for the parse duration | `hoi4_content_maker.py:_import_txt`, `hoi4_content_maker.py:_import_drawio` | Move parse (and, for the batch loader, parse+build) off the Tk thread via `ui/tasks.py`'s `run_bg`, marshal the result back via `on_done` | fixed in phase 5 | not yet measured, needs a display session against the real mod |
| GFX interface tree walked 3x per mod scan. The first unified cache still walked all directories and statted every image before accepting a warm hit | `mod/graphics_catalog.py` | One `os.scandir` inventory feeds every sprite map and browser query. The persistent workspace snapshot stores relative paths, directory stamps, `.gfx` file stamps, and the image inventory | fixed | old unification: cold 2128.5ms -> 1051.1ms, warm 1425.3ms -> 78.2ms (66k-file synthetic fixture). The workspace snapshot still needs a real-mod measurement |
| `_scan_files_cached` reads cache-miss files in parallel, then extracts them serially in a follow-up loop | `mod/context.py:341` | Read+extract submitted together per file to one `ThreadPoolExecutor`, so a file's read (GIL released) overlaps another file's extraction; cache put/prune/commit stay on the calling thread since the sqlite connection isn't thread-safe | fixed in phase 6 | not yet measured, needs a display session against the real mod |
| Undo deep-copied every loaded focus (`copy.deepcopy` of the whole `self.focuses` dict) on every `_push_undo`, 60 entries retained (`deque(maxlen=60)`), then `_undo` did `cv.delete("all")` and rebuilt every focus | `hoi4_content_maker.py:1561` (`_push_undo`/`_undo`) | `core/undo.py`'s `UndoStack`: each push snapshots only the focus ids the caller says it's about to mutate/delete (`touched_ids`), plus a `frozenset` of every id at push time so undo can spot and delete ids the action created without ever snapshotting them. The few call sites that touch most of the tree anyway (draw.io import) fall back to one zlib-compressed full snapshot instead of bounding the set. `_undo` now deletes canvas items only for the ids that came back changed/removed and does one `_redraw()`, no more `cv.delete("all")` | fixed in phase 7 | not yet measured, needs a display session against the real mod |
| No canvas viewport culling: `_do_redraw` iterates every loaded `Focus` regardless of what's on screen; loading all trees puts ~329k items on the canvas | `ui/canvas.py` (`_do_redraw`, `_draw_focus`, `_draw_lines`) | Viewport rect computed once per redraw (`ui/viewport.py`'s pure `visible_world_rect`/`focus_visible`/`edge_visible`); offscreen focuses never get canvas items (lazy creation), and an already-drawn focus that pans offscreen gets one `itemconfig(state="hidden")` per redraw instead of a full coord/style recompute | fixed in phase 8 | not yet measured, needs a display session against the real mod |
| A single-focus drag rebuilt every `FocusDocument` index on each snap step (`move()`) and did a full `SceneIndex` rebuild (all edges rasterized) on each throttled line-redraw frame, O(F+E) per drag frame | `models/document.py` (`move`), `ui/scene_index.py` (`rebuild`/`update_focus`), `ui/canvas.py` (`_do_draw_lines_throttled`) | `move()` patches only `occupied_positions`; `SceneIndex.update_focus` patches the moved focus's cell and re-rasterizes only its incident edges; the drag line-redraw calls `update_focus` instead of `ensure`'s full rebuild | fixed | synthetic 2000-focus / 2860-edge tree (Python 3.14): drag-snap step (`move` + scene) median 7.8-8.3ms -> 0.029ms, p95 12-14ms -> 0.05ms, max up to 21ms -> 0.1ms. See the drag-snap note below |
| Every wizard file write rebuilt the whole graphics state: image/gfx list copies, two full goal/idea `_is_under` passes, a full `_derive_references`, a 64k-entry `_image_stamps` rebuild, a whole-snapshot SQLite store, and a flush of the decoded-image LRU | `mod/graphics_catalog.py` (`note_written`/`note_deleted`), `mod/context.py` (`_apply_graphics_maps`) | `note_written`/`note_deleted` patch `PathReference`-keyed dicts in place, re-derive only the affected sprite-map entries (per-file declaration diffs plus disk-derived claims), defer the SQLite store to the next refresh or shutdown, and evict only the changed names from the decoded-image LRU | fixed in issue #29 | 50k-image synthetic tree (Python 3.14): in-place image overwrite 1609ms -> 0.07ms, new image 1607ms -> 0.06ms, `.gfx` append+write 1324ms -> 0.84ms, image delete 3216ms -> 77ms. A reload after writes now pays the deferred store once (~0.7s) instead of once per write |

The `_draw_key`/state-key check in `_draw_focus` (`ui/canvas.py:486`) already
makes an unchanged focus close to free to redraw, but every `_redraw()` call
still iterates the full focus dict to find that out. That per-redraw
**iteration** is still O(total loaded focuses) after phase 8 — culling
changes the *cost per offscreen focus* (a bbox check instead of ~14
create/coords/itemconfig calls), not the loop count. What actually caps
memory on a huge load is **item count**: before phase 8 every loaded focus
had 14 canvas items whether on screen or not (776 focuses = ~10.9k items,
23,524 focuses = ~329k items, which Tk cannot handle); after phase 8 a
focus that has never been on screen has zero items, so item count scales
with what's visible, not with what's loaded. That cap doesn't apply at
fit-all zoom on a huge load, since fit-all sizes the zoom so every focus is
simultaneously in-viewport — culling has nothing to cull there, and the
329k-item case at fit-all is unchanged. It's normal (zoomed-in) work on a
huge load — the common case, and the one that used to allocate all 329k
items up front regardless of zoom — that phase 8 fixes. Minimap dots/edges
are pooled the same way `_draw_lines`' line pool already was (reuse +
hide-surplus instead of delete-and-recreate every call), and above 2,000
focuses the minimap buckets to one dot per occupied pixel cell and skips
prereq lines, since individual dots/edges aren't legible at that density
anyway. A low-zoom level-of-detail pass (one pooled rectangle per focus
below some zoom threshold, instead of the full multi-item card) was
scoped for phase 8 but not implemented — noted here as future work, since
lazy item creation already removes the up-front item explosion for the
zoomed-in case, which was the more common one.

### Drag-snap step

Dragging one focus is the interactive hot path: `_foc_mv` calls
`FocusDocument.move()` on every grid cell crossed, and the throttled line
redraw (`_do_draw_lines_throttled`, ~60fps) has to reflect the new position.
Both used to be O(F+E): `move()` did a full index rebuild, and the redraw did
a full `SceneIndex.rebuild`. Two changes make the update cost independent of
the whole tree size: `move()` only x/y touches `occupied_positions`, so it
patches that one index instead of rebuilding all seven; and
`SceneIndex.update_focus` moves just the dragged focus between cells and
re-rasterizes only its incident edges. The resulting work is O(1 + focus
degree), not O(F+E).

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
interleaving with I/O waits. The phase 5 fix for import-blocking-the-UI
(`ui/tasks.py`'s `run_bg`) moves work off the Tk thread for responsiveness,
not to parallelize the parse itself: `_load_all_trees`' batch loader parses
and builds each file's focuses sequentially on one worker thread, not
fanned out across the pool, since later files' cross-tree relative
positions/prerequisites need to resolve against earlier files' newly-built
focuses, and parallelizing pure-Python parsing wouldn't help anyway per the
GIL point above.

Multiprocessing was considered and rejected: pickling `MOD` and parsed
focus trees across process boundaries costs more than the parse itself at
this scale, PyInstaller-frozen builds have their own multiprocessing
quirks per platform, and `MOD` is a shared singleton that every wizard
reads from. Splitting it across processes would need a much bigger
redesign than the performance problem justifies.

### Cross-step scan parallelism: considered and skipped

Phase 5 also asked whether the mod scan's steps (per-domain extraction,
GFX indexing, cache read/write) could overlap across steps, not just within
a step's file loop. Decided against it, for now:

- `ScanCache` opens its SQLite connection inside `scan()` and that
  connection is thread-affine; handing it to more than one worker thread
  would need its own lock or a connection-per-thread scheme.
- The extract functions are pure Python and GIL-bound (same reasoning as
  above), so running two of them concurrently on separate threads doesn't
  buy real parallelism, only interleaving.
- Read/extract overlap *within* a step already exists (phase 6): the
  cache-miss read and its extraction are submitted together per file, so
  I/O waits on one file already overlap another file's extraction.
- The dominant cold-scan cost was fixed algorithmically in phase 6 (the
  unified GFX walk and the read+extract pairing above), not by adding more
  concurrency.

If this is ever revisited, the right shape is a single `ScanCache`
connection serialized behind a lock, not one connection per thread: the
cache is small and fast enough that lock contention wouldn't be the
bottleneck, and it avoids SQLite's own cross-connection consistency
concerns on a single file.

## Cache inventory

| Cache | Scope | Keyed by | Eviction |
|---|---|---|---|
| `WorkspaceCache` graphics snapshot (SQLite, `~/.hoi4cm/scan_cache/<hash>.db`) | relative graphics inventory, sprite declarations, and configured focus/idea views | root identity, graphics path fingerprint, directory `mtime_ns`/`ctime_ns`, `.gfx` file stamps, and image stamps | one snapshot per graphics path configuration; detected stale rows rebuild. A warm load restats the known images, so an in-place image overwrite (same filename) is caught without an explicit refresh |
| `ScanCache` (same SQLite database) | per-file scan contribution, per domain | `(mtime, size)` | none, though `prune()` drops rows for paths no longer in the mod (no size/age cap) |
| Canvas `ImageBroker` | one application session | normalized path, file stamp, transform, and catalog generation for zero-stamp assets | bounded LRU; visible renderer bundles own bounded pins and offscreen bundles release them |
| Browser `ImageBroker` | one browser dialog | normalized path, file stamp, transform, and catalog generation for zero-stamp assets | bounded LRU; the virtual thumbnail grid pins only visible rows plus overscan |

Warm graphics loads stat known directories, `.gfx` files, and the known image
paths. They do not recursively enumerate directories or reparse `.gfx` files.
Statting the known images is what catches an in-place overwrite (the directory
mtime doesn't move when a file's content changes), and it's far cheaper than a
full rescan. `ScanCache.prune`'s stale-path removal remains its only eviction.
The image brokers bound decoded Tk images and visible pins independently.

Wizard writes are not re-stored per file: `note_written`/`note_deleted` patch
the in-memory snapshot (dicts keyed by `PathReference`) and mark it dirty; the
SQLite store runs at the next refresh or at shutdown (`flush_cache`), so a
wizard save that writes an image plus a `.gfx` entry pays nothing per file and
the decoded-image LRU is evicted per changed sprite name, not wholesale.
