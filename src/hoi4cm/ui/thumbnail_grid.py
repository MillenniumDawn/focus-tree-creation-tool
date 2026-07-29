from __future__ import annotations

import os
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import ceil, floor

from hoi4cm.core.image import PIL_OK
from hoi4cm.mod.graphics_catalog import AssetRef, FileStamp
from hoi4cm.ui.image_broker import ImageBroker, ImageTransform
from hoi4cm.ui.tasks import get_executor
from hoi4cm.ui.theme import BG_CARD, BG_PANEL, BLUE, BORDER_G, SEL_BG, TEXT_DIM


@dataclass(frozen=True)
class ThumbnailItem:
    key: str
    path: str


def visible_row_range(
    item_count: int,
    columns: int,
    tile_height: int,
    row_gap: int,
    top: float,
    bottom: float,
    *,
    top_padding: int = 0,
    overscan_rows: int = 1,
) -> range:
    if item_count <= 0 or columns <= 0 or bottom < top:
        return range(0)
    stride = tile_height + row_gap
    row_count = (item_count + columns - 1) // columns
    first = ceil((top - top_padding - tile_height) / stride)
    last = floor((bottom - top_padding) / stride)
    first = max(0, first - overscan_rows)
    last = min(row_count - 1, last + overscan_rows)
    if last < first:
        return range(0)
    return range(first, last + 1)


def visible_index_range(
    item_count: int,
    columns: int,
    tile_height: int,
    row_gap: int,
    top: float,
    bottom: float,
    *,
    top_padding: int = 0,
    overscan_rows: int = 1,
) -> range:
    rows = visible_row_range(
        item_count,
        columns,
        tile_height,
        row_gap,
        top,
        bottom,
        top_padding=top_padding,
        overscan_rows=overscan_rows,
    )
    if not rows:
        return range(0)
    return range(rows.start * columns, min(item_count, rows.stop * columns))


