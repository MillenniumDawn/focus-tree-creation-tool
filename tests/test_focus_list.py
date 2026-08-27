from collections.abc import Hashable

import pytest

from hoi4cm.ui.focus_list import (
    HOVER_BG,
    SELECTED_BG,
    FocusListCache,
    FocusListItem,
    VirtualFocusList,
    filter_focus_items,
    row_pool_size,
    visible_row_range,
)
from hoi4cm.ui.theme import BG_PANEL


def test_filter_preserves_order_and_matches_names_case_insensitively() -> None:
    items = (
        FocusListItem(1, "Industrial Effort"),
        FocusListItem(2, "Army Reform"),
        FocusListItem(3, "Industrial Expansion"),
    )

    assert [item.key for item in filter_focus_items(items, "INDUSTRIAL")] == [1, 3]
    assert filter_focus_items(items, "  army  ") == (items[1],)


def test_filter_ignores_empty_query_and_search_placeholder() -> None:
    items = (FocusListItem(1, "First"), FocusListItem(2, "Second"))

    assert filter_focus_items(items, "  ") == items
    assert filter_focus_items(items, "Search...") == items
    assert filter_focus_items(items, "Buscar...", placeholder="Buscar...") == items


def test_filter_matches_via_precomputed_lowercase_name() -> None:
    item = FocusListItem(1, "Industrial Effort")
    assert item.name_lower == "industrial effort"
    assert filter_focus_items((item,), "INDUSTRIAL") == (item,)


class _FakeDoc:
    def __init__(self, revision: int) -> None:
        self.revision = revision


def test_focus_list_cache_rebuilds_only_on_document_change() -> None:
    cache = FocusListCache()
    doc = _FakeDoc(0)
    calls = 0

    def build():
        nonlocal calls
        calls += 1
        return [FocusListItem(1, "A")]

    assert cache.get(doc, build) == (FocusListItem(1, "A"),)
    assert calls == 1
    # Same doc, same revision: cached, no rebuild.
    assert cache.get(doc, build) == (FocusListItem(1, "A"),)
    assert calls == 1

    # Revision bump: rebuild.
    doc.revision = 1
    assert cache.get(doc, build) == (FocusListItem(1, "A"),)
    assert calls == 2


def test_focus_list_cache_rebuilds_on_document_swap_at_same_revision() -> None:
    # A project load swaps in a fresh FocusDocument that also starts at
    # revision 0; the cache must not serve stale items from the old doc.
    cache = FocusListCache()
    old_doc = _FakeDoc(0)
    new_doc = _FakeDoc(0)
    calls = 0

    def build():
        nonlocal calls
        calls += 1
        return [FocusListItem(calls, f"item-{calls}")]

    assert cache.get(old_doc, build) == (FocusListItem(1, "item-1"),)
    assert cache.get(new_doc, build) == (FocusListItem(2, "item-2"),)
    assert calls == 2


def test_focus_list_cache_invalidate_forces_rebuild() -> None:
    cache = FocusListCache()
    doc = _FakeDoc(0)
    calls = 0

    def build():
        nonlocal calls
        calls += 1
        return [FocusListItem(calls, f"item-{calls}")]

    assert cache.get(doc, build) == (FocusListItem(1, "item-1"),)
    assert calls == 1
    cache.invalidate()
    assert cache.get(doc, build) == (FocusListItem(2, "item-2"),)
    assert calls == 2


@pytest.mark.parametrize(
    "top,height,expected",
    [
        (0, 54, range(0, 4)),
        (27, 54, range(0, 5)),
        (270, 54, range(8, 14)),
        (2673, 54, range(97, 100)),
    ],
)
def test_visible_row_range_includes_viewport_and_overscan(
    top: int, height: int, expected: range
) -> None:
    assert visible_row_range(100, 27, top, height, overscan_rows=2) == expected


def test_visible_row_range_handles_empty_or_invalid_dimensions() -> None:
    assert not visible_row_range(0, 27, 0, 100)
    assert not visible_row_range(10, 0, 0, 100)
    assert not visible_row_range(10, 27, 0, 0)


def test_visible_row_range_is_empty_when_scrolled_past_the_last_row() -> None:
    # A shrinking list can leave the canvas parked below its new content.
    assert not visible_row_range(10, 27, 1_000, 100, overscan_rows=2)


