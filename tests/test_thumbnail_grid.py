import tkinter as tk

import pytest

from hoi4cm.ui.thumbnail_grid import (
    ThumbnailItem,
    VirtualThumbnailGrid,
    visible_index_range,
    visible_row_range,
)


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


def test_tk_grid_keeps_only_viewport_tiles_live() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    try:
        root.geometry("600x300")
        grid = VirtualThumbnailGrid(root)
        grid.pack(fill="both", expand=True)
        grid.set_items(
            [
                ThumbnailItem(f"item-{index}", f"/missing/{index}.png")
                for index in range(100_000)
            ]
        )
        root.update()
        grid.refresh()
        initial_live = grid.live_count

        for position in (0.9, 0.5, 0.1, 0.99):
            grid.canvas.yview_moveto(position)
            grid.refresh()
            root.update_idletasks()

        assert initial_live <= 25
        assert grid.live_count <= 25
        assert len(grid.canvas.find_all()) == grid.live_count * 3
        assert grid.pin_count <= grid.live_count
    finally:
        root.destroy()
