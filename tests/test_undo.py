"""Tests for hoi4cm.core.undo — sparse-snapshot undo stack.

No tkinter anywhere here: `UndoStack` only knows about dicts of ids to
objects with `.to_dict()`, plus a caller-supplied factory to rebuild them.
`Focus` stands in for that object since it's the only thing this stack is
used for today, but the module itself never imports it.
"""

import random
import zlib

import pytest

from hoi4cm.core.undo import UndoStack, _decode_full
from hoi4cm.focus_tree.export import export_focus_tree
from hoi4cm.models import Focus, FocusDocument


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
    assert stack.redo({}, Focus.from_dict) is None
    stack.push("x", {}, touched_ids=())
    assert len(stack) == 1
    assert stack.redo({}, Focus.from_dict) is None
    stack.undo({}, Focus.from_dict)
    assert len(stack) == 0
    assert stack.redo({}, Focus.from_dict) is not None
    stack.clear()
    assert len(stack) == 0
    assert stack.redo({}, Focus.from_dict) is None


def test_undo_on_empty_stack_returns_none():
    stack = UndoStack()
    assert stack.undo({}, Focus.from_dict) is None
    assert stack.redo({}, Focus.from_dict) is None


def test_redo_on_empty_redo_returns_none():
    """`redo` is independent of `undo`: an unused stack has nothing to redo."""
    stack = UndoStack()
    focuses = {1: _mk_focus(1, "focus_1")}
    stack.push("x", focuses, touched_ids=())
    assert stack.redo(focuses, Focus.from_dict) is None


def test_push_clears_redo_trail():
    """A new edit branch invalidates the redo stack, like every editor does."""
    focuses = {1: _mk_focus(1, "focus_1")}
    stack = UndoStack()
    stack.push("a", focuses, touched_ids=(1,))
    focuses[1].name = "after_a"
    stack.undo(focuses, Focus.from_dict)
    assert focuses[1].name == "focus_1"
    # Capture the redo result without binding it: redo() is mutating and
    # would push us back to "after_a". The point of this branch is just
    # that redo was non-empty after the undo.
    assert stack.redo(focuses, Focus.from_dict) is not None

    # Branching: a new push must wipe the redo stack.
    stack.push("b", focuses, touched_ids=(1,))
    focuses[1].name = "after_b"
    assert stack.redo(focuses, Focus.from_dict) is None


def test_clear_empties_both_stacks():
    """`clear` is supposed to be a full reset, not just undo."""
    stack = UndoStack()
    focuses = {1: _mk_focus(1, "focus_1")}
    stack.push("a", focuses, touched_ids=(1,))
    stack.push("b", focuses, touched_ids=(1,))
    stack.undo(focuses, Focus.from_dict)
    assert len(stack) == 1
    assert stack.redo(focuses, Focus.from_dict) is not None
    stack.clear()
    assert len(stack) == 0
    assert stack.redo(focuses, Focus.from_dict) is None


def test_undo_then_redo_roundtrip_restores_state_and_changed_set():
    """After undo, redo must reconstruct the post-edit focus and report it
    as `changed_ids` so the caller's redraw picks it up."""
    focuses = {1: _mk_focus(1, "focus_1", cost=10)}
    stack = UndoStack()
    stack.push("edit cost", focuses, touched_ids=(1,))
    focuses[1].cost = 99
    pre_state = focuses[1].to_dict()

    label, changed, removed = stack.undo(focuses, Focus.from_dict)
    assert label == "edit cost"
    assert changed == {1}
    assert removed == set()
    assert focuses[1].cost == 10

    label2, changed2, removed2 = stack.redo(focuses, Focus.from_dict)
    assert label2 == "edit cost"
    assert changed2 == {1}
    assert removed2 == set()
    assert focuses[1].to_dict() == pre_state
    assert stack.redo(focuses, Focus.from_dict) is None


