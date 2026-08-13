# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""Dynamic Modifier builder wizard."""

import json
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

from hoi4cm.core import (
    autosave_path,
    sanitize_component,
    tr,
)
from hoi4cm.core.image import PIL_OK, PILImage, PILImageTk
from hoi4cm.core.paths import read_file
from hoi4cm.mod import MOD
from hoi4cm.script.syntax import match_brace, parse_script, serialize_block
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    ORANGE,
    SEL_BG,
    TEXT,
    TEXT_DIM,
    _safe_after,
    _safe_after_idle,
    report_error,
)
from hoi4cm.wizards._generators import build_dyn_mod_output
from hoi4cm.wizards._graphics import browser_folders, collect_image_pairs
from hoi4cm.wizards._image_loader import TkImageLoader
from hoi4cm.wizards._shared import notifying_workspace_files


def open_dyn_mod_wizard(app):
    """Wizard to create a HOI4 dynamic modifier .txt file."""
    win = tk.Toplevel(app)
    win.title(tr("wizard.dynamic_modifier.title", "Dynamic Modifier Generator"))
    win.configure(bg=BG_DARK)
    win.geometry("640x720")
    win.resizable(True, True)
    win.grab_set()
    _dm_autosave_p = autosave_path("dyn_mod.json")

    def _dynmod_close():
        try:
            data = {k: v.get() for k, v in _dm_svars.items()}
            with open(_dm_autosave_p, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _dynmod_close)
    _dm_svars = {}  # populated below

    tk.Label(
        win,
        text=tr("wizard.dynamic_modifier.header", "DYNAMIC MODIFIER GENERATOR"),
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 11, "bold"),
        pady=10,
    ).pack(fill="x", padx=14)
    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

    # Draggable split
    dm_paned = tk.PanedWindow(
        win,
        orient="horizontal",
        bg=BORDER_G,
        sashwidth=5,
        sashrelief="flat",
        handlesize=0,
    )
    dm_paned.pack(fill="both", expand=True)

    # LEFT — scrollable form
    dm_left = tk.Frame(dm_paned, bg=BG_PANEL)
    dm_paned.add(dm_left, minsize=280, width=400, stretch="always")
    sc = tk.Canvas(dm_left, bg=BG_PANEL, highlightthickness=0)
    sb = tk.Scrollbar(dm_left, orient="vertical", command=sc.yview)
    frm = tk.Frame(sc, bg=BG_PANEL)
    sc.create_window((0, 0), window=frm, anchor="nw")
    sc.configure(yscrollcommand=sb.set)
    frm.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
    sc.bind(
        "<Configure>", lambda e: sc.itemconfig(sc.find_withtag("all")[0], width=e.width)
    )
    sb.pack(side="right", fill="y")
    sc.pack(fill="both", expand=True, padx=0)

    # RIGHT — preview panel
    dm_right = tk.Frame(dm_paned, bg=BG_DARK)
    dm_paned.add(dm_right, minsize=200, width=300, stretch="always")

    def lbl(text, fg=TEXT_DIM, bold=False):
        tk.Label(
            frm,
            text=text,
            bg=BG_PANEL,
            fg=fg,
            font=("Helvetica", 9, "bold" if bold else "normal"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(6, 0))

    def entry(var):
        e = tk.Entry(
            frm,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        e.pack(fill="x", padx=12, pady=2, ipady=4)
        return e

    def sep():
        tk.Frame(frm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=6)

    # ── Core fields ──────────────────────────────────────────
    lbl(
        tr(
            "dynamic_modifier.field.modifier_id",
            "MODIFIER ID  (must match add_dynamic_modifier = { modifier = ... })",
        ),
        bold=True,
    )
    v_id = tk.StringVar(value="TAG_my_dynamic_modifier")
    entry(v_id)

    lbl(tr("dynamic_modifier.field.scope", "Scope:  country | state | unit_leader"))
    v_scope = tk.StringVar(value="country")
    om_scope = tk.OptionMenu(frm, v_scope, "country", "state", "unit_leader")
    om_scope.config(
        bg=BG_CARD,
        fg=TEXT,
        activebackground=BORDER_G,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        anchor="w",
    )
    om_scope["menu"].config(bg=BG_CARD, fg=TEXT, activebackground=BORDER_G)
    om_scope.pack(fill="x", padx=12, pady=2)

    lbl(
        tr(
            "dynamic_modifier.field.icon_gfx",
            "Icon GFX  (optional - shows in national spirits list if set)",
        )
    )
    v_icon = tk.StringVar(value="")
    _icon_row = tk.Frame(frm, bg=BG_PANEL)
    _icon_row.pack(fill="x", padx=12, pady=2)
    tk.Entry(
        _icon_row,
        textvariable=v_icon,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", fill="x", expand=True, ipady=4)

    def _open_dynmod_gfx_browser():
        ideas_root = os.path.join(MOD.root, MOD.path_ideas_gfx) if MOD.loaded else None
        catalog = (
            MOD.graphics_catalog if ideas_root and os.path.isdir(ideas_root) else None
        )
        if not MOD.loaded or not ideas_root or not os.path.isdir(ideas_root):
            folder = filedialog.askdirectory(
                title=tr(
                    "filedialog.select_idea_gfx_folder_hint",
                    "Select idea GFX folder (gfx/interface/ideas)",
                )
            )
            if not folder:
                return
            ideas_root = folder
            catalog = None
        folders = browser_folders(ideas_root, "[ideas root]", catalog=catalog)
        if not folders:
            messagebox.showinfo(
                "No Folders",
                "No image files or subfolders found in the ideas GFX path.",
                parent=win,
            )
            return
        bwin = tk.Toplevel(win)
        bwin.title(
            tr(
                "gfx.browser.ideas_dynamic_title",
                "GFX Browser  -  Ideas / Dynamic Modifier",
            )
        )
        bwin.configure(bg=BG_DARK)
        bwin.geometry("900x580")
        bwin.resizable(True, True)
        bwin.grab_set()
        image_loader = TkImageLoader(bwin)
        panes = tk.Frame(bwin, bg=BG_DARK)
        panes.pack(fill="both", expand=True, padx=8, pady=8)
        lf = tk.Frame(panes, bg=BG_PANEL, width=200)
        lf.pack(side="left", fill="y", padx=(0, 6))
        lf.pack_propagate(False)
        tk.Label(
            lf,
            text=tr("gfx.folders", "  FOLDERS"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold"),
            anchor="w",
            pady=6,
        ).pack(fill="x")
        tk.Frame(lf, bg=BORDER_G, height=1).pack(fill="x")
        folder_lb = tk.Listbox(
            lf,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=BLUE,
            selectforeground=TEXT,
            font=("Courier", 9),
            relief="flat",
            bd=0,
            activestyle="none",
            highlightthickness=0,
        )
        fsb = tk.Scrollbar(lf, orient="vertical", command=folder_lb.yview)
        folder_lb.configure(yscrollcommand=fsb.set)
        fsb.pack(side="right", fill="y")
        folder_lb.pack(fill="both", expand=True, padx=2, pady=4)
        for display, _ in folders:
            folder_lb.insert("end", "  " + display)
        rf = tk.Frame(panes, bg=BG_DARK)
        rf.pack(side="left", fill="both", expand=True)
        top_r = tk.Frame(rf, bg=BG_DARK)
        top_r.pack(fill="x", pady=(0, 6))
        tk.Label(
            top_r,
            text=tr("common.filter", "Filter:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(
            top_r,
            textvariable=search_var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(side="left", padx=6, fill="x", expand=True, ipady=3)
        status_lbl = tk.Label(
            top_r,
            text=tr("gfx.select_folder_status", "select a folder"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        )
        status_lbl.pack(side="right", padx=6)
        cv_frame = tk.Frame(rf, bg=BG_PANEL)
        cv_frame.pack(fill="both", expand=True)
        cv = tk.Canvas(cv_frame, bg=BG_PANEL, highlightthickness=0)
        vsb = tk.Scrollbar(cv_frame, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        bot2 = tk.Frame(bwin, bg=BG_DARK)
        bot2.pack(fill="x", padx=10, pady=6)
        selected_var2 = tk.StringVar(value="")
        tk.Label(
            bot2, textvariable=selected_var2, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
        ).pack(side="left", padx=4)
        tk.Button(
            bot2,
            text=tr("common.cancel", "Cancel"),
            command=bwin.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right", padx=4)

        def _apply_dynmod_icon():
            v_icon.set(selected_var2.get())
            bwin.destroy()

        _sel_btn2 = tk.Button(
            bot2,
            text=tr("common.select_arrow", "Select ->"),
            command=_apply_dynmod_icon,
            bg="#1a3322",
            fg="#4b7a5e",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=5,
            cursor="arrow",
            state="disabled",
        )
        _sel_btn2.pack(side="right")

        def _on_sel2(*_):
            if selected_var2.get():
                _sel_btn2.config(
                    bg="#14532d", fg="#0a0a0a", cursor="hand2", state="normal"
                )
            else:
                _sel_btn2.config(
                    bg="#1a3322", fg="#4b7a5e", cursor="arrow", state="disabled"
                )

        selected_var2.trace_add("write", _on_sel2)
        COLS2 = 5
        TILE_W2 = 110
        TILE_H2 = 100
        PAD2 = 6
        IMG_W2 = 80
        IMG_H2 = 70
        _st2 = {
            "pairs": [],
            "img_cache": {},
            "drawn": set(),
            "canvas_ids": {},
            "sel_idx": None,
        }

        def _tile_xy2(idx):
            col = idx % COLS2
            row = idx // COLS2
            return PAD2 + col * (TILE_W2 + PAD2), PAD2 + row * (TILE_H2 + PAD2)

        def _select_tile2(idx):
            old = _st2["sel_idx"]
            if old is not None and old in _st2["canvas_ids"]:
                rid, _, _ = _st2["canvas_ids"][old]
                cv.itemconfig(rid, fill=BG_CARD, outline=BORDER_G)
            _st2["sel_idx"] = idx
            gfx_key = _st2["pairs"][idx][0]
            selected_var2.set(gfx_key)
            if idx in _st2["canvas_ids"]:
                rid, _, _ = _st2["canvas_ids"][idx]
                cv.itemconfig(rid, fill=SEL_BG, outline=BLUE)

        def _draw_tile2(idx):
            if idx in _st2["drawn"]:
                return
            _st2["drawn"].add(idx)
            gfx_key, path = _st2["pairs"][idx]
            x, y = _tile_xy2(idx)
            is_sel = gfx_key == selected_var2.get()
            rid = cv.create_rectangle(
                x,
                y,
                x + TILE_W2,
                y + TILE_H2,
                fill=SEL_BG if is_sel else BG_CARD,
                outline=BLUE if is_sel else BORDER_G,
                width=2,
                tags=("dt", f"dt{idx}"),
            )
            iid = cv.create_text(
                x + TILE_W2 // 2,
                y + 44,
                text="...",
                fill=TEXT_DIM,
                font=("Helvetica", 14),
                tags=("dt", f"dt{idx}"),
            )
            short = gfx_key.replace("GFX_idea_", "").replace("GFX_focus_", "")
            short = (short[:16] + "...") if len(short) > 16 else short
            lid = cv.create_text(
                x + TILE_W2 // 2,
                y + TILE_H2 - 14,
                text=short,
                fill=TEXT_DIM,
                font=("Helvetica", 7),
                width=TILE_W2 - 8,
                tags=("dt", f"dt{idx}"),
            )
            _st2["canvas_ids"][idx] = (rid, iid, lid)
            for item in (rid, iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile2(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile2(i), _apply_dynmod_icon()],
                )
            if path in _st2["img_cache"]:
                _fill_image2(idx)

        def _fill_image2(idx):
            if idx not in _st2["canvas_ids"]:
                return
            rid, iid, lid = _st2["canvas_ids"][idx]
            gfx_key, path = _st2["pairs"][idx]
            img = _st2["img_cache"].get(path)
            cv.delete(iid)
            if img:
                new_iid = cv.create_image(
                    _tile_xy2(idx)[0] + TILE_W2 // 2,
                    _tile_xy2(idx)[1] + 44,
                    anchor="center",
                    image=img,
                    tags=("dt", f"dt{idx}"),
                )
            else:
                new_iid = cv.create_text(
                    _tile_xy2(idx)[0] + TILE_W2 // 2,
                    _tile_xy2(idx)[1] + 34,
                    text="?",
                    fill=TEXT_DIM,
                    font=("Helvetica", 20),
                    tags=("dt", f"dt{idx}"),
                )
            _st2["canvas_ids"][idx] = (rid, new_iid, lid)
            for item in (rid, new_iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile2(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile2(i), _apply_dynmod_icon()],
                )

        def _decode_image2(item):
            i, path = item
            if not PIL_OK:
                return None
            paths_try = [path] + [
                os.path.splitext(path)[0] + ext
                for ext in (".png", ".tga")
                if os.path.exists(os.path.splitext(path)[0] + ext)
            ]
            for tp in paths_try:
                try:
                    if not os.path.exists(tp):
                        continue
                    with PILImage.open(tp) as source:
                        pil = source.convert("RGBA")
                    rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                    pw, ph = pil.size
                    ratio = min(IMG_W2 / max(pw, 1), IMG_H2 / max(ph, 1))
                    return pil.resize(
                        (max(1, int(pw * ratio)), max(1, int(ph * ratio))), rs
                    )
                except Exception:
                    pass
            return None

        def _apply_image2(item, img):
            i, path = item
            _st2["img_cache"][path] = img
            if i < len(_st2["pairs"]) and _st2["pairs"][i][1] == path:
                _fill_image2(i)

        def _lazy_fill2(*_):
            if not _st2["pairs"]:
                return
            cv.update_idletasks()
            top = cv.canvasy(0)
            bottom = cv.canvasy(cv.winfo_height())
            visible = []
            for idx in range(len(_st2["pairs"])):
                _, ty = _tile_xy2(idx)
                if ty + TILE_H2 >= top and ty <= bottom:
                    _draw_tile2(idx)
                    visible.append(idx)
            last = max(visible) if visible else 0
            ahead = list(range(last + 1, min(last + 41, len(_st2["pairs"]))))
            to_load = [
                i
                for i in (visible + ahead)
                if _st2["pairs"][i][1] not in _st2["img_cache"]
            ]
            if to_load:
                snap = list(_st2["pairs"])
                image_loader.submit_many(
                    ((i, snap[i][1]) for i in to_load if i < len(snap)),
                    _decode_image2,
                    realizer=lambda pil: PILImageTk.PhotoImage(pil),
                    apply=_apply_image2,
                )

        def _rebuild2(pairs):
            image_loader.invalidate()
            cv.delete("all")
            _st2.update(
                {"pairs": pairs, "drawn": set(), "canvas_ids": {}, "sel_idx": None}
            )
            if not pairs:
                status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
                return
            status_lbl.config(text="%d icons" % len(pairs))
            rows = (len(pairs) + COLS2 - 1) // COLS2
            cv.configure(
                scrollregion=(
                    0,
                    0,
                    PAD2 + COLS2 * (TILE_W2 + PAD2),
                    PAD2 + rows * (TILE_H2 + PAD2),
                )
            )
            cv.yview_moveto(0)
            _safe_after_idle(bwin, _lazy_fill2)

        def _collect_files2(folder_path):
            return collect_image_pairs(
                folder_path,
                "GFX_idea_",
                search=search_var.get().strip(),
                catalog=catalog,
            )

        def _load_folder2(folder_path):
            status_lbl.config(text=tr("gfx.scanning", "scanning..."))
            bwin.update_idletasks()
            _rebuild2(_collect_files2(folder_path))

        def _on_folder_select2(evt=None):
            s = folder_lb.curselection()
            if s:
                _load_folder2(folders[s[0]][1])

        cv.bind("<Configure>", lambda e: _safe_after_idle(bwin, _lazy_fill2))
        for _ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                _ev,
                lambda e: [
                    cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                    _safe_after_idle(bwin, _lazy_fill2),
                ],
            )
        folder_lb.bind("<<ListboxSelect>>", _on_folder_select2)
        search_var.trace_add(
            "write",
            lambda *_: _safe_after(
                bwin,
                300,
                lambda: _on_folder_select2() if folder_lb.curselection() else None,
            ),
        )
        if folders:
            folder_lb.selection_set(0)
            _load_folder2(folders[0][1])

    tk.Button(
        _icon_row,
        text=tr("gfx.browse_gfx", "Browse GFX >"),
        command=_open_dynmod_gfx_browser,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 9),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(side="right", padx=(4, 0))

    lbl(
        tr(
            "dynamic_modifier.field.enable_trigger",
            "Enable Trigger  (optional - modifier removed when trigger becomes false)\ne.g.  has_country_flag = TAG_modifier_active",
        )
    )
    v_enable = tk.Text(
        frm,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        height=3,
        wrap="none",
    )
    v_enable.pack(fill="x", padx=12, pady=2)

    sep()
    lbl(
        tr(
            "dynamic_modifier.section.variable_modifiers",
            "VARIABLE MODIFIERS  (modifier_key = variable_name = tooltip_key, one per line)",
        ),
        bold=True,
    )
    lbl(
        tr(
            "dynamic_modifier.hint.variable_modifiers",
            "Format:  stability_factor = TAG_stability_var = stability_factor_tt\nThe 3rd value is the tooltip localisation key shown to the player in the focus reward.\nLeave tooltip blank to omit it:  stability_factor = TAG_stability_var",
        )
    )
    v_mods = tk.Text(
        frm,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        height=8,
        wrap="none",
    )
    v_mods.pack(fill="x", padx=12, pady=2)
    v_mods.insert(
        "1.0",
        "stability_factor = TAG_stability_factor_var = stability_factor_tt\n"
        "industrial_capacity_factory = TAG_industrial_capacity_factory_var = industrial_capacity_factory_tt\n"
        "political_power_factor = TAG_political_power_var = political_power_gain_tt",
    )

    sep()
    lbl(
        tr(
            "dynamic_modifier.section.constant_modifiers",
            "CONSTANT MODIFIERS  (modifier_key = 0.05, one per line)\nExample:  political_power_gain = 0.1",
        ),
        bold=True,
    )
    lbl(
        tr(
            "dynamic_modifier.hint.constant_modifiers",
            "These are fixed values (not variable-driven).",
        )
    )
    v_const = tk.Text(
        frm,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        height=4,
        wrap="none",
    )
    v_const.pack(fill="x", padx=12, pady=2)

    sep()
    lbl(
        tr(
            "dynamic_modifier.section.localisation",
            "LOCALISATION  (for the modifier's display name & description)",
        ),
        bold=True,
    )
    lbl(
        tr(
            "dynamic_modifier.field.display_name",
            "Display Name  (shown in national spirits panel)",
        )
    )
    v_loc_name = tk.StringVar(value="My Dynamic Modifier")
    entry(v_loc_name)
    lbl(tr("common.description_no_colon", "Description"))
    v_loc_desc = tk.StringVar(value="Scaling bonuses from economic variables.")
    entry(v_loc_desc)

    sep()
    # ── Right pane: preview header + text ────────────────
    dm_prev_hdr = tk.Frame(dm_right, bg=BG_DARK)
    dm_prev_hdr.pack(fill="x", pady=(8, 2))
    tk.Label(
        dm_prev_hdr,
        text=tr("common.output_preview", "  OUTPUT PREVIEW"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        anchor="w",
    ).pack(side="left")
    _dm_edit_mode = [False]
    _dm_raw_override = [None]

    _dm_edit_btn = tk.Button(
        dm_prev_hdr,
        text=tr("common.edit", "Edit"),
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 8, "bold"),
        padx=8,
        pady=1,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _dm_edit_btn.pack(side="right", padx=4)

    _dm_save_raw_btn = tk.Button(
        dm_prev_hdr,
        text=tr("common.save_raw", "Save Raw"),
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 8, "bold"),
        padx=8,
        pady=1,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _dm_save_raw_btn.pack(side="right", padx=2)

    _dm_lock_lbl = tk.Label(
        dm_prev_hdr,
        text=tr("common.live", "live"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 7, "italic"),
    )
    _dm_lock_lbl.pack(side="right")
    dm_prev_sb = tk.Scrollbar(dm_right, orient="vertical")
    dm_prev_sb.pack(side="right", fill="y", padx=(0, 4))
    preview = tk.Text(
        dm_right,
        bg="#0d1117",
        fg="#a8d8a8",
        font=("Courier", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        wrap="none",
        state="disabled",
        yscrollcommand=dm_prev_sb.set,
    )
    dm_prev_sb.config(command=preview.yview)
    preview.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))

    def _dm_get_output():
        if _dm_raw_override[0] is not None:
            return _dm_raw_override[0]
        return _build_output()

    def _dm_toggle_edit():
        _dm_edit_mode[0] = not _dm_edit_mode[0]
        if _dm_edit_mode[0]:
            preview.config(state="normal", bg="#0d1a0d", highlightbackground="#4ade80")
            _dm_edit_btn.config(
                text=tr("common.cancel_edit", "Cancel Edit"), fg=TEXT_DIM, bg=BG_CARD
            )
            _dm_lock_lbl.config(text=tr("common.editing", "editing..."), fg="#fbbf24")
        else:
            preview.config(state="normal", bg="#0d1117", highlightbackground=BORDER_G)
            _dm_show_preview()
            preview.config(state="disabled")
            _dm_raw_override[0] = None
            _dm_edit_btn.config(text=tr("common.edit", "Edit"), fg=TEXT_DIM, bg=BG_CARD)
            _dm_save_raw_btn.config(
                text=tr("common.save_raw", "Save Raw"), fg=TEXT_DIM, bg=BG_CARD
            )
            preview.config(bg="#0d1117", highlightbackground=BORDER_G)
            _dm_lock_lbl.config(text=tr("common.live", "live"), fg=TEXT_DIM)

    def _dm_save_raw():
        """Save raw preview: sync safe scalar fields back, store override,
        notify user of anything that couldn't be auto-synced."""
        preview.config(state="normal")
        txt = preview.get("1.0", "end").strip()
        _dm_raw_override[0] = txt
        _dm_edit_mode[0] = False
        preview.config(state="disabled", bg="#0d1117", highlightbackground=ORANGE)
        _dm_edit_btn.config(text=tr("common.edit", "Edit"), fg=TEXT_DIM, bg=BG_CARD)

        changes = []
        warnings = []

        # Only parse up to the FOCUS SNIPPET section
        stop_at = next(
            (
                i
                for i, l in enumerate(txt.splitlines())
                if l.strip().startswith("# FOCUS SNIPPET")
                or l.strip().startswith("# LOCALISATION")
            ),
            None,
        )
        dm_lines = (
            txt.splitlines()[:stop_at] if stop_at is not None else txt.splitlines()
        )

        in_block = False
        in_enable = False
        enable_depth = 0
        enable_buf = []

        for ln in dm_lines:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue

            if not in_block:
                m = re.match(r"^(\w+)\s*=\s*\{", s)
                if m:
                    new_id = m.group(1)
                    if new_id != v_id.get():
                        v_id.set(new_id)
                        changes.append(f"Modifier ID → {new_id!r}")
                    in_block = True
                continue

            if s == "}" and enable_depth == 0 and not in_enable:
                in_block = False
                continue

            if in_enable:
                if "{" in s:
                    enable_depth += 1
                if "}" in s:
                    enable_depth -= 1
                    if enable_depth == 0:
                        in_enable = False
                        content = "\n".join(
                            l[2:] if l.startswith("\t\t") else l for l in enable_buf
                        ).strip()
                        old = v_enable.get("1.0", "end").strip()
                        if content != old:
                            v_enable.delete("1.0", "end")
                            if content:
                                v_enable.insert("1.0", content)
                            changes.append("enable trigger updated")
                        enable_buf = []
                        continue
                enable_buf.append(ln)
                continue

            m = re.match(r"scope\s*=\s*(\w+)", s)
            if m:
                if m.group(1) != v_scope.get():
                    v_scope.set(m.group(1))
                    changes.append(f"Scope → {m.group(1)!r}")
                continue
            m = re.match(r"icon\s*=\s*(\S+)", s)
            if m:
                if m.group(1) != v_icon.get():
                    v_icon.set(m.group(1))
                    changes.append(f"Icon GFX → {m.group(1)!r}")
                continue
            if re.match(r"enable\s*=\s*\{", s):
                in_enable = True
                enable_depth = 1
                enable_buf = []
                continue

            # Variable / constant modifiers — can't safely map back to v_mods lines
            m = re.match(r"^(\w+)\s*=\s*(\S+)$", s)
            if m:
                key, val = m.group(1), m.group(2)
                if key in ("scope", "icon"):
                    continue
                try:
                    float(val)
                    warnings.append(
                        f"Constant modifier {key} = {val} — check Constant Modifiers field"
                    )
                except ValueError:
                    warnings.append(
                        f"Variable modifier {key} = {val} — check Variable Modifiers field"
                    )

        # Localisation — accept both `key: "value"` and legacy `key:0 "value"`
        loc_idx = next(
            (i for i, l in enumerate(txt.splitlines()) if "# LOCALISATION" in l), None
        )
        if loc_idx:
            for ln in txt.splitlines()[loc_idx:]:
                m = re.match(r'^\s+(\S+?)(?::\d+)?\s*[=:]?\s*"(.*)"', ln)
                if m:
                    key, val = m.group(1), m.group(2)
                    if key.endswith("_desc"):
                        if val != v_loc_desc.get():
                            v_loc_desc.set(val)
                            changes.append(f"Description → {val!r}")
                    elif "_tt" not in key:
                        if val != v_loc_name.get():
                            v_loc_name.set(val)
                            changes.append(f"Display name → {val!r}")

        _dm_lock_lbl.config(
            text=tr("common.raw_override_active", "raw override active"), fg=ORANGE
        )

        parts = []
        if changes:
            parts.append(
                "Fields updated from your code:\n"
                + "\n".join(f"  • {c}" for c in changes)
            )
        if warnings:
            parts.append(
                "Please check these fields manually:\n"
                + "\n".join(f"  ⚠ {w}" for w in warnings)
            )
        if not changes and not warnings:
            parts.append("No field changes detected. Raw override saved.")
        parts.append("\nThe output will export exactly as shown in the preview.")

        messagebox.showinfo("Saved — Review Changes", "\n\n".join(parts), parent=win)

    def _dm_show_preview():
        preview.config(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", _dm_get_output())
        if not _dm_edit_mode[0]:
            preview.config(state="disabled")

    _dm_edit_btn.config(command=_dm_toggle_edit)
    _dm_save_raw_btn.config(command=_dm_save_raw)

    # Real builder + line parser live in _generators.py (headless-testable).
    def _parse_mod_line(ln):
        return _parse_mod_line_pure(ln)

    def _build_output():
        return build_dyn_mod_output(
            mod_id=v_id.get(),
            scope=v_scope.get(),
            icon=v_icon.get(),
            enable=v_enable.get("1.0", "end"),
            mods_raw=v_mods.get("1.0", "end"),
            const=v_const.get("1.0", "end"),
            loc_name=v_loc_name.get(),
            loc_desc=v_loc_desc.get(),
        )

    def _preview(*_):
        if _dm_edit_mode[0]:
            return
        if _dm_raw_override[0] is not None:
            return
        preview.config(state="normal")
        preview.delete("1.0", "end")
        preview.insert("1.0", _build_output())
        preview.config(state="disabled")

    # live preview on any change
    for sv in (v_id, v_scope, v_icon, v_loc_name, v_loc_desc):
        sv.trace_add("write", _preview)
    for t in (v_enable, v_mods, v_const):
        t.bind("<KeyRelease>", _preview)
    _preview()

    def _save_file():
        mid = sanitize_component(
            v_id.get().strip() or "TAG_my_dynamic_modifier",
            fallback="TAG_my_dynamic_modifier",
        )
        icon = v_icon.get().strip()
        name = v_loc_name.get().strip()
        desc = v_loc_desc.get().strip()
        scope = v_scope.get().strip()
        enable = v_enable.get("1.0", "end").strip()

        mod_entries = []
        for ln in v_mods.get("1.0", "end").strip().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                modifier, var, tooltip = _parse_mod_line(ln)
                if modifier and var:
                    mod_entries.append((modifier, var, tooltip))

        const_lines = [
            ln.strip()
            for ln in v_const.get("1.0", "end").strip().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]

        # ── Ask for mod root ──────────────────────────────────
        mod_root = filedialog.askdirectory(
            title="Select your MOD ROOT folder (the folder that contains common/, localisation/, …)"
        )
        if not mod_root:
            return

        results = []  # (rel_path, action, note)
        errors = []
        workspace_files = notifying_workspace_files(MOD, mod_root)

        # ── Helpers ───────────────────────────────────────────
        def full(rel):
            return os.path.join(mod_root, rel)

        def read_existing(rel, encoding="utf-8-sig"):
            p = full(rel)
            if not os.path.exists(p):
                return None
            try:
                with open(p, encoding=encoding, errors="replace") as f:
                    return f.read()
            except Exception:
                return None

        def write(rel, content, encoding="utf-8"):
            p = full(rel)
            try:
                workspace_files.write_text(p, content, encoding=encoding)
                return True
            except Exception as e:
                errors.append(f"{rel}: {e}")
                return False

        # ════════════════════════════════════════════════════════
        # FILE 1 — common/dynamic_modifiers/  (one file per modifier)
        # Strategy: if file exists, replace the block for `mid`;
        #           if not, create it fresh.
        # ════════════════════════════════════════════════════════
        dm_rel = os.path.join("common", "dynamic_modifiers", f"{mid}.txt")
        dm_existing = read_existing(dm_rel)

        # Build the new block
        icon_gfx = (
            (icon if icon.startswith("GFX_") else f"GFX_idea_{icon}") if icon else ""
        )
        dm_block_lines = [f"{mid} = {{"]
        if scope != "country":
            dm_block_lines.append(f"\tscope = {scope}")
        if icon_gfx:
            dm_block_lines.append(f"\ticon = {icon_gfx}")
        if enable:
            dm_block_lines.append("\tenable = {")
            for ln in enable.splitlines():
                if ln.strip():
                    dm_block_lines.append(f"\t\t{ln.strip()}")
            dm_block_lines.append("\t}")
        dm_block_lines.append("")
        for modifier, var, _ in mod_entries:
            dm_block_lines.append(f"\t{modifier} = {var}")
        if const_lines:
            dm_block_lines.append("")
            for ln in const_lines:
                dm_block_lines.append(f"\t{ln}")
        dm_block_lines.append("}")
        dm_new_block = "\n".join(dm_block_lines)

        if dm_existing is None:
            # Fresh file
            dm_final = dm_new_block + "\n"
            action = "created"
        else:
            # Replace existing block for `mid` if present, else append
            # Match: mid = { ... } at top level (handles nested braces)
            def replace_or_append(src, block_id, new_block):
                # Find "block_id = {" and extract to matching "}"
                pattern = re.compile(
                    r"^\s*" + re.escape(block_id) + r"\s*=\s*\{", re.MULTILINE
                )
                m = pattern.search(src)
                if not m:
                    # Not found — append
                    return src.rstrip() + "\n\n" + new_block + "\n", "appended"
                i = match_brace(src, m.end() - 1)
                if i < len(src):
                    replaced = src[: m.start()] + new_block + src[i + 1 :]
                    return replaced, "updated"
                return src.rstrip() + "\n\n" + new_block + "\n", "appended"

            dm_final, action = replace_or_append(dm_existing, mid, dm_new_block)

        if write(dm_rel, dm_final):
            results.append((dm_rel, action, f"{len(mod_entries)} variable modifiers"))

        # ════════════════════════════════════════════════════════
        # FILE 2 — localisation/english/
        # Strategy: scan ALL .yml files under localisation/english/
        # for existing keys; only add missing ones.
        # Write to mid_l_english.yml (create or append).
        # ════════════════════════════════════════════════════════
        loc_dir = os.path.join(mod_root, "localisation", "english")
        existing_keys = set()

        # Collect all keys already in any loc file
        # Accept both modern `key: "value"` and legacy `key:0 "value"` forms
        if os.path.isdir(loc_dir):
            for fname in os.listdir(loc_dir):
                if fname.endswith(".yml"):
                    content = read_existing(
                        os.path.join("localisation", "english", fname), "utf-8-sig"
                    )
                    if content:
                        for m in re.finditer(
                            r'^\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', content, re.MULTILINE
                        ):
                            existing_keys.add(m.group(1))

        # Build only the missing entries
        if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file):
            loc_rel = (
                os.path.relpath(MOD.edit_loc_file, mod_root)
                if mod_root
                else MOD.edit_loc_file
            )
        else:
            loc_rel = os.path.join("localisation", "english", f"{mid}_l_english.yml")
        loc_existing = read_existing(loc_rel, "utf-8-sig")

        new_loc_lines = []

        def add_loc(key, value):
            if key not in existing_keys:
                new_loc_lines.append(f' {key}: "{value}"')

        add_loc(mid, name)
        add_loc(f"{mid}_desc", desc)
        add_loc("modifies_dynamic_modifier_tt", "Modifies $MODIFIER$")
        for modifier, var, tooltip in mod_entries:
            if tooltip:
                add_loc(tooltip, modifier.replace("_", " ").title())

        if new_loc_lines:
            if loc_existing is None:
                loc_final = "l_english:\n" + "\n".join(new_loc_lines) + "\n"
                loc_action = "created"
            else:
                # Append after last non-empty line, preserving file
                loc_final = (
                    loc_existing.rstrip()
                    + "\n\n"
                    + f" # {mid} — added by Focus Maker\n"
                    + "\n".join(new_loc_lines)
                    + "\n"
                )
                loc_action = f"appended {len(new_loc_lines)} new keys"
            if write(loc_rel, loc_final, "utf-8-sig"):
                results.append((loc_rel, loc_action, f"{len(new_loc_lines)} loc keys"))
        else:
            results.append((loc_rel, "skipped", "all keys already exist"))

        # ════════════════════════════════════════════════════════
        # FILE 3 — focus snippet (always overwrite — it's a helper)
        # ════════════════════════════════════════════════════════
        snip_rel = os.path.join("_focus_snippets", f"{mid}_focus_snippet.txt")
        snippet = [
            "# ============================================================",
            f"# Focus snippet for: {mid}",
            "# ============================================================",
            "",
            "# ── ACTIVATION focus (first time adding this modifier) ────────",
            "# Use adds_dynamic_modifier_tt when the block contains add_dynamic_modifier",
            f"\t\t\tadd_dynamic_modifier = {{ modifier = {mid} }}",
            "\t\t\tcustom_effect_tooltip = {",
            "\t\t\t\tlocalization_key = adds_dynamic_modifier_tt",
            f"\t\t\t\tMODIFIER = {mid}",
            "\t\t\t}",
            "",
            "# ── MODIFICATION focus (changing variables only, no add_dynamic_modifier) ─",
            "# Use modifies_dynamic_modifier_tt when only variables are changed",
            "\t\t\tcustom_effect_tooltip = {",
            "\t\t\t\tlocalization_key = modifies_dynamic_modifier_tt",
            f"\t\t\t\tMODIFIER = {mid}",
            "\t\t\t}",
        ]
        for modifier, var, tooltip in mod_entries:
            tt = f" tooltip = {tooltip}" if tooltip else ""
            snippet.append(f"\t\t\tadd_to_variable = {{ {var} = 0.05{tt} }}")
        if write(snip_rel, "\n".join(snippet) + "\n"):
            results.append((snip_rel, "created", "paste into your focus file"))

        # ════════════════════════════════════════════════════════
        # FILE 4 — interface/ideas.gfx (if icon set)
        # Strategy: if file exists, check if spriteType already there;
        #           if not, append it before the last closing }.
        # ════════════════════════════════════════════════════════
        if icon_gfx:
            icon_name = icon_gfx.replace("GFX_idea_", "").replace("GFX_", "")
            sprite_block = (
                f"\tspriteType = {{\n"
                f'\t\tname = "{icon_gfx}"\n'
                f'\t\ttexturefile = "gfx/interface/ideas/{icon_name}.dds"\n'
                f"\t}}"
            )
            gfx_rel = os.path.join("interface", "ideas.gfx")
            gfx_existing = read_existing(gfx_rel)
            if gfx_existing is None:
                gfx_final = f"spriteTypes = {{\n\n" f"{sprite_block}\n\n" f"}}\n"
                gfx_action = "created"
            elif icon_gfx in gfx_existing:
                gfx_final = gfx_existing
                gfx_action = "skipped (icon already defined)"
            else:
                # Insert before last closing }
                last = gfx_existing.rfind("}")
                if last >= 0:
                    gfx_final = gfx_existing[:last] + f"\n{sprite_block}\n\n}}\n"
                else:
                    gfx_final = gfx_existing.rstrip() + f"\n{sprite_block}\n"
                gfx_action = "appended sprite"
            if gfx_action != "skipped (icon already defined)":
                if write(gfx_rel, gfx_final):
                    results.append(
                        (
                            gfx_rel,
                            gfx_action,
                            f"icon: {icon_gfx} → gfx/interface/ideas/{icon_name}.dds",
                        )
                    )
            else:
                results.append((gfx_rel, gfx_action, ""))

        # ── Summary ───────────────────────────────────────────
        if errors:
            report_error("\n".join(errors), title="Errors during file generation")

        lines = [f"Mod root: {mod_root}\n"]
        for rel, action, note in results:
            note_str = f"  ({note})" if note else ""
            lines.append(f"  [{action}]  {rel}{note_str}")
        lines += [
            "",
            "Next steps:",
            "  1. Copy snippet from _focus_snippets/ into your focus .txt",
            "  2. Add add_dynamic_modifier effect to activate the modifier",
            "  3. Add icon .dds to gfx/interface/ideas/ if needed",
            "  4. Restart HOI4 (dynamic modifiers require full restart)",
        ]
        messagebox.showinfo(
            "Done" if not errors else "Done (with errors)", "\n".join(lines)
        )

    def _browse_mod_dynmods():
        import glob as _glob

        if not MOD.loaded or not MOD.root:
            messagebox.showinfo(
                "No Mod Loaded",
                "Load a mod first to browse existing dynamic modifiers.",
                parent=win,
            )
            return
        dm_dir = os.path.join(MOD.root, "common", "dynamic_modifiers")
        if not os.path.isdir(dm_dir):
            messagebox.showinfo(
                "Not Found",
                "No common/dynamic_modifiers/ directory found in mod.",
                parent=win,
            )
            return

        # Scan all files for modifier IDs
        mods = []  # list of (modifier_id, file_path)
        for fp in sorted(_glob.glob(os.path.join(dm_dir, "*.txt"))):
            try:
                src = read_file(fp)
                if not src:
                    continue
                parsed = parse_script(src)
                for k, v in parsed.items():
                    if k not in ("_values", "=") and isinstance(v, dict):
                        mods.append((k, fp))
            except Exception:
                pass

        if not mods:
            messagebox.showinfo(
                "No Modifiers Found",
                "No dynamic modifier definitions found.",
                parent=win,
            )
            return

        dlg = tk.Toplevel(win)
        dlg.title("Browse Mod Dynamic Modifiers")
        dlg.configure(bg=BG_DARK)
        dlg.geometry("560x440")
        dlg.resizable(True, True)
        dlg.grab_set()
        tk.Label(
            dlg,
            text=tr("dynamic_modifier.browser.header", "BROWSE DYNAMIC MODIFIERS"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=8,
        ).pack(fill="x", padx=12)
        tk.Label(
            dlg,
            text=tr(
                "dynamic_modifier.browser.description",
                "Select a modifier to load it into the editor.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(fill="x", padx=12)
        tk.Frame(dlg, bg=BORDER_G, height=1).pack(fill="x", pady=(4, 0))

        frm = tk.Frame(dlg, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=10, pady=6)
        lb = tk.Listbox(
            frm,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=SEL_BG,
            selectforeground=TEXT,
            font=("Courier", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            activestyle="none",
        )
        sb = tk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for mid, fp in mods:
            lb.insert("end", f"  {mid:<50}  {os.path.basename(fp)}")

        def _block_to_enable_text(blk, depth=0):
            return serialize_block(blk, indent="\t" * depth, include_bare_values=True)

        def _load_selected():
            sel = lb.curselection()
            if not sel:
                return
            modifier_id, fp = mods[sel[0]]
            try:
                src = read_file(fp)
                parsed = parse_script(src)
                blk = parsed.get(modifier_id, {})
                if not isinstance(blk, dict):
                    report_error(
                        f"Could not parse modifier '{modifier_id}'",
                        parent=dlg,
                        title="Parse Error",
                    )
                    return
            except Exception as e:
                report_error(str(e), e, parent=dlg, title="Parse Error")
                return

            # Populate identity fields
            v_id.set(modifier_id)
            v_scope.set(blk.get("scope", "country"))
            v_icon.set(blk.get("icon", ""))

            # Enable trigger block
            enable_blk = blk.get("enable", {})
            v_enable.delete("1.0", "end")
            if enable_blk:
                v_enable.insert("1.0", _block_to_enable_text(enable_blk))

            # Split modifier entries: variable vs constant
            var_lines = []
            const_lines = []
            skip_keys = {"scope", "icon", "enable", "_values"}
            for k, v in blk.items():
                if k in skip_keys or isinstance(v, dict):
                    continue
                val_str = str(v)
                # If value looks like a number, it's a constant modifier
                try:
                    float(val_str)
                    const_lines.append(f"{k} = {val_str}")
                except ValueError:
                    # It's a variable reference — format as "modifier = var"
                    var_lines.append(f"{k} = {val_str}")

            v_mods.delete("1.0", "end")
            if var_lines:
                v_mods.insert("1.0", "\n".join(var_lines))
            v_const.delete("1.0", "end")
            if const_lines:
                v_const.insert("1.0", "\n".join(const_lines))

            # Look up loc strings
            loc_name = loc_desc = ""
            loc_dir = os.path.join(MOD.root, "localisation", "english")
            if os.path.isdir(loc_dir):
                for lf in sorted(os.listdir(loc_dir)):
                    if not lf.endswith(".yml"):
                        continue
                    try:
                        loc_src = read_file(os.path.join(loc_dir, lf))
                        for m in re.finditer(
                            r'^\s+(\S+?)(?::\d+)?\s+"(.*)"', loc_src, re.MULTILINE
                        ):
                            k2, v2 = m.group(1), m.group(2)
                            if k2 == modifier_id and not loc_name:
                                loc_name = v2
                            elif k2 == f"{modifier_id}_desc" and not loc_desc:
                                loc_desc = v2
                        if loc_name and loc_desc:
                            break
                    except Exception:
                        pass
            v_loc_name.set(loc_name)
            v_loc_desc.set(loc_desc)

            _preview()
            dlg.destroy()
            app._hint(
                f"Loaded dynamic modifier '{modifier_id}' from {os.path.basename(fp)}"
            )

        lb.bind("<Double-Button-1>", lambda e: _load_selected())
        bot_dlg = tk.Frame(dlg, bg=BG_DARK, pady=6)
        bot_dlg.pack(fill="x")
        tk.Button(
            bot_dlg,
            text=tr("common.load_selected", "Load Selected"),
            command=_load_selected,
            bg="#14532d",
            fg="#4ade80",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=16,
            pady=5,
            cursor="hand2",
        ).pack(side="left", padx=10)
        tk.Button(
            bot_dlg,
            text=tr("common.cancel", "Cancel"),
            command=dlg.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 10),
            padx=12,
            pady=5,
            cursor="hand2",
        ).pack(side="right", padx=10)

    bf = tk.Frame(win, bg=BG_DARK)
    bf.pack(fill="x", padx=12, pady=8)
    tk.Button(
        bf,
        text=tr("common.refresh", "Refresh"),
        command=_preview,
        bg=BG_CARD,
        fg=TEXT,
        font=("Helvetica", 9, "bold"),
        relief="flat",
        padx=12,
        pady=5,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", padx=2)

    def _dm_copy():
        txt = _dm_get_output()
        win.clipboard_clear()
        win.clipboard_append(txt)

    tk.Button(
        bf,
        text=tr("common.copy", "Copy"),
        command=_dm_copy,
        bg=BG_CARD,
        fg=TEXT,
        font=("Helvetica", 9, "bold"),
        relief="flat",
        padx=12,
        pady=5,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", padx=2)
    if MOD.loaded:
        tk.Button(
            bf,
            text=tr("common.browse_mod", "Browse Mod"),
            command=_browse_mod_dynmods,
            bg=BG_CARD,
            fg=BLUE,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(side="left", padx=2)
    tk.Button(
        bf,
        text=tr("common.generate_all_files", "Generate All Files ->"),
        command=_save_file,
        bg="#14532d",
        fg="#0a0a0a",
        font=("Helvetica", 10, "bold"),
        relief="flat",
        padx=14,
        pady=6,
        cursor="hand2",
        highlightthickness=0,
    ).pack(side="right", padx=2)


# ─────────────────── STATUS BAR ──────────────────────────────
