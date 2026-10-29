"""Headless tests for cooperative cancel in the batch-load worker."""

from __future__ import annotations

import threading

from hoi4cm.focus_tree import batch_load as batch_load_module
from hoi4cm.focus_tree.batch_load import batch_load_trees
from hoi4cm.models import Focus, FocusDocument

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


def test_batch_load_allocates_unique_ids_across_trees_and_existing_seed(tmp_path):
    first = _write_tree(tmp_path / "a.txt", "a")
    second = _write_tree(tmp_path / "b.txt", "b")
    seed = Focus(id=41)
    document = FocusDocument([seed])
    undone = document.new_focus()
    document.add(undone)
    document.delete_many((undone.id,))

    results, stopped = batch_load_trees(
        [(first, "shared"), (second, "joint")],
        [seed],
        0,
        "TST",
        lambda *_args: None,
        allocator_floor=document.last_allocated_id,
    )
    added = [focus for result in results for focus in result["new_focuses"]]

    assert stopped is False
    assert [focus.id for focus in added] == [43, 44]
    document.extend(added)
    assert list(document) == [41, 43, 44]


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


def test_batch_load_worker_drops_current_file_when_cancelled_during_parse(tmp_path):
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
    assert results == []
    assert seen == ["a.txt"]


def test_batch_load_reconciles_earlier_results_without_reparsing(tmp_path, monkeypatch):
    child = tmp_path / "a-child.txt"
    target = tmp_path / "b-target.txt"
    child.write_text(
        "focus_tree = { id = CHILD focus = { id = CHILD_one x = 2 y = 3 "
        "relative_position_id = MID prerequisite = { focus = LATE } "
        "mutually_exclusive = { focus = LATE } } "
        "focus = { id = MID x = 1 y = 1 relative_position_id = LATE } }",
        encoding="utf-8",
    )
    target.write_text(
        "focus_tree = { id = TARGET focus = { id = LATE x = 8 y = 9 } }",
        encoding="utf-8",
    )
    parse_calls = 0
    original_parse = batch_load_module.parse_focus_tree

    def counted_parse(*args, **kwargs):
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(batch_load_module, "parse_focus_tree", counted_parse)
    results, stopped = batch_load_trees(
        [(str(child), "shared"), (str(target), "joint")],
        [],
        0,
        "TST",
        lambda *_args: None,
    )

    first_focuses = results[0]["new_focuses"]
    first_by_name = {focus.name: focus for focus in first_focuses}
    late = results[1]["new_focuses"][0]
    assert stopped is False
    assert all(result["ok"] for result in results)
    assert parse_calls == 2
    assert (first_by_name["MID"].x, first_by_name["MID"].y) == (9, 10)
    assert (first_by_name["CHILD_one"].x, first_by_name["CHILD_one"].y) == (11, 13)
    assert first_by_name["CHILD_one"].prereqs == [[late.id]]
    assert first_by_name["CHILD_one"].mutex == [late.id]
    assert first_by_name["CHILD_one"]._unresolved_prereqs == [[]]
    assert first_by_name["CHILD_one"]._unresolved_mutex == []


def test_failed_tree_does_not_prevent_later_reference_reconciliation(tmp_path):
    dependent = tmp_path / "dependent.txt"
    broken = tmp_path / "broken.txt"
    target = tmp_path / "target.txt"
    dependent.write_text(
        "focus_tree = { id = D focus = { id = D_child x = 1 y = 1 "
        "prerequisite = { focus = TARGET } } }",
        encoding="utf-8",
    )
    broken.write_text("not a tree", encoding="utf-8")
    target.write_text(
        "focus_tree = { id = T focus = { id = TARGET } }", encoding="utf-8"
    )

    results, stopped = batch_load_trees(
        [(str(dependent), "shared"), (str(broken), "shared"), (str(target), "joint")],
        [],
        0,
        "TST",
        lambda *_args: None,
    )

    child = results[0]["new_focuses"][0]
    target_focus = results[-1]["new_focuses"][0]
    assert stopped is False
    assert [result["ok"] for result in results] == [True, False, True]
    assert child.prereqs == [[target_focus.id]]
    assert child._unresolved_prereqs == [[]]


