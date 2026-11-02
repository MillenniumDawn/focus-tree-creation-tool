"""Full recovery callbacks and Tk timer intervals. Run under private Xvfb.

Invoke this file directly when --repo selects a different checkout. Timing and
tracemalloc samples are separate. Filesystem caches are not flushed.
"""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import logging
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--focus-dir", type=Path, required=True)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[3]
    )
    return parser


def _summarize(samples: list[dict[str, float]]) -> dict[str, object]:
    return {
        "samples": samples,
        "medians": {
            key: statistics.median(sample[key] for sample in samples)
            for key in samples[0]
        },
    }


def run_recovery_callback_benchmark(argv: list[str] | None = None) -> None:
    import tkinter as tk

    args = _parser().parse_args(argv)
    if (
        args.repo.resolve() != Path(__file__).resolve().parents[3]
        and "hoi4cm" in sys.modules
    ):
        raise SystemExit(
            "Select another checkout by running this file directly, not with -m"
        )
    if not os.environ.get("DISPLAY"):
        raise SystemExit("Run under a private Xvfb display")
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(args.out.resolve() / "home")
    sys.path.insert(0, str(args.repo))
    sys.path.insert(0, str(args.repo / "src"))

    import hoi4_content_maker as app_module
    from hoi4cm.editor.project_codec import encode_project
    from hoi4cm.focus_tree.batch_load import batch_load_trees
    from hoi4cm.models import EditorWorkspace, FocusDocument
    from hoi4cm.ui.lifecycle import ApplicationLifecycle

    try:
        recovery_ui: Any = importlib.import_module("hoi4cm.ui.recovery")
    except ModuleNotFoundError as error:
        if error.name != "hoi4cm.ui.recovery":
            raise
        recovery_ui = importlib.import_module("hoi4_content_maker")

    logging.getLogger("HOI4CM").setLevel(logging.WARNING)
    root = tk.Tk()
    root.withdraw()
    files = sorted(args.focus_dir.rglob("*.txt"))
    rows, _ = batch_load_trees(
        [(str(path), "shared") for path in files], [], 0, "", lambda *_: None
    )
    focuses = []
    trees = []
    for index, row in enumerate(row for row in rows if row["ok"]):
        for focus in row["new_focuses"]:
            focus.tree_idx = index + 1
            focuses.append(focus)
        trees.append(
            {
                "type": "shared",
                "file_path": f"tree_{index}.txt",
                "tree_id": row["parsed"].tree_id,
                "focus_ids": {focus.id for focus in row["new_focuses"]},
            }
        )
    workspace = EditorWorkspace(focuses=FocusDocument(focuses))

    def variable(value):
        return SimpleNamespace(get=lambda: value)

    app = SimpleNamespace(
        workspace=workspace,
        focuses=workspace.focuses,
        _saved_revision=-1,
        _saved_fingerprint=None,
        _tree_id=variable("benchmark"),
        _tree_extras={},
        _cfp_x_var=variable(""),
        _cfp_y_var=variable(""),
        _cfp_x=None,
        _cfp_y=None,
        _shared_focuses=[],
        _joint_focuses=[],
        _extra_trees=trees,
        _canvas_min=[0, 0],
        _canvas_max=[9, 9],
        _default_focus_prefix="",
        edit_focus_file="",
        _autosave_job=None,
        _autosave_interval_ms=60000,
        _last_project_path=None,
        _log_error=lambda message: (_ for _ in ()).throw(AssertionError(message)),
        after=root.after,
        after_cancel=root.after_cancel,
        winfo_exists=root.winfo_exists,
        _lifecycle=ApplicationLifecycle(cast(Any, root)),
        master=None,
    )
    for name in (
        "_capture_workspace",
        "_workspace_fingerprint",
        "_is_dirty",
        "_autosave_tick",
        "_schedule_autosave",
        "_cancel_autosave",
    ):
        setattr(app, name, getattr(app_module.App, name).__get__(app))
    if recovery_ui is not app_module:
        app._recovery = recovery_ui.RecoveryController(app)
    phases: dict[str, float] = {}

    def measure(owner, name, label):
        original = getattr(owner, name)

        def measured(*values, **kwargs):
            started = time.perf_counter()
            try:
                return original(*values, **kwargs)
            finally:
                phases[label] = (
                    phases.get(label, 0) + (time.perf_counter() - started) * 1000
                )

        setattr(owner, name, measured)

    measure(app, "_is_dirty", "dirty_ms")
    measure(app, "_capture_workspace", "metadata_capture_ms")
    if recovery_ui is app_module:
        writer_module = importlib.import_module("hoi4cm.editor.autosave_writer")
        measure(writer_module, "serialize_project", "snapshot_encode_ms")
        measure(writer_module, "write_project_text", "write_ms")
    else:
        writer_module = importlib.import_module("hoi4cm.editor.recovery")
        measure(recovery_ui, "capture_recovery_snapshot", "snapshot_encode_ms")
        measure(writer_module, "write_recovery_bytes", "write_ms")
    report: dict[str, Any] = {
        "files": len(files),
        "accepted": sum(row["ok"] for row in rows),
        "focuses": len(workspace.focuses),
        "python": sys.version,
        "runs": {},
    }
    primary = args.out / "workspace.json"

    def primary_path(name: str = "workspace.json") -> str:
        return str(primary)

    recovery_ui.workspace_autosave_path = primary_path
    app_module.workspace_autosave_path = primary_path

    def run_sample():
        gc.collect()
        workspace.focuses.mark_content_changed()
        phases.clear()
        intervals = []
        previous = time.perf_counter()
        result = {}

        def heartbeat():
            nonlocal previous
            now = time.perf_counter()
            intervals.append((now - previous) * 1000)
            previous = now
            if "finished" not in result:
                root.after(5, heartbeat)

        def complete():
            if recovery_ui is not app_module and app._recovery.busy:
                root.after(5, complete)
                return
            result["total_ms"] = (time.perf_counter() - result.pop("started")) * 1000
            result["finished"] = True
            root.after(10, root.quit)

        def save():
            result["started"] = time.perf_counter()
            started = time.perf_counter()
            app._autosave_tick()
            result["callback_ms"] = (time.perf_counter() - started) * 1000
            app._cancel_autosave()
            complete()

        root.after(5, heartbeat)
        root.after(25, save)
        root.mainloop()
        result.pop("finished")
        result.update(phases)
        result["timer_p95_ms"] = sorted(intervals)[(len(intervals) - 1) * 95 // 100]
        result["timer_max_ms"] = max(intervals)
        try:
            actual = json.loads(primary.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AssertionError("recovery output missing or invalid") from error
        assert actual == encode_project(app.workspace)
        if app._last_project_path:
            sibling = Path(app_module.sibling_autosave_path(app._last_project_path))
            assert primary.read_bytes() == sibling.read_bytes()
        return result

    try:
        for destinations in (1, 2):
            app._last_project_path = (
                str(args.out / "project.json") if destinations == 2 else None
            )
            report["runs"][str(destinations)] = _summarize(
                [run_sample() for _ in range(5)]
            )
        tracemalloc.start()
        run_sample()
        report["separate_peak_bytes"] = tracemalloc.get_traced_memory()[1]
        report["recovery_file_bytes"] = primary.stat().st_size
        tracemalloc.stop()
    finally:
        app._lifecycle.close()
        root.destroy()
    (args.out / "measurements.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


__all__ = ["run_recovery_callback_benchmark"]

if __name__ == "__main__":
    run_recovery_callback_benchmark()