class VirtualThumbnailGrid(tk.Frame):
    def __init__(
        self,
        master,
        *,
        columns: int = 5,
        tile_width: int = 110,
        tile_height: int = 100,
        gap: int = 6,
        image_size: tuple[int, int] = (72, 72),
        image_y: int = 44,
        preserve_aspect: bool = False,
        overscan_rows: int = 1,
        label_text: Callable[[ThumbnailItem], str] | None = None,
        on_select: Callable[[ThumbnailItem], None] | None = None,
        on_activate: Callable[[ThumbnailItem], None] | None = None,
        background: str = BG_PANEL,
    ) -> None:
        super().__init__(master, bg=background)
        self.columns = columns
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.gap = gap
        self.image_size = image_size
        self.image_y = image_y
        self.overscan_rows = overscan_rows
        self._label_text = label_text or (lambda item: item.key)
        self._on_select = on_select
        self._on_activate = on_activate
        self._items: tuple[ThumbnailItem, ...] = ()
        self._live: dict[int, tuple[int, int, int]] = {}
        self._selected_index: int | None = None
        self._generation = 0
        self._refresh_job = None
        self._poll_job = None
        self._broker = ImageBroker(
            get_executor(self),
            generation=lambda: self._generation,
            cache_size=512,
            pin_size=256,
        )
        self._transform = ImageTransform(image_size, preserve_aspect=preserve_aspect)

        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=self._scrollbar)
        self.canvas.configure(yscrollcommand=self._set_scrollbar)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar_widget = scrollbar
        self.canvas.bind("<Configure>", self._schedule_refresh)
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(event, self._mousewheel)
        self.bind("<Destroy>", self._on_destroy, add="+")

    @property
    def live_count(self) -> int:
        return len(self._live)

    @property
    def pin_count(self) -> int:
        return self._broker.pin_count

    @property
    def selected_item(self) -> ThumbnailItem | None:
        if self._selected_index is None:
            return None
        return self._items[self._selected_index]

    def set_items(
        self, items: Sequence[ThumbnailItem], *, selected_key: str | None = None
    ) -> None:
        self._clear_live()
        self._generation += 1
        self._items = tuple(items)
        self._selected_index = next(
            (
                index
                for index, item in enumerate(self._items)
                if item.key == selected_key
            ),
            None,
        )
        rows = (len(self._items) + self.columns - 1) // self.columns
        width = self.gap + self.columns * (self.tile_width + self.gap)
        height = self.gap + rows * (self.tile_height + self.gap)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.canvas.yview_moveto(0)
        self._schedule_refresh()

    def refresh(self) -> None:
        self._refresh_job = None
        if not self.winfo_exists():
            return
        top = self.canvas.canvasy(0)
        bottom = self.canvas.canvasy(max(1, self.canvas.winfo_height()))
        wanted = set(
            visible_index_range(
                len(self._items),
                self.columns,
                self.tile_height,
                self.gap,
                top,
                bottom,
                top_padding=self.gap,
                overscan_rows=self.overscan_rows,
            )
        )
        for index in self._live.keys() - wanted:
            self._remove(index)
        for index in sorted(wanted - self._live.keys()):
            self._draw(index)
        self._start_polling()

    def select(self, index: int, *, notify: bool = True) -> None:
        if not 0 <= index < len(self._items):
            return
        old = self._selected_index
        self._selected_index = index
        self._set_selection_style(old)
        self._set_selection_style(index)
        if notify and self._on_select is not None:
            self._on_select(self._items[index])

    def _tile_xy(self, index: int) -> tuple[int, int]:
        column = index % self.columns
        row = index // self.columns
        return (
            self.gap + column * (self.tile_width + self.gap),
            self.gap + row * (self.tile_height + self.gap),
        )

    def _draw(self, index: int) -> None:
        item = self._items[index]
        x, y = self._tile_xy(index)
        selected = index == self._selected_index
        rectangle = self.canvas.create_rectangle(
            x,
            y,
            x + self.tile_width,
            y + self.tile_height,
            fill=SEL_BG if selected else BG_CARD,
            outline=BLUE if selected else BORDER_G,
            width=2,
            tags=("thumbnail", f"thumbnail-{index}"),
        )
        placeholder = self.canvas.create_text(
            x + self.tile_width // 2,
            y + self.image_y,
            text="..." if PIL_OK else "?",
            fill=TEXT_DIM,
            font=("Helvetica", 14 if PIL_OK else 20),
            tags=("thumbnail", f"thumbnail-{index}"),
        )
        label = self.canvas.create_text(
            x + self.tile_width // 2,
            y + self.tile_height - 14,
            text=self._label_text(item),
            fill=TEXT_DIM,
            font=("Helvetica", 7),
            width=self.tile_width - 8,
            tags=("thumbnail", f"thumbnail-{index}"),
        )
        self._live[index] = (rectangle, placeholder, label)
        self._bind_items(index)
        owner = self._owner(index)
        image = self._broker.request(
            self._asset(item),
            item.path,
            transform=self._transform,
            owner=owner,
            callback=lambda photo, i=index, g=self._generation: self._show_image(
                i, g, photo
            ),
        )
        if image is not None:
            self._show_image(index, self._generation, image)

    def _show_image(self, index: int, generation: int, image: object) -> None:
        if generation != self._generation or index not in self._live:
            return
        rectangle, old_image, label = self._live[index]
        if image is None:
            # Decode failed: turn the "..." placeholder into a "?" marker
            # instead of leaving it spinning forever.
            self.canvas.itemconfigure(old_image, text="?")
            return
        self.canvas.delete(old_image)
        x, y = self._tile_xy(index)
        image_id = self.canvas.create_image(
            x + self.tile_width // 2,
            y + self.image_y,
            anchor="center",
            image=image,
            tags=("thumbnail", f"thumbnail-{index}"),
        )
        self._live[index] = (rectangle, image_id, label)
        self._bind_items(index)

    def _asset(self, item: ThumbnailItem) -> AssetRef:
        try:
            stat = os.stat(item.path)
            stamp = FileStamp(stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        except OSError:
            stamp = FileStamp(0, 0, 0)
        return AssetRef("absolute", item.path, stamp, self._generation)

    def _bind_items(self, index: int) -> None:
        for canvas_id in self._live[index]:
            self.canvas.tag_bind(
                canvas_id, "<Button-1>", lambda _event, i=index: self.select(i)
            )
            self.canvas.tag_bind(
                canvas_id,
                "<Double-Button-1>",
                lambda _event, i=index: self._activate(i),
            )

    def _activate(self, index: int) -> None:
        self.select(index)
        if self._on_activate is not None:
            self._on_activate(self._items[index])

    def _set_selection_style(self, index: int | None) -> None:
        if index is None or index not in self._live:
            return
        rectangle = self._live[index][0]
        selected = index == self._selected_index
        self.canvas.itemconfigure(
            rectangle,
            fill=SEL_BG if selected else BG_CARD,
            outline=BLUE if selected else BORDER_G,
        )

    def _owner(self, index: int) -> tuple[int, int, int]:
        return id(self), self._generation, index

    def _remove(self, index: int) -> None:
        ids = self._live.pop(index, ())
        for canvas_id in ids:
            self.canvas.delete(canvas_id)
        self._broker.release(self._owner(index))

    def _clear_live(self) -> None:
        for index in tuple(self._live):
            self._remove(index)

    def _schedule_refresh(self, _event=None) -> None:
        if self._refresh_job is None:
            self._refresh_job = self.after_idle(self.refresh)

    def _set_scrollbar(self, first: str, last: str) -> None:
        self._scrollbar_widget.set(first, last)
        self._schedule_refresh()

    def _scrollbar(self, *args: str) -> None:
        self.canvas.yview(*args)
        self._schedule_refresh()

    def _mousewheel(self, event) -> str:
        number = getattr(event, "num", None)
        delta = getattr(event, "delta", 0)
        up = number == 4 or (number not in (4, 5) and delta > 0)
        self.canvas.yview_scroll(-1 if up else 1, "units")
        self._schedule_refresh()
        return "break"

    def _start_polling(self) -> None:
        if self._poll_job is None and self._broker.pending:
            self._poll_job = self.after(16, self._poll_images)

    def _poll_images(self) -> None:
        self._poll_job = None
        if not self.winfo_exists():
            return
        self._broker.drain()
        self._start_polling()

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        for index in tuple(self._live):
            self._broker.release(self._owner(index))
        self._live.clear()
        self._broker.close()


__all__ = [
    "ThumbnailItem",
    "VirtualThumbnailGrid",
    "visible_index_range",
    "visible_row_range",
]