def test_redo_after_undo_then_push_is_blocked():
    """Redo state should vanish as soon as any new edit is pushed, even after
    several undo/redo hops that left the trail non-empty."""
    focuses = {1: _mk_focus(1, "focus_1", cost=10)}
    stack = UndoStack()
    stack.push("a", focuses, touched_ids=(1,))
    focuses[1].cost = 20
    stack.undo(focuses, Focus.from_dict)
    stack.redo(focuses, Focus.from_dict)
    stack.undo(focuses, Focus.from_dict)
    assert stack.redo(focuses, Focus.from_dict) is not None

    stack.push("b", focuses, touched_ids=(1,))
    assert stack.redo(focuses, Focus.from_dict) is None
    focuses[1].cost = 30

    result = stack.redo(focuses, Focus.from_dict)
    assert result is None
    assert focuses[1].cost == 30


def test_redo_restores_created_focuses():
    """`redo` must recreate focuses the user added between push and undo,
    not just leave them absent, so the round-trip is genuinely a no-op."""
    focuses = {1: _mk_focus(1, "focus_1")}
    stack = UndoStack()
    stack.push("add focus", focuses, touched_ids=())
    new = _mk_focus(2, "focus_2", cost=7)
    focuses[2] = new
    new_dict = new.to_dict()

    label, changed, removed = stack.undo(focuses, Focus.from_dict)
    assert label == "add focus"
    assert removed == {2}
    assert 2 not in focuses

    label2, changed2, removed2 = stack.redo(focuses, Focus.from_dict)
    assert label2 == "add focus"
    # `changed_ids` is the snapshot's full keyset, not just the diff: every
    # focus gets a redraw, since the document was reloaded wholesale. The
    # important invariant is that focus 2 came back and nothing was removed.
    assert changed2 == {1, 2}
    assert removed2 == set()
    assert 2 in focuses
    assert focuses[2].to_dict() == new_dict
    assert focuses[2].cost == 7


def test_redo_eviction_caps_at_maxlen():
    """Both stacks must honor `maxlen`; full-snapshot redo entries are heavy,
    so an unbounded redo would balloon memory."""
    stack = UndoStack(maxlen=4)
    focuses = {1: _mk_focus(1, "focus_1", cost=0)}
    for i in range(10):
        stack.push(f"op_{i}", focuses, touched_ids=(1,))
        focuses[1].cost = i + 1
    assert len(stack) == 4

    # Undo all four pushes: each undo enqueues one redo entry. Since none
    # of the undo-then-push churn happens, redo also fills to maxlen.
    undone_labels = []
    for _ in range(4):
        result = stack.undo(focuses, Focus.from_dict)
        undone_labels.append(result[0])
    assert len(stack) == 0

    # Two extra undos when the undo stack is empty must be no-ops, not
    # overflow the redo stack past maxlen.
    assert stack.undo(focuses, Focus.from_dict) is None
    assert stack.undo(focuses, Focus.from_dict) is None

    redo_labels = []
    while True:
        result = stack.redo(focuses, Focus.from_dict)
        if result is None:
            break
        redo_labels.append(result[0])
    # Only 4 redo entries survived; the undos past the cap didn't enqueue.
    assert len(redo_labels) == 4
    # Redo pops from the most recent undo first, so the survivor list is
    # the last 4 undo labels in the order they get re-applied.
    assert redo_labels == ["op_6", "op_7", "op_8", "op_9"]


