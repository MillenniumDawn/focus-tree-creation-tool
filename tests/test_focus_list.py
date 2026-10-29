import pytest

from hoi4cm.ui.focus_list import (
    FocusListItem,
    filter_focus_items,
    row_pool_size,
    visible_row_range,
)


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
