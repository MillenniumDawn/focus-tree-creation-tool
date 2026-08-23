"""Sequential focus-tree batch load. No Tk."""

from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

from hoi4cm.core.logger import get_logger
from hoi4cm.core.paths import read_file

from .build import BuildContext, build_focuses
from .parse import parse_focus_tree

_log = get_logger("batch_load")


def make_cancel_handle(*, cancellable=False, on_cancel=None):
    """Return a pollable cancel flag. No Tk objects."""
    cancelled = threading.Event()

    def request_cancel():
        if not cancellable or cancelled.is_set():
            return
        cancelled.set()
        if on_cancel is not None:
            on_cancel()

    return SimpleNamespace(cancelled=cancelled, request_cancel=request_cancel)


def batch_load_trees(
    to_load,
    existing_seed,
    extra_trees_start_idx,
    country_tag,
    progress,
    cancelled=None,
):
    """Parse and build selected trees sequentially, stopping if cancelled."""
    total = len(to_load)
    existing = list(existing_seed)
    build_context = BuildContext(existing)
    tree_idx = extra_trees_start_idx
    results = []
    stopped_early = False
    for i, (path, ttype) in enumerate(to_load, start=1):
        if cancelled is not None and cancelled.is_set():
            stopped_early = True
            break
        progress(i, total, os.path.basename(path))
        try:
            raw = read_file(path)
            t0 = time.perf_counter()
            parsed = parse_focus_tree(raw, path)
            t1 = time.perf_counter()
            new_focuses = build_focuses(
                parsed,
                tree_idx + 1,
                country_tag=country_tag,
                context=build_context,
            )
            tree_idx += 1
            t2 = time.perf_counter()
            _log.debug(
                "install tree %s: parse %.1fms build %.1fms (%d focuses)",
                path,
                (t1 - t0) * 1000,
                (t2 - t1) * 1000,
                len(new_focuses),
            )
            existing.extend(new_focuses)
            results.append(
                {
                    "path": path,
                    "type": ttype,
                    "ok": True,
                    "parsed": parsed,
                    "new_focuses": new_focuses,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"path": path, "type": ttype, "ok": False, "error": exc})
    return results, stopped_early


__all__ = [
    "batch_load_trees",
    "make_cancel_handle",
]
