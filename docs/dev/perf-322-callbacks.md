# Focus callback lifetime (#322)

Every full card registers 70 Tcl commands. Deleting canvas items does not delete
those commands. Bundles now own the binding IDs and release them when culled,
when changing LOD, on mod reload, on Clear All, and after external canvas deletion.

Run on a private display (Python 3.14, Tk, Xvfb/xauth):

```sh
xvfb-run -a python scripts/bench_canvas_callbacks.py --out callbacks-time.json
xvfb-run -a python scripts/bench_canvas_callbacks.py --memory --out callbacks-memory.json
```

The script accepts `--repo` to compare an unmodified checkout, and uses the existing
AppFake with real Tk. Three fresh roots, each 30 revisits of ten full cards:
base a0c9ac0 retained 21,000 callbacks and ~12.39 MB traced Python memory; the fix
retains zero callbacks. Native Tcl memory is not covered by tracemalloc. The
external cleanup control is retained for comparison, not used by production.
Uninstrumented cycle medians before: 10.37/10.00/9.87 ms; after:
11.33/12.89/9.83 ms. This trades small cleanup cost for bounded lifetime, not a
claimed throughput speedup. No filesystem caching or displayed frame latency is
involved. Test `test_focus_callbacks_released_on_cull_lod_and_external_delete`
asserts actual command counts, not merely bounded canvas item counts.
