#!/usr/bin/env python3
"""Real Tk canvas-culling callback retention probe. Run only on private Xvfb.
Example: xvfb-run -a python scripts/bench_canvas_callbacks.py --out raw.json
--memory runs tracemalloc separately; timing without it is the throughput pass.
No production source changes. Cleanup control deletes only newly registered
callback commands once their focus bundles have been reclaimed.
"""

# pylint: disable=wrong-import-position

import argparse
import gc
import json
import os
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
parser.add_argument("--out", required=True)
parser.add_argument("--memory", action="store_true")
parser.add_argument("--rounds", type=int, default=30)
parser.add_argument("--focuses", type=int, default=10)
parser.add_argument("--repeats", type=int, default=3)
args = parser.parse_args()
if not os.environ.get("DISPLAY"):
    raise SystemExit("Requires explicitly supplied private Xvfb DISPLAY")
sys.path[:0] = [args.repo + "/src", args.repo + "/tests"]
import tkinter as tk  # noqa: E402

from ui_fakes import AppFake  # noqa: E402  (runtime: tests/ on sys.path above)

from hoi4cm.models import Focus  # noqa: E402


def rss_bytes():
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def tcl_commands(cv: tk.Canvas) -> set[str]:
    """tk.Canvas._tclCommands is a private Tk attribute (not in stubs)."""
    return set(getattr(cv, "_tclCommands", None) or ())


def run(cleanup):
    root = tk.Tk()
    root.withdraw()
    cv = tk.Canvas(root, width=1200, height=800)
    focuses = [Focus(id=i + 1, x=i, y=1) for i in range(args.focuses)]
    for i, focus in enumerate(focuses):
        focus.name = f"TEST_{i}"
    app = AppFake(focuses, cv=cv)
    rect = (-1, -1, args.focuses + 1, 3)
    gc.collect()
    if args.memory:
        tracemalloc.start()
    baseline_rss = rss_bytes()
    rows = []
    times = []
    baseline_commands = tcl_commands(cv)
    for cycle in range(args.rounds + 1):
        if cycle:
            started = time.perf_counter_ns()
            before = tcl_commands(cv) if cleanup else set()
            for focus in focuses:
                app._draw_focus(focus, rect)
            bundles = len(app._focus_bundles)
            item_count_before_reclaim = len(cv.find_all())
            app._reclaim_focus_bundles(set())
            if cleanup:
                for command in tcl_commands(cv) - before:
                    cv.deletecommand(command)
            times.append((time.perf_counter_ns() - started) / 1e6)
            assert bundles == args.focuses and not app._focus_bundles
            assert len(cv.find_all()) == 1, "only sentinel should remain"
        else:
            item_count_before_reclaim = 1
        if cycle in {0, 1, 5, 10, 20, args.rounds}:
            gc.collect()
            commands = tuple(tcl_commands(cv))
            actual = sum(bool(cv.tk.call("info", "commands", cmd)) for cmd in commands)
            current, peak = (
                tracemalloc.get_traced_memory() if args.memory else (None, None)
            )
            rows.append(
                dict(
                    cycle=cycle,
                    canvas_items=len(cv.find_all()),
                    items_before_reclaim=item_count_before_reclaim,
                    callback_commands=len(commands),
                    actual_live_tcl_commands=actual,
                    python_traced_current_bytes=current,
                    python_traced_peak_bytes=peak,
                    rss_bytes=rss_bytes(),
                )
            )
    result = dict(
        cleanup_control=cleanup,
        baseline_rss_bytes=baseline_rss,
        samples=rows,
        cycle_times_ms=times,
        cycle_median_ms=statistics.median(times),
        callback_increase=len(tcl_commands(cv)) - len(baseline_commands),
    )
    root.destroy()
    del app, cv, root
    gc.collect()
    if args.memory:
        result["python_traced_after_destroy_bytes"] = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
    return result


results = []
for repeat in range(args.repeats):
    for cleanup in (False, True):
        result = run(cleanup)
        result["repeat"] = repeat
        results.append(result)
report = dict(
    head=subprocess.check_output(
        ["git", "-C", args.repo, "rev-parse", "HEAD"], text=True
    ).strip(),
    python=sys.version,
    tk=tk.TkVersion,
    display=os.environ["DISPLAY"],
    instrumented_memory=args.memory,
    focuses=args.focuses,
    rounds=args.rounds,
    caveat=(
        "Synthetic production render/reclaim with real Tk; hidden widget. "
        "No presentation latency measured; filesystem cache irrelevant."
    ),
    results=results,
)
Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "out": args.out,
            "callback_increases": [r["callback_increase"] for r in results],
            "cycle_median_ms": [r["cycle_median_ms"] for r in results],
        }
    )
)
