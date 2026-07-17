# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""National Spirit / Idea builder wizard."""

import json
import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from hoi4cm.core import (
    MODIFIER_CATS,
    MODIFIER_DEFS,
    append_scripted_loc,
    autosave_path,
    modifiers_in_cat,
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
    RED,
    SEL_BG,
    TEXT,
    TEXT_DIM,
    _safe_after,
    _safe_after_idle,
)
from hoi4cm.wizards._graphics import browser_folders, collect_image_pairs
from hoi4cm.wizards._image_loader import TkImageLoader
from hoi4cm.wizards._shared import notifying_workspace_files


def open_national_spirit_wizard(app):
    """Visual National Spirit / Idea builder with searchable modifier cards."""
    win = tk.Toplevel(app)
    win.title(tr("wizard.national_spirit.title", "National Spirit Builder"))
    win.configure(bg=BG_DARK)
    win.geometry("820x860")
    win.resizable(True, True)
    win.grab_set()

    # ── Auto-save on close ─────────────────────────────────────────────
    _sp_autosave = autosave_path("national_spirit.json")

    def _spirit_autosave(data):
        try:
            with open(_sp_autosave, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_spirit_close():
        data = {k: v.get() for k, v in _spirit_svars.items() if hasattr(v, "get")}
        data["modifiers"] = spirit_modifiers[:]
        threading.Thread(target=_spirit_autosave, args=(data,), daemon=True).start()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_spirit_close)

    # ── State ─────────────────────────────────────────────────────────
    spirit_modifiers = []  # list of {"key": str, "value": str}
    _spirit_svars = {}  # populated by _field() calls for autosave

    # ── Header ────────────────────────────────────────────────────────
    tk.Label(
        win,
        text=tr("wizard.national_spirit.header", "NATIONAL SPIRIT BUILDER"),
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 12, "bold"),
        pady=10,
    ).pack(fill="x", padx=14)
    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

    # ── Two-column layout ─────────────────────────────────────────────
    body = tk.Frame(win, bg=BG_DARK)
    body.pack(fill="both", expand=True)

    # Draggable split — PanedWindow
    paned = tk.PanedWindow(
        body,
        orient="horizontal",
        bg=BORDER_G,
        sashwidth=5,
        sashrelief="flat",
        handlesize=0,
    )
    paned.pack(fill="both", expand=True)

    # LEFT pane (scrollable form)
    left_outer = tk.Frame(paned, bg=BG_PANEL)
    paned.add(left_outer, minsize=300, width=460, stretch="always")

    lc = tk.Canvas(left_outer, bg=BG_PANEL, highlightthickness=0)
    lsb = tk.Scrollbar(left_outer, orient="vertical", command=lc.yview)
    lfrm = tk.Frame(lc, bg=BG_PANEL)
    lc.create_window((0, 0), window=lfrm, anchor="nw")
    lc.configure(yscrollcommand=lsb.set)
    lfrm.bind("<Configure>", lambda e: lc.configure(scrollregion=lc.bbox("all")))
    lc.bind(
        "<Configure>",
        lambda e: (
            lc.itemconfig(lc.find_withtag("all")[0], width=e.width)
            if lc.find_withtag("all")
            else None
        ),
    )
    lfrm.bind(
        "<MouseWheel>", lambda e: lc.yview_scroll(int(-1 * (e.delta / 120)), "units")
    )
    lsb.pack(side="right", fill="y")
    lc.pack(fill="both", expand=True)

    # RIGHT pane (preview)
    right_outer = tk.Frame(paned, bg=BG_DARK)
    paned.add(right_outer, minsize=200, width=360, stretch="always")
    # Preview header with Edit toggle
    prev_hdr = tk.Frame(right_outer, bg=BG_DARK)
    prev_hdr.pack(fill="x", pady=(8, 2))
    tk.Label(
        prev_hdr,
        text=tr("common.output_preview", "  OUTPUT PREVIEW"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        anchor="w",
    ).pack(side="left")
    _edit_mode = [False]  # True while preview text box is editable
    _raw_override = [
        None
    ]  # if not None, Copy/Save use this raw string instead of _build_output

    _edit_btn = tk.Button(
        prev_hdr,
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
    _edit_btn.pack(side="right", padx=4)

    _save_raw_btn = tk.Button(
        prev_hdr,
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
    _save_raw_btn.pack(side="right", padx=2)

    _lock_lbl = tk.Label(
        prev_hdr,
        text=tr("common.live", "live"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 7, "italic"),
    )
    _lock_lbl.pack(side="right")
    preview_txt = tk.Text(
        right_outer,
        bg="#0d1117",
        fg="#a8d8a8",
        font=("Courier", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        wrap="none",
        state="disabled",
    )
    prev_sb = tk.Scrollbar(right_outer, orient="vertical", command=preview_txt.yview)
    prev_sb.pack(side="right", fill="y", padx=(0, 4))
    preview_txt.configure(yscrollcommand=prev_sb.set)
    preview_txt.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))

    # ── UI helpers ────────────────────────────────────────────────────
    def _sep():
        tk.Frame(lfrm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=6)

    def _sec(text):
        tk.Label(
            lfrm,
            text=text,
            bg=BG_PANEL,
            fg=TEXT,
            font=("Helvetica", 9, "bold"),
            anchor="w",
            padx=10,
            pady=4,
        ).pack(fill="x")

    def _lbl(text):
        tk.Label(
            lfrm,
            text=text,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            anchor="w",
            padx=12,
        ).pack(fill="x")

    def _field(label, var, width=None):
        row = tk.Frame(lfrm, bg=BG_PANEL)
        row.pack(fill="x", padx=10, pady=2)
        tk.Label(
            row,
            text=label,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=14,
            anchor="w",
        ).pack(side="left")
        kw = {"width": width} if width else {}
        e = tk.Entry(
            row,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            **kw,
        )
        e.pack(side="left", fill="x", expand=True, ipady=4)
        return e

    def _dropdown(label, var, options):
        row = tk.Frame(lfrm, bg=BG_PANEL)
        row.pack(fill="x", padx=10, pady=2)
        tk.Label(
            row,
            text=label,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=14,
            anchor="w",
        ).pack(side="left")
        om = tk.OptionMenu(row, var, *options)
        om.config(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=BORDER_G,
            font=("Helvetica", 9),
            relief="flat",
            anchor="w",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        om["menu"].config(bg=BG_CARD, fg=TEXT, activebackground=BORDER_G)
        om.pack(side="left", fill="x", expand=True)

    def _trigger_field(label, height=2):
        row = tk.Frame(lfrm, bg=BG_PANEL)
        row.pack(fill="x", padx=10, pady=2)
        tk.Label(
            row,
            text=label,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=14,
            anchor="nw",
        ).pack(side="left")
        t = tk.Text(
            row,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            height=height,
            wrap="none",
        )
        t.pack(side="left", fill="x", expand=True, ipady=2)
        t.bind("<KeyRelease>", lambda e: _refresh_preview())
        return t

    # ── IDENTITY ──────────────────────────────────────────────────────
    _sec(tr("spirit.section.identity", "IDENTITY"))
    v_id = tk.StringVar(value="TAG_my_spirit")
    v_name_key = tk.StringVar(value="TAG_my_spirit")
    v_picture = tk.StringVar(value="GFX_idea_TAG_my_spirit")
    v_slot = tk.StringVar(value="country")
    v_cost = tk.StringVar(value="0")
    v_removal = tk.StringVar(value="-1")
    _field(tr("spirit.field.idea_id", "Idea ID:"), v_id)
    _field(tr("spirit.field.name_loc_key", "Name loc key:"), v_name_key)
    # Picture GFX row with ⊞ browse button
    _gfx_row = tk.Frame(lfrm, bg=BG_PANEL)
    _gfx_row.pack(fill="x", padx=10, pady=2)
    tk.Label(
        _gfx_row,
        text=tr("spirit.field.picture_gfx", "Picture GFX:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=14,
        anchor="w",
    ).pack(side="left")
    _gfx_ent = tk.Entry(
        _gfx_row,
        textvariable=v_picture,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _gfx_ent.pack(side="left", fill="x", expand=True, ipady=4)
    tk.Button(
        _gfx_row,
        text="⊞",
        command=lambda: _open_idea_gfx_browser(),
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 11),
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        padx=4,
    ).pack(side="right", padx=(2, 0))

    # ── Idea GFX picker row  (identical UX to focus GFX picker) ──
    def _open_idea_gfx_browser():
        ideas_root = os.path.join(MOD.root, MOD.path_ideas_gfx) if MOD.loaded else None
        catalog = (
            MOD.graphics_catalog if ideas_root and os.path.isdir(ideas_root) else None
        )

        if not MOD.loaded or not ideas_root or not os.path.isdir(ideas_root):
            # Fallback: let user pick a folder manually
            folder = filedialog.askdirectory(
                title=tr("filedialog.select_idea_gfx_folder", "Select idea GFX folder")
            )
            if not folder:
                return
            ideas_root = folder
            catalog = None

        # Build folder list (same logic as focus browser)
        folders = browser_folders(ideas_root, "[ideas root]", catalog=catalog)

        if not folders:
            messagebox.showinfo(
                "No Folders",
                "No image files or subfolders found in the ideas GFX path.",
            )
            return

        # ── Browser window ────────────────────────────────────────
        bwin = tk.Toplevel(win)
        bwin.title(tr("gfx.browser.ideas_title", "GFX Browser  -  Ideas"))
        bwin.configure(bg=BG_DARK)
        bwin.geometry("900x580")
        bwin.resizable(True, True)
        bwin.grab_set()
        image_loader = TkImageLoader(bwin)

        panes = tk.Frame(bwin, bg=BG_DARK)
        panes.pack(fill="both", expand=True, padx=8, pady=8)

        # Left: folder list
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

        # Right panel
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

        # Bottom bar
        bot = tk.Frame(bwin, bg=BG_DARK)
        bot.pack(fill="x", padx=10, pady=6)
        selected_var = tk.StringVar(value="")
        tk.Label(
            bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
        ).pack(side="left", padx=4)
        tk.Button(
            bot,
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

        def _apply_idea():
            v_picture.set(selected_var.get())
            bwin.destroy()

        _sel_btn_i = tk.Button(
            bot,
            text=tr("common.select_arrow", "Select ->"),
            command=_apply_idea,
            bg="#1a3322",
            fg="#4b7a5e",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=5,
            cursor="arrow",
            state="disabled",
        )
        _sel_btn_i.pack(side="right")

        def _on_sel_change_i(*_):
            v = selected_var.get()
            if v:
                _sel_btn_i.config(
                    bg="#14532d", fg="#0a0a0a", cursor="hand2", state="normal"
                )
            else:
                _sel_btn_i.config(
                    bg="#1a3322", fg="#4b7a5e", cursor="arrow", state="disabled"
                )

        selected_var.trace_add("write", _on_sel_change_i)

        # ── Grid constants (same as focus browser) ────────────────
        COLS = 5
        TILE_W = 110
        TILE_H = 100
        PAD = 6

        _st = {
            "pairs": [],
            "img_cache": {},
            "drawn": set(),
            "canvas_ids": {},
            "sel_idx": None,
        }

        def _tile_xy(idx):
            col = idx % COLS
            row = idx // COLS
            return PAD + col * (TILE_W + PAD), PAD + row * (TILE_H + PAD)

        def _select_tile(idx):
            old = _st["sel_idx"]
            if old is not None and old in _st["canvas_ids"]:
                rid, _, _ = _st["canvas_ids"][old]
                cv.itemconfig(rid, fill=BG_CARD, outline=BORDER_G)
            _st["sel_idx"] = idx
            gfx_key = _st["pairs"][idx][0]
            selected_var.set(gfx_key)
            if idx in _st["canvas_ids"]:
                rid, _, _ = _st["canvas_ids"][idx]
                cv.itemconfig(rid, fill=SEL_BG, outline=BLUE)

        def _draw_tile(idx):
            if idx in _st["drawn"]:
                return
            _st["drawn"].add(idx)
            gfx_key, path = _st["pairs"][idx]
            x, y = _tile_xy(idx)
            is_sel = gfx_key == selected_var.get()
            rid = cv.create_rectangle(
                x,
                y,
                x + TILE_W,
                y + TILE_H,
                fill=SEL_BG if is_sel else BG_CARD,
                outline=BLUE if is_sel else BORDER_G,
                width=2,
                tags=("tile", f"t{idx}"),
            )
            iid = cv.create_text(
                x + TILE_W // 2,
                y + 44,
                text="...",
                fill=TEXT_DIM,
                font=("Helvetica", 14),
                tags=("tile", f"t{idx}"),
            )
            short = gfx_key.replace("GFX_idea_", "").replace("GFX_focus_", "")
            short = (short[:16] + "...") if len(short) > 16 else short
            lid = cv.create_text(
                x + TILE_W // 2,
                y + TILE_H - 14,
                text=short,
                fill=TEXT_DIM,
                font=("Helvetica", 7),
                width=TILE_W - 8,
                tags=("tile", f"t{idx}"),
            )
            _st["canvas_ids"][idx] = (rid, iid, lid)
            for item in (rid, iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile(i), _apply_idea()],
                )
            if path in _st["img_cache"]:
                _fill_image(idx)

        def _fill_image(idx):
            if idx not in _st["canvas_ids"]:
                return
            rid, iid, lid = _st["canvas_ids"][idx]
            gfx_key, path = _st["pairs"][idx]
            img = _st["img_cache"].get(path)
            cv.delete(iid)
            if img:
                new_iid = cv.create_image(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 44,
                    anchor="center",
                    image=img,
                    tags=("tile", f"t{idx}"),
                )
            else:
                new_iid = cv.create_text(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 30,
                    text="?",
                    fill=TEXT_DIM,
                    font=("Helvetica", 20),
                    tags=("tile", f"t{idx}"),
                )
            _st["canvas_ids"][idx] = (rid, new_iid, lid)
            for item in (rid, new_iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile(i), _apply_idea()],
                )

        def _decode_image(item):
            idx, path = item
            if not PIL_OK or not os.path.exists(path):
                return None
            with PILImage.open(path) as source:
                pil = source.convert("RGBA")
            rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
            return pil.resize((72, 72), rs)

        def _apply_image(item, img):
            idx, path = item
            _st["img_cache"][path] = img
            if idx < len(_st["pairs"]) and _st["pairs"][idx][1] == path:
                _fill_image(idx)

        def _lazy_fill(*_):
            if not _st["pairs"]:
                return
            cv.update_idletasks()
            top = cv.canvasy(0)
            bottom = cv.canvasy(cv.winfo_height())
            visible = []
            for idx in range(len(_st["pairs"])):
                _, ty = _tile_xy(idx)
                if ty + TILE_H >= top and ty <= bottom:
                    _draw_tile(idx)
                    visible.append(idx)
            last = max(visible) if visible else 0
            ahead = list(range(last + 1, min(last + 41, len(_st["pairs"]))))
            to_load = [
                i
                for i in (visible + ahead)
                if _st["pairs"][i][1] not in _st["img_cache"]
            ]
            if to_load:
                snap = list(_st["pairs"])
                image_loader.submit_many(
                    ((i, snap[i][1]) for i in to_load if i < len(snap)),
                    _decode_image,
                    realizer=lambda pil: PILImageTk.PhotoImage(pil),
                    apply=_apply_image,
                )

        def _rebuild_grid(pairs):
            image_loader.invalidate()
            cv.delete("all")
            _st["pairs"] = pairs
            _st["drawn"].clear()
            _st["canvas_ids"].clear()
            _st["sel_idx"] = None
            if not pairs:
                status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
                return
            status_lbl.config(text="%d icons" % len(pairs))
            rows = (len(pairs) + COLS - 1) // COLS
            cv.configure(
                scrollregion=(
                    0,
                    0,
                    PAD + COLS * (TILE_W + PAD),
                    PAD + rows * (TILE_H + PAD),
                )
            )
            cv.yview_moveto(0)
            _safe_after_idle(bwin, _lazy_fill)

        def _collect_files(folder_path):
            return collect_image_pairs(
                folder_path,
                "GFX_idea_",
                search=search_var.get(),
                catalog=catalog,
            )

        def _load_folder(folder_path):
            status_lbl.config(text=tr("gfx.scanning", "scanning..."))
            bwin.update_idletasks()
            _rebuild_grid(_collect_files(folder_path))

        def _on_folder_select(evt):
            sel = folder_lb.curselection()
            if not sel:
                return
            _load_folder(folders[sel[0]][1])

        cv.bind("<Configure>", lambda e: _safe_after_idle(bwin, _lazy_fill))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                ev,
                lambda e: [
                    cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                    _safe_after_idle(bwin, _lazy_fill),
                ],
            )
        folder_lb.bind("<<ListboxSelect>>", _on_folder_select)
        search_var.trace_add(
            "write",
            lambda *_: _safe_after(
                bwin,
                300,
                lambda: _on_folder_select(None) if folder_lb.curselection() else None,
            ),
        )

        if folders:
            folder_lb.selection_set(0)
            _load_folder(folders[0][1])

    _dropdown(
        tr("spirit.field.slot", "Slot:"),
        v_slot,
        [
            "country",
            "political_advisor",
            "army_chief",
            "navy_chief",
            "air_chief",
            "high_command",
            "theorist",
            "industrial_concern",
            "materiel_designer",
            "naval_manufacturer",
            "aircraft_manufacturer",
            "tank_manufacturer",
        ],
    )
    _field(tr("spirit.field.cost_pp", "Cost (PP):"), v_cost, width=6)
    _field(tr("spirit.field.removal_cost", "Removal cost:"), v_removal, width=6)
    _lbl(
        tr(
            "spirit.hint.removal_cost",
            "  removal_cost = -1  means the spirit cannot be manually removed",
        )
    )

    _sep()
    # ── TRIGGERS ──────────────────────────────────────────────────────
    _sec(tr("spirit.section.triggers", "TRIGGERS  (optional)"))
    t_allowed = _trigger_field(tr("spirit.field.allowed", "allowed:"), height=2)
    t_available = _trigger_field(tr("spirit.field.available", "available:"), height=2)
    t_cancel = _trigger_field(tr("spirit.field.cancel", "cancel:"), height=2)
    t_visible = _trigger_field(tr("spirit.field.visible", "visible:"), height=2)
    t_allowed.insert("1.0", "original_tag = TAG")

    _sep()
    # ── SCRIPTED EFFECTS ──────────────────────────────────────────────
    _sec(tr("spirit.section.scripted_effects", "SCRIPTED EFFECTS  (optional)"))
    t_on_add = _trigger_field(tr("spirit.field.on_add", "on_add:"), height=3)
    t_on_remove = _trigger_field(tr("spirit.field.on_remove", "on_remove:"), height=2)
    _lbl(tr("spirit.example.set_rule", "  e.g.  set_rule = { can_access_market = no }"))

    _sep()
    # ── RULE ──────────────────────────────────────────────────────────
    _sec(tr("spirit.section.rule", "RULE  (optional)"))
    t_rule = _trigger_field(tr("spirit.field.rule", "rule:"), height=2)
    _lbl(tr("spirit.example.rule", "  e.g.  can_access_market = no"))

    _sep()
    # ── MODIFIER BUILDER ──────────────────────────────────────────────
    _sec(tr("spirit.section.modifiers", "MODIFIERS"))
    mod_outer = tk.Frame(lfrm, bg=BG_PANEL)
    mod_outer.pack(fill="x", padx=8, pady=4)

    # Search bar — use _sv.set() exclusively (not entry.insert/delete which bypasses textvariable)
    _sv = tk.StringVar()
    _PH = "Search modifiers..."
    search_entry = tk.Entry(
        mod_outer,
        textvariable=_sv,
        bg=BG_CARD,
        fg=TEXT_DIM,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    _sv.set(_PH)
    search_entry.pack(fill="x", expand=True, ipady=4, padx=2, pady=(0, 2))

    def _ph_in(e):
        if _sv.get() == _PH:
            _sv.set("")
            search_entry.config(fg=TEXT)

    def _ph_out(e):
        if not _sv.get():
            _sv.set(_PH)
            search_entry.config(fg=TEXT_DIM)

    search_entry.bind("<FocusIn>", _ph_in)
    search_entry.bind("<FocusOut>", _ph_out)

    # Category + dropdown row
    cd_row = tk.Frame(mod_outer, bg=BG_PANEL)
    cd_row.pack(fill="x", pady=2)
    tk.Label(
        cd_row,
        text=tr("common.category", "Category:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    ).pack(side="left")
    _mc = tk.StringVar(value=MODIFIER_CATS[0])
    cat_om = tk.OptionMenu(
        cd_row, _mc, *MODIFIER_CATS, command=lambda _: _rebuild_mod_dd()
    )
    cat_om.config(
        bg=BG_CARD,
        fg=TEXT,
        activebackground=BORDER_G,
        font=("Helvetica", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        width=14,
        anchor="w",
    )
    cat_om["menu"].config(
        bg=BG_CARD, fg=TEXT, activebackground=BORDER_G, font=("Helvetica", 9)
    )
    cat_om.pack(side="left", padx=4)

    dd_frame = tk.Frame(cd_row, bg=BG_PANEL)
    dd_frame.pack(side="left", fill="x", expand=True)
    _mt = tk.StringVar()

    def _rebuild_mod_dd():
        for w in dd_frame.winfo_children():
            w.destroy()
        items = modifiers_in_cat(_mc.get())
        if not items:
            return
        _mt.set(items[0][0])
        om = tk.OptionMenu(dd_frame, _mt, *[k for k, _ in items])
        menu = om["menu"]
        menu.delete(0, "end")
        for k, v in items:
            menu.add_command(
                label="{}  ({})".format(k, v["hint"]),
                command=lambda val=k: _mt.set(val),
            )
        om.config(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=SEL_BG,
            font=("Helvetica", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            anchor="w",
            width=26,
        )
        om["menu"].config(
            bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 9)
        )
        om.pack(fill="x", expand=True)

    _rebuild_mod_dd()

    def _set_cat_menu(cats, on_select_cmd):
        """Repopulate the category OptionMenu with `cats`."""
        menu = cat_om["menu"]
        menu.delete(0, "end")
        for cat in cats:
            menu.add_radiobutton(
                label=cat,
                variable=_mc,
                value=cat,
                command=lambda c=cat: on_select_cmd(c),
            )

    def _filter_mod_dd(*_):
        raw = _sv.get()
        query = "" if raw == _PH else raw.lower().strip()

        if not query:
            # Restore full category list and show category-filtered modifiers
            _set_cat_menu(MODIFIER_CATS, lambda c: [_mc.set(c), _rebuild_mod_dd()])
            if _mc.get() not in MODIFIER_CATS:
                _mc.set(MODIFIER_CATS[0])
            for w in dd_frame.winfo_children():
                w.destroy()
            _rebuild_mod_dd()
            return

        # Filter all modifiers across all categories
        matches = [
            (k, v)
            for k, v in MODIFIER_DEFS.items()
            if query in k.lower()
            or query in v["desc"].lower()
            or query in v["cat"].lower()
        ]

        # Update category dropdown to show only categories that have matches
        matching_cats = sorted(set(v["cat"] for _, v in matches)) if matches else []
        _set_cat_menu(matching_cats or MODIFIER_CATS, lambda c: [_mc.set(c)])
        if matching_cats and _mc.get() not in matching_cats:
            _mc.set(matching_cats[0])

        # Rebuild modifier dropdown with all matches (ignoring category filter while searching)
        for w in dd_frame.winfo_children():
            w.destroy()
        if not matches:
            tk.Label(
                dd_frame,
                text=tr("modifier.none_found", "No modifiers found"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
            ).pack(anchor="w")
            return
        _mt.set(matches[0][0])
        om = tk.OptionMenu(dd_frame, _mt, *[k for k, _ in matches])
        menu2 = om["menu"]
        menu2.delete(0, "end")
        for k, v in matches:
            menu2.add_command(
                label="[{}]  {}  ({})".format(v["cat"], k, v["hint"]),
                command=lambda val=k: _mt.set(val),
            )
        om.config(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=SEL_BG,
            font=("Helvetica", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            anchor="w",
            width=30,
        )
        om["menu"].config(
            bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 9)
        )
        om.pack(fill="x", expand=True)

    _sv.trace_add("write", _filter_mod_dd)

    # + Add Modifier button
    tk.Button(
        mod_outer,
        text=tr("modifier.add", "+ Add Modifier"),
        command=lambda: _add_mod_card(),
        bg="#14532d",
        fg="#4ade80",
        font=("Helvetica", 10, "bold"),
        relief="flat",
        pady=6,
        cursor="hand2",
    ).pack(fill="x", padx=2, pady=(4, 2))

    tk.Frame(mod_outer, bg=BORDER_G, height=1).pack(fill="x", pady=4)
    tk.Label(
        mod_outer,
        text=tr("modifier.added", "  ADDED MODIFIERS"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")

    mod_box = tk.Frame(mod_outer, bg=BG_PANEL)
    mod_box.pack(fill="x", padx=2)

    def _refresh_mod_cards():
        for w in mod_box.winfo_children():
            w.destroy()
        if not spirit_modifiers:
            tk.Label(
                mod_box,
                text=tr("modifier.none_added", "None -- add modifiers above"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w", padx=6)
            return
        for i, mod in enumerate(spirit_modifiers):
            _draw_mod_card(i, mod)

    def _draw_mod_card(i, mod):
        key = mod["key"]
        defn = MODIFIER_DEFS.get(key, {})
        cat = defn.get("cat", "Custom")
        hint = defn.get("hint", "number")
        desc = defn.get("desc", "")
        known = bool(defn)
        hdr_bg = "#0d1117" if known else "#1a1020"
        bdr = BORDER_G if known else ORANGE

        card = tk.Frame(
            mod_box, bg=BG_CARD, highlightthickness=1, highlightbackground=bdr
        )
        card.pack(fill="x", pady=2)

        hdr = tk.Frame(card, bg=hdr_bg)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=f"[{cat}]  {key}",
            bg=hdr_bg,
            fg=TEXT_DIM if known else ORANGE,
            font=("Helvetica", 9, "bold"),
            anchor="w",
            padx=6,
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            hdr,
            text="X",
            command=lambda idx=i: _rm_mod(idx),
            bg=hdr_bg,
            fg=RED,
            relief="flat",
            font=("Georgia", 9),
            cursor="hand2",
            padx=4,
        ).pack(side="right")

        val_row = tk.Frame(card, bg=BG_CARD)
        val_row.pack(fill="x", padx=6, pady=3)
        tk.Label(
            val_row,
            text=tr("common.value_label", "value:"),
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=6,
            anchor="w",
        ).pack(side="left")
        vvar = tk.StringVar(value=mod["value"])
        ve = tk.Entry(
            val_row,
            textvariable=vvar,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        ve.pack(side="left", fill="x", expand=True, ipady=3)
        vvar.trace_add("write", lambda *a, idx=i, v=vvar: _update_mod_val(idx, v))

        if hint or desc:
            info = "  {}{}".format(hint, ("  --  " + desc[:70]) if desc else "")
            tk.Label(
                card,
                text=info,
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                anchor="w",
                padx=6,
            ).pack(fill="x", pady=(0, 3))

    def _add_mod_card():
        key = _mt.get().strip()
        if not key:
            return
        defn = MODIFIER_DEFS.get(key, {})
        hint = defn.get("hint", "number")
        if "bool" in hint:
            default = "yes"
        elif "float" in hint:
            default = "0.05"
        elif "int" in hint:
            default = "1"
        else:
            default = "0.1"
        spirit_modifiers.append({"key": key, "value": default})
        _refresh_mod_cards()
        _refresh_preview()

    def _rm_mod(idx):
        spirit_modifiers.pop(idx)
        _refresh_mod_cards()
        _refresh_preview()

    def _update_mod_val(idx, var):
        if idx < len(spirit_modifiers):
            spirit_modifiers[idx]["value"] = var.get()
            _refresh_preview()

    _sep()
    # ── EXTRA / CUSTOM MODIFIERS ──────────────────────────────────────
    _sec(
        tr(
            "spirit.section.extra_modifiers",
            "EXTRA / CUSTOM MODIFIERS  (free text  key = value)",
        )
    )
    t_extra = tk.Text(
        lfrm,
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
    t_extra.pack(fill="x", padx=10, pady=2)
    t_extra.bind("<KeyRelease>", lambda e: _refresh_preview())
    _lbl(
        tr(
            "spirit.example.custom_modifier",
            "  e.g.  modifier_army_sub_unit_Militia_Bat_attack_factor = 0.15",
        )
    )

    _sep()
    # ── LOCALISATION ──────────────────────────────────────────────────
    _sec(tr("spirit.section.localisation", "LOCALISATION"))
    v_loc_name = tk.StringVar(value="My National Spirit")
    v_loc_desc = tk.StringVar(value="A spirit granting special bonuses.")
    _field(tr("common.display_name", "Display name:"), v_loc_name)
    _field(tr("common.description", "Description:"), v_loc_desc)

    _sep()
    # ── AI ────────────────────────────────────────────────────────────
    _sec(tr("spirit.section.ai", "AI  (optional)"))
    v_ai = tk.StringVar(value="1")
    _field(tr("spirit.field.ai_will_do", "ai_will_do:"), v_ai)

    # ── Output builder ────────────────────────────────────────────────
    def _build_output():
        sid = v_id.get().strip() or "TAG_my_spirit"
        namekey = v_name_key.get().strip() or sid
        pic = v_picture.get().strip() or (f"GFX_idea_{sid}")
        slot = v_slot.get().strip() or "country"
        cost = v_cost.get().strip()
        removal = v_removal.get().strip()
        loc_n = v_loc_name.get().strip()
        loc_d = v_loc_desc.get().strip()
        ai_f = v_ai.get().strip()

        def _tri(t):
            return t.get("1.0", "end").strip()

        allowed = _tri(t_allowed)
        available = _tri(t_available)
        cancel = _tri(t_cancel)
        visible = _tri(t_visible)
        on_add = _tri(t_on_add)
        on_remove = _tri(t_on_remove)
        rule = _tri(t_rule)
        extra = t_extra.get("1.0", "end").strip()

        def _block(name, body, indent="\t\t\t"):
            lines = [f"{indent}{name} = {{"]
            for ln in body.splitlines():
                if ln.strip():
                    lines.append(f"{indent}\t{ln.strip()}")
            lines.append(f"{indent}}}")
            return lines

        out = []
        out.append("# ============================================================")
        out.append(f"# FILE: common/ideas/{sid}.txt")
        out.append("# ============================================================")
        out.append("")
        out.append("ideas = {")
        out.append(f"\t{slot} = {{")
        out.append(f"\t\t{sid} = {{")
        if namekey != sid:
            out.append(f"\t\t\tname = {namekey}")
        out.append(f"\t\t\tpicture = {pic}")
        if slot == "country":
            out.append("\t\t\tallowed_civil_war = { always = yes }")
        if cost:
            out.append(f"\t\t\tcost = {cost}")
        if removal:
            out.append(f"\t\t\tremoval_cost = {removal}")
        if allowed:
            out += _block("allowed", allowed)
        if available:
            out += _block("available", available)
        if visible:
            out += _block("visible", visible)
        if cancel:
            out += _block("cancel", cancel)
        if on_add:
            out += _block("on_add", on_add)
        if on_remove:
            out += _block("on_remove", on_remove)
        if rule:
            out += _block("rule", rule)

        # Collect all modifiers
        all_mods = list(spirit_modifiers)
        if extra:
            for ln in extra.splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    parts = ln.split("=", 1)
                    all_mods.append(
                        {"key": parts[0].strip(), "value": parts[1].strip()}
                    )
        if all_mods:
            out.append("\t\t\tmodifier = {")
            for m in all_mods:
                out.append("\t\t\t\t{} = {}".format(m["key"], m["value"]))
            out.append("\t\t\t}")

        if ai_f and ai_f != "0":
            out.append(f"\t\t\tai_will_do = {{ factor = {ai_f} }}")

        out.append("\t\t}")
        out.append("\t}")
        out.append("}")
        out.append("")
        out.append("# ============================================================")
        out.append(f"# LOCALISATION  localisation/english/{sid}_l_english.yml")
        out.append("# ============================================================")
        out.append("")
        out.append(f' {sid}: "{loc_n}"')
        out.append(f' {sid}_desc: "{loc_d}"')
        return "\n".join(out)

    def _refresh_preview(*_):
        """Rebuild preview from form fields (no-op in edit mode or raw override)."""
        if _edit_mode[0]:
            return
        if _raw_override[0] is not None:
            return  # raw override takes precedence
        try:
            preview_txt.config(state="normal")
            preview_txt.delete("1.0", "end")
            preview_txt.insert("1.0", _build_output())
            preview_txt.config(state="disabled")
        except Exception:
            pass

    def _get_output_text():
        """Return the text to use for Copy/Save — raw override if set, else live."""
        if _raw_override[0] is not None:
            return _raw_override[0]
        return _build_output()

    def _toggle_edit():
        """Enter/exit raw edit mode.  Does NOT affect the raw override."""
        _edit_mode[0] = not _edit_mode[0]
        if _edit_mode[0]:
            # Entering edit mode — populate box with current output first
            preview_txt.config(state="normal")
            preview_txt.delete("1.0", "end")
            preview_txt.insert("1.0", _get_output_text())
            preview_txt.config(bg="#0d1a0d", highlightbackground="#4ade80")
            _edit_btn.config(
                text=tr("common.cancel_edit", "Cancel Edit"), fg="#ef4444", bg="#2a0a0a"
            )
            _lock_lbl.config(
                text=tr(
                    "common.editing_save_raw_hint",
                    "editing - click Save Raw to keep changes",
                ),
                fg="#fbbf24",
            )
        else:
            # Cancel edit — discard changes and go fully back to live-from-fields
            _raw_override[0] = None
            _edit_btn.config(text=tr("common.edit", "Edit"), fg=TEXT_DIM, bg=BG_CARD)
            _save_raw_btn.config(
                text=tr("common.save_raw", "Save Raw"), fg=TEXT_DIM, bg=BG_CARD
            )
            preview_txt.config(bg="#0d1117", highlightbackground=BORDER_G)
            _lock_lbl.config(text=tr("common.live", "live"), fg=TEXT_DIM)
            _refresh_preview()

    def _save_raw():
        """Save raw preview: parse safe fields back into form, store as override,
        notify user of anything that couldn't be synced to a field."""
        preview_txt.config(state="normal")
        txt = preview_txt.get("1.0", "end").strip()
        _raw_override[0] = txt
        _edit_mode[0] = False
        preview_txt.config(state="disabled", bg="#0d1117", highlightbackground=ORANGE)
        _edit_btn.config(text=tr("common.edit", "Edit"), fg=TEXT_DIM, bg=BG_CARD)

        # ── Parse safe fields from the raw text ──────────────────────────
        changes = []
        warnings = []

        # Section split
        loc_idx = next(
            (i for i, l in enumerate(txt.splitlines()) if "# LOCALISATION" in l), None
        )
        ideas_lines = txt.splitlines()[:loc_idx] if loc_idx else txt.splitlines()
        loc_lines = txt.splitlines()[loc_idx:] if loc_idx else []

        # Localisation scalars
        for ln in loc_lines:
            m = re.match(r'^\s+(\S+?)(?::\d+)?\s+"(.*)"', ln)
            if m:
                key, val = m.group(1), m.group(2)
                if key.endswith("_desc"):
                    if val != v_loc_desc.get():
                        v_loc_desc.set(val)
                        changes.append(f"Description → {val!r}")
                else:
                    if val != v_loc_name.get():
                        v_loc_name.set(val)
                        changes.append(f"Display name → {val!r}")

        # Walk the ideas block with a state machine
        state = "top"
        depth = 0
        spirit_id = None
        slot_val = None
        current_block = None
        block_buf = []

        def _strip_block(buf):
            """Strip one level of leading tabs from block body lines."""
            out = []
            for l in buf:
                if l.startswith("\t\t\t\t"):
                    out.append(l[4:])
                elif l.startswith("\t\t\t"):
                    out.append(l[3:])
                else:
                    out.append(l)
            return "\n".join(out).strip()

        def _set_text(widget, content, label):
            old = widget.get("1.0", "end").strip()
            if content != old:
                widget.delete("1.0", "end")
                if content:
                    widget.insert("1.0", content)
                changes.append(f"{label} block updated")

        for ln in ideas_lines:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue

            if state == "top":
                if re.match(r"ideas\s*=\s*\{", s):
                    state = "in_ideas"
                    depth = 1
                continue
            if state == "in_ideas":
                m = re.match(r"(\w+)\s*=\s*\{", s)
                if m:
                    slot_val = m.group(1)
                    state = "in_slot"
                    depth = 2
                continue
            if state == "in_slot":
                m = re.match(r"(\w+)\s*=\s*\{", s)
                if m:
                    spirit_id = m.group(1)
                    state = "in_spirit"
                    depth = 3
                continue
            if state != "in_spirit":
                continue

            if current_block is not None:
                opens = s.count("{")
                closes = s.count("}")
                depth += opens - closes
                if depth <= 3:
                    # block just closed — write to widget
                    content = _strip_block(block_buf)
                    if current_block == "allowed":
                        _set_text(t_allowed, content, "allowed")
                    elif current_block == "available":
                        _set_text(t_available, content, "available")
                    elif current_block == "cancel":
                        _set_text(t_cancel, content, "cancel")
                    elif current_block == "visible":
                        _set_text(t_visible, content, "visible")
                    elif current_block == "on_add":
                        _set_text(t_on_add, content, "on_add")
                    elif current_block == "on_remove":
                        _set_text(t_on_remove, content, "on_remove")
                    elif current_block == "rule":
                        _set_text(t_rule, content, "rule")
                    elif current_block == "modifier":
                        warnings.append(
                            "modifier block — modifier cards not updated "
                            "(use Extra / Custom Modifiers field if needed)"
                        )
                    current_block = None
                    block_buf = []
                    depth = 3
                else:
                    block_buf.append(ln)
                continue

            # Scalar fields
            m = re.match(r"picture\s*=\s*(\S+)", s)
            if m and m.group(1) != v_picture.get():
                v_picture.set(m.group(1))
                changes.append(f"Picture GFX → {m.group(1)!r}")
                continue
            m = re.match(r"^name\s*=\s*(\S+)", s)
            if m and m.group(1) != v_name_key.get():
                v_name_key.set(m.group(1))
                changes.append(f"Name key → {m.group(1)!r}")
                continue
            m = re.match(r"cost\s*=\s*(-?\d+(?:\.\d+)?)", s)
            if m and m.group(1) != v_cost.get():
                v_cost.set(m.group(1))
                changes.append(f"Cost → {m.group(1)}")
                continue
            m = re.match(r"removal_cost\s*=\s*(-?\d+(?:\.\d+)?)", s)
            if m and m.group(1) != v_removal.get():
                v_removal.set(m.group(1))
                changes.append(f"Removal cost → {m.group(1)}")
                continue
            m = re.match(r"ai_will_do\s*=\s*\{\s*factor\s*=\s*(\S+)\s*\}", s)
            if m and m.group(1) != v_ai.get():
                v_ai.set(m.group(1))
                changes.append(f"AI will do → {m.group(1)}")
                continue

            # Spirit/slot ID changes
            if spirit_id and spirit_id != v_id.get():
                v_id.set(spirit_id)
                changes.append(f"Idea ID → {spirit_id!r}")
            if slot_val and slot_val != v_slot.get():
                v_slot.set(slot_val)
                changes.append(f"Slot → {slot_val!r}")

            # Block openings
            matched_block = False
            for bname in (
                "allowed",
                "available",
                "cancel",
                "visible",
                "on_add",
                "on_remove",
                "rule",
                "modifier",
            ):
                if re.match(rf"{bname}\s*=\s*\{{", s):
                    current_block = bname
                    block_buf = []
                    depth = 4
                    matched_block = True
                    break
            if not matched_block and s not in ("}", "{{"):
                # line inside spirit block we didn't handle
                if not re.match(r"^(picture|name|cost|removal_cost|ai_will_do)\b", s):
                    warnings.append(f"Unrecognised line kept as-is: {s!r}")

        # Apply spirit_id / slot if not caught inside loop
        if spirit_id and spirit_id != v_id.get():
            v_id.set(spirit_id)
            changes.append(f"Idea ID → {spirit_id!r}")
        if slot_val and slot_val != v_slot.get():
            v_slot.set(slot_val)
            changes.append(f"Slot → {slot_val!r}")

        # ── Build notification message ────────────────────────────────────
        _lock_lbl.config(
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
                "Please check these manually:\n"
                + "\n".join(f"  ⚠ {w}" for w in warnings)
            )
        if not changes and not warnings:
            parts.append("No field changes detected. Raw override saved.")

        parts.append("\nThe output will export exactly as shown in the preview.")

        messagebox.showinfo("Saved — Review Changes", "\n\n".join(parts), parent=win)

    def _show_current_preview():
        """Render the current output (raw override or live) into the preview box."""
        preview_txt.config(state="normal")
        preview_txt.delete("1.0", "end")
        preview_txt.insert("1.0", _get_output_text())
        if not _edit_mode[0]:
            preview_txt.config(state="disabled")

    _edit_btn.config(command=_toggle_edit)
    _save_raw_btn.config(command=_save_raw)

    # Wire all StringVar fields to live-update the preview
    for _sv in (
        v_id,
        v_name_key,
        v_picture,
        v_slot,
        v_cost,
        v_removal,
        v_loc_name,
        v_loc_desc,
        v_ai,
    ):
        _sv.trace_add("write", _refresh_preview)

    _refresh_mod_cards()
    _refresh_preview()

    def _copy_output():
        txt = _get_output_text()
        win.clipboard_clear()
        win.clipboard_append(txt)
        app._hint("National Spirit code copied to clipboard!")

    def _save_to_mod():
        sid = sanitize_component(
            v_id.get().strip() or "TAG_my_spirit", fallback="TAG_my_spirit"
        )
        slot = v_slot.get().strip() or "country"
        loc_n = v_loc_name.get().strip()
        loc_d = v_loc_desc.get().strip()
        full_txt = _get_output_text()

        split_idx = full_txt.find("# LOCALISATION")
        ideas_block = full_txt[:split_idx].strip() if split_idx > 0 else full_txt

        saved = []
        errs = []
        warnings = []

        # ── Determine ideas file ──────────────────────────────────────────
        if MOD.edit_ideas_file:
            ideas_path = MOD.edit_ideas_file
            mod_root = MOD.root or os.path.dirname(os.path.dirname(ideas_path))
        elif MOD.root:
            mod_root = MOD.root
            ideas_path = os.path.join(mod_root, "common", "ideas", f"{sid}.txt")
        else:
            mod_root = filedialog.askdirectory(
                title="Select MOD ROOT folder (common/ideas/ will be used)"
            )
            if not mod_root:
                return
            ideas_path = os.path.join(mod_root, "common", "ideas", f"{sid}.txt")

        os.makedirs(os.path.dirname(ideas_path), exist_ok=True)
        wf = notifying_workspace_files(MOD, mod_root)

        # ── SAFE APPEND to ideas file ─────────────────────────────────────
        try:
            file_exists = os.path.isfile(ideas_path)
            if file_exists:
                with open(ideas_path, encoding="utf-8-sig", errors="replace") as f:
                    existing = f.read()
                # Check if spirit ID already defined
                if re.search(r"\b" + re.escape(sid) + r"\s*=\s*\{", existing):
                    warnings.append(
                        f"Spirit '{sid}' already exists in file — skipped (edit the file manually to update it)."
                    )
                else:
                    # Extract the spirit's own block from ideas_block
                    # ideas_block = "ideas { <slot> { <sid> = { ... } } }"
                    m_spirit = re.search(
                        r"\b" + re.escape(sid) + r"\s*=\s*\{", ideas_block
                    )
                    if m_spirit:
                        spirit_start = m_spirit.start()
                        brace_start = ideas_block.index("{", spirit_start)
                        close_pos = match_brace(ideas_block, brace_start)
                        spirit_end = (
                            close_pos + 1
                            if close_pos < len(ideas_block)
                            else brace_start
                        )
                        spirit_block = "\t\t" + ideas_block[
                            spirit_start:spirit_end
                        ].replace("\n", "\n\t\t")
                    else:
                        spirit_block = None

                    if spirit_block:
                        # Find the slot section (e.g. "country = {") and insert before its closing }
                        slot_pat = re.compile(r"\b" + re.escape(slot) + r"\s*=\s*\{")
                        sm = slot_pat.search(existing)
                        if sm:
                            si2 = existing.index("{", sm.start())
                            close_pos = match_brace(existing, si2)
                            if close_pos >= len(existing):
                                close_pos = si2
                            new_existing = (
                                existing[:close_pos].rstrip()
                                + "\n\n"
                                + spirit_block
                                + "\n\t"
                                + existing[close_pos:]
                            )
                        else:
                            # Slot section not found — append full block at end
                            new_existing = (
                                existing.rstrip() + "\n\n" + ideas_block + "\n"
                            )
                    else:
                        new_existing = existing.rstrip() + "\n\n" + ideas_block + "\n"

                    wf.write_text(ideas_path, new_existing, encoding="utf-8")
                    rel = os.path.relpath(ideas_path, mod_root)
                    saved.append(rel + "  (spirit appended into existing file)")
            else:
                # New file — write as-is
                wf.write_text(ideas_path, ideas_block, encoding="utf-8")
                rel = os.path.relpath(ideas_path, mod_root)
                saved.append(rel + "  (new file created)")

        except Exception as e:
            errs.append("Ideas: " + str(e))

        # ── SAFE APPEND to localisation ───────────────────────────────────
        if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file):
            loc_path = MOD.edit_loc_file
        else:
            loc_path = os.path.join(
                mod_root, "localisation", "english", f"{sid}_l_english.yml"
            )
        os.makedirs(os.path.dirname(loc_path), exist_ok=True)
        try:
            new_entries = {sid: loc_n, f"{sid}_desc": loc_d}
            existing_keys = set()
            if os.path.isfile(loc_path):
                with open(loc_path, encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        m = re.match(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', line)
                        if m:
                            existing_keys.add(m.group(1))

            to_add = {k: v for k, v in new_entries.items() if k not in existing_keys}
            if to_add:
                if not os.path.isfile(loc_path):
                    wf.write_text(loc_path, "l_english:\n", encoding="utf-8-sig")
                loc_body = "".join(f' {k}: "{v}"\n' for k, v in to_add.items())
                wf.append_text(loc_path, loc_body, encoding="utf-8-sig")
                rel = os.path.relpath(loc_path, mod_root)
                saved.append(rel + f"  (+{len(to_add)} keys)")
            else:
                warnings.append("Localisation keys already present — skipped.")
        except Exception as e:
            errs.append("Localisation: " + str(e))

        # ── SCRIPTED LOC ─────────────────────────────────────────────────
        if MOD.edit_scripted_loc_file:
            sloc_blocks = []
            if sid:
                sloc_blocks.append(
                    {"name": f"GET_{sid}_name", "texts": [], "default": sid}
                )
                if v_loc_desc.get().strip():
                    sloc_blocks.append(
                        {
                            "name": f"GET_{sid}_desc",
                            "texts": [],
                            "default": f"{sid}_desc",
                        }
                    )
            append_scripted_loc(
                MOD.edit_scripted_loc_file, sloc_blocks, saved, errs, mod_root
            )

        msg = ""
        if saved:
            msg += "Saved:\n" + "\n".join(saved)
        if warnings:
            msg += ("\n\n" if msg else "") + "Notes:\n" + "\n".join(warnings)
        if errs:
            msg += ("\n\n" if msg else "") + "Errors:\n" + "\n".join(errs)
        if not msg:
            msg = "Nothing to save."
        messagebox.showinfo("Saved to Mod", msg, parent=win)

    def _browse_existing_spirits():
        import glob as _glob

        if not MOD.loaded or not MOD.root:
            messagebox.showinfo(
                "No Mod Loaded",
                "Load a mod first to browse existing spirits.",
                parent=win,
            )
            return

        ideas_dir = os.path.join(MOD.root, "common", "ideas")
        if not os.path.isdir(ideas_dir):
            messagebox.showinfo(
                "Not Found", "No common/ideas/ directory found in mod.", parent=win
            )
            return

        # Scan all .txt files for spirit/idea IDs
        spirits = []  # list of (spirit_id, slot, file_path)
        for fp in sorted(_glob.glob(os.path.join(ideas_dir, "*.txt"))):
            try:
                src = read_file(fp)
                if not src:
                    continue
                parsed = parse_script(src)
                ideas = parsed.get("ideas", {})
                if not isinstance(ideas, dict):
                    continue
                for slot_key, slot_data in ideas.items():
                    if slot_key in ("_values", "="):
                        continue
                    if not isinstance(slot_data, dict):
                        continue
                    for sid, sdata in slot_data.items():
                        if sid in ("_values", "="):
                            continue
                        if isinstance(sdata, dict):
                            spirits.append((sid, slot_key, fp))
            except Exception:
                pass

        if not spirits:
            messagebox.showinfo(
                tr("spirit.dialog.no_spirits_found.title", "No Spirits Found"),
                tr(
                    "spirit.dialog.no_spirits_found.body",
                    "No spirit/idea definitions found in common/ideas/.",
                ),
                parent=win,
            )
            return

        dlg = tk.Toplevel(win)
        dlg.title(tr("spirit.browse_existing.title", "Browse Existing Spirits"))
        dlg.configure(bg=BG_DARK)
        dlg.geometry("600x520")
        dlg.resizable(True, True)
        dlg.grab_set()

        tk.Label(
            dlg,
            text=tr("spirit.browse_existing.header", "BROWSE EXISTING SPIRITS"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=8,
        ).pack(fill="x", padx=12)
        tk.Label(
            dlg,
            text=tr(
                "spirit.browse_existing.hint",
                "Select a spirit to load it into the editor.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(fill="x", padx=12)
        tk.Frame(dlg, bg=BORDER_G, height=1).pack(fill="x", pady=(4, 0))

        sv_q = tk.StringVar()
        tk.Entry(
            dlg,
            textvariable=sv_q,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(fill="x", padx=10, pady=6, ipady=3)

        frm_list = tk.Frame(dlg, bg=BG_DARK)
        frm_list.pack(fill="both", expand=True, padx=10)
        lb = tk.Listbox(
            frm_list,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=SEL_BG,
            selectforeground=TEXT,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            activestyle="none",
        )
        lb_sb = tk.Scrollbar(frm_list, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        _filtered = list(spirits)

        def _populate(items):
            lb.delete(0, "end")
            for sid, slot_key, fp in items:
                fname = os.path.basename(fp)
                lb.insert("end", f"  {sid:<42}  [{slot_key}]  {fname}")

        def _filter_list(*_):
            q = sv_q.get().lower().strip()
            filtered = [
                (sid, sk, fp)
                for sid, sk, fp in spirits
                if not q
                or q in sid.lower()
                or q in sk.lower()
                or q in os.path.basename(fp).lower()
            ]
            _filtered[:] = filtered
            _populate(filtered)

        sv_q.trace_add("write", _filter_list)
        _populate(spirits)

        info_lbl = tk.Label(
            dlg,
            text=f"{len(spirits)} spirits found in mod",
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
        )
        info_lbl.pack(padx=10, anchor="w", pady=(2, 0))

        def _block_to_text(blk, depth=0):
            return serialize_block(blk, indent="\t" * depth, include_bare_values=True)

        def _set_tw(widget, content):
            widget.delete("1.0", "end")
            if content:
                widget.insert("1.0", content)

        def _load_selected():
            sel = lb.curselection()
            if not sel:
                return
            spirit_id, slot_key, fp = _filtered[sel[0]]
            try:
                src = read_file(fp)
                parsed = parse_script(src)
                ideas = parsed.get("ideas", {})
                slot_data = ideas.get(slot_key, {})
                spirit = (
                    slot_data.get(spirit_id, {}) if isinstance(slot_data, dict) else {}
                )
                if not isinstance(spirit, dict):
                    messagebox.showerror(
                        "Parse Error",
                        f"Could not parse spirit '{spirit_id}'",
                        parent=dlg,
                    )
                    return
            except Exception as e:
                messagebox.showerror("Parse Error", str(e), parent=dlg)
                return

            # Populate identity fields
            v_id.set(spirit_id)
            v_slot.set(slot_key)
            v_picture.set(spirit.get("picture", f"GFX_idea_{spirit_id}"))
            name_key = spirit.get("name", spirit_id)
            v_name_key.set(name_key)
            cost = spirit.get("cost", "")
            v_cost.set(str(cost) if cost else "")
            removal = spirit.get("removal_cost", "")
            v_removal.set(str(removal) if removal else "")
            ai_blk = spirit.get("ai_will_do", {})
            ai_val = str(ai_blk.get("factor", "1")) if isinstance(ai_blk, dict) else "1"
            v_ai.set(ai_val)

            # Populate trigger/effect blocks
            _set_tw(t_allowed, _block_to_text(spirit.get("allowed", {})))
            _set_tw(t_available, _block_to_text(spirit.get("available", {})))
            _set_tw(t_cancel, _block_to_text(spirit.get("cancel", {})))
            _set_tw(t_visible, _block_to_text(spirit.get("visible", {})))
            _set_tw(t_on_add, _block_to_text(spirit.get("on_add", {})))
            _set_tw(t_on_remove, _block_to_text(spirit.get("on_remove", {})))
            _set_tw(t_rule, _block_to_text(spirit.get("rule", {})))
            _set_tw(t_extra, "")

            # Populate modifiers
            spirit_modifiers.clear()
            mod_blk = spirit.get("modifier", {})
            if isinstance(mod_blk, dict):
                for mk, mv in mod_blk.items():
                    if mk == "_values":
                        continue
                    spirit_modifiers.append({"key": mk, "value": str(mv)})
            _refresh_mod_cards()

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
                            k, v = m.group(1), m.group(2)
                            if k == spirit_id and not loc_name:
                                loc_name = v
                            elif k == f"{spirit_id}_desc" and not loc_desc:
                                loc_desc = v
                        if loc_name and loc_desc:
                            break
                    except Exception:
                        pass
            v_loc_name.set(loc_name)
            v_loc_desc.set(loc_desc)

            # Set edit target file so Save to Mod updates the correct file
            MOD.edit_ideas_file = fp

            _refresh_preview()
            dlg.destroy()
            app._hint(f"Loaded spirit '{spirit_id}' from {os.path.basename(fp)}")

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

    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")
    bot = tk.Frame(win, bg=BG_DARK, pady=8)
    bot.pack(fill="x")
    tk.Button(
        bot,
        text=tr("common.copy_to_clipboard", "Copy to Clipboard"),
        command=_copy_output,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=16,
        pady=6,
        cursor="hand2",
    ).pack(side="left", padx=12)
    tk.Button(
        bot,
        text=tr("common.save_to_mod_folder", "Save to Mod Folder"),
        command=_save_to_mod,
        bg="#1a3a1a",
        fg="#4ade80",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=16,
        pady=6,
        cursor="hand2",
    ).pack(side="left", padx=4)
    if MOD.loaded:
        tk.Button(
            bot,
            text=tr("common.browse_existing", "Browse Existing"),
            command=_browse_existing_spirits,
            bg=BG_CARD,
            fg=BLUE,
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=4)
    tk.Button(
        bot,
        text=tr("common.close", "Close"),
        command=win.destroy,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 10),
        padx=16,
        pady=6,
        cursor="hand2",
    ).pack(side="right", padx=12)


# ══════════════════════════════════════════════════════════════════════════════
#  DECISION MAKER WIZARD
#  open_decision_wizard(app)
# ══════════════════════════════════════════════════════════════════════════════
