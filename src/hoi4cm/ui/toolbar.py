"""Content navigation, project actions, and focus canvas tools."""

import tkinter as tk

from hoi4cm.mod import MOD
from hoi4cm.ui.editor_chrome import EditorChrome
from hoi4cm.ui.theme import BG_CARD, BLUE, BORDER_G, ORANGE, TEXT, TEXT_DIM
from hoi4cm.ui.widgets import Tooltip


def build_toolbar_row2(app, toolbar):
    """Keep content navigation separate from the active focus-tree tools."""
    background = "#090d14"
    app._editor_chrome = EditorChrome(app)

    def row():
        frame = tk.Frame(toolbar, bg=background)
        frame.pack(fill="x")
        return frame

    def button(parent, label, command, *, bg=BG_CARD, fg=TEXT, tip=None):
        widget = app._mk_btn(parent, label, command, bg=bg, fg=fg, padx=8, pady=3)
        widget.configure(takefocus=True, highlightcolor=BLUE, highlightthickness=2)
        widget.pack(side="left", padx=2, pady=3)
        if tip:
            Tooltip(widget, tip)
        return widget

    def separator(parent):
        widget = tk.Frame(parent, bg=BORDER_G, width=1, height=20)
        widget.pack(side="left", padx=5)
        return widget

    context = row()
    app._editor_context_lbl = tk.Label(
        context,
        text="Focus Trees",
        bg=background,
        fg=TEXT,
        padx=8,
        font=("Helvetica", 10, "bold"),
    )
    separator(context)
    button(context, "Save Project", app._save, bg="#163e2b")
    button(context, "Validate", app._validate_tree, bg="#26375a")
    button(context, "Export", app._export, bg="#503818")
    app._editor_save_lbl = tk.Label(
        context, text="Saved", bg=background, fg=TEXT_DIM, padx=8
    )
    app._editor_save_lbl.pack(side="left")
    app._editor_validation_lbl = tk.Label(
        context, text="Validation: not run", bg=background, fg=TEXT_DIM, padx=4
    )
    app._editor_validation_lbl.pack(side="left")
    app._editor_context_lbl.pack(side="right", padx=8)


def build_canvas_toolbar(app, toolbar):
    """Keep canvas tools beside the project sidebar."""
    background = "#090d14"
    chrome = app._editor_chrome

    def row():
        frame = tk.Frame(toolbar, bg=background)
        frame.pack(fill="x")
        return frame

    def button(parent, label, command, *, bg=BG_CARD, fg=TEXT, tip=None):
        widget = app._mk_btn(parent, label, command, bg=bg, fg=fg, padx=8, pady=3)
        widget.configure(takefocus=True, highlightcolor=BLUE, highlightthickness=2)
        widget.pack(side="left", padx=2, pady=3)
        if tip:
            Tooltip(widget, tip)
        return widget

    def separator(parent):
        widget = tk.Frame(parent, bg=BORDER_G, width=1, height=20)
        widget.pack(side="left", padx=5)
        return widget

    tools = row()
    app._sidebar_toggle_btn = button(
        tools, "Sidebar", app._toggle_focus_list, tip="Collapse or restore sidebar (F)"
    )
    app._sidebar_toggle_btn.config(
        image=app._project_sidebar.collapse_icon, compound="left"
    )
    app._add_focus_btn = button(tools, "+ Focus", app._add_focus, bg="#1e3a6e")
    app._conn_btn = button(tools, "Prereq", app._pick_prereq)
    app._mutex_btn = button(tools, "Mutex", app._toggle_mutex, fg=ORANGE)
    separator(tools)
    button(
        tools,
        "Search Focuses",
        chrome.search,
        tip="Open the focus list and search by focus ID or name.",
    )
    button(tools, "Reveal Selected", chrome.reveal)
    button(tools, "Focus Actions", chrome.actions)
    separator(tools)
    button(tools, "Tree Settings", lambda: app._focus_editor.open_tree_settings())
    app._additional_income_btn = button(
        tools, "Add Income", app._additional_income_wizard, fg="#4ade80", bg="#0d2b1a"
    )
    app._additional_income_separator = separator(tools)
    if not MOD.is_md:
        app._additional_income_btn.pack_forget()

    view = row()
    button(view, "Fit", app._fit_all)
    button(view, "−", lambda: chrome.zoom(1 / 1.2), tip="Zoom out")
    app._editor_zoom_lbl = tk.Label(view, text="100%", width=5, bg=background, fg=TEXT)
    app._editor_zoom_lbl.pack(side="left")
    button(view, "+", lambda: chrome.zoom(1.2), tip="Zoom in")
    separator(view)
    app._msel_btn = button(view, "Multi", app._toggle_multisel, bg="#1a1a2e")
    button(view, "Delete Selected", app._delete_selected, bg="#4a1010")
    button(view, "Clear All", app._clear_all, bg="#7f1d1d")
    app._coord_lbl = tk.Label(
        view,
        text="  x=0  y=0  ",
        bg=background,
        fg=TEXT_DIM,
        font=("Courier", 9),
        padx=4,
    )
    app._coord_lbl.pack(side="right", padx=4)
    Tooltip(app._coord_lbl, "Cursor position on the focus grid")
    for frame in (tools, view):
        _wrap_commands(app, frame)


def _wrap_commands(app, frame):
    """Wrap real controls at narrow widths, preserving keyboard access."""
    widgets = frame.winfo_children()

    previous = None
    frame.pack_propagate(False)

    def reflow(event=None):
        nonlocal previous
        signature = frame.winfo_width(), MOD.is_md
        if signature == previous:
            return
        previous = signature
        x, y, height = 3, 3, 0
        for widget in widgets:
            widget.pack_forget()
            widget.place_forget()
            if widget is app._additional_income_btn and not MOD.is_md:
                continue
            width = widget.winfo_reqwidth()
            if x > 3 and x + width + 3 > frame.winfo_width():
                x, y, height = 3, y + height + 6, 0
            widget.place(x=x, y=y)
            x += width + 6
            height = max(height, widget.winfo_reqheight())
        frame.configure(height=y + height + 3)

    frame.bind("<Configure>", reflow)
    if app._additional_income_btn in widgets:
        app._refresh_canvas_commands = reflow


__all__ = ["build_canvas_toolbar", "build_toolbar_row2"]
