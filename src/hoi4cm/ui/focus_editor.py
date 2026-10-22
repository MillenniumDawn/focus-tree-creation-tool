"""Persistent contextual focus form and its pending-edit boundary."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any

from hoi4cm.models.sidebar_form import parse_focus_cost, sidebar_values_match_focus
from hoi4cm.ui.focus_list import filter_focus_items
from hoi4cm.ui.theme import BG_CARD, BG_DARK, BG_PANEL, BLUE, TEXT


def reveal_search_result(app: Any) -> None:
    items = filter_focus_items(
        getattr(app, "_focus_list_items", ()), app._lp_search_var.get()
    )
    if items:
        app._select_focus_from_list(items[0].key)


def flush_pending_editor(app: Any, *, autosave: bool = False) -> bool:
    """Commit a valid draft, or keep it visible for correction.

    The form remains the sole owner of its widgets. In particular, an unlocked
    Code tab must be parsed before a selection change can replace those widgets.
    """
    focus = app.selected
    if focus is None:
        return True
    try:
        parse_focus_cost(app._fv_cost.get())
        int(app._fv_x.get())
        int(app._fv_y.get())
    except ValueError, OverflowError:
        if not autosave:
            messagebox.showwarning(
                "Pending focus edits",
                "Correct the cost and position before leaving this focus.",
                parent=app,
            )
        return False
    values = app._read_sidebar_values()
    if values is None or not app.focuses.position_free(
        values.x, values.y, except_id=focus.id
    ):
        if not autosave:
            messagebox.showwarning(
                "Pending focus edits",
                "Enter a focus ID and an unoccupied position "
                "before leaving this focus.",
                parent=app,
            )
        return False
    changed = not sidebar_values_match_focus(focus, values)
    revision = app.focuses.revision
    app._autosave()
    if not sidebar_values_match_focus(focus, values):
        return False
    if changed and app.focuses.revision == revision:
        # Older documents only advance their revision for structural changes.
        app.focuses.touch()
    if not autosave and app._code_edit_mode[0]:
        app._code_edit_btn.invoke()
        if app._code_edit_mode[0]:
            return False
    app._update_statusbar()
    return True


class FocusEditor:
    """Keep the legacy field builders alive in a resizable, hidden-until-used form."""

    def __init__(self, app: Any):
        self.app = app
        self.window = tk.Toplevel(app)
        self.window.withdraw()
        self.window.title("Edit Focus")
        self.window.configure(bg=BG_PANEL)
        self.window.geometry("480x700")
        self.window.minsize(380, 320)
        self.window.transient(app)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<KeyPress>", self._local_shortcuts)
        for sequence in (
            "<Control-n>",
            "<Control-o>",
            "<Control-e>",
            "<Control-d>",
            "<Control-a>",
            "<Control-Shift-s>",
            "<Control-Shift-S>",
            "<F1>",
            "<Delete>",
            "<Left>",
            "<Right>",
            "<Up>",
            "<Down>",
        ):
            self.window.bind(sequence, app.bind(sequence))
        header = tk.Frame(self.window, bg=BG_DARK)
        header.pack(fill="x")
        self.heading = tk.Label(
            header,
            text="Edit Focus",
            bg=BG_DARK,
            fg=TEXT,
            font=("Segoe UI", 11, "bold"),
            padx=10,
            pady=8,
        )
        self.heading.pack(side="left")
        tk.Button(
            header,
            text="Apply & Close",
            command=self.close,
            bg=BG_CARD,
            fg=TEXT,
            highlightcolor=BLUE,
            highlightthickness=2,
        ).pack(side="right", padx=8, pady=4)
        self.tree_panel = tk.Frame(self.window, bg=BG_PANEL)
        self.focus_panel = tk.Frame(self.window, bg=BG_PANEL)
        self.advanced = False
        self.advanced_panel: tk.Frame | None = None
        self.advanced_button: tk.Button | None = None

    def _local_shortcuts(self, event: Any) -> str | None:
        if not event.state & 0x0004:
            return None
        key = event.keysym.lower()
        if key == "s":
            if self.flush():
                self.app._save()
            return "break"
        if key in ("z", "y") and not isinstance(event.widget, tk.Text):
            if self.flush():
                redo = key == "y" or bool(event.state & 0x0001)
                (self.app._redo if redo else self.app._undo)()
            return "break"
        return None

    def flush(self, *, autosave: bool = False) -> bool:
        return flush_pending_editor(self.app, autosave=autosave)

    def open(self, *, tab: str = "Properties") -> None:
        if self.app.selected is None:
            return
        self.tree_panel.pack_forget()
        self.focus_panel.pack(fill="both", expand=True)
        self.heading.config(text=f"Edit Focus: {self.app.selected.name}")
        self.window.title(f"Edit Focus — {self.app.selected.name}")
        if tab in ("Conditions", "Code") and not self.advanced:
            self.toggle_advanced()
        self.app._switch_tab_fn(tab)
        self.window.deiconify()
        self.window.lift()
        self.app._tab_btns[tab][0].focus_set()

    def open_tree_settings(self) -> None:
        if not self.flush():
            return
        self.focus_panel.pack_forget()
        self.tree_panel.pack(fill="both", expand=True)
        self.heading.config(text="Loaded trees & tree settings")
        self.window.title("Tree Settings")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_set()

    def close(self) -> bool:
        if not self.flush():
            return False
        self.window.withdraw()
        self.app.cv.focus_set()
        return True

    def reset(self) -> None:
        self.window.withdraw()
        self.app._focus_actions.dismiss()

    def make_advanced_properties(self, parent: tk.Frame) -> tk.Frame:
        self.advanced_panel = tk.Frame(parent, bg=BG_PANEL)
        return self.advanced_panel

    def finish_build(self) -> None:
        controls = tk.Frame(self.tree_panel, bg=BG_PANEL)
        controls.pack(
            fill="x", padx=8, pady=8, before=self.tree_panel.winfo_children()[0]
        )
        for label, variable in (
            ("Focus tree ID", self.app._tree_id),
            ("Continuous focus X", self.app._cfp_x_var),
            ("Continuous focus Y", self.app._cfp_y_var),
        ):
            tk.Label(controls, text=label, bg=BG_PANEL, fg=TEXT).pack(anchor="w")
            entry = tk.Entry(
                controls,
                textvariable=variable,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=TEXT,
                highlightcolor=BLUE,
                highlightthickness=2,
            )
            entry.pack(fill="x", pady=(0, 5))
            entry.bind("<FocusOut>", self._commit_tree_settings)
            entry.bind("<Return>", self._commit_tree_settings)
        for label, command in (
            ("Load Shared Tree", lambda: self.app._load_extra_tree("shared")),
            ("Load Joint Tree", lambda: self.app._load_extra_tree("joint")),
            ("Load Trees…", self.app._load_all_trees),
            ("Export All Trees", self.app._save_all_trees),
        ):
            tk.Button(
                controls,
                text=label,
                command=command,
                bg=BG_CARD,
                fg=TEXT,
                highlightcolor=BLUE,
                highlightthickness=2,
            ).pack(fill="x", pady=2)
        self.advanced_button = tk.Button(
            self.focus_panel,
            text="Advanced settings ▸",
            command=self.toggle_advanced,
            bg=BG_CARD,
            fg=TEXT,
            highlightcolor=BLUE,
            highlightthickness=2,
            font=("Segoe UI", 10),
            pady=5,
        )
        self.advanced_button.pack(side="bottom", fill="x")
        for name in ("Conditions", "Code"):
            self.app._tab_btns[name][0].master.pack_forget()

    def _commit_tree_settings(self, _event: Any = None) -> None:
        for axis in ("x", "y"):
            value = getattr(self.app, f"_cfp_{axis}_var").get().strip()
            try:
                setattr(self.app, f"_cfp_{axis}", int(value) if value else None)
            except ValueError:
                return
        self.app._update_title()
        self.app._redraw()

    def toggle_advanced(self) -> None:
        self.advanced = not self.advanced
        if self.advanced_panel is not None:
            if self.advanced:
                self.advanced_panel.pack(fill="x")
            else:
                self.advanced_panel.pack_forget()
        for name in ("Conditions", "Code"):
            column = self.app._tab_btns[name][0].master
            if self.advanced:
                column.pack(side="left", expand=True, fill="x")
            else:
                column.pack_forget()
        if not self.advanced and self.app._active_tab.get() in ("Conditions", "Code"):
            self.app._switch_tab_fn("Properties")
        if self.advanced_button is not None:
            self.advanced_button.config(
                text="Advanced settings ▾" if self.advanced else "Advanced settings ▸"
            )


__all__ = ["FocusEditor", "flush_pending_editor", "reveal_search_result"]
