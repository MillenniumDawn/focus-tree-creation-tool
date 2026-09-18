"""Deterministic per-area performance tracking.

Each hot area gets a synthetic workload built without randomness, timed with
``time.perf_counter`` over several repeats, and summarized as a median. The
result is a JSON-serializable report meant to be recorded over time so slow
spots show up as deltas, not anecdotes.

Stdlib only, no tkinter, no display: safe to run headless. The canvas itself
needs Tk, so the ``scene`` area times the headless geometry work a frame
depends on (``SceneIndex`` rebuild / no-op ``ensure`` / single-focus update)
instead of real widget calls.
"""

from __future__ import annotations

import gc
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from hoi4cm.core.paths import read_file
from hoi4cm.core.undo import UndoStack
from hoi4cm.focus_tree.batch_load import batch_load_trees
from hoi4cm.focus_tree.build import build_focuses
from hoi4cm.focus_tree.export import export_main_tree
from hoi4cm.focus_tree.parse import parse_focus_tree
from hoi4cm.mod import scan_cache
from hoi4cm.mod.graphics_catalog import (
    GraphicsCatalog,
    GraphicsScanConfig,
)
from hoi4cm.models import Focus
from hoi4cm.ui.scene_index import SceneIndex

AREAS = (
    "parse",
    "build",
    "batch_load",
    "undo",
    "graphics_scan",
    "scene",
    "export",
)

_DESCRIPTIONS = {
    "parse": "parse_focus_tree on one synthetic tree (text in, ParsedFocusTree out)",
    "build": "build_focuses from an already-parsed tree (ParsedFocusTree to Focus)",
    "batch_load": "batch_load_trees over synthetic files on disk (read+parse+build)",
    "undo": "sparse push, small mutate, undo, redo on a focus dict",
    "graphics_scan": "cold GraphicsCatalog.refresh over synthetic images and .gfx",
    "scene": "SceneIndex rebuild, no-op ensure, and single-focus update (drag proxy)",
    "export": "export_main_tree rendering synthetic focuses back to script text",
}

# Per-preset workload sizes. "full" mirrors the reference mod's largest tree
# (776 focuses) where cheap; "quick" is for a fast local check; "tiny" keeps
# the pytest smoke test under a second or two.
_PRESETS = {
    "full": {
        "parse": 776,
        "export": 776,
        "batch_files": 20,
        "batch_per_file": 25,
        "undo": 2000,
        "graphics": 2000,
        "scene": 2000,
        "repeats": 5,
    },
    "quick": {
        "parse": 200,
        "export": 200,
        "batch_files": 8,
        "batch_per_file": 10,
        "undo": 500,
        "graphics": 300,
        "scene": 500,
        "repeats": 3,
    },
    "tiny": {
        "parse": 12,
        "export": 12,
        "batch_files": 2,
        "batch_per_file": 3,
        "undo": 30,
        "graphics": 12,
        "scene": 30,
        "repeats": 2,
    },
}


@dataclass
class AreaResult:
    area: str
    description: str
    workload: dict
    repeats: int
    median_ms: float
    min_ms: float
    max_ms: float
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "area": self.area,
            "description": self.description,
            "workload": self.workload,
            "repeats": self.repeats,
            "median_ms": self.median_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "extra": self.extra,
        }


@dataclass
class PerfReport:
    preset: str
    repeats: int
    results: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tool": "track_perf",
            "generated_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
            "platform": sys.platform,
            "preset": self.preset,
            "repeats": self.repeats,
            "areas": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _median_ms(values: list) -> float:
    return round(statistics.median(values), 3)


def _samples(fn, repeats: int) -> list:
    fn()  # warmup, discarded
    out = []
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        fn()
        out.append((time.perf_counter() - start) * 1000.0)
    return out


def _summarize(
    area: str, workload: dict, repeats: int, samples: list, extra: dict | None = None
) -> AreaResult:
    return AreaResult(
        area=area,
        description=_DESCRIPTIONS[area],
        workload=workload,
        repeats=repeats,
        median_ms=round(statistics.median(samples), 3),
        min_ms=round(min(samples), 3),
        max_ms=round(max(samples), 3),
        extra=extra or {},
    )


def focus_tree_text(count: int, prefix: str = "PERF") -> str:
    """Build deterministic synthetic focus-tree script with ``count`` focuses."""
    lines = ["focus_tree = {", f"\tid = {prefix}_tree"]
    for i in range(count):
        x = i % 28
        y = i // 28
        lines.append("\tfocus = {")
        lines.append(f"\t\tid = {prefix}_{i:04d}")
        lines.append(f"\t\tx = {x}")
        lines.append(f"\t\ty = {y}")
        lines.append("\t\tcost = 10")
        lines.append("\t\ticon = GFX_goal_generic_political_pressure")
        if i % 4 == 0:
            lines.append("\t\tcompletion_reward = {")
            lines.append("\t\t\tadd_political_power = 50")
            lines.append("\t\t}")
        if i % 8 == 1:
            lines.append("\t\tavailable = {")
            lines.append("\t\t\thas_war = no")
            lines.append("\t\t}")
        lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _time_parse(count: int, repeats: int) -> AreaResult:
    text = focus_tree_text(count)
    samples = _samples(lambda: parse_focus_tree(text, "synthetic.txt"), repeats)
    return _summarize(
        "parse",
        {"focuses": count, "chars": len(text)},
        repeats,
        samples,
    )


