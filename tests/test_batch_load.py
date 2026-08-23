"""Headless tests for cooperative cancel in the batch-load worker."""

from __future__ import annotations

import threading

import pytest

from hoi4cm.focus_tree.batch_load import batch_load_trees
from hoi4cm.models import Focus

_TREE = """\
focus_tree = {
	id = TST_{name}_tree
	focus = {
		id = TST_{name}_root
		x = 0
		y = 0
		cost = 1
	}
}
"""


@pytest.fixture(autouse=True)
def reset_focus_counter():
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _write_tree(path, name):
    path.write_text(_TREE.replace("{name}", name), encoding="utf-8")
    return str(path)


def test_batch_load_worker_returns_all_files_when_not_cancelled(tmp_path):
    first = _write_tree(tmp_path / "a.txt", "a")
    second = _write_tree(tmp_path / "b.txt", "b")
    seen = []

    results, stopped = batch_load_trees(
        [(first, "shared"), (second, "joint")],
        [],
        0,
        "TST",
        lambda i, total, label: seen.append(label),
    )

    assert stopped is False
    assert [item["path"] for item in results] == [first, second]
    assert all(item["ok"] for item in results)
    assert seen == ["a.txt", "b.txt"]


def test_batch_load_worker_stops_before_any_file_when_already_cancelled(tmp_path):
    first = _write_tree(tmp_path / "a.txt", "a")
    second = _write_tree(tmp_path / "b.txt", "b")
    flag = threading.Event()
    flag.set()
    seen = []

    results, stopped = batch_load_trees(
        [(first, "shared"), (second, "joint")],
        [],
        0,
        "TST",
        lambda i, total, label: seen.append(label),
        cancelled=flag,
    )

    assert stopped is True
    assert results == []
    assert seen == []


def test_batch_load_worker_finishes_current_file_then_stops(tmp_path):
    first = _write_tree(tmp_path / "a.txt", "a")
    second = _write_tree(tmp_path / "b.txt", "b")
    flag = threading.Event()
    seen = []

    def progress(_i, _total, label):
        seen.append(label)
        flag.set()

    results, stopped = batch_load_trees(
        [(first, "shared"), (second, "joint")],
        [],
        0,
        "TST",
        progress,
        cancelled=flag,
    )

    assert stopped is True
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["path"] == first
    assert seen == ["a.txt"]