def test_redo_sparse_matches_full_snapshot_reference():
    """Round-tripping undo+redo must converge on the same state for both
    sparse and full-snapshot stacks, across randomized push/undo/redo."""
    rng = random.Random(1)

    def seed():
        return {
            1: _mk_focus(1, "seed_1"),
            2: _mk_focus(2, "seed_2", prereqs=[[1]]),
            3: _mk_focus(3, "seed_3", mutex=[1]),
        }

    sparse_focuses = seed()
    full_focuses = seed()
    sparse_stack = UndoStack()
    full_stack = UndoStack()
    next_id = [4]

    def snapshot_state(focuses):
        return {fid: f.to_dict() for fid, f in focuses.items()}

    def assert_in_sync():
        assert snapshot_state(sparse_focuses) == snapshot_state(full_focuses)
        assert len(sparse_stack) == len(full_stack)

    assert_in_sync()

    for _step in range(120):
        op = rng.choice(["add_sparse", "add_full", "undo", "redo"])

        if op in ("add_sparse", "add_full"):
            fid = next_id[0]
            next_id[0] += 1
            # Push to both stacks using their respective snapshot strategy so
            # they remain in sync. The pre-id_set differs (sparse captures
            # empty touched_ids, full captures the pre-state as a full blob)
            # but the post-state is identical and redo restores both to the
            # same place.
            sparse_stack.push("add", sparse_focuses, touched_ids=())
            sparse_focuses[fid] = _mk_focus(fid, f"gen_{fid}")
            full_stack.push("add", full_focuses, touched_ids=None)
            full_focuses[fid] = _mk_focus(fid, f"gen_{fid}")
        elif op == "undo" and sparse_stack:
            r1 = sparse_stack.undo(sparse_focuses, Focus.from_dict)
            r2 = full_stack.undo(full_focuses, Focus.from_dict)
            assert r1 is not None and r2 is not None
            # Sparse and full undo entries can legitimately disagree on
            # `changed_ids`/`removed_ids` for an "add" op: the sparse
            # snapshot doesn't include the newly-added focus, so its
            # `changed_ids` is empty and `removed_ids` carries the diff.
            # The full snapshot includes it, so its `changed_ids` covers
            # every restored key. Both must converge on the same final
            # document state.
            assert r1[0] == r2[0]
        elif op == "redo":
            pre_sparse = snapshot_state(sparse_focuses)
            pre_full = snapshot_state(full_focuses)
            r1 = sparse_stack.redo(sparse_focuses, Focus.from_dict)
            r2 = full_stack.redo(full_focuses, Focus.from_dict)
            assert (r1 is None) == (r2 is None)
            if r1 is not None:
                assert r1[0] == r2[0]
                # Round-trip: undo should restore the pre-redo state. This
                # catches a redo that forgot to push back onto the undo
                # stack.
                sparse_stack.undo(sparse_focuses, Focus.from_dict)
                full_stack.undo(full_focuses, Focus.from_dict)
                assert snapshot_state(sparse_focuses) == pre_sparse
                assert snapshot_state(full_focuses) == pre_full

        assert_in_sync()


def test_undo_refreshes_id_set_cache_for_redo():
    """The redo post-snapshot must read the document's id_set, not a stale
    pre-undo one; otherwise redo would try to "delete" ids the user just
    got back and drop them on the floor."""
    focuses = FocusDocument([_mk_focus(1, "focus_1")])
    stack = UndoStack()
    stack.push("add focus", focuses, touched_ids=())
    focuses.add(_mk_focus(2, "focus_2"))
    assert focuses.id_set == frozenset({1, 2})

    stack.undo(focuses, Focus.from_dict)
    assert focuses.id_set == frozenset({1})

    result = stack.redo(focuses, Focus.from_dict)
    assert result is not None
    # `changed_ids` is the snapshot's full keyset: focus 2 came back AND
    # focus 1 was reloaded by `FocusDocument.load(restored)`. The redraw
    # workload is the union; the important assertion is that focus 2 is in
    # it and nothing was wrongly removed.
    assert result[1] == {1, 2}
    assert result[2] == set()
    assert focuses.id_set == frozenset({1, 2})


def test_redo_with_focus_document_uses_load_replace():
    """When applying a redo entry, calling `load` must replace, not append,
    otherwise every redo would accumulate duplicates of the same focus."""
    focuses = FocusDocument([_mk_focus(1, "focus_1")])
    stack = UndoStack()
    stack.push("edit", focuses, touched_ids=(1,))
    focuses[1].cost = 42

    stack.undo(focuses, Focus.from_dict)
    assert focuses[1].cost == 10
    stack.redo(focuses, Focus.from_dict)
    assert len(focuses) == 1
    assert focuses[1].cost == 42
    assert focuses.validate_indexes()


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


