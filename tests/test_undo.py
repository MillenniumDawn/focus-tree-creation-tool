"""Tests for hoi4cm.core.undo — sparse-snapshot undo stack.

No tkinter anywhere here: `UndoStack` only knows about dicts of ids to
objects with `.to_dict()`, plus a caller-supplied factory to rebuild them.
`Focus` stands in for that object since it's the only thing this stack is
used for today, but the module itself never imports it.
"""

import random

import pytest

from hoi4cm.core.undo import UndoStack
from hoi4cm.models import Focus


@pytest.fixture(autouse=True)
def reset_counter():
    """Isolate the module-level auto-increment counter."""
    old = Focus._next
    Focus._next = 0
    yield
    Focus._next = old


def _mk_focus(fid, name, x=0, y=0, cost=10, desc="", prereqs=None, mutex=None):
    return Focus.from_dict(
        {
            "id": fid,
            "x": x,
            "y": y,
            "name": name,
            "icon": "⚔",
            "gfx": "GFX_goal_generic_political_pressure",
            "cost": cost,
            "desc": desc,
            "effects": [],
            "prereqs": prereqs or [],
            "mutex": mutex or [],
        }
    )


def _delete_with_cleanup(focuses, stack, fid, label="delete focus"):
    """Mirror `_delete_focus`'s touched-set + reference cleanup."""
    touched = {fid}
    for o in focuses.values():
        if o.id == fid:
            continue
        if any(fid in g for g in o.prereqs) or fid in o.mutex:
            touched.add(o.id)
    stack.push(label, focuses, touched_ids=touched)
    for o in focuses.values():
        o.prereqs = [[p for p in g if p != fid] for g in o.prereqs]
        o.prereqs = [g for g in o.prereqs if g]
        o.mutex = [m for m in o.mutex if m != fid]
    del focuses[fid]


def test_len_and_clear():
    stack = UndoStack()
    assert len(stack) == 0
    stack.push("x", {}, touched_ids=())
    assert len(stack) == 1
    stack.clear()
    assert len(stack) == 0


def test_undo_on_empty_stack_returns_none():
    stack = UndoStack()
    assert stack.undo({}, Focus.from_dict) is None


def test_creation_only_undo_removes_new_focus():
    """`touched_ids=()` (add/duplicate/new-at) — undo deletes via id-set diff."""
    focuses = {1: _mk_focus(1, "focus_1")}
    stack = UndoStack()
    stack.push("add focus", focuses, touched_ids=())
    focuses[2] = _mk_focus(2, "focus_2")

    label, changed, removed = stack.undo(focuses, Focus.from_dict)

    assert label == "add focus"
    assert changed == set()
    assert removed == {2}
    assert set(focuses) == {1}


def test_single_edit_undo_restores_fields():
    f = _mk_focus(1, "focus_1", cost=10, desc="old")
    focuses = {1: f}
    stack = UndoStack()
    stack.push("edit focus", focuses, touched_ids=(1,))
    f.cost = 99
    f.desc = "new"
    f.name = "renamed"

    label, changed, removed = stack.undo(focuses, Focus.from_dict)

    assert label == "edit focus"
    assert changed == {1}
    assert removed == set()
    assert focuses[1].id == 1
    assert focuses[1].cost == 10
    assert focuses[1].desc == "old"
    assert focuses[1].name == "focus_1"


def test_multi_delete_undo_restores_focuses_and_links():
    a = _mk_focus(1, "a")
    b = _mk_focus(2, "b", prereqs=[[1]])
    c = _mk_focus(3, "c", mutex=[1])
    focuses = {1: a, 2: b, 3: c}
    stack = UndoStack()

    _delete_with_cleanup(focuses, stack, 1)

    assert 1 not in focuses
    assert focuses[2].prereqs == []
    assert focuses[3].mutex == []

    label, changed, removed = stack.undo(focuses, Focus.from_dict)

    assert label == "delete focus"
    assert changed == {1, 2, 3}
    assert removed == set()
    assert focuses[1].id == 1
    assert focuses[2].prereqs == [[1]]
    assert focuses[3].mutex == [1]


def test_rename_set_undo_restores_names_only():
    focuses = {
        1: _mk_focus(1, "old_a"),
        2: _mk_focus(2, "old_b"),
        3: _mk_focus(3, "keep"),
    }
    stack = UndoStack()
    renamed = {1, 2}
    stack.push("bulk_rename", focuses, touched_ids=renamed)
    focuses[1].name = "new_a"
    focuses[2].name = "new_b"

    label, changed, removed = stack.undo(focuses, Focus.from_dict)

    assert label == "bulk_rename"
    assert changed == {1, 2}
    assert removed == set()
    assert focuses[1].name == "old_a"
    assert focuses[2].name == "old_b"
    assert focuses[3].name == "keep"


