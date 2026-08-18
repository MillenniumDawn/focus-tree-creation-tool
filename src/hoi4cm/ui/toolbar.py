# ruff: noqa: E501
"""Toolbar row 2: canvas action buttons, wizard shortcuts, coord display."""

import tkinter as tk

from hoi4cm.core.i18n import tr
from hoi4cm.ui.theme import BG_CARD, BLUE, BORDER_G, ORANGE, TEXT, TEXT_DIM
from hoi4cm.ui.widgets import Tooltip


def build_toolbar_row2(app, toolbar):
    """Build toolbar row 2: canvas action buttons and coord display."""
    # ROW 2 — canvas tools (clean grouped toolbar)
    row2 = tk.Frame(toolbar, bg="#090d14", height=36)
    row2.pack(fill="x")
    row2.pack_propagate(False)

    def _tb_sep():
        tk.Frame(row2, bg=BORDER_G, width=1, height=20).pack(side="left", padx=5)

    def _tb_lbl(t):
        tk.Label(
            row2,
            text=t,
            bg="#090d14",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            padx=4,
        ).pack(side="left")

    def _tb_btn(lbl, cmd, fg, bg, tip, padx=2):
        b = tk.Button(
            row2,
            text=lbl,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground=BORDER_G,
            activeforeground=TEXT,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=9,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        b.pack(side="left", padx=padx, pady=3)
        Tooltip(b, tip)
        return b

    _tb_lbl(tr("toolbar.section.canvas", "Canvas"))
    _tb_btn(
        tr("toolbar.add_focus", "+ Focus"),
        app._add_focus,
        TEXT,
        "#1e3a6e",
        tr(
            "toolbar.add_focus.tip",
            "Add a new focus.\nAlso: right-click the canvas.",
        ),
    )
    app._conn_btn = _tb_btn(
        tr("toolbar.prereq", "Prereq"),
        app._toggle_connect,
        TEXT,
        BG_CARD,
        tr(
            "toolbar.prereq.tip",
            "Open the prerequisite picker for the selected focus.",
        ),
    )
    app._mutex_btn = _tb_btn(
        tr("toolbar.mutex", "Mutex"),
        app._toggle_mutex,
        ORANGE,
        BG_CARD,
        tr("toolbar.mutex.tip", "Draw a mutually exclusive link."),
    )
    _tb_sep()
    _tb_lbl(tr("toolbar.section.tools", "Tools"))
    _tb_btn(
        tr("toolbar.ideas", "Ideas"),
        app._national_spirit_wizard,
        TEXT,
        "#1a2040",
        tr("toolbar.ideas.tip", "Build National Spirits / Ideas."),
    )
    _tb_btn(
        tr("toolbar.dyn_mod", "Dyn Mod"),
        app._dyn_mod_wizard,
        TEXT,
        BG_CARD,
        tr("toolbar.dyn_mod.tip", "Dynamic Modifier wizard."),
    )
    _tb_btn(
        tr("toolbar.decisions", "Decisions"),
        app._decision_wizard,
        TEXT,
        BG_CARD,
        tr("toolbar.decisions.tip", "Decision / Decision Category maker."),
    )
    _tb_btn(
        tr("toolbar.events", "Events"),
        app._event_wizard,
        TEXT,
        BG_CARD,
        tr("toolbar.events.tip", "Event Maker wizard."),
    )
    _tb_btn(
        tr("toolbar.add_income", "Add Income"),
        app._additional_income_wizard,
        "#4ade80",
        "#0d2b1a",
        tr(
            "toolbar.add_income.tip",
            "MD Additional Income Wizard - creates/links a spirit and wires up all money system files automatically.",
        ),
    )
    _tb_sep()
    _tb_lbl(tr("toolbar.section.select", "Select"))
    app._msel_btn = _tb_btn(
        tr("toolbar.multi", "Multi"),
        app._toggle_multisel,
        TEXT,
        "#1a1a2e",
        tr(
            "toolbar.multi.tip",
            "Toggle multi-select mode.\nCtrl+click focuses, then Delete.",
        ),
    )
    _tb_btn(
        tr("toolbar.delete_selected", "Del Selected"),
        app._delete_selected,
        TEXT,
        "#4a1010",
        tr("toolbar.delete_selected.tip", "Delete all selected focuses."),
    )
    _tb_sep()
    _tb_btn(
        tr("toolbar.clear_all", "Clear All"),
        app._clear_all,
        TEXT,
        "#7f1d1d",
        tr(
            "toolbar.clear_all.tip",
            "Delete ALL focuses from the canvas.\nSave first!",
        ),
    )
    _tb_sep()
    _tb_lbl(tr("toolbar.section.multi_tree", "Multi-Tree"))
    _tb_btn(
        tr("toolbar.shared", "+ Shared"),
        lambda: app._load_extra_tree("shared"),
        TEXT,
        "#2d1c08",
        tr(
            "toolbar.shared.tip",
            "Load a shared_focus tree alongside the main tree.\nIts focuses appear on canvas with amber [S] badges.",
        ),
    )
    _tb_btn(
        tr("toolbar.joint", "+ Joint"),
        lambda: app._load_extra_tree("joint"),
        TEXT,
        "#1a0d40",
        tr(
            "toolbar.joint.tip",
            "Load a joint_focus tree alongside the main tree.\nIts focuses appear on canvas with purple [J] badges.",
        ),
    )
    _tb_btn(
        tr("toolbar.load_all", "Load All"),
        app._load_all_trees,
        TEXT,
        "#0d1a2e",
        tr(
            "toolbar.load_all.tip",
            "Scan the mod's national_focus folder and load selected trees from a checklist.",
        ),
    )
    _tb_btn(
        tr("toolbar.save_all", "Save All"),
        app._save_all_trees,
        "#4ade80",
        "#0d1a0a",
        tr(
            "toolbar.save_all.tip",
            "Export all loaded trees (main + shared + joint) at once.",
        ),
    )

    # Coord display right side
    app._coord_lbl = tk.Label(
        row2,
        text="  x=0  y=0  ",
        bg="#090d14",
        fg=TEXT_DIM,
        font=("Courier", 9),
        padx=4,
    )
    app._coord_lbl.pack(side="right", padx=4)
    tk.Label(
        row2,
        text=tr("toolbar.cursor", "Cursor:"),
        bg="#090d14",
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(side="right")

    # Continuous Focus Position inputs (tree-level setting)
    tk.Frame(row2, bg=BORDER_G, width=1, height=20).pack(side="right", padx=5)

    def _cfp_commit(*_):
        try:
            app._cfp_x = int(app._cfp_x_var.get())
        except ValueError, TypeError, tk.TclError, AttributeError:
            pass
        try:
            app._cfp_y = int(app._cfp_y_var.get())
        except ValueError, TypeError, tk.TclError, AttributeError:
            pass

    _cfp_y_ent = tk.Entry(
        row2,
        textvariable=app._cfp_y_var,
        width=6,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _cfp_y_ent.pack(side="right", ipady=1, padx=(0, 2))
    _cfp_y_ent.bind("<FocusOut>", _cfp_commit)
    _cfp_y_ent.bind("<Return>", _cfp_commit)
    tk.Label(row2, text="y:", bg="#090d14", fg=TEXT_DIM, font=("Courier", 9)).pack(
        side="right"
    )
    _cfp_x_ent = tk.Entry(
        row2,
        textvariable=app._cfp_x_var,
        width=6,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _cfp_x_ent.pack(side="right", ipady=1, padx=(0, 2))
    _cfp_x_ent.bind("<FocusOut>", _cfp_commit)
    _cfp_x_ent.bind("<Return>", _cfp_commit)
    tk.Label(row2, text="x:", bg="#090d14", fg=TEXT_DIM, font=("Courier", 9)).pack(
        side="right"
    )
    tk.Label(
        row2,
        text=tr("toolbar.continuous_focus_pos", "Continuous Focus Pos:"),
        bg="#090d14",
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(side="right")


__all__ = ["build_toolbar_row2"]