def test_focus_document_undo_batches_index_rebuilds():
    focuses = FocusDocument(_mk_focus(i, f"focus_{i}") for i in range(100))
    stack = UndoStack()
    stack.push("bulk edit", focuses, touched_ids=tuple(focuses))
    for focus in focuses.values():
        focus.name += "_changed"
    focuses.touch()
    before_undo = focuses.revision

    stack.undo(focuses, Focus.from_dict)

    assert focuses.revision == before_undo + 1
    assert focuses.validate_indexes()


def test_pushes_without_structural_change_share_one_id_set():
    """Pure edits must not allocate a fresh per-action set of every id."""
    focuses = FocusDocument(_mk_focus(i, f"focus_{i}") for i in range(1000))
    stack = UndoStack()
    stack.push("edit 1", focuses, touched_ids=(1,))
    stack.push("edit 2", focuses, touched_ids=(2,))
    first_id_set = focuses.id_set

    stack.push("edit 3", focuses, touched_ids=(3,))

    assert focuses.id_set is first_id_set
    assert stack._stack[0][3] is first_id_set
    assert stack._stack[1][3] is first_id_set
    assert stack._stack[2][3] is first_id_set


def test_structural_change_rebuilds_id_set():
    focuses = FocusDocument(_mk_focus(i, f"focus_{i}") for i in range(3))
    before = focuses.id_set

    focuses.add(_mk_focus(9, "focus_9"))

    assert focuses.id_set is not before
    assert focuses.id_set == frozenset({0, 1, 2, 9})

    before = focuses.id_set
    focuses.delete_many((1,))
    assert focuses.id_set is not before
    assert focuses.id_set == frozenset({0, 2, 9})

    before = focuses.id_set
    focuses.load([_mk_focus(7, "focus_7")])
    assert focuses.id_set is not before
    assert focuses.id_set == frozenset({7})

    before = focuses.id_set
    focuses.clear()
    assert focuses.id_set is not before
    assert focuses.id_set == frozenset()


def test_pure_edits_between_pushes_keep_sharing_id_set():
    """Geometry-only changes and field edits must not invalidate the cache;
    invalidating on every mutation would rebuild the set per action again."""
    focuses = FocusDocument(_mk_focus(i, f"focus_{i}") for i in range(5))
    stack = UndoStack()
    stack.push("edit 1", focuses, touched_ids=(1,))
    first_id_set = focuses.id_set

    focuses.move(1, 3, 4)
    focuses.touch()
    focuses.link_prerequisite(2, [1])
    focuses.rename_prefix("focus", "f_")
    stack.push("edit 2", focuses, touched_ids=(2,))

    assert focuses.id_set is first_id_set
    assert stack._stack[0][3] is first_id_set
    assert stack._stack[1][3] is first_id_set


def test_undo_refreshes_id_set_cache():
    """Undo deletes created ids through the document; the next id_set read
    must reflect the restored keys, not the stale pre-undo set."""
    focuses = FocusDocument([_mk_focus(1, "focus_1")])
    stack = UndoStack()

    stack.push("add focus", focuses, touched_ids=())
    focuses.add(_mk_focus(2, "focus_2"))
    stack.undo(focuses, Focus.from_dict)
    assert focuses.id_set == frozenset({1})

    stack.push("full import", focuses)
    focuses.clear()
    focuses.load([_mk_focus(9, "focus_9")])
    stack.undo(focuses, Focus.from_dict)
    assert focuses.id_set == frozenset({1})
    assert focuses.id_set == frozenset(focuses.keys())


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


