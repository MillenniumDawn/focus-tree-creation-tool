# Changed recovery callbacks (#385)

Recovery now stages and writes files off Tk from one immutable UTF-8 snapshot.
This reduces blocking, but does not remove the snapshot pause. On the workload
below, the two-destination callback median fell from 322.11 to 255.27 ms and the
median maximum Tk timer interval fell from 326.91 to 261.93 ms. These are timer
measurements on an isolated display, not presented-frame latency.

## Ownership and ordering

`ui/recovery.py` owns the App's recovery controller. It captures compact project
JSON and encodes UTF-8 on Tk, then sends only immutable bytes, paths, and a commit
generation to the worker. The worker never reads live focuses or widgets. One
snapshot runs at a time; repeated ticks retain one pending flag, not a queue of
snapshots. A follow-up captures the latest state only after the worker finishes.

The successful token retains document identity, content revision, detached
metadata, and targets. Unchanged successful pairs skip capture while both files
exist. A partial failure invalidates the token and retries the complete pair,
even after a metadata revert. Primary and sibling failures still have separate,
deduplicated error reporting. Completion never marks the manual-save state clean.

`WorkspaceFiles.stage_bytes` stages and fsyncs outside the commit gate. Only the
final replacement is guarded. Manual save, document replacement, declined
restore, and shutdown advance the gate before clearing or abandoning recovery
state. An older staged write cannot replace a cleared file afterward. This avoids
waiting for a worker's fsync on Tk when invalidating it. Each destination retains
atomic replacement and both successful destinations use the same bytes.

## Workload and results

Linux, CPython 3.14.4, private Xvfb, baseline `0d7ef48`. The fixture was the clean
`common/national_focus` directory from Millennium Dawn commit
`7895d78153fdeb147a8dcc2ff3137f7a998783f1`: 115 files, 112 accepted, 26,368 focuses.
Every accepted tree was loaded as an extra tree for a model-scale workload, not
the default Shared + Joint selection. Project paths were relative in tree
metadata. The same prebuilt model was used for five changed single-destination
saves, then five changed pairs. GC ran normally, with a collection before each
sample; filesystem caches were not flushed. No coverage or concurrent validators
ran during timing.

The controlled comparison writes to Linux `/tmp` (tmpfs) to separate CPU and
callback effects from storage stalls. It still executes staging, fsync, and
replacement, but does not measure durable-disk throughput. Total completion is
observed by a five-millisecond Tk poll. Callback time includes dirty checks,
metadata capture, snapshot encoding, submission, and timer rescheduling.

| Metric, median across five samples | Baseline, one file | Patched, one file | Baseline, pair | Patched, pair |
| --- | ---: | ---: | ---: | ---: |
| Complete Tk callback, ms | 289.33 | 256.03 | 322.11 | 255.27 |
| Callback start to completion, ms | 289.41 | 271.38 | 322.12 | 281.79 |
| Metadata capture, ms | 0.67 | 0.67 | 0.65 | 0.74 |
| Snapshot encoding, ms | 247.56 | 252.76 | 245.54 | 251.64 |
| Destination write phase, ms | 35.48 | 11.48 | 71.00 | 22.84 |
| Tk interval p95, ms | 5.20 | 5.23 | 5.22 | 5.20 |
| Maximum Tk interval per sample, ms | 294.29 | 262.56 | 326.91 | 261.93 |

Dirty checks were below 0.01 ms in both arms. The baseline write phase includes
UTF-8 encoding on Tk; the patched snapshot phase includes that encoding, while
its writes run off-thread. Intervals include the requested five milliseconds.
The largest observed interval across the pair samples was 338.86 ms before and
266.78 ms after. Snapshot encoding remains about 250 ms and is not claimed faster.

Separate tracemalloc samples peaked at 201.08 MB before and 211.69 MB after,
a 5.3% increase in traced Python allocations, not process RSS. The pipeline is
bounded to one owned byte snapshot plus metadata. Recovery files were 57.48 MB
before and 41.85 MB after; smaller output alone is not evidence of lower latency.
Every sample checked decoded project equality and identical primary/sibling bytes.

Earlier backing-disk runs had multi-second write outliers in both arms, including
a 34.87-second synchronous baseline callback. Those runs are not used to claim a
throughput improvement. An initial detached-object worker design was also
rejected: its copy kept blocking Tk for roughly 400–570 ms and raised traced peak
allocations to about 249.5 MB. Keeping an immutable byte snapshot avoids that
copy and avoids a second large UTF-8 conversion in the worker.

## Reproduction

Run the probe from the patched checkout against both code revisions, using the
same fixture and filesystem for outputs. Invoke it as a file so `--repo` selects
all imports from the intended checkout.

```sh
xvfb-run -a python src/hoi4cm/perf/recovery_callback.py \
  --repo /path/to/baseline --focus-dir /path/to/MD/common/national_focus \
  --out /tmp/recovery-before
xvfb-run -a python src/hoi4cm/perf/recovery_callback.py \
  --focus-dir /path/to/MD/common/national_focus --out /tmp/recovery-after
```

The probe records all samples in `measurements.json` and isolates its home under
the output directory. `tests/test_background_recovery.py` covers ownership,
bounded follow-ups, complete-pair retries, manual save, replacement documents,
restore dismissal, shutdown, and cancellation during staging of either target.
The existing sidebar persistence and failure-streak regressions use the extracted
worker seam. No pending-sidebar behavior from #365 or import-worker scheduling
from #326 is changed.
