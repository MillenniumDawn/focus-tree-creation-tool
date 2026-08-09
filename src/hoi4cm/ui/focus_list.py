from __future__ import annotations

import tkinter as tk
from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from math import ceil, floor
from typing import Protocol

from hoi4cm.ui.theme import BG_PANEL, BLUE, TEXT_DIM


class _Revisioned(Protocol):
    """Minimal shape the cache keys on: a document with a revision counter."""

    revision: int


SELECTED_BG = "#1e2d4a"
SELECTED_FG = "#93c5fd"
HOVER_BG = "#253550"


@dataclass(frozen=True)
class FocusListItem:
    key: Hashable
    name: str
    has_effects: bool = False
    has_broken_prerequisite: bool = False
    name_lower: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name_lower", self.name.lower())


class FocusListCache:
    """Caches the item tuple against a document's identity and revision.

    A project load swaps in a fresh FocusDocument that also starts at
    revision 0, so the cache keys on object identity as well as revision.
    """

    def __init__(self) -> None:
        self._doc: _Revisioned | None = None
        self._revision: int | None = None
        self._items: tuple[FocusListItem, ...] = ()

    def get(
        self,
        doc: _Revisioned,
        build: Callable[[], Iterable[FocusListItem]],
    ) -> tuple[FocusListItem, ...]:
        if self._doc is not doc or self._revision != doc.revision:
            self._items = tuple(build())
            self._doc = doc
            self._revision = doc.revision
        return self._items

    def invalidate(self) -> None:
        """Force the next get() to rebuild, e.g. after a direct effects edit."""
        self._doc = None
        self._revision = None


def filter_focus_items(
    items: Sequence[FocusListItem],
    query: str,
    *,
    placeholder: str = "Search...",
) -> tuple[FocusListItem, ...]:
    normalized = query.strip()
    if not normalized or normalized == placeholder:
        return tuple(items)
    normalized = normalized.lower()
    return tuple(item for item in items if normalized in item.name_lower)


def visible_row_range(
    item_count: int,
    row_height: int,
    top: float,
    viewport_height: int,
    *,
    overscan_rows: int = 2,
) -> range:
    if item_count <= 0 or row_height <= 0 or viewport_height <= 0:
        return range(0)
    first = max(0, floor(top / row_height) - overscan_rows)
    last = min(
        item_count,
        ceil((top + viewport_height) / row_height) + overscan_rows,
    )
    if last <= first:
        return range(0)
    return range(first, last)


def row_pool_size(
    viewport_height: int, row_height: int, *, overscan_rows: int = 2
) -> int:
    if viewport_height <= 0 or row_height <= 0:
        return 0
    return ceil(viewport_height / row_height) + 1 + overscan_rows * 2


class _FocusRow:
    def __init__(
        self,
        master: tk.Canvas,
        on_select: Callable[[Hashable], None],
    ) -> None:
        self.key: Hashable | None = None
        self.selected = False
        self._on_select = on_select
        self.frame = tk.Frame(master, bg=BG_PANEL, cursor="hand2")
        self.bar = tk.Frame(self.frame, bg=BG_PANEL, width=3)
        self.bar.pack(side="left", fill="y")
        self.dot = tk.Label(
            self.frame,
            text="\u25cf",
            bg=BG_PANEL,
            fg="#fbbf24",
            font=("Helvetica", 7),
            padx=2,
        )
        self.dot.pack(side="left")
        self.label = tk.Label(
            self.frame,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Courier", 9),
            anchor="w",
            padx=2,
            pady=4,
        )
        self.label.pack(side="left", fill="both", expand=True)
        for widget in (self.frame, self.bar, self.dot, self.label):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def show(self, item: FocusListItem, *, selected: bool) -> None:
        self.key = item.key
        self.label.configure(text=item.name)
        color = (
            "#ef4444"
            if item.has_broken_prerequisite
            else "#22c55e" if item.has_effects else "#fbbf24"
        )
        self.dot.configure(fg=color)
        self.apply_selection(selected)

    def apply_selection(self, selected: bool) -> None:
        self.selected = selected
        bg = SELECTED_BG if selected else BG_PANEL
        fg = SELECTED_FG if selected else TEXT_DIM
        self._set_background(bg)
        self.bar.configure(bg=BLUE if selected else bg)
        self.label.configure(fg=fg)

    def _set_background(self, color: str) -> None:
        self.frame.configure(bg=color)
        self.dot.configure(bg=color)
        self.label.configure(bg=color)

    def _click(self, _event) -> None:
        if self.key is not None:
            self._on_select(self.key)

    def _enter(self, _event) -> None:
        if not self.selected:
            self._set_background(HOVER_BG)

    def _leave(self, _event) -> None:
        self.apply_selection(self.selected)


class _PooledRow(Protocol):
    """A row widget a pooled list can place on its canvas."""

    frame: tk.Frame