def _time_build(count: int, repeats: int) -> AreaResult:
    parsed = parse_focus_tree(focus_tree_text(count), "synthetic.txt")
    samples = _samples(lambda: build_focuses(parsed, 1, country_tag="PERF"), repeats)
    return _summarize("build", {"focuses": count}, repeats, samples)


def _time_batch_load(files: int, per_file: int, repeats: int) -> AreaResult:
    with tempfile.TemporaryDirectory(prefix="hoi4cm-perf-batch-") as tmp:
        paths = []
        for i in range(files):
            path = os.path.join(tmp, f"tree_{i:02d}.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(focus_tree_text(per_file, prefix=f"PB{i:02d}"))
            paths.append((path, "shared"))

        def load_once() -> None:
            batch_load_trees(paths, [], 0, "PERF", lambda *a: None)

        samples = _samples(load_once, repeats)
    return _summarize(
        "batch_load",
        {
            "files": files,
            "focuses_per_file": per_file,
            "focuses_total": files * per_file,
        },
        repeats,
        samples,
    )


def _focus_dict(count: int) -> dict:
    old = Focus._next
    Focus._next = 0
    try:
        focuses = {}
        for i in range(count):
            focus = Focus(i % 64, i // 64)
            focus.name = f"PERF_{i:05d}"
            focuses[focus.id] = focus
        return focuses
    finally:
        Focus._next = old


def _time_undo(count: int, repeats: int) -> AreaResult:
    focuses = _focus_dict(count)
    ids = list(focuses)
    first, second = ids[0], ids[1]
    stack = UndoStack()
    totals: list = []
    pushes: list = []
    mutates: list = []
    undos: list = []
    redos: list = []
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        mark = time.perf_counter()
        stack.push("perf", focuses, touched_ids=(first, second))
        pushes.append((time.perf_counter() - mark) * 1000.0)
        mark = time.perf_counter()
        focuses[first].cost += 1
        focuses[second].cost += 1
        mutates.append((time.perf_counter() - mark) * 1000.0)
        mark = time.perf_counter()
        stack.undo(focuses, Focus.from_dict)
        undos.append((time.perf_counter() - mark) * 1000.0)
        mark = time.perf_counter()
        stack.redo(focuses, Focus.from_dict)
        redos.append((time.perf_counter() - mark) * 1000.0)
        totals.append((time.perf_counter() - start) * 1000.0)
    med = _median_ms
    return AreaResult(
        area="undo",
        description=_DESCRIPTIONS["undo"],
        workload={"focuses": count, "touched_ids_per_push": 2},
        repeats=repeats,
        median_ms=med(totals),
        min_ms=round(min(totals), 3),
        max_ms=round(max(totals), 3),
        extra={
            "push_median_ms": med(pushes),
            "mutate_median_ms": med(mutates),
            "undo_median_ms": med(undos),
            "redo_median_ms": med(redos),
        },
    )


def _graphics_fixture(root: str, images: int) -> None:
    goals = os.path.join(root, "gfx", "interface", "goals")
    ideas = os.path.join(root, "gfx", "interface", "ideas")
    interface = os.path.join(root, "interface")
    os.makedirs(goals)
    os.makedirs(ideas)
    os.makedirs(interface)
    for i in range(images):
        with open(os.path.join(goals, f"goal_{i:05d}.dds"), "wb") as handle:
            handle.write(b"dds")
    with open(os.path.join(ideas, "idea_000.png"), "wb") as handle:
        handle.write(b"png")
    declared = min(25, images)
    with open(os.path.join(interface, "declared.gfx"), "w", encoding="utf-8") as handle:
        for i in range(declared):
            handle.write(
                f'spriteType = {{ name = "GFX_perf_declared_{i}" '
                f'texturefile = "gfx/interface/goals/goal_{i:05d}.dds" }}\n'
            )


def _read_text(path: str) -> str:
    content = read_file(path)
    assert content is not None
    return content


def _time_graphics_scan(images: int, repeats: int) -> AreaResult:
    config = GraphicsScanConfig(
        path_goals="gfx/interface/goals",
        path_ideas_gfx="gfx/interface/ideas",
        custom_gfx_dirs=(),
    )
    previous_state_dir = scan_cache.STATE_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="hoi4cm-perf-gfx-") as tmp:
            root = os.path.join(tmp, "mod")
            _graphics_fixture(root, images)
            samples = []
            metrics: dict = {}
            for i in range(repeats + 1):
                cold_state = os.path.join(tmp, f"state-{i}")
                os.makedirs(cold_state)
                scan_cache.STATE_DIR = cold_state
                catalog = GraphicsCatalog()
                gc.collect()
                start = time.perf_counter()
                catalog.refresh(str(root), config, read_text=_read_text)
                elapsed = (time.perf_counter() - start) * 1000.0
                if i > 0:
                    samples.append(elapsed)
                    metrics = {
                        "cache_status": catalog.last_metrics.cache_status,
                        "directory_listings": catalog.last_metrics.directory_listings,
                        "image_stats": catalog.last_metrics.image_stats,
                        "gfx_reads": catalog.last_metrics.gfx_reads,
                    }
    finally:
        scan_cache.STATE_DIR = previous_state_dir
    return _summarize(
        "graphics_scan",
        {"images": images, "gfx_files": 1},
        repeats,
        samples,
        extra=metrics,
    )


def _scene_doc(count: int) -> dict:
    focuses = _focus_dict(count)
    ids = list(focuses)
    for index in range(1, len(ids)):
        focuses[ids[index]].prereqs = [[ids[index - 1]]]
    return focuses


def _time_scene(count: int, repeats: int) -> AreaResult:
    focuses = _scene_doc(count)
    edges = sum(len(group) for f in focuses.values() for group in f.prereqs)
    index = SceneIndex()
    index.rebuild(focuses)
    victim = list(focuses)[len(focuses) // 2]

    def rebuild_once() -> None:
        SceneIndex().rebuild(focuses)

    rebuilds = _samples(rebuild_once, repeats)
    noop_index = SceneIndex()
    noop_index.rebuild(focuses)
    noops = _samples(lambda: noop_index.ensure(focuses), repeats)
    updates = []
    far = 100000
    for _ in range(repeats):
        gc.collect()
        focuses[victim].x = far
        far += 1
        start = time.perf_counter()
        noop_index.update_focus(focuses, victim)
        updates.append((time.perf_counter() - start) * 1000.0)
    med = _median_ms
    result = _summarize("scene", {"focuses": count, "edges": edges}, repeats, rebuilds)
    result.extra = {
        "ensure_noop_median_ms": med(noops),
        "update_focus_median_ms": med(updates),
    }
    return result


def _time_export(count: int, repeats: int) -> AreaResult:
    parsed = parse_focus_tree(focus_tree_text(count), "synthetic.txt")
    built = build_focuses(parsed, 0, country_tag="PERF")
    lookup = {f.id: f for f in built}
    info = {
        "tree_id": "PERF_tree",
        "country_tag": "PERF",
        "cfp_x": 0,
        "cfp_y": 0,
        "country_raw": "",
        "shared_focuses": [],
        "joint_focuses": [],
    }
    samples = _samples(
        lambda: export_main_tree(built, info, focus_lookup=lookup), repeats
    )
    return _summarize("export", {"focuses": count}, repeats, samples)


_TIMERS = {
    "parse": lambda s, r: _time_parse(s["parse"], r),
    "build": lambda s, r: _time_build(s["parse"], r),
    "batch_load": lambda s, r: _time_batch_load(
        s["batch_files"], s["batch_per_file"], r
    ),
    "undo": lambda s, r: _time_undo(s["undo"], r),
    "graphics_scan": lambda s, r: _time_graphics_scan(s["graphics"], r),
    "scene": lambda s, r: _time_scene(s["scene"], r),
    "export": lambda s, r: _time_export(s["export"], r),
}


def run_area(
    area: str, *, preset: str = "full", repeats: int | None = None
) -> AreaResult:
    """Time one area and return its result."""
    if area not in _TIMERS:
        raise KeyError(f"unknown perf area: {area!r} (expected one of {AREAS})")
    if preset not in _PRESETS:
        raise KeyError(f"unknown preset: {preset!r}")
    sizes = _PRESETS[preset]
    count = repeats if repeats is not None else sizes["repeats"]
    return _TIMERS[area](sizes, count)


def run_all(
    *,
    areas: list | tuple | None = None,
    preset: str = "full",
    repeats: int | None = None,
) -> PerfReport:
    """Time every requested area (default: all) and return the report."""
    wanted = list(areas) if areas is not None else list(AREAS)
    for area in wanted:
        if area not in _TIMERS:
            raise KeyError(f"unknown perf area: {area!r} (expected one of {AREAS})")
    if preset not in _PRESETS:
        raise KeyError(f"unknown preset: {preset!r}")
    sizes = _PRESETS[preset]
    count = repeats if repeats is not None else sizes["repeats"]
    report = PerfReport(preset=preset, repeats=count)
    for area in wanted:
        report.results.append(_TIMERS[area](sizes, count))
    return report


__all__ = [
    "AREAS",
    "AreaResult",
    "PerfReport",
    "focus_tree_text",
    "run_all",
    "run_area",
]
