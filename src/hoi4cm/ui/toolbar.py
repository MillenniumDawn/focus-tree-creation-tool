"""Content navigation, project actions, and focus canvas tools."""

import tkinter as tk

from hoi4cm.mod import MOD
from hoi4cm.ui.editor_chrome import EditorChrome
from hoi4cm.ui.theme import BG_CARD, BLUE, BORDER_G, ORANGE, TEXT, TEXT_DIM
from hoi4cm.ui.widgets import Tooltip


def build_toolbar_row2(app, toolbar):
    """Keep content navigation separate from the active focus-tree tools."""
    background = "#090d14"
    chrome = app._editor_chrome = EditorChrome(app)

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

    navigation = row()
    tk.Label(navigation, text="Content", bg=background, fg=TEXT_DIM, padx=8).pack(
        side="left"
    )
    for label, command in (
        ("Focus Trees", None),
        ("Events", app._event_wizard),
        ("Decisions", app._decision_wizard),
        ("Ideas", app._national_spirit_wizard),
        ("Dynamic Modifiers", app._dyn_mod_wizard),
    ):
        chrome.navigation_buttons[label] = button(
            navigation,
            label,
            lambda label=label, command=command: chrome.navigate(label, command),
        )

    context = row()
    app._editor_context_lbl = tk.Label(
        context,
        text="Focus Trees",
        bg=background,
        fg=TEXT,
        padx=8,
        font=("Helvetica", 10, "bold"),
    )
    app._editor_context_lbl.pack(side="left")
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

    tools = row()
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
    tk.Label(view, text="Cursor:", bg=background, fg=TEXT_DIM).pack(side="right")


__all__ = ["build_toolbar_row2"]
