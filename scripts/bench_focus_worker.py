#!/usr/bin/env python3
"""Tk timer responsiveness during real batch import; private Xvfb only.

--disable-gc is a diagnostic control, never a recommended application setting.
Fresh models each sample, uncontrolled filesystem caches. GC spans are observed
process-wide with thread IDs; overlap is evidence of correlation, not sole cause.
"""

# ruff: noqa: E402
# pylint: disable=wrong-import-position
import argparse
import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--focus-dir", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--samples", type=int, default=3)
parser.add_argument("--disable-gc", action="store_true")
args = parser.parse_args()
if not os.environ.get("DISPLAY"):
    raise SystemExit("Requires an explicit private Xvfb DISPLAY")
sys.path.insert(0, str(args.repo / "src"))
import tkinter as tk

from hoi4cm.focus_tree.batch_load import batch_load_trees

files = sorted(args.focus_dir.rglob("*.txt"))
root = tk.Tk()
root.withdraw()


def run_sample():
    gc.collect()
    done = threading.Event()
    intervals = []
    spans = []
    gc_start = {}
    previous = [time.perf_counter()]
    result = {}

    def observe(phase, info):
        key = (threading.get_ident(), info["generation"])
        now = time.perf_counter()
        if phase == "start":
            gc_start[key] = now
        else:
            spans.append(
                {
                    "start": gc_start.pop(key, now),
                    "end": now,
                    "generation": key[1],
                    "thread": key[0],
                }
            )

    def work():
        start = time.perf_counter()
        try:
            rows, _ = batch_load_trees(
                [(str(p), "shared") for p in files], [], 0, "", lambda *_: None
            )
            result.update(
                ms=(time.perf_counter() - start) * 1000,
                focuses=sum(len(row["new_focuses"]) for row in rows if row["ok"]),
                failures=sum(not row["ok"] for row in rows),
            )
        except Exception as error:
            result["error"] = repr(error)
        finally:
            done.set()

    def tick():
        now = time.perf_counter()
        intervals.append(
            {"start": previous[0], "end": now, "ms": (now - previous[0]) * 1000}
        )
        previous[0] = now
        if done.is_set():
            root.quit()
        else:
            root.after(5, tick)

    gc.callbacks.append(observe)
    if args.disable_gc:
        gc.disable()
    try:
        root.after(5, tick)
        thread = threading.Thread(target=work)
        thread.start()
        root.mainloop()
        thread.join()
    finally:
        gc.callbacks.remove(observe)
        gc.enable()
    values = sorted(interval["ms"] for interval in intervals)
    result.update(
        intervals=intervals,
        gc_spans=spans,
        p95_ms=values[int(0.95 * (len(values) - 1))],
        max_ms=max(values),
    )
    return result


runs = [run_sample() for _ in range(args.samples)]
root.destroy()
args.out.write_text(
    json.dumps({"gc_disabled_control": args.disable_gc, "runs": runs}, indent=2),
    encoding="utf-8",
)
print(
    [
        {
            key: value
            for key, value in row.items()
            if key not in ("intervals", "gc_spans")
        }
        for row in runs
    ]
)