def test_batch_reference_parity_and_measured_parse_reconciliation_work(
    tmp_path, monkeypatch
):
    tree_a = """focus_tree = { id = A
        focus = { id = A_focus x = 2 y = 3 relative_position_id = B_focus
            prerequisite = { focus = B_focus } }
    }"""
    tree_b = """focus_tree = { id = B
        focus = { id = B_focus x = 5 y = 7
            prerequisite = { focus = A_focus } }
    }"""
    original_parse = batch_load_module.parse_focus_tree
    original_reconcile = batch_load_module.BuildContext._reconcile_pending
    measurements = []

    for order in (("A", "B"), ("B", "A")):
        paths = {}
        for name, source in (("A", tree_a), ("B", tree_b)):
            path = tmp_path / f"{len(measurements)}-{name}.txt"
            path.write_text(source, encoding="utf-8")
            paths[name] = str(path)
        counts = {"parse": 0, "reconcile": 0, "visited": 0}

        def counted_parse(*args, _counts=counts, **kwargs):
            _counts["parse"] += 1
            return original_parse(*args, **kwargs)

        def counted_reconcile(context, _counts=counts):
            _counts["reconcile"] += 1
            _counts["visited"] += len(context._focuses_by_id)
            return original_reconcile(context)

        monkeypatch.setattr(batch_load_module, "parse_focus_tree", counted_parse)
        monkeypatch.setattr(
            batch_load_module.BuildContext, "_reconcile_pending", counted_reconcile
        )
        results, stopped = batch_load_trees(
            [(paths[name], "shared") for name in order],
            [],
            0,
            "TST",
            lambda *_args: None,
        )
        assert stopped is False
        all_focuses = [focus for result in results for focus in result["new_focuses"]]
        by_name = {focus.name: focus for focus in all_focuses}
        name_by_id = {focus.id: focus.name for focus in all_focuses}
        measurements.append(
            (
                {name: (focus.x, focus.y) for name, focus in by_name.items()},
                {
                    name: [
                        [name_by_id[focus_id] for focus_id in group]
                        for group in focus.prereqs
                    ]
                    for name, focus in by_name.items()
                },
                counts,
            )
        )
        monkeypatch.setattr(batch_load_module, "parse_focus_tree", original_parse)
        monkeypatch.setattr(
            batch_load_module.BuildContext, "_reconcile_pending", original_reconcile
        )

    assert measurements[0][:2] == measurements[1][:2]
    assert measurements[0][2] == measurements[1][2]
    assert measurements[0][0] == {"A_focus": (7, 10), "B_focus": (5, 7)}
    assert measurements[0][2] == {"parse": 2, "reconcile": 1, "visited": 2}


def test_cancel_after_build_does_not_link_unadopted_target(tmp_path, monkeypatch):
    dependent_path = tmp_path / "dependent.txt"
    target_path = tmp_path / "target.txt"
    dependent_path.write_text(
        "focus_tree = { id = D focus = { id = D_child prerequisite = { "
        "focus = TARGET } } }",
        encoding="utf-8",
    )
    target_path.write_text(
        "focus_tree = { id = T focus = { id = TARGET } }", encoding="utf-8"
    )
    dependent_results, _stopped = batch_load_trees(
        [(str(dependent_path), "shared")], [], 0, "TST", lambda *_args: None
    )
    child = dependent_results[0]["new_focuses"][0]
    cancel = threading.Event()
    original_build = batch_load_module.build_focuses

    def cancel_after_build(*args, **kwargs):
        focuses = original_build(*args, **kwargs)
        cancel.set()
        return focuses

    monkeypatch.setattr(batch_load_module, "build_focuses", cancel_after_build)
    results, stopped = batch_load_trees(
        [(str(target_path), "joint")],
        [child],
        1,
        "TST",
        lambda *_args: None,
        cancelled=cancel,
    )

    assert stopped is True
    assert results == []
    assert child.prereqs == [[]]
    assert child._unresolved_prereqs == [["TARGET"]]


def test_batch_reconciliation_does_not_mutate_existing_seed(tmp_path):
    target_path = tmp_path / "target.txt"
    target_path.write_text(
        "focus_tree = { id = T focus = { id = TARGET x = 10 y = 0 } }",
        encoding="utf-8",
    )
    child = Focus(id=50, x=1, y=0)
    child.name = "CHILD"
    child.prereqs = [[]]
    child._unresolved_prereqs = [["TARGET"]]
    child.relative_position_id = "TARGET"
    child._relative_pending = True
    child._build_gx = 1
    child._build_gy = 0
    document = FocusDocument([child])

    results, stopped = batch_load_trees(
        [(str(target_path), "shared")], [child], 0, "TST", lambda *_args: None
    )

    target = results[0]["new_focuses"][0]
    assert stopped is False
    assert child.x == 1
    assert child.prereqs == [[]]
    assert child._unresolved_prereqs == [["TARGET"]]
    assert child._relative_pending is True
    assert document.reverse_prerequisites == {}
    assert target.id != child.id
