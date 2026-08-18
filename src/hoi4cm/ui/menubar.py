# ruff: noqa: E501, B023
"""Top menu bar: File/Edit/View/Tools dropdowns, error-log button, mod label."""

import tkinter as tk

from hoi4cm.core.i18n import tr
from hoi4cm.mod import MOD
from hoi4cm.ui.theme import BG_CARD, BG_DARK, BORDER_G, TEXT, TEXT_DIM
from hoi4cm.ui.widgets import Tooltip


def build_menubar(app, toolbar):
    """Build menu bar with File/Edit/View/Tools dropdowns."""
    # ── MENU BAR ──────────────────────────────────────────────
    menubar = tk.Frame(toolbar, bg="#080b10", height=30)
    menubar.pack(fill="x")
    menubar.pack_propagate(False)
    tk.Frame(menubar, bg=BORDER_G, height=1).place(relx=0, rely=1, relwidth=1)

    # Branding
    tk.Label(
        menubar,
        text=tr("app.brand", "HOI4 CONTENT MAKER"),
        bg="#080b10",
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        padx=12,
    ).pack(side="left")
    tk.Frame(menubar, bg=BORDER_G, width=1, height=18).pack(side="left", padx=2)

    # ── Menu helpers ──────────────────────────────────────────
    open_menu_win = None
    open_menu_btn = None

    def _close_menu():
        nonlocal open_menu_win, open_menu_btn
        w = open_menu_win
        b = open_menu_btn
        if w:
            try:
                w.destroy()
            except tk.TclError:
                pass
        open_menu_win = None
        open_menu_btn = None
        if b:
            try:
                b.config(bg="#080b10", fg=TEXT_DIM)
            except tk.TclError, RuntimeError, AttributeError:
                pass

    def _menu_btn(parent, label, items):
        btn = tk.Button(
            parent,
            text=label,
            bg="#080b10",
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=10,
            pady=0,
            cursor="hand2",
            bd=0,
            activebackground="#1a2030",
            activeforeground=TEXT,
        )
        btn.pack(side="left")

        def _open(b=btn):
            nonlocal open_menu_win, open_menu_btn
            # If this menu is already open, close it
            if open_menu_btn is b:
                _close_menu()
                return
            _close_menu()
            b.config(bg="#1a2030", fg=TEXT)
            # Build a Toplevel dropdown
            b.update_idletasks()
            rx = b.winfo_rootx()
            ry = b.winfo_rooty() + b.winfo_height()
            drop = tk.Toplevel(app)
            drop.wm_overrideredirect(True)
            drop.configure(bg="#0d1218")
            drop.attributes("-topmost", True)
            # build contents
            inner = tk.Frame(
                drop,
                bg="#0d1218",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            inner.pack(fill="both", expand=True)
            min_w = 340
            for item in items:
                if item is None:
                    tk.Frame(inner, bg=BORDER_G, height=1).pack(
                        fill="x", padx=0, pady=2
                    )
                elif isinstance(item, str):
                    tk.Label(
                        inner,
                        text=item.upper(),
                        bg="#0d1218",
                        fg=TEXT_DIM,
                        font=("Helvetica", 8, "bold"),
                        anchor="w",
                        padx=16,
                        pady=3,
                    ).pack(fill="x")
                else:
                    lbl_i, cmd_i, *rest = item
                    kbd = rest[0] if len(rest) > 0 else ""
                    tip_txt = rest[1] if len(rest) > 1 else ""
                    item_bg_n = "#0d1218"
                    item_bg_h = "#141c2a"
                    row_f = tk.Frame(inner, bg=item_bg_n)
                    row_f.pack(fill="x")

                    def _make_cmd(c=cmd_i):
                        def _do():
                            _close_menu()
                            if c:
                                app.after(10, c)

                        return _do

                    # main label + kbd shortcut row
                    top_row = tk.Frame(row_f, bg=item_bg_n)
                    top_row.pack(fill="x")
                    ib = tk.Button(
                        top_row,
                        text=lbl_i,
                        command=_make_cmd(),
                        bg=item_bg_n,
                        fg=TEXT_DIM,
                        font=("Helvetica", 9, "bold"),
                        relief="flat",
                        anchor="w",
                        padx=16,
                        pady=4,
                        cursor="hand2",
                        bd=0,
                        activebackground=item_bg_h,
                        activeforeground=TEXT,
                    )
                    ib.pack(side="left", fill="x", expand=True)
                    if kbd:
                        tk.Label(
                            top_row,
                            text=kbd,
                            bg=item_bg_n,
                            fg="#3a4a60",
                            font=("Courier", 8),
                            padx=12,
                        ).pack(side="right")
                    # tooltip description line (dim, indented)
                    if tip_txt:
                        tip_lbl = tk.Label(
                            row_f,
                            text=tip_txt,
                            bg=item_bg_n,
                            fg="#3d5068",
                            font=("Helvetica", 8),
                            anchor="w",
                            padx=26,
                            pady=0,
                        )
                        tip_lbl.pack(fill="x")
                    else:
                        tip_lbl = None
                    # hover: highlight entire row including tip
                    all_widgets = [row_f, top_row, ib] + ([tip_lbl] if tip_lbl else [])

                    def _enter(e, ws=all_widgets, kl=top_row, tl=tip_lbl, ib_=ib):
                        for w in ws:
                            w.config(bg=item_bg_h)
                        ib_.config(fg=TEXT)
                        if tl:
                            tl.config(fg="#6b849a")

                    def _leave(e, ws=all_widgets, tl=tip_lbl, ib_=ib):
                        for w in ws:
                            w.config(bg=item_bg_n)
                        ib_.config(fg=TEXT_DIM)
                        if tl:
                            tl.config(fg="#3d5068")

                    for w in all_widgets:
                        w.bind("<Enter>", _enter)
                        w.bind("<Leave>", _leave)
            # position and show
            drop.update_idletasks()
            dw = max(drop.winfo_reqwidth(), min_w)
            dh = drop.winfo_reqheight()
            drop.geometry(f"{dw}x{dh}+{rx}+{ry}")
            # close on any click outside
            drop.bind(
                "<FocusOut>",
                lambda e: app.after(
                    100,
                    lambda: _close_menu() if open_menu_win is drop else None,
                ),
            )
            open_menu_win = drop
            open_menu_btn = b

        btn.config(command=_open)
        btn.bind(
            "<Enter>",
            lambda e, b=btn: b.config(fg=TEXT) if open_menu_btn is not b else None,
        )
        btn.bind(
            "<Leave>",
            lambda e, b=btn: (
                b.config(fg=TEXT_DIM, bg="#080b10") if open_menu_btn is not b else None
            ),
        )
        return btn

    # ── FILE MENU ─────────────────────────────────────────────
    _menu_btn(
        menubar,
        tr("menu.file", "File"),
        [
            tr("menu.section.project", "Project"),
            (
                tr("menu.new_tree", "New Tree"),
                app._new_tree_dialog,
                "Ctrl+N",
                tr(
                    "menu.new_tree.tip",
                    "Start fresh - set country tag and auto-prefix all focus IDs.",
                ),
            ),
            (
                tr("menu.save_project", "Save Project"),
                app._save,
                "Ctrl+S",
                tr(
                    "menu.save_project.tip",
                    "Save as .json so you can reopen and keep editing later.",
                ),
            ),
            (
                tr("menu.load_project", "Load Project"),
                app._load,
                "Ctrl+O",
                tr(
                    "menu.load_project.tip",
                    "Open a previously saved .json project file.",
                ),
            ),
            None,
            tr("menu.section.recent", "Recent"),
            *(
                [(tr("menu.no_recent_files", "  (no recent files)"), None)]
                if not getattr(MOD, "_recent_mods", [])
                else [
                    (f"  {r}", lambda p=r: app._load_mod_path(p))
                    for r in (getattr(MOD, "_recent_mods", []) or [])
                ]
            ),
            None,
            tr("menu.section.import_export", "Import / Export"),
            (
                tr("menu.export_txt", "Export .txt"),
                app._export,
                "Ctrl+E",
                tr(
                    "menu.export_txt.tip",
                    "Write HOI4-ready script to a .txt file for your mod folder.",
                ),
            ),
            (
                tr("menu.export_mod", "Export to Mod"),
                app._export,
                "Ctrl+Shift+E",
                tr(
                    "menu.export_mod.tip",
                    "Write directly into your loaded mod's national_focus folder.",
                ),
            ),
            (
                tr("menu.import_txt", "Import .txt"),
                app._import_txt,
                "",
                tr(
                    "menu.import_txt.tip",
                    "Read an existing HOI4 focus tree .txt and populate the canvas.",
                ),
            ),
            (
                tr("menu.import_drawio", "Import Draw.io"),
                app._import_drawio,
                "",
                tr(
                    "menu.import_drawio.tip",
                    "Convert a Draw.io diagram into focus nodes and prerequisite arrows.",
                ),
            ),
        ],
    )

    # ── EDIT MENU ─────────────────────────────────────────────
    _menu_btn(
        menubar,
        tr("menu.edit", "Edit"),
        [
            (
                tr("menu.undo", "Undo"),
                app._undo,
                "Ctrl+Z",
                tr(
                    "menu.undo.tip",
                    "Revert the last canvas action (move, add, delete, edit).",
                ),
            ),
            None,
            (
                tr("menu.duplicate_focus", "Duplicate Focus"),
                app._duplicate_focus,
                "",
                tr(
                    "menu.duplicate_focus.tip",
                    "Copy the selected focus - gets a _copy suffix, shifted one column right.",
                ),
            ),
            (
                tr("menu.bulk_rename_prefix", "Bulk Rename Prefix"),
                app._bulk_rename_dialog,
                "",
                tr(
                    "menu.bulk_rename_prefix.tip",
                    "Replace a prefix across all focus IDs, prerequisites and mutex links at once.",
                ),
            ),
            None,
            (
                tr("menu.select_all", "Select All"),
                app._select_all_focuses,
                "Ctrl+A",
                tr(
                    "menu.select_all.tip",
                    "Enable multi-select and mark every focus on the canvas.",
                ),
            ),
            (
                tr("menu.delete_selected", "Delete Selected"),
                app._delete_selected,
                "Del",
                tr(
                    "menu.delete_selected.tip",
                    "Remove all multi-selected focuses after confirmation.",
                ),
            ),
        ],
    )

    # ── VIEW MENU ─────────────────────────────────────────────
    _menu_btn(
        menubar,
        tr("menu.view", "View"),
        [
            (
                tr("menu.toggle_grid", "Toggle Grid"),
                app._toggle_grid,
                "G",
                tr(
                    "menu.toggle_grid.tip",
                    "Show or hide the background snap grid on the canvas.",
                ),
            ),
            (
                tr("menu.toggle_minimap", "Toggle Minimap"),
                app._toggle_minimap,
                "M",
                tr(
                    "menu.toggle_minimap.tip",
                    "Show or hide the minimap overview in the bottom-right corner.",
                ),
            ),
            (
                tr("menu.toggle_focus_list", "Toggle Focus List"),
                app._toggle_focus_list,
                "F",
                tr(
                    "menu.toggle_focus_list.tip",
                    "Collapse or expand the left-side focus list panel.",
                ),
            ),
            None,
            (
                tr("menu.fit_all_focuses", "Fit All Focuses"),
                app._fit_all,
                "0",
                tr(
                    "menu.fit_all_focuses.tip",
                    "Zoom and pan so every focus on the canvas is visible at once.",
                ),
            ),
        ],
    )

    # ── TOOLS MENU ────────────────────────────────────────────
    _menu_btn(
        menubar,
        tr("menu.tools", "Tools"),
        [
            (
                tr("menu.national_spirit_builder", "National Spirit Builder"),
                app._national_spirit_wizard,
                "",
                tr(
                    "menu.national_spirit_builder.tip",
                    "Create ideas/spirits with a modifier editor and live HOI4 preview.",
                ),
            ),
            (
                tr("menu.dynamic_modifier", "Dynamic Modifier"),
                app._dyn_mod_wizard,
                "",
                tr(
                    "menu.dynamic_modifier.tip",
                    "Build add_dynamic_modifier effects with variable-driven scaling.",
                ),
            ),
            (
                tr("menu.decision_maker", "Decision Maker"),
                app._decision_wizard,
                "",
                tr(
                    "menu.decision_maker.tip",
                    "Build decisions and decision categories with GFX placement editor.",
                ),
            ),
            (
                tr("menu.event_maker", "Event Maker"),
                app._event_wizard,
                "",
                tr(
                    "menu.event_maker.tip",
                    "Build country_event / news_event blocks with options and live preview.",
                ),
            ),
            None,
            (
                tr("menu.validate_tree", "Validate Tree"),
                app._validate_tree,
                "",
                tr(
                    "menu.validate_tree.tip",
                    "Check for broken prerequisites, missing effects, and bad GFX references.",
                ),
            ),
            (
                tr("menu.load_mod", "Load Mod"),
                app._load_mod,
                "",
                tr(
                    "menu.load_mod.tip",
                    "Point to your mod root folder to browse GFX and enable direct export.",
                ),
            ),
            (
                tr("menu.set_edit_targets", "Set Edit Targets"),
                app._show_post_load_prompt,
                "",
                tr(
                    "menu.set_edit_targets.tip",
                    "Choose which existing ideas/events files new content should be appended to.",
                ),
            ),
            (
                tr("menu.settings", "Settings"),
                app._open_settings,
                "",
                tr(
                    "menu.settings.tip",
                    "Configure mod path, GFX directories, MD detection, and UI options.",
                ),
            ),
        ],
    )

    # Right side of menu bar
    app._errlog_btn = tk.Button(
        menubar,
        text=tr("menu.error_log", "Log"),
        command=app._show_error_log,
        bg="#080b10",
        fg="#6e7681",
        font=("Helvetica", 8, "bold"),
        relief="flat",
        padx=8,
        pady=0,
        cursor="hand2",
        bd=0,
        activebackground=BG_CARD,
        activeforeground=TEXT,
    )
    app._errlog_btn.pack(side="right", padx=4)
    Tooltip(
        app._errlog_btn,
        tr(
            "menu.error_log.tip",
            "View in-app error log.\nTurns red if any errors are caught during the session.",
        ),
    )
    tk.Frame(menubar, bg=BORDER_G, width=1, height=16).pack(side="right", padx=2)
    app._mod_lbl = tk.Label(
        menubar,
        text=tr("status.no_mod_loaded", "No mod loaded"),
        bg="#080b10",
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
        padx=8,
    )
    app._mod_lbl.pack(side="right")
    # close menu when clicking on canvas
    app.bind(
        "<Button-1>",
        lambda e: (
            _close_menu()
            if open_menu_win and not str(e.widget).startswith(str(open_menu_win))
            else None
        ),
        add="+",
    )

    # hint label (used by _hint() method)
    app._hint_lbl = tk.Label(
        toolbar,
        text=tr(
            "hint.canvas_controls",
            "Right-click canvas to place a focus  -  Ctrl+drag to pan  -  Scroll to zoom",
        ),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
        anchor="w",
        padx=10,
    )
    app._hint_lbl.pack(fill="x", pady=1)


__all__ = ["build_menubar"]
