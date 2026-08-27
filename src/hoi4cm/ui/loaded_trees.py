from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from hoi4cm.core.i18n import tr
from hoi4cm.ui.focus_list import _PooledList
from hoi4cm.ui.theme import BG_CARD, BG_DARK, BLUE, BORDER_G, TEXT, TEXT_DIM


@dataclass(frozen=True)
class LoadedTreeRowItem:
    """One rendered row of the sidebar's Loaded Trees panel."""

    tree_idx: int
    badge_text: str
    badge_color: str
    tree_id: str
    summary: str


class _LoadedTreeRow:
    def __init__(
        self,
        master: tk.Canvas,
        on_export: Callable[[int], None],
        on_unload: Callable[[int], None],
    ) -> None:
        self.tree_idx: int | None = None
        self._on_export = on_export
        self._on_unload = on_unload
        self.frame = tk.Frame(
            master,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        self.badge = tk.Label(
            self.frame,
            bg=BG_CARD,
            fg="#000000",
            font=("Courier", 8, "bold"),
            padx=4,
            pady=2,
        )
        self.badge.pack(side="left")
        info_f = tk.Frame(self.frame, bg=BG_CARD)
        info_f.pack(side="left", fill="x", expand=True)
        self.id_label = tk.Label(
            info_f,
            bg=BG_CARD,
            fg=TEXT,
            font=("Courier", 8, "bold"),
            anchor="w",
        )
        self.id_label.pack(fill="x", padx=4, pady=(2, 0))
        self.summary_label = tk.Label(
            info_f,
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 7),
            anchor="w",
        )
        self.summary_label.pack(fill="x", padx=4, pady=(0, 2))
        btn_f = tk.Frame(self.frame, bg=BG_CARD)
        btn_f.pack(side="right", padx=2)
        self.save_btn = tk.Button(
            btn_f,
            text=tr("common.save", "Save"),
            command=self._export,
            bg=BG_CARD,
            fg=BLUE,
            font=("Helvetica", 8),
            relief="flat",
            padx=4,
            pady=1,
            cursor="hand2",
        )
        self.save_btn.pack(pady=(4, 0))
        self.unload_btn = tk.Button(
            btn_f,
            text="✕",
            command=self._unload,
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            relief="flat",
            padx=4,
            pady=1,
            cursor="hand2",
        )
        self.unload_btn.pack(pady=(0, 4))

    def show(self, item: LoadedTreeRowItem) -> None:
        self.tree_idx = item.tree_idx
        self.badge.config(text=f" [{item.badge_text}]", bg=item.badge_color)
        self.id_label.config(text=item.tree_id)
        self.summary_label.config(text=item.summary)

    def clear(self) -> None:
        self.tree_idx = None

    def _export(self) -> None:
        if self.tree_idx is not None:
            self._on_export(self.tree_idx)

    def _unload(self) -> None:
        if self.tree_idx is not None:
            self._on_unload(self.tree_idx)


class VirtualLoadedTreesList(_PooledList[_LoadedTreeRow]):
    """Virtualized sidebar "Loaded Trees" list.

    Rows (badge + tree id + focus count + Save/Unload) are pooled and
    recycled, so a project with thousands of extra trees only ever builds
    the handful of rows that fit the sidebar's fixed-height viewport.
    """

    def __init__(
        self,
        master,
        *,
        on_export: Callable[[int], None],
        on_unload: Callable[[int], None],
        row_height: int = 48,
        overscan_rows: int = 2,
        background: str = BG_DARK,
    ) -> None:
        self._on_export = on_export
        self._on_unload = on_unload
        super().__init__(
            master,
            row_height=row_height,
            overscan_rows=overscan_rows,
            background=background,
        )

    def _make_row(self) -> _LoadedTreeRow:
        return _LoadedTreeRow(self.canvas, self._on_export, self._on_unload)

    def _render(self, row: _LoadedTreeRow, item: LoadedTreeRowItem, index: int) -> None:
        row.show(item)

    def _unrender(self, row: _LoadedTreeRow) -> None:
        row.clear()


__all__ = ["LoadedTreeRowItem", "VirtualLoadedTreesList"]
