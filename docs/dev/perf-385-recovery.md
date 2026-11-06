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
primary write runs at a time; repeated ticks retain one pending flag. After each
primary success, a separate sibling writer receives those same bytes. While that
writer is busy, only its latest pending snapshot is retained. Primary saves keep
running even if sibling staging or replacement stalls.

The successful primary token retains document identity, content revision, detached
metadata, and targets. Unchanged snapshots skip capture while the primary exists
and the sibling exists or is pending. A partial failure invalidates the token and
retries the complete pair, even after a metadata revert. Primary and sibling
failures still have separate,
deduplicated error reporting. Completion never marks the manual-save state clean.

`WorkspaceFiles.stage_bytes` stages, fsyncs and atomically replaces outside the
generation lock. Manual save, document replacement, declined restore, and clean
shutdown revoke the generation's durable eligibility in a separate local SQLite
store. Invalidation never waits for a destination's staging or final rename.
A rename already inside the OS cannot be cancelled; its late file remains
ineligible to `read_project`/`decode_project`, even after restart or when manually
opening a sibling. Startup skips it quietly. Workers never unlink late output,
avoiding a race with another process's publication. Each destination keeps its
worker slot across invalidation, so newer snapshots for that destination wait
for the old worker, while the other destination can continue.

There is one registry row and at most two accepted tokens: the generation being
written and a previously committed recovery until primary publication succeeds.
Failed initial capture or writing preserves the previous recovery. New snapshots
within a generation reuse one token. A crash preserves eligibility; clean close
intentionally revokes completed as well as pending recovery from that generation.
Metadata is stripped on decode so ordinary manual project saves remain readable
without the registry. Local transactions are serialized independently of
destination I/O; external SQLite contention fails immediately and is reported.
Normal save/close do not claim success if revocation fails. Both destinations
still use identical snapshot bytes. These eligibility changes have not been
included in the latency measurements below.

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
bounded to one owned byte snapshot plus metadata in these measurements. The
independent sibling follow-up can now retain up to three byte snapshots during
an overlapping primary write. That overlap has not been remeasured. Recovery
files were 57.48 MB before and 41.85 MB after; smaller output alone is not
evidence of lower latency.
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
`tests/test_recovery_eligibility.py` additionally blocks final replacement at
either target, verifies prompt invalidation and close, rejects late files in a
fresh process, preserves newer snapshots and prior good recovery on failure,
tests SQLite contention and parallel destinations, and verifies process exit
with a permanently stalled daemon worker.
The existing sidebar persistence and failure-streak regressions use the extracted
worker seam. No pending-sidebar behavior from #365 or import-worker scheduling
from #326 is changed.