def test_visible_row_range_never_exceeds_item_count() -> None:
    assert visible_row_range(3, 27, 0, 500, overscan_rows=2) == range(0, 3)


def test_row_pool_size_covers_partial_row_and_overscan() -> None:
    assert row_pool_size(54, 27, overscan_rows=2) == 7
    assert row_pool_size(55, 27, overscan_rows=2) == 8
    assert row_pool_size(0, 27, overscan_rows=2) == 0


@pytest.mark.parametrize("row_height", [1, 27, 28, 100])
@pytest.mark.parametrize("viewport_height", [1, 70, 199, 200, 640])
@pytest.mark.parametrize("overscan_rows", [0, 2, 5])
def test_pool_always_holds_every_visible_row(
    row_height: int, viewport_height: int, overscan_rows: int
) -> None:
    # _PooledList.refresh() renders visible[slot] into _rows[slot] and drops
    # anything past the pool, so a pool smaller than the visible window makes
    # rows silently disappear. The two sizing helpers must stay in step.
    pool = row_pool_size(viewport_height, row_height, overscan_rows=overscan_rows)
    for top in range(0, 5 * row_height + 1):
        visible = visible_row_range(
            10_000,
            row_height,
            top,
            viewport_height,
            overscan_rows=overscan_rows,
        )
        assert len(visible) <= pool, f"top={top}"


@pytest.mark.visible_tk
def test_tk_list_reuses_bounded_pool_and_updates_only_selected_rows(tk_root) -> None:
    selected: list[Hashable] = []
    tk_root.geometry("220x180")
    focus_list = VirtualFocusList(tk_root, on_select=selected.append)
    focus_list.pack(fill="both", expand=True)
    items = [FocusListItem(index, f"Focus {index}") for index in range(100_000)]
    focus_list.invalidate_structure(items, selected_key=0)
    tk_root.update()
    focus_list.refresh()

    pool_size = focus_list.pool_size
    version = focus_list.structure_version
    assert focus_list.materialized_count <= pool_size
    assert pool_size == row_pool_size(
        focus_list.canvas.winfo_height(),
        focus_list.row_height,
        overscan_rows=focus_list.overscan_rows,
    )
    focus_list._materialized[0].label.event_generate("<Button-1>")
    tk_root.update()
    assert selected == [0]

    assert focus_list.update_selection(1) == 2
    assert focus_list.structure_version == version
    assert focus_list.filtered_count == 100_000

    focus_list.canvas.yview_moveto(0.9)
    focus_list.refresh()
    assert focus_list.pool_size == pool_size
    assert focus_list.materialized_count <= pool_size
    assert focus_list.update_selection(90_000) <= 1
    assert focus_list.structure_version == version

    focus_list.invalidate_structure(items, query="Focus 99999")
    focus_list.refresh()
    assert focus_list.filtered_count == 1
    assert focus_list.materialized_count == 1


def test_tk_list_reselecting_the_same_key_touches_no_rows(tk_root) -> None:
    focus_list = VirtualFocusList(tk_root, on_select=lambda _key: None)
    focus_list.pack(fill="both", expand=True)
    focus_list.invalidate_structure(
        [FocusListItem(index, f"Focus {index}") for index in range(10)],
        selected_key=3,
    )
    tk_root.update()

    assert focus_list.update_selection(3) == 0


def test_tk_row_hover_restores_selection_colors_on_leave(tk_root) -> None:
    focus_list = VirtualFocusList(tk_root, on_select=lambda _key: None)
    focus_list.pack(fill="both", expand=True)
    focus_list.invalidate_structure([FocusListItem(1, "Focus")], selected_key=1)
    tk_root.update()
    focus_list.refresh()
    row = focus_list._materialized[1]

    row.frame.event_generate("<Enter>")
    tk_root.update()
    # A selected row keeps its selection color under the cursor.
    assert row.frame.cget("bg") == SELECTED_BG

    focus_list.update_selection(None)
    row.frame.event_generate("<Enter>")
    tk_root.update()
    assert row.frame.cget("bg") == HOVER_BG
    row.frame.event_generate("<Leave>")
    tk_root.update()
    assert row.frame.cget("bg") == BG_PANEL
