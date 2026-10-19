# Optional scene fingerprints (#325)

Normal scene rebuilds trust the document revision and no longer allocate a full
nested focus signature. Validation rebuilds retain a signature. Enabling validation
later forces a rebuild before establishing its baseline, so direct untracked edits
cannot be hidden by capturing the already-changed document as an initial signature.

Run `pytest --no-tk tests/test_scene_index.py`; the new regression counts signature
calls and checks late enablement after an untracked position mutation. The shared
`scripts/bench_focus_recovery.py` benchmark records rebuild timings: five samples
on 26,245 public MD focuses, median 163.83 -> 122.90 ms. Initial investigation's
seven paired signature-suppression controls compared geometry indexes exactly.
The validation toggle remains available for detecting missing mutation tracking;
no extra such detection is promised when validation is disabled.