class _PooledList[T: _PooledRow](tk.Frame, ABC):
    """Canvas list that recycles a bounded pool of row widgets.

    Subclasses build rows via _make_row() and bind/release them via
    _render()/_unrender(). set_items() feeds the data; refresh() repaints
    only the rows intersecting the viewport.
    """

    def __init__(
        self,
        master,
        *,
        row_height: int,
        overscan_rows: int,
        background: str,
    ) -> None:
        super().__init__(master, bg=background)
        self.row_height = row_height
        self.overscan_rows = overscan_rows
        self._items: tuple = ()
        self._rows: list[T] = []
        self._row_windows: list[int] = []
        self._refresh_job: str | None = None

        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=0,
            yscrollincrement=row_height,
        )
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self._scrollbar)
        self.canvas.configure(yscrollcommand=self._set_scrollbar)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._configure)
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(event, self._mousewheel)
        self.bind("<Destroy>", self._destroy, add="+")

    @property
    def filtered_count(self) -> int:
        return len(self._items)

    @property
    def pool_size(self) -> int:
        return len(self._rows)

    def set_items(self, items: Sequence) -> None:
        self._items = tuple(items)
        height = len(self._items) * self.row_height
        self.canvas.configure(scrollregion=(0, 0, 0, height))
        self._schedule_refresh()

    def refresh(self) -> None:
        self._refresh_job = None
        if not self.winfo_exists():
            return
        viewport_height = self.canvas.winfo_height()
        self._resize_pool(viewport_height)
        top = self.canvas.canvasy(0)
        visible = visible_row_range(
            len(self._items),
            self.row_height,
            top,
            viewport_height,
            overscan_rows=self.overscan_rows,
        )
        width = self.canvas.winfo_width()
        for slot, row in enumerate(self._rows):
            window = self._row_windows[slot]
            if slot >= len(visible):
                self._unrender(row)
                self.canvas.itemconfigure(window, state="hidden")
                continue
            index = visible.start + slot
            item = self._items[index]
            self._render(row, item, index)
            self.canvas.coords(window, 0, index * self.row_height)
            self.canvas.itemconfigure(window, width=width, state="normal")

    @abstractmethod
    def _make_row(self) -> T:
        """Create one pooled row widget for the canvas."""

    @abstractmethod
    def _render(self, row: T, item, index: int) -> None:
        """Bind row to item at the given list index."""

    @abstractmethod
    def _unrender(self, row: T) -> None:
        """Release a row that scrolled out of the viewport."""

    def _resize_pool(self, viewport_height: int) -> None:
        wanted = row_pool_size(
            viewport_height,
            self.row_height,
            overscan_rows=self.overscan_rows,
        )
        while len(self._rows) < wanted:
            row = self._make_row()
            window = self.canvas.create_window(
                0,
                0,
                window=row.frame,
                anchor="nw",
                height=self.row_height,
                state="hidden",
            )
            self._rows.append(row)
            self._row_windows.append(window)
        while len(self._rows) > wanted:
            row = self._rows.pop()
            window = self._row_windows.pop()
            self.canvas.delete(window)
            row.frame.destroy()

    def _configure(self, _event=None) -> None:
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self._refresh_job is None:
            self._refresh_job = self.after_idle(self.refresh)

    def _set_scrollbar(self, first: float, last: float) -> None:
        self.scrollbar.set(first, last)
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

    def _destroy(self, event) -> None:
        if event.widget is not self or self._refresh_job is None:
            return
        self.after_cancel(self._refresh_job)
        self._refresh_job = None


class VirtualFocusList(_PooledList[_FocusRow]):
    def __init__(
        self,
        master,
        *,
        on_select: Callable[[Hashable], None],
        row_height: int = 27,
        overscan_rows: int = 2,
        background: str = BG_PANEL,
    ) -> None:
        self._on_select = on_select
        self._selected_key: Hashable | None = None
        self._materialized: dict[Hashable, _FocusRow] = {}
        self._structure_version = 0
        super().__init__(
            master,
            row_height=row_height,
            overscan_rows=overscan_rows,
            background=background,
        )

    @property
    def materialized_count(self) -> int:
        return len(self._materialized)

    @property
    def structure_version(self) -> int:
        return self._structure_version

    def invalidate_structure(
        self,
        items: Sequence[FocusListItem],
        *,
        query: str = "",
        placeholder: str = "Search...",
        selected_key: Hashable | None = None,
    ) -> None:
        self._selected_key = selected_key
        self._structure_version += 1
        self.set_items(filter_focus_items(items, query, placeholder=placeholder))

    def update_selection(self, selected_key: Hashable | None) -> int:
        old_key = self._selected_key
        if old_key == selected_key:
            return 0
        self._selected_key = selected_key
        touched = 0
        for key in {old_key, selected_key}:
            row = self._materialized.get(key)
            if row is not None:
                row.apply_selection(key == selected_key)
                touched += 1
        return touched

    def refresh(self) -> None:
        self._materialized.clear()
        super().refresh()

    def _make_row(self) -> _FocusRow:
        return _FocusRow(self.canvas, self._on_select)

    def _render(self, row: _FocusRow, item, index: int) -> None:
        row.show(item, selected=item.key == self._selected_key)
        self._materialized[item.key] = row

    def _unrender(self, row: _FocusRow) -> None:
        row.key = None


__all__ = [
    "FocusListCache",
    "FocusListItem",
    "VirtualFocusList",
    "filter_focus_items",
    "row_pool_size",
    "visible_row_range",
]
