"""Captured-target focus actions presented in the centered spotlight."""

import tkinter as tk
from typing import Any

from hoi4cm.ui.error_report import report_error
from hoi4cm.ui.focus_spotlight import FocusSpotlight

ACTIONS = (
    ("edit_focus", "Edit Focus"),
    ("add_prerequisite", "Add Prerequisite"),
    ("add_effect", "Add Effect"),
    ("add_child", "Add Child"),
    ("duplicate", "Duplicate"),
    ("delete", "Delete"),
)


class FocusActions:
    """Keep presentation and input restrictions separate from existing actions."""

    def __init__(self, app: Any):
        self.app = app
        self.focus_id: int | None = None
        self._view_state: tuple[float, tuple[float, ...]] | None = None
        self._keyboard_focus: tk.Misc | None = None
        self.spotlight = FocusSpotlight(app, ACTIONS, self.invoke, self.dismiss)
        self.bindings = []
        for sequence, callback in (
            ("<Shift-F10>", self._keyboard_show),
            ("<KeyPress-Menu>", self._keyboard_show),
            ("<Escape>", self._escape),
        ):
            self.bindings.append((sequence, app.cv.bind(sequence, callback, add="+")))

    @property
    def blocks_canvas(self) -> bool:
        return self.focus_id is not None

    @property
    def buttons(self) -> list[tk.Button]:
        return self.spotlight.buttons

    @property
    def images(self) -> list[tk.PhotoImage]:
        return self.spotlight.images

    def _keyboard_show(self, event=None):
        selected = self.app.selected
        if selected is not None and not self.app.mutex_mode:
            self.show(selected.id)
        return "break"

    def _escape(self, event=None):
        self.dismiss()
        return "break"

    def show(self, fid):
        self.dismiss()
        if fid not in self.app.focuses or self.app.mutex_mode:
            return
        self.focus_id = fid
        self._view_state = (self.app.zoom, tuple(self.app.offset))
        self._keyboard_focus = self.app.focus_get()
        try:
            self.spotlight.open(self.app.focuses[fid])
        except tk.TclError as exc:
            self.dismiss()
            report_error(
                f"Focus Spotlight could not open. Tk reported: {exc}",
                exc,
                parent=self.app,
            )
            return

    def reflow(self):
        if self.focus_id is None:
            return
        if self.focus_id not in self.app.focuses:
            self.dismiss()
            return
        self.spotlight.reflow()

    def dismiss(self):
        visible = self.focus_id is not None
        self.focus_id = None
        self.spotlight.close()
        state, self._view_state = self._view_state, None
        if state is not None:
            zoom, offset = state
            changed = self.app.zoom != zoom or tuple(self.app.offset) != offset
            self.app.zoom = zoom
            self.app.offset[:] = offset
            if changed:
                self.app._redraw()
        if visible:
            previous, self._keyboard_focus = self._keyboard_focus, None
            if previous is None or not previous.winfo_exists():
                previous = self.app.cv
            previous.focus_force()

    def close(self):
        self.dismiss()
        self.spotlight.dispose()
        for sequence, binding in self.bindings:
            self.app.cv.unbind(sequence, binding)
        self.bindings.clear()

    def invoke(self, action):
        fid = self.focus_id
        self.dismiss()
        focus = self.app.focuses.get(fid)
        if focus is None or action not in {key for key, _ in ACTIONS}:
            return
        if not self.app._focus_editor.flush():
            return
        if self.app._select(focus) is False:
            return
        if self.app.selected is None or self.app.selected.id != fid:
            return
        if action in {"edit_focus", "add_effect"}:
            self.app._focus_editor.open(
                tab="Effects" if action == "add_effect" else "Properties"
            )
        elif action == "add_child":
            self._add_child(focus)
        else:
            getattr(
                self.app,
                {
                    "add_prerequisite": "_pick_prereq",
                    "duplicate": "_duplicate_focus",
                    "delete": "_delete_focus",
                }[action],
            )()

    def _add_child(self, parent):
        app = self.app
        x, y = parent.x, parent.y + 1
        while not app.focuses.position_free(x, y):
            y += 1
        try:
            child = app.focuses.new_focus(x, y)
        except ValueError as exc:
            report_error(str(exc), exc, parent=app)
            return
        child.tree_idx = parent.tree_idx
        child.prereqs = [[parent.id]]
        if app._default_focus_prefix:
            child.name = f"{app._default_focus_prefix}focus_{child.id}"
        trees: list[dict[str, Any]] = app._extra_trees
        tree = trees[parent.tree_idx - 1] if 0 < parent.tree_idx <= len(trees) else None
        if tree is not None:
            app._push_undo("add child", touched_ids=(), tree_state=True)
        else:
            app._push_undo("add child", touched_ids=())
        app.focuses.add(child)
        if tree is not None:
            tree.setdefault("focus_ids", set()).add(child.id)
            app._refresh_loaded_trees_panel()
        app._redraw()
        app._select(child)
        app._invalidate_focus_list_structure()