@pytest.mark.parametrize("touched_ids", [(1,), None])
def test_undo_restores_imported_focus_metadata_without_tk_state(touched_ids):
    focus = _mk_focus(1, "imported")
    focus._raw_gx = 6
    focus._raw_gy = 7
    focus._rel_dx = 2
    focus._rel_dy = 3
    focus._joint_extra = "joint_trigger = { always = yes }"
    focuses = {focus.id: focus}
    stack = UndoStack()
    stack.push("edit imported focus", focuses, touched_ids=touched_ids)

    focus._raw_gx = 60
    focus._raw_gy = 70
    focus._rel_dx = 20
    focus._rel_dy = 30
    focus._joint_extra = ""

    stack.undo(focuses, Focus.from_dict)

    restored = focuses[focus.id]
    assert (
        restored._raw_gx,
        restored._raw_gy,
        restored._rel_dx,
        restored._rel_dy,
        restored._joint_extra,
    ) == (6, 7, 2, 3, "joint_trigger = { always = yes }")
    assert not hasattr(restored, "_items")
    assert not hasattr(restored, "_draw_key")
    assert not hasattr(restored, "_culled")


def test_undo_preserves_imported_joint_focus_export_data():
    parent = _mk_focus(1, "JNT_parent", x=20, y=30)
    focus = _mk_focus(2, "JNT_child", x=22, y=33)
    focus.tree_idx = 1
    focus.relative_position_id = parent.name
    focus._raw_gx = 22
    focus._raw_gy = 33
    focus._rel_dx = 2
    focus._rel_dy = 3
    focus._joint_extra = "joint_trigger = {\n\talways = yes\n}"
    focuses = {parent.id: parent, focus.id: focus}
    stack = UndoStack()
    stack.push("edit imported joint focus", focuses, touched_ids=(focus.id,))

    focus.x = 99
    focus.y = 99
    focus._raw_gx = 99
    focus._raw_gy = 99
    focus._rel_dx = 99
    focus._rel_dy = 99
    focus._joint_extra = ""

    stack.undo(focuses, Focus.from_dict)

    text = export_focus_tree(
        [focuses[focus.id]],
        {
            "tree_id": "JNT_tree",
            "country_tag": "JNT",
            "cfp_x": 0,
            "cfp_y": 0,
            "type": "joint",
            "had_wrapper": False,
            "shared_focuses": [],
            "joint_focuses": [],
        },
        focus_lookup=focuses,
        effect_renderer=lambda _effect: "",
    )

    assert "x = 2" in text
    assert "y = 3" in text
    assert "relative_position_id = JNT_parent" in text
    assert "\tjoint_trigger = {\n\t\talways = yes\n\t}" in text


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


def test_apply_with_corrupt_full_payload_returns_none():
    """A full-snapshot entry whose payload decodes to None must
    short-circuit before touching `focuses`, so the document is left
    untouched and the entry is silently dropped."""
    focuses = {1: _mk_focus(1, "focus_1", cost=10)}
    stack = UndoStack()
    stack._stack.append(("bad", "full", b"not a zlib blob", frozenset({1})))
    pre_cost = focuses[1].cost
    result = stack.undo(focuses, Focus.from_dict)
    assert result is None
    assert focuses[1].cost == pre_cost


def test_decode_full_zlib_error_returns_none():
    assert _decode_full(b"not a zlib blob") is None


def test_decode_full_unicode_error_returns_none():
    payload = zlib.compress(b'{"1": "\x80\x81\x82"}')
    assert _decode_full(payload) is None


def test_decode_full_invalid_json_returns_none():
    payload = zlib.compress(b"{")
    assert _decode_full(payload) is None


def test_decode_full_non_dict_payload_returns_none():
    """Documented contract: 'None if the payload is corrupt.'
    A JSON-valid non-dict payload is corrupted-for-our-purposes and
    must return None, not raise."""
    for payload in (b"null", b"42", b"[1,2]", b'"a string"'):
        assert _decode_full(zlib.compress(payload)) is None
