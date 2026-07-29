from hoi4cm.focus_tree.operations import (
    build_focus_name_lookup,
    group_focuses_by_tree,
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