def test_full_snapshot_roundtrip_unicode_and_big_text():
    big_raw = "base = { modifier = { factor = 1 } }\n" * 500 + "特殊文字"
    f1 = _mk_focus(1, "f1", desc="ünïcödé désc")
    f1.ai_will_do_raw = big_raw
    focuses = {1: f1, 2: _mk_focus(2, "f2")}
    stack = UndoStack()
    stack.push("draw.io import", focuses)  # touched_ids=None -> full snapshot
    focuses.clear()
    focuses[100] = _mk_focus(100, "imported")

    label, changed, removed = stack.undo(focuses, Focus.from_dict)

    assert label == "draw.io import"
    assert removed == {100}
    assert changed == {1, 2}
    assert 100 not in focuses
    assert focuses[1].ai_will_do_raw == big_raw
    assert focuses[1].desc == "ünïcödé désc"
    assert focuses[2].name == "f2"


def test_eviction_caps_at_60():
    stack = UndoStack()
    focuses = {}
    for i in range(65):
        stack.push(f"op{i}", focuses, touched_ids=())

    assert len(stack) == 60

    labels = []
    while len(stack):
        result = stack.undo(focuses, Focus.from_dict)
        labels.append(result[0])

    assert len(labels) == 60
    assert labels[0] == "op64"  # most recent pops first
    assert labels[-1] == "op5"  # op0..op4 evicted
    assert "op0" not in labels
    assert "op4" not in labels


def test_property_sparse_matches_full_snapshot_reference():
    """Precisely-bounded touched_ids must produce the same undo result as
    always taking a full snapshot, across ~200 randomized op sequences."""
    rng = random.Random(0)

    def seed():
        return {
            1: _mk_focus(1, "seed_1"),
            2: _mk_focus(2, "seed_2", prereqs=[[1]]),
            3: _mk_focus(3, "seed_3", mutex=[1]),
        }

    focuses_sparse = seed()
    focuses_full = seed()
    stack_sparse = UndoStack()
    stack_full = UndoStack()
    next_id = [4]

    def assert_in_sync():
        a = {fid: f.to_dict() for fid, f in focuses_sparse.items()}
        b = {fid: f.to_dict() for fid, f in focuses_full.items()}
        assert a == b
        assert len(stack_sparse) == len(stack_full)

    assert_in_sync()

    for step in range(200):
        live = sorted(focuses_sparse)
        kind = rng.choice(["add", "edit", "delete", "rename", "link", "undo"])

        if kind == "add":
            fid = next_id[0]
            next_id[0] += 1
            name = f"gen_{fid}"
            stack_sparse.push("add", focuses_sparse, touched_ids=())
            focuses_sparse[fid] = _mk_focus(fid, name)
            stack_full.push("add", focuses_full, touched_ids=None)
            focuses_full[fid] = _mk_focus(fid, name)

        elif kind == "edit" and live:
            fid = rng.choice(live)
            new_cost = rng.randint(0, 500)
            new_desc = f"desc_{rng.randint(0, 1_000_000)}"
            stack_sparse.push("edit", focuses_sparse, touched_ids=(fid,))
            focuses_sparse[fid].cost = new_cost
            focuses_sparse[fid].desc = new_desc
            stack_full.push("edit", focuses_full, touched_ids=None)
            focuses_full[fid].cost = new_cost
            focuses_full[fid].desc = new_desc

        elif kind == "delete" and live:
            fid = rng.choice(live)
            _delete_with_cleanup(focuses_sparse, stack_sparse, fid, label="delete")
            stack_full.push("delete", focuses_full, touched_ids=None)
            for o in focuses_full.values():
                o.prereqs = [[p for p in g if p != fid] for g in o.prereqs]
                o.prereqs = [g for g in o.prereqs if g]
                o.mutex = [m for m in o.mutex if m != fid]
            del focuses_full[fid]

        elif kind == "rename" and live:
            ids = rng.sample(live, k=min(len(live), rng.randint(1, 3)))
            suffix = f"_r{step}"
            stack_sparse.push("rename", focuses_sparse, touched_ids=set(ids))
            for i in ids:
                focuses_sparse[i].name += suffix
            stack_full.push("rename", focuses_full, touched_ids=None)
            for i in ids:
                focuses_full[i].name += suffix

        elif kind == "link" and len(live) >= 2:
            a, b = rng.sample(live, 2)
            stack_sparse.push("link", focuses_sparse, touched_ids=(a,))
            focuses_sparse[a].prereqs.append([b])
            stack_full.push("link", focuses_full, touched_ids=None)
            focuses_full[a].prereqs.append([b])

        elif kind == "undo":
            r1 = stack_sparse.undo(focuses_sparse, Focus.from_dict)
            r2 = stack_full.undo(focuses_full, Focus.from_dict)
            assert (r1 is None) == (r2 is None)
            if r1 is not None:
                assert r1[0] == r2[0]

        assert_in_sync()
