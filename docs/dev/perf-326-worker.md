# Import worker responsiveness investigation (#326)

No production scheduling or GC change is included. The real batch importer is
already threaded. In three private-Xvfb runs over 114 public MD files (26,245
focuses), a 5 ms Tk timer had maximum intervals 205.6/213.1/225.9 ms and p95
31.4/30.3/31.1 ms. Process-wide GC callbacks overlapped 186.1/193.5/209.7 ms of
the longest intervals; the longest individual collection was 182.9/188.6/209.2 ms.
Imports took 5.11/4.92/5.20 seconds.

A separate diagnostic process disabling cyclic GC during the batch reduced max
timer intervals to 49.5/38.7/42.4 ms and imports to 4.43/4.18/4.57 s. P95 remained
31.1/28.9/31.4 ms. This implicates collection in the worst pauses while leaving
ordinary Python thread contention unresolved. Disabling process-wide GC in the
application risks memory retention and simply moving collection pauses elsewhere;
that is not a safe narrowly justified production fix. No process-worker rewrite
or speculative yielding patch is included. Peak memory of this GC control was
not measured, and pause overlap alone does not isolate every scheduler effect.

```sh
DISPLAY=:99 python scripts/bench_focus_worker.py \
  --focus-dir /path/to/Millennium-Dawn/common/national_focus --out /tmp/worker.json
# Diagnostic only, separate process:
DISPLAY=:99 python scripts/bench_focus_worker.py --disable-gc \
  --focus-dir /path/to/Millennium-Dawn/common/national_focus --out /tmp/worker-control.json
```

Use a private Xvfb server. New models each sample; filesystem caches are
uncontrolled, normally warm from prior runs. Raw timer and GC start/end timestamps
and thread IDs are saved. The three rejected files are the same baseline empty or
non-focus fixtures (`00_titlebar_styles.txt`, `05_aln.txt`, `05_zombies.txt`).

The harness runs `batch_load_trees` in one worker while the main thread services
only the timer. It excludes application progress rendering, model installation,
GFX decoding and presented-frame latency. Normal and diagnostic controls are
separate processes, not randomized paired trials.
