#!/usr/bin/env python3
"""Actual wheel burst benchmark; DISPLAY must be a private Xvfb server.

Uses fresh roots and warm parsed models. Measures CPU/event-handler throughput,
not compositor FPS. Final view/item geometry is saved for baseline comparison.
"""

# ruff: noqa: E402
# pylint: disable=wrong-import-position
import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--samples", type=int, default=7)
args = parser.parse_args()
if not os.environ.get("DISPLAY"):
    raise SystemExit("Requires an explicit private Xvfb DISPLAY")
sys.path[:0] = [str(args.repo / "src"), str(args.repo / "tests")]
import tkinter as tk

# Reuse the headless suite's host double for the canvas benchmark.
from ui_fakes import AppFake

from hoi4cm.core.paths import read_file
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.parse import parse_focus_tree

focuses = build_focuses(parse_focus_tree(read_file(args.fixture), str(args.fixture)), 0)
rows = []
for _ in range(args.samples):
    root = tk.Tk()
    root.geometry("1200x800")
    canvas = tk.Canvas(root)
    canvas.pack(fill="both", expand=True)
    root.update()
    app = AppFake(focuses, cv=canvas)
    app.zoom = 0.45
    app.offset = [600 - focuses[0].x * 96 * 0.45, 400 - focuses[0].y * 130 * 0.45]
    app._mm_visible = False
    app._grow_canvas_to_focuses()
    app._redraw_now()
    root.update()
    gc.collect()
    started = time.perf_counter()
    for index in range(12):
        app._scroll(
            SimpleNamespace(
                x=600,
                y=400,
                num=4 if index % 2 == 0 else 5,
                delta=120 if index % 2 == 0 else -120,
            )
        )
    handlers_ms = (time.perf_counter() - started) * 1000
    if app._redraw_job:
        canvas.after_cancel(app._redraw_job)
        app._do_redraw()
    rows.append(
        {
            "handlers_ms": handlers_ms,
            "including_final_render_ms": (time.perf_counter() - started) * 1000,
            "view": [app.zoom, app.offset],
            "items": [
                [fid, [canvas.coords(i) for i in bundle.items]]
                for fid, bundle in sorted(app._focus_bundles.items())
            ],
        }
    )
    root.destroy()
args.out.write_text(
    json.dumps({"samples": rows, "focuses": len(focuses)}, indent=2), encoding="utf-8"
)
print([row["including_final_render_ms"] for row in rows])
