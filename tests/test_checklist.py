from typing import Any

import pytest

from hoi4cm.ui.checklist import (
    ChecklistItem,
    apply_select_mode,
    default_tree_type,
    is_loadable,
)


class _Var:
    """The get/set half of a Tk variable, which is all the pure helpers use."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


def _item(
    index: int, *, already: bool = False, tree_type: str = "shared"
) -> ChecklistItem:
    checked: Any = _Var(False)
    type_var: Any = _Var(tree_type)
    return ChecklistItem(
        key=f"file_{index:03d}.txt",
        name=f"file_{index:03d}.txt",
        already=already,
        checked=checked,
        type_var=type_var,
    )


@pytest.mark.parametrize(
    "fname,expected",
    [
        ("05_afghanistan.txt", "main"),  # exact boundary
        ("04_afghanistan.txt", "shared"),  # one below
        ("06_afghanistan.txt", "main"),  # one above
        ("5_afghanistan.txt", "main"),
        ("999_afghanistan.txt", "main"),
        ("00_afghanistan.txt", "shared"),
        ("afghanistan.txt", "shared"),  # no numeric prefix
        ("_afghanistan.txt", "shared"),  # underscore but no digits
        ("5foo.txt", "shared"),  # digits but no underscore
    ],
)
def test_default_tree_type_prefix_boundaries(fname: str, expected: str) -> None:
    assert default_tree_type(fname) == expected


def test_is_loadable_truth_table() -> None:
    # (checked, already, type) -> batch-loadable; main trees and
    # already-loaded rows are never loadable
    table = {
        (True, False, "shared"): True,
        (True, False, "joint"): True,
        (True, False, "main"): False,
        (True, True, "shared"): False,
        (True, True, "joint"): False,
        (True, True, "main"): False,
        (False, False, "shared"): False,
        (False, False, "joint"): False,
        (False, False, "main"): False,
        (False, True, "shared"): False,
        (False, True, "joint"): False,
        (False, True, "main"): False,
    }
    for (checked, already, tree_type), expected in table.items():
        item = _item(0, already=already, tree_type=tree_type)
        item.checked.set(checked)
        assert is_loadable(item) is expected


def test_apply_select_mode_presets() -> None:
    items = [
        _item(1, tree_type="main"),
        _item(2, tree_type="shared"),
        _item(3, tree_type="joint"),
        _item(4, tree_type="shared", already=True),
    ]
    apply_select_mode(items, "all")
    assert [i.checked.get() for i in items] == [False, True, True, False]

    apply_select_mode(items, "none")
    assert [i.checked.get() for i in items] == [False, False, False, False]

    items[3].checked.set(True)  # already-loaded row manually re-checked
    apply_select_mode(items, "shared")
    assert [i.checked.get() for i in items] == [False, True, False, True]

    apply_select_mode(items, "joint")
    assert [i.checked.get() for i in items] == [False, False, True, True]
