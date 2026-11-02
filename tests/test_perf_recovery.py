"""Headless coverage of the recovery probe's scheduling and report contract."""

import heapq
import json
import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

import hoi4_content_maker as app_module
from hoi4cm.editor import recovery as recovery_editor
from hoi4cm.perf import recovery_callback
from hoi4cm.ui import recovery as recovery_ui


class _Root:
    def __init__(self):
        self._clock = 0
        self._next_job = 0
        self._jobs = {}
        self._queue = []
        self._quit = False
        self.destroyed = False
        self.tk = SimpleNamespace(call=lambda *_args: tuple(self._jobs))

    def withdraw(self):
        pass

    def winfo_exists(self):
        return int(not self.destroyed)

    def after(self, delay, callback):
        self._next_job += 1
        self._jobs[self._next_job] = callback
        heapq.heappush(self._queue, (self._clock + delay, self._next_job))
        return self._next_job

    def after_cancel(self, job):
        self._jobs.pop(job, None)

    def quit(self):
        self._quit = True

    def mainloop(self):
        self._quit = False
        while self._queue and not self._quit:
            self._clock, job = heapq.heappop(self._queue)
            callback = self._jobs.pop(job, None)
            if callback is not None:
                callback()

    def destroy(self):
        self.destroyed = True


def test_recovery_probe_parser_and_summary(tmp_path):
    args = recovery_callback._parser().parse_args(
        ["--out", str(tmp_path), "--focus-dir", "focuses"]
    )
    assert args.out == tmp_path
    assert args.focus_dir == Path("focuses")
    assert args.repo.is_dir()
    assert recovery_callback._summarize(
        [
            {"callback_ms": 1.0, "total_ms": 3.0},
            {"callback_ms": 3.0, "total_ms": 5.0},
        ]
    )["medians"] == {"callback_ms": 2.0, "total_ms": 4.0}


def test_recovery_probe_exercises_callback_without_building_widgets(
    tmp_path, monkeypatch, capsys
):
    root = _Root()
    monkeypatch.setattr(tk, "Tk", lambda: root)
    monkeypatch.setenv("DISPLAY", ":isolated-fake")
    monkeypatch.setenv("HOME", os.environ["HOME"])
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(
        app_module, "workspace_autosave_path", app_module.workspace_autosave_path
    )
    for module, name in (
        (recovery_ui, "workspace_autosave_path"),
        (recovery_ui, "capture_recovery_snapshot"),
        (recovery_editor, "write_recovery_bytes"),
    ):
        monkeypatch.setattr(module, name, getattr(module, name))

    def submit(_owner, work, on_done, **_kwargs):
        on_done(work())

    monkeypatch.setattr(recovery_ui, "run_bg", submit)
    focus_dir = tmp_path / "focuses"
    focus_dir.mkdir()
    (focus_dir / "tree.txt").write_text(
        "focus_tree = { id = T focus = { id = A x = 0 y = 0 } }"
    )
    out = tmp_path / "out"
    logger = logging.getLogger("HOI4CM")
    old_level = logger.level
    try:
        recovery_callback.run_recovery_callback_benchmark(
            ["--out", str(out), "--focus-dir", str(focus_dir)]
        )
    finally:
        logger.setLevel(old_level)

    report = json.loads((out / "measurements.json").read_text())
    assert report["files"] == report["accepted"] == report["focuses"] == 1
    assert report["separate_peak_bytes"] > 0
    assert report["recovery_file_bytes"] > 0
    for destinations in ("1", "2"):
        run = report["runs"][destinations]
        assert len(run["samples"]) == 5
        assert set(run["medians"]) == {
            "callback_ms",
            "total_ms",
            "dirty_ms",
            "metadata_capture_ms",
            "snapshot_encode_ms",
            "write_ms",
            "timer_p95_ms",
            "timer_max_ms",
        }
    assert root.destroyed
    assert json.loads(capsys.readouterr().out) == report


def test_recovery_probe_refuses_missing_display(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(SystemExit, match="private Xvfb"):
        recovery_callback.run_recovery_callback_benchmark(
            ["--out", str(tmp_path), "--focus-dir", "focuses"]
        )


def test_recovery_probe_refuses_mixed_checkout_imports(tmp_path):
    with pytest.raises(SystemExit, match="directly"):
        recovery_callback.run_recovery_callback_benchmark(
            ["--repo", str(tmp_path), "--out", str(tmp_path), "--focus-dir", "focuses"]
        )
