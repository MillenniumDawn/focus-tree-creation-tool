"""Focus action helix with native buttons and captured-target dispatch."""

import math
import tkinter as tk
from pathlib import Path
from typing import Any

from hoi4cm.ui.error_report import report_error
from hoi4cm.ui.theme import BG_CARD, BLUE, TEXT

ACTIONS = (
    ("edit_focus", "Edit Focus"),
    ("add_prerequisite", "Add Prerequisite"),
    ("add_effect", "Add Effect"),
    ("add_child", "Add Child"),
    ("duplicate", "Duplicate"),
    ("delete", "Delete"),
)


def action_positions(
    width, height, cx, cy, button_width, button_height, *, keyboard=False
):
    """Clamp the helix to the viewport; use a compact list on narrow canvases."""
    gap = 6
    wide = not keyboard and width >= 2 * button_width + 64
    menu_width = 2 * button_width + 40 if wide else button_width
    rows = 3 if wide else 6
    menu_height = rows * (button_height + gap) - gap
    if width < menu_width or height < menu_height:
        return []
    left = max(0, min(cx - menu_width / 2, width - menu_width))
    top = max(0, min(cy - menu_height / 2, height - menu_height))
    return [
        (
            left
            + (
                (i % 2) * (button_width + 40)
                + (20 if i % 2 == 0 else -20) * (i // 2 != 1)
                if wide
                else 0
            ),
            top + ((i // 2 if wide else i) * (button_height + gap)),
        )
        for i in range(6)
    ]


class FocusActions:
    """Transient action UI owned by the canvas, without a separate Tk root."""

    def __init__(self, app: Any):
        self.app = app
        self.focus_id: int | None = None
        self.keyboard = False
        self.buttons: list[tk.Button] = []
        self.images: list[tk.PhotoImage] = []
        self.popup: tk.Menu | None = None
        self.bindings = []
        for sequence, callback in (
            ("<Shift-F10>", self._keyboard_show),
            ("<KeyPress-Menu>", self._keyboard_show),
            ("<Escape>", self._escape),
            ("<Configure>", lambda event: self.reflow()),
        ):
            self.bindings.append((sequence, app.cv.bind(sequence, callback, add="+")))

    def _keyboard_show(self, event=None):
        selected = self.app.selected
        if selected is not None and not self.app.mutex_mode:
            self.show(selected.id, keyboard=True)
        return "break"

    def _escape(self, event=None):
        self.dismiss()
        return "break"

    def show(self, fid, keyboard=False):
        """Show actions for this exact focus, never a later selection."""
        self.dismiss()
        if fid not in self.app.focuses or self.app.mutex_mode:
            return
        self.focus_id = fid
        self.keyboard = keyboard
        scaling = float(self.app.cv.tk.call("tk", "scaling")) / (96 / 72)
        icon_size = max(16, round(24 * scaling))
        for action, label in ACTIONS:
            source = tk.PhotoImage(
                master=self.app.cv,
                data=(
                    Path(__file__).with_name("assets") / f"{action}.png"
                ).read_bytes(),
            )
            image = source.subsample(
                max(1, math.ceil(max(source.width(), source.height()) / icon_size))
            )
            self.images.append(image)
            button = tk.Button(
                self.app.cv,
                text=label,
                image=image,
                compound="left",
                anchor="w",
                padx=10,
                pady=7,
                bg=BG_CARD,
                fg="#ef6b73" if action == "delete" else TEXT,
                activebackground="#203442",
                activeforeground=TEXT,
                highlightbackground=BG_CARD,
                highlightcolor=BLUE,
                highlightthickness=2,
                takefocus=True,
                command=lambda key=action: self.invoke(key),
            )
            button.bind("<Escape>", self._escape)
            button.bind(
                "<Return>", lambda event, key=action: self.invoke(key) or "break"
            )
            index = len(self.buttons)
            button.bind("<Down>", lambda event, i=index: self._step(i, 1))
            button.bind("<Up>", lambda event, i=index: self._step(i, -1))
            self.buttons.append(button)
        self.reflow()
        if keyboard and self.popup is None:
            self.buttons[0].focus_set()

    def _step(self, index, delta):
        self.buttons[(index + delta) % len(self.buttons)].focus_set()
        return "break"

    def reflow(self):
        """Re-anchor after canvas zoom, resize, or document changes."""
        if self.focus_id is None:
            return
        focus = self.app.focuses.get(self.focus_id)
        if focus is None:
            self.dismiss()
            return
        width, height = self.app.cv.winfo_width(), self.app.cv.winfo_height()
        bw = max(button.winfo_reqwidth() for button in self.buttons)
        bh = max(button.winfo_reqheight() for button in self.buttons)
        cx, cy = self.app.w2c(focus.x, focus.y)
        positions = action_positions(
            width, height, cx, cy, bw, bh, keyboard=self.keyboard
        )
        if not positions:
            for button in self.buttons:
                button.place_forget()
            self._show_popup(cx, cy)
            return
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        for button, (x, y) in zip(self.buttons, positions, strict=True):
            button.place(x=round(x), y=round(y), width=bw, height=bh)
            button.lift()

    def _show_popup(self, cx, cy):
        if self.popup is not None:
            return
        menu = tk.Menu(self.app.cv, tearoff=False)
        self.popup = menu
        for action, label in ACTIONS:
            menu.add_command(label=label, command=lambda key=action: self.invoke(key))
        menu.bind("<Escape>", self._escape)
        menu.update_idletasks()
        x = min(
            self.app.cv.winfo_rootx() + round(cx),
            menu.winfo_screenwidth() - menu.winfo_reqwidth(),
        )
        y = min(
            self.app.cv.winfo_rooty() + round(cy),
            menu.winfo_screenheight() - menu.winfo_reqheight(),
        )
        menu.post(max(0, x), max(0, y))
        menu.activate(0)
        menu.focus_set()

    def dismiss(self):
        """Discard the menu without changing document state or undo history."""
        visible = self.focus_id is not None
        self.focus_id = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        for button in self.buttons:
            button.destroy()
        self.buttons.clear()
        self.images.clear()
        if visible:
            self.app.cv.focus_set()

    def close(self):
        self.dismiss()
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
        trees = getattr(app, "_extra_trees", ())
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
