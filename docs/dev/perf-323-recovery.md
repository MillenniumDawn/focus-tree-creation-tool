# Recovery serialization (#323)

`AutosaveWriter` serializes a changed workspace once for both atomic recovery
writes. It skips an unchanged pair only when document identity, revision,
deep-copied non-focus metadata and targets match the last successful pair and
both files still exist. Any attempted write invalidates the previous token,
including partial failure followed by a metadata revert. It retains metadata,
not a second full focus snapshot. Main and sibling error behavior is unchanged.

This deliberately keeps serialization on the Tk thread. A first changed recovery
still stalls; workers would require an owned immutable snapshot and coordinated
manual-save/close/restore lifecycle. Revision tracking remains the mutation
contract, as for the existing scene index and dirty indicator.

Reproduce on baseline and branch using the same script:

```sh
python scripts/bench_focus_recovery.py --repo /path/to/checkout \
  --focus-dir /path/to/Millennium-Dawn/common/national_focus --out /tmp/recovery
pytest tests/test_autosave_writer.py tests/test_workspace_dirty.py
```

Public fixture revision `bcbf8ed2ef59ad58068feecaea68bff1c06c2552`, 114 files,
111 accepted, 26,245 focuses. Five uninstrumented samples: changed recovery pair
median 778.59 -> 487.57 ms; unchanged 737.67 -> 0.72 ms. Both files equal the
encoded workspace. Separate tracemalloc peak 120.48 -> 120.47 MB: no meaningful
peak-memory reduction. Fresh import before the timed warm application-state
operations; filesystem caches uncontrolled and not flushed. These numbers measure
writer throughput, not independent Tk timer latency. The benchmark uses a prebuilt
workspace and excludes App dirty checks, workspace capture, timer scheduling and
dialogs; these are not full `_autosave_tick` durations. Input/output JSON paths are relative
to avoid intentional project path sanitization changing the comparison.
