from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from hoi4cm.ui.focus_list import _PooledList
from hoi4cm.ui.theme import BG_CARD, BG_DARK, BORDER_G, TEXT, TEXT_DIM

LOADED_BG = "#1a1f2e"
LOADED_FG = "#4ade80"
LOADED_MARKER = " (loaded)"


@dataclass
class ChecklistItem:
    """One selectable file row; Tk vars carry the live checkbox/type state."""

    key: Hashable
    name: str
    already: bool
    checked: tk.BooleanVar
    type_var: tk.StringVar


def default_tree_type(fname: str) -> str:
    """Filename prefix convention: `NN_` prefixes with NN >= 5 are main trees."""
    m = re.match(r"^(\d+)_", fname)
    if m:
        # group(1) is all digits by the regex, so int() cannot fail
        return "main" if int(m.group(1)) >= 5 else "shared"
    return "shared"


def is_loadable(item: ChecklistItem) -> bool:
    """A row is batch-loadable when checked, not already loaded, and not a main tree."""
    return item.checked.get() and not item.already and item.type_var.get() != "main"


def apply_select_mode(items: Sequence[ChecklistItem], mode: str) -> None:
    """Apply a dialog preset: "all" (Shared+Joint), "none", "shared", "joint".
    Already-loaded rows are never selected; "none" clears them too.
    """
    for item in items:
        if mode == "none":
            item.checked.set(False)
        elif not item.already:
            tree_type = item.type_var.get()
            if mode == "all":
                item.checked.set(tree_type != "main")
            elif mode == "shared":
                item.checked.set(tree_type == "shared")
            elif mode == "joint":
                item.checked.set(tree_type == "joint")


class _ChecklistRow:
    def __init__(
        self,
        master: tk.Canvas,
        type_choices: Sequence[tuple[str, str, str]],
        loaded_marker: str,
    ) -> None:
        self.key: Hashable | None = None
        self._loaded_marker = loaded_marker
        self.frame = tk.Frame(
            master,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        self._pooled_checked = tk.BooleanVar()
        self._pooled_type = tk.StringVar()
        self.checkbox = tk.Checkbutton(
            self.frame,
            variable=self._pooled_checked,
            bg=BG_CARD,
            fg=TEXT,
            selectcolor=BG_DARK,
            activebackground=BG_CARD,
            relief="flat",
        )
        self.checkbox.pack(side="left", padx=4)
        self.name_label = tk.Label(
            self.frame,
            bg=BG_CARD,
            fg=TEXT,
            font=("Courier", 8),
            anchor="w",
        )
        self.name_label.pack(side="left", fill="x", expand=True, padx=2)
        self.marker = tk.Label(
            self.frame,
            bg=BG_CARD,
            fg=LOADED_FG,
            font=("Helvetica", 8, "italic"),
        )
        self.marker.pack(side="left")
        type_frame = tk.Frame(self.frame, bg=BG_CARD)
        type_frame.pack(side="right", padx=4)
        self.type_buttons = []
        for label, value, color in type_choices:
            btn = tk.Radiobutton(
                type_frame,
                text=label,
                variable=self._pooled_type,
                value=value,
                bg=BG_CARD,
                fg=color,
                selectcolor=BG_DARK,
                activebackground=BG_CARD,
                font=("Helvetica", 8),
                relief="flat",
            )
            btn.pack(side="left")
            self.type_buttons.append(btn)
        self._palette = [
            self.frame,
            self.checkbox,
            self.name_label,
            self.marker,
            type_frame,
            *self.type_buttons,
        ]

    def show(self, item: ChecklistItem) -> None:
        self.key = item.key
        bg = LOADED_BG if item.already else BG_CARD
        self._set_background(bg)
        state = "disabled" if item.already else "normal"
        self.checkbox.config(variable=item.checked, state=state)
        self.name_label.config(text=item.name, fg=TEXT_DIM if item.already else TEXT)
        self.marker.config(text=self._loaded_marker if item.already else "")
        for btn in self.type_buttons:
            btn.config(variable=item.type_var, state=state)

    def clear(self) -> None:
        self.key = None

    def _set_background(self, color: str) -> None:
        for widget in self._palette:
            widget.configure(bg=color)


class VirtualChecklist(_PooledList):
    """Virtualized checklist over a scrolling canvas.

    Rows (checkbox + name + type radios) are pooled and recycled, so a
    dialog listing thousands of candidate files only ever builds the
    handful of rows that fit the viewport.
    """

    def __init__(
        self,
        master,
        *,
        type_choices: Sequence[tuple[str, str, str]],
        loaded_marker: str = LOADED_MARKER,
        row_height: int = 28,
        overscan_rows: int = 2,
        background: str = BG_DARK,
    ) -> None:
        self._type_choices = tuple(type_choices)
        self._loaded_marker = loaded_marker
        super().__init__(
            master,
            row_height=row_height,
            overscan_rows=overscan_rows,
            background=background,
        )

    def _make_row(self) -> _ChecklistRow:
        return _ChecklistRow(self.canvas, self._type_choices, self._loaded_marker)

    def _render(self, row, item, index: int) -> None:
        row.show(item)

    def _unrender(self, row) -> None:
        row.clear()


__all__ = [
    "ChecklistItem",
    "VirtualChecklist",
    "apply_select_mode",
    "default_tree_type",
    "is_loadable",
]
