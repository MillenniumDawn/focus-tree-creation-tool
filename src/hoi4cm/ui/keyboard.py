"""Keyboard actions shared by the Tk application shell."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from typing import Protocol

from hoi4cm.core import tr
from hoi4cm.models import Focus


class NudgeDocument(Protocol):
    """Document operations needed to nudge one or more focuses."""

    occupied_positions: dict[tuple[int, int], set[int]]

    def __getitem__(self, focus_id: int) -> Focus: ...

    def keys(self) -> Iterable[int]: ...

    def move(
        self, focus_id: int, x: int, y: int, *, allow_occupied: bool = False
    ) -> bool: ...


class KeyboardNudgeHost(Protocol):
    """Small view of the App state used by the arrow-key action."""

    selected: Focus | None
    _multi_sel: set[int]
    _fv_x: StringValue
    _fv_y: StringValue
    focuses: NudgeDocument

    def focus_get(self) -> tk.Misc | None: ...

    def _push_undo(self, label: str, *, touched_ids: set[int]) -> None: ...

    def _redraw(self) -> None: ...

    def _hint(self, message: str) -> None: ...


class StringValue(Protocol):
    """String-backed Tk value interface used for the two coordinate fields."""

    def set(self, value: str) -> None: ...


def nudge_selection(app: KeyboardNudgeHost, dx: int, dy: int) -> None:
    """Move the current selection one grid cell, preserving document undo."""
    widget = app.focus_get()
    # Keep normal keyboard navigation in text controls and listboxes. These
    # can live inside the main window, so their arrow keys reach this binding
    # through Tk's toplevel bind tag as well.
    if isinstance(widget, (tk.Text, tk.Entry, tk.Listbox)):
        return
    focus_ids = set(app._multi_sel)
    if not focus_ids and app.selected:
        focus_ids.add(app.selected.id)
    focus_ids.intersection_update(app.focuses.keys())
    if not focus_ids:
        return

    targets = {
        focus_id: (app.focuses[focus_id].x + dx, app.focuses[focus_id].y + dy)
        for focus_id in focus_ids
    }
    # Export coordinates for a relative-positioned focus are offsets from its
    # named parent. When the parent moves with it, preserve the child's stored
    # raw and relative coordinates; FocusDocument.move() otherwise increments
    # both metadata pairs by the child's canvas movement.
    name_to_id: dict[str, int] = {}
    for focus_id in app.focuses.keys():
        name_to_id.setdefault(app.focuses[focus_id].name, focus_id)
    moving_ids = set(targets)
    relative_metadata: dict[
        int, tuple[int | None, int | None, int | None, int | None]
    ] = {}
    for focus_id in moving_ids:
        focus = app.focuses[focus_id]
        parent_id = name_to_id.get(focus.relative_position_id or "")
        if parent_id is not None and parent_id in moving_ids:
            relative_metadata[focus_id] = tuple(
                getattr(focus, attribute, None)
                for attribute in ("_raw_gx", "_raw_gy", "_rel_dx", "_rel_dy")
            )
    for x, y in targets.values():
        blockers = app.focuses.occupied_positions.get((x, y), set()) - moving_ids
        if blockers:
            return

    app._push_undo(
        "nudge focus" if len(focus_ids) == 1 else "nudge focuses",
        touched_ids=focus_ids,
    )
    for focus_id, (x, y) in targets.items():
        app.focuses.move(focus_id, x, y, allow_occupied=True)
    for focus_id, values in relative_metadata.items():
        focus = app.focuses[focus_id]
        for attribute, value in zip(
            ("_raw_gx", "_raw_gy", "_rel_dx", "_rel_dy"), values
        ):
            setattr(focus, attribute, value)
    app._redraw()
    if app.selected and app.selected.id in moving_ids:
        app.selected = app.focuses[app.selected.id]
        app._fv_x.set(str(app.selected.x))
        app._fv_y.set(str(app.selected.y))
    app._hint(
        tr(
            "hint.focus_nudged",
            "Moved selection {direction}.",
            direction={(-1, 0): "left", (1, 0): "right", (0, -1): "up", (0, 1): "down"}[
                (dx, dy)
            ],
        )
    )


__all__ = ["KeyboardNudgeHost", "NudgeDocument", "StringValue", "nudge_selection"]
