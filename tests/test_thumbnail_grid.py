import pytest

from hoi4cm.ui.thumbnail_grid import visible_index_range, visible_row_range


def test_visible_range_uses_intersecting_rows() -> None:
    assert visible_row_range(100, 5, 100, 6, 0, 100, top_padding=6) == range(0, 2)
    assert visible_index_range(
        100, 5, 100, 6, 107, 211, top_padding=6, overscan_rows=0
    ) == range(5, 10)


def test_visible_range_includes_touching_tile_edge() -> None:
    assert visible_row_range(
        100, 5, 100, 6, 106, 106, top_padding=6, overscan_rows=0
    ) == range(0, 1)


def test_visible_range_clamps_overscan_and_partial_last_row() -> None:
    assert visible_index_range(
        12, 5, 100, 6, 218, 318, top_padding=6, overscan_rows=1
    ) == range(5, 12)
    assert visible_index_range(
        12, 5, 100, 6, 218, 318, top_padding=6, overscan_rows=0
    ) == range(10, 12)


@pytest.mark.parametrize(
    "item_count,columns,top,bottom",
    [(0, 5, 0, 100), (10, 0, 0, 100), (10, 5, 100, 0), (10, 5, 1000, 1100)],
)
def test_visible_range_is_empty_outside_content(
    item_count: int, columns: int, top: float, bottom: float
) -> None:
    assert not visible_index_range(item_count, columns, 100, 6, top, bottom)
