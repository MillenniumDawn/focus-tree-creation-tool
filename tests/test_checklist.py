import tkinter as tk

import pytest

from hoi4cm.ui.checklist import (
    ChecklistItem,
    VirtualChecklist,
    apply_select_mode,
    default_tree_type,
    is_loadable,
)
from hoi4cm.ui.focus_list import row_pool_size
from hoi4cm.ui.theme import TEXT_DIM

TYPE_CHOICES = [
    ("Main", "main", "#6b7280"),
    ("Shared", "shared", "#f59e0b"),
    ("Joint", "joint", "#a855f7"),
]


def _item(
    index: int, *, already: bool = False, tree_type: str = "shared"
) -> ChecklistItem:
    return ChecklistItem(
        key=f"file_{index:03d}.txt",
        name=f"file_{index:03d}.txt",
        already=already,
        checked=tk.BooleanVar(value=False),
        type_var=tk.StringVar(value=tree_type),
    )


def _count_widgets(widget) -> int:
    return 1 + sum(_count_widgets(w) for w in widget.winfo_children())


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
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
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
    finally:
        root.destroy()


def test_apply_select_mode_presets() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
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
    finally:
        root.destroy()


def test_tk_checklist_reuses_bounded_pool_and_renders_item_state() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("340x200")
        checklist = VirtualChecklist(root, type_choices=TYPE_CHOICES)
        checklist.pack(fill="both", expand=True)
        items = [_item(i) for i in range(5_000)]
        checklist.set_items(items)
        root.update()
        checklist.refresh()

        pool = checklist.pool_size
        assert pool == row_pool_size(
            checklist.canvas.winfo_height(),
            checklist.row_height,
            overscan_rows=checklist.overscan_rows,
        )
        assert pool < 30  # 5,000 items rendered through a bounded pool
        assert checklist.filtered_count == 5_000
        # The issue's 5,500-widget blowup: 5,000 files must not scale widgets
        assert _count_widgets(checklist) < 250

        # Top rows are bound to the first items, normal rows undecorated
        row0 = checklist._rows[0]
        assert row0.key == items[0].key
        assert row0.checkbox.cget("state") == "normal"
        assert row0.name_label.cget("text") == items[0].name
        assert row0.marker.cget("text") == ""

        # An already-loaded item renders dimmed with its controls disabled
        items[1].already = True
        checklist.refresh()
        row1 = checklist._rows[1]
        assert row1.key == items[1].key
        assert row1.checkbox.cget("state") == "disabled"
        assert row1.name_label.cget("fg") == TEXT_DIM
        assert row1.marker.cget("text") == " (loaded)"
        assert all(b.cget("state") == "disabled" for b in row1.type_buttons)

        # The row's checkbox is bound to the item's var, and clicks write back
        assert str(row0.checkbox.cget("variable")) == str(items[0].checked)
        row0.checkbox.invoke()
        assert items[0].checked.get() is True
        row0.checkbox.invoke()
        assert items[0].checked.get() is False

        # Scrolling recycles the same pool; state survives a round trip
        checklist.canvas.yview_moveto(0.5)
        checklist.refresh()
        assert checklist.pool_size == pool
        assert checklist._rows[0].key != items[0].key

        checklist.canvas.yview_moveto(0.0)
        checklist.refresh()
        assert checklist._rows[0].key == items[0].key
        # Recycled row rebinds to the item's state, not a stale one
        assert str(checklist._rows[0].checkbox.cget("variable")) == str(
            items[0].checked
        )
        assert checklist._rows[1].key == items[1].key
        assert checklist._rows[1].checkbox.cget("state") == "disabled"
    finally:
        root.destroy()


def test_tk_checklist_type_radios_rebind_and_write_through() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("340x200")
        checklist = VirtualChecklist(root, type_choices=TYPE_CHOICES)
        checklist.pack(fill="both", expand=True)
        items = [_item(i) for i in range(100)]
        items[0].type_var.set("joint")
        checklist.set_items(items)
        root.update()
        checklist.refresh()

        row0 = checklist._rows[0]
        buttons = row0.type_buttons
        assert len(buttons) == 3
        assert [b.cget("value") for b in buttons] == ["main", "shared", "joint"]
        # All radios bind to the item's type var
        assert all(str(b.cget("variable")) == str(items[0].type_var) for b in buttons)
        # Clicking a radio writes through to the item's var
        buttons[0].invoke()
        assert items[0].type_var.get() == "main"

        # A recycled row rebinds to the next item's var, not the old one
        items[1].type_var.set("joint")
        checklist._rows[0].show(items[1])
        assert all(str(b.cget("variable")) == str(items[1].type_var) for b in buttons)
        buttons[1].invoke()
        assert items[1].type_var.get() == "shared"
        assert items[0].type_var.get() == "main"
    finally:
        root.destroy()


def test_tk_checklist_custom_loaded_marker() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("340x200")
        checklist = VirtualChecklist(
            root,
            type_choices=TYPE_CHOICES,
            loaded_marker="（已加载）",
        )
        checklist.pack(fill="both", expand=True)
        checklist.set_items([_item(0), _item(1, already=True)])
        root.update()
        checklist.refresh()

        assert checklist._rows[0].marker.cget("text") == ""
        assert checklist._rows[1].marker.cget("text") == "（已加载）"
    finally:
        root.destroy()


def test_tk_checklist_shrinks_pool_on_smaller_viewport() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("340x200")
        checklist = VirtualChecklist(root, type_choices=TYPE_CHOICES)
        checklist.pack(fill="both", expand=True)
        checklist.set_items([_item(i) for i in range(5_000)])
        root.update()
        checklist.refresh()
        tall_pool = checklist.pool_size
        assert tall_pool > 0

        root.geometry("340x70")
        root.update()
        checklist.refresh()
        assert checklist.pool_size < tall_pool
        assert checklist.pool_size == row_pool_size(
            checklist.canvas.winfo_height(),
            checklist.row_height,
            overscan_rows=checklist.overscan_rows,
        )
    finally:
        root.destroy()


def test_tk_checklist_empty_items_renders_no_rows() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("340x200")
        checklist = VirtualChecklist(root, type_choices=TYPE_CHOICES)
        checklist.pack(fill="both", expand=True)
        checklist.set_items([])
        root.update()
        checklist.refresh()

        assert checklist.filtered_count == 0
        assert all(row.key is None for row in checklist._rows)
    finally:
        root.destroy()
