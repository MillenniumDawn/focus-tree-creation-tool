from hoi4cm.core.undo import UndoStack
from hoi4cm.focus_tree.operations import (
    build_focus_name_lookup,
    group_focuses_by_tree,
    plan_reference_cleanup,
)
from hoi4cm.models import Focus


def _focus(focus_id, name, *, tree_idx=0, prereqs=None, mutex=None):
    focus = Focus()
    focus.id = focus_id
    focus.name = name
    focus.tree_idx = tree_idx
    focus.prereqs = prereqs or []
    focus.mutex = mutex or []
    return focus


def test_plan_reference_cleanup_removes_all_deleted_references():
    deleted = _focus(1, "deleted")
    kept = _focus(
        3,
        "kept",
        prereqs=[[1, 2], [1], [4, 1, 5]],
        mutex=[1, 2, 1],
    )

    updates = plan_reference_cleanup([deleted, kept], {1, 4})

    assert updates == {3: ([[2], [5]], [2])}
    assert kept.prereqs == [[1, 2], [1], [4, 1, 5]]
    assert kept.mutex == [1, 2, 1]


def test_plan_reference_cleanup_only_returns_changed_survivors():
    deleted = _focus(1, "deleted", prereqs=[[2]], mutex=[2])
    unchanged = _focus(2, "unchanged", prereqs=[[3]], mutex=[4])

    assert plan_reference_cleanup([deleted, unchanged], {1}) == {}


def test_reference_cleanup_plan_preserves_sparse_undo_state():
    first = _focus(1, "first")
    second = _focus(2, "second")
    survivor = _focus(3, "survivor", prereqs=[[1, 2]], mutex=[1, 2])
    focuses = {focus.id: focus for focus in [first, second, survivor]}
    deleted_ids = {1, 2}
    updates = plan_reference_cleanup(focuses.values(), deleted_ids)
    stack = UndoStack()
    stack.push("delete selected", focuses, touched_ids=deleted_ids | updates.keys())

    for focus_id, (prereqs, mutex) in updates.items():
        focuses[focus_id].prereqs = prereqs
        focuses[focus_id].mutex = mutex
    for focus_id in deleted_ids:
        del focuses[focus_id]

    stack.undo(focuses, Focus.from_dict)

    assert set(focuses) == {1, 2, 3}
    assert focuses[3].prereqs == [[1, 2]]
    assert focuses[3].mutex == [1, 2]


def test_group_focuses_by_tree_preserves_focus_order():
    main_a = _focus(1, "main_a")
    extra = _focus(2, "extra", tree_idx=2)
    main_b = _focus(3, "main_b")

    groups = group_focuses_by_tree([main_a, extra, main_b])

    assert groups == {0: [main_a, main_b], 2: [extra]}


def test_build_focus_name_lookup_keeps_first_duplicate():
    first = _focus(1, "duplicate")
    second = _focus(2, "duplicate")

    assert build_focus_name_lookup([first, second]) == {"duplicate": first}
