"""Universal GFX browser and drag-to-place GFX editor.

Three dialogs, two shared across wizards and one owned by the main app:

* :func:`open_universal_gfx_browser` — pick any sprite from any mod GFX
  folder (decisions, ideas, goals, events, flags, interface, custom). Used
  by the decision / event / dyn-mod / spirit wizards.
* :func:`open_gfx_placement_editor` — drag-drop a few sprites on a mock
  decision panel and emit the matching ``interface/*.gfx`` code.
* :func:`open_focus_icon_browser` — the sidebar's Focus icon picker.
  Deliberately narrower than the universal browser: it only ever looks in
  ``gfx/interface/goals/`` and always emits a ``GFX_focus_``-prefixed key,
  matching what the sidebar's Icon GFX field expects. Kept separate rather
  than folded into the universal browser (see the class docstring there for
  why); see ``docs/dev/monolith-migration.md`` for the fuller rationale.

Pillow is optional. If it's missing the tiles render with placeholder text
and the rest of the dialog still works.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from hoi4cm.core.i18n import tr
from hoi4cm.core.image import PIL_OK as _PIL_OK
from hoi4cm.core.image import PILImage as _PILImage
from hoi4cm.core.image import PILImageTk as _PILImageTk
from hoi4cm.core.lru import LRUCache
from hoi4cm.ui.theme import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    GOLD,
    GREEN,
    RED,
    SEL_BG,
    TEAL,
    TEXT,
    TEXT_DIM,
)
from hoi4cm.ui.widgets import _safe_after, _safe_after_idle


def _load_thumbnail(path, width, height, *, preserve_aspect=False):
    if not _PIL_OK or not os.path.exists(path):
        return None
    try:
        with _PILImage.open(path) as source:
            pil = source.convert("RGBA")
    except OSError:
        return None
    resample = getattr(_PILImage, "LANCZOS", getattr(_PILImage, "ANTIALIAS", 1))
    if preserve_aspect:
        source_width, source_height = pil.size
        ratio = min(width / max(source_width, 1), height / max(source_height, 1))
        size = (
            max(1, int(source_width * ratio)),
            max(1, int(source_height * ratio)),
        )
    else:
        size = (width, height)
    return pil.resize(size, resample)


# ─────────────────────────────────────────────────────────────────
# Universal browser
# ─────────────────────────────────────────────────────────────────
def open_universal_gfx_browser(
    win, on_select, title="GFX Browser", gfx_hints=None, mod=None
):
    """Open the universal GFX picker dialog.

    ``on_select(gfx_key, abs_path)`` is called on Confirm.
    ``gfx_hints`` is an optional list of folder category hints to pre-select
    (e.g. ``["decisions", "ideas"]``).
    ``mod`` is the :class:`ModContext` instance — passed in to keep this
    module decoupled from the global mod singleton.
    """
    if mod is None:
        from hoi4cm.mod import MOD

        mod = MOD

    # ── Collect scannable folder groups ──────────────────────────────────
    folder_groups = []  # (group_label, abs_folder_path, gfx_prefix)

    if mod.loaded and os.path.isdir(mod.root):
        r = mod.root
        candidates = [
            (
                "decisions icons",
                os.path.join("gfx", "interface", "decisions"),
                "GFX_decision_",
            ),
            ("decisions (root)", os.path.join("interface"), "GFX_decision_"),
            ("ideas", mod.path_ideas_gfx, "GFX_idea_"),
            ("focus goals", mod.path_goals, "GFX_focus_"),
            (
                "event pictures",
                getattr(
                    mod, "path_event_pictures", os.path.join("gfx", "event_pictures")
                ),
                "GFX_event_",
            ),
            ("flags", os.path.join("gfx", "flags"), "GFX_flag_"),
            ("interface", os.path.join("gfx", "interface"), "GFX_"),
            ("interface (root)", os.path.join("interface"), "GFX_"),
        ]
        for lbl, rel, pfx in candidates:
            full = os.path.join(r, rel)
            if os.path.isdir(full):
                folder_groups.append((lbl, full, pfx))
        for cdir in getattr(mod, "custom_gfx_dirs", []):
            if os.path.isdir(cdir):
                folder_groups.append(
                    (os.path.basename(cdir) + " (custom)", cdir, "GFX_")
                )
        expanded = []
        seen = set()
        for lbl, base, pfx in folder_groups:
            if base in seen:
                continue
            seen.add(base)
            expanded.append((lbl, base, pfx))
            try:
                for ent in sorted(os.listdir(base)):
                    sub = os.path.join(base, ent)
                    if os.path.isdir(sub) and sub not in seen:
                        seen.add(sub)
                        expanded.append((f"  {lbl}/{ent}", sub, pfx))
            except Exception:
                pass
        folder_groups = expanded

    if not folder_groups:
        folder = filedialog.askdirectory(
            title=tr("filedialog.select_gfx_folder", "Select GFX folder"),
            parent=win,
        )
        if not folder:
            return
        folder_groups = [("(selected)", folder, "GFX_")]

    bwin = tk.Toplevel(win)
    bwin.title(title)
    bwin.configure(bg=BG_DARK)
    bwin.geometry("1000x640")
    bwin.resizable(True, True)
    bwin.grab_set()

    top_bar = tk.Frame(bwin, bg=BG_DARK)
    top_bar.pack(fill="x", padx=8, pady=(6, 0))
    tk.Label(top_bar, text="🔍", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 11)).pack(
        side="left", padx=(0, 4)
    )
    search_var = tk.StringVar()
    search_ent = tk.Entry(
        top_bar,
        textvariable=search_var,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    search_ent.pack(side="left", fill="x", expand=True, ipady=4)
    status_lbl = tk.Label(
        top_bar,
        text=tr("gfx.select_folder", "select a folder"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    )
    status_lbl.pack(side="right", padx=8)

    def _add_custom():
        d = filedialog.askdirectory(
            title=tr("filedialog.add_custom_gfx_folder", "Add custom GFX folder"),
            parent=bwin,
        )
        if d:
            if d not in [g[1] for g in folder_groups]:
                folder_groups.append((os.path.basename(d) + " (custom)", d, "GFX_"))
                folder_lb.insert("end", "  " + os.path.basename(d) + " (custom)")
            if d not in getattr(mod, "custom_gfx_dirs", []):
                mod.custom_gfx_dirs.append(d)

    tk.Button(
        top_bar,
        text=tr("gfx.add_folder", "+ Add Folder"),
        command=_add_custom,
        bg=BG_CARD,
        fg=TEAL,
        relief="flat",
        font=("Helvetica", 9),
        cursor="hand2",
        padx=8,
        pady=3,
    ).pack(side="right", padx=4)

    tk.Frame(bwin, bg=BORDER_G, height=1).pack(fill="x", padx=4, pady=(4, 0))

    body_f = tk.Frame(bwin, bg=BG_DARK)
    body_f.pack(fill="both", expand=True, padx=6, pady=6)
    lf = tk.Frame(body_f, bg=BG_PANEL, width=210)
    lf.pack(side="left", fill="y", padx=(0, 5))
    lf.pack_propagate(False)
    tk.Label(
        lf,
        text=tr("gfx.folders", "  FOLDERS"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9, "bold"),
        anchor="w",
        pady=5,
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
    folder_lb.pack(fill="both", expand=True, pady=4, padx=2)
    for lbl2, _, _ in folder_groups:
        folder_lb.insert("end", lbl2)

    rf = tk.Frame(body_f, bg=BG_DARK)
    rf.pack(side="left", fill="both", expand=True)
    cv_f = tk.Frame(rf, bg=BG_PANEL)
    cv_f.pack(fill="both", expand=True)
    cv = tk.Canvas(cv_f, bg=BG_PANEL, highlightthickness=0)
    vsb = tk.Scrollbar(cv_f, orient="vertical", command=cv.yview)
    cv.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    cv.pack(side="left", fill="both", expand=True)

    bot_f = tk.Frame(bwin, bg=BG_DARK)
    bot_f.pack(fill="x", padx=10, pady=6)
    sel_var = tk.StringVar(value="")
    tk.Label(
        bot_f, textvariable=sel_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
    ).pack(side="left", padx=4)
    tk.Button(
        bot_f,
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
    sel_btn = tk.Button(
        bot_f,
        text=tr("common.select", "Select"),
        bg="#1a3322",
        fg="#4b7a5e",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=5,
        cursor="arrow",
        state="disabled",
    )
    sel_btn.pack(side="right")
    sel_path = [None]

    def _do_select():
        if sel_var.get() and sel_path[0]:
            on_select(sel_var.get(), sel_path[0])
            bwin.destroy()

    sel_btn.config(command=_do_select)

    def _on_sel_change(*_):
        v = sel_var.get()
        if v:
            sel_btn.config(bg="#14532d", fg="#0a0a0a", cursor="hand2", state="normal")
        else:
            sel_btn.config(bg="#1a3322", fg="#4b7a5e", cursor="arrow", state="disabled")

    sel_var.trace_add("write", _on_sel_change)

    # ── Grid rendering ────────────────────────────────────────────────────
    COLS = 5
    TILE_W = 110
    TILE_H = 100
    PAD_G = 6
    _st = {
        "pairs": [],
        "img_cache": LRUCache(512),
        # Strong refs for every path with a live canvas image right now — a
        # PhotoImage that drops out of the bounded img_cache above would
        # otherwise get garbage-collected while still on screen, blanking
        # the tile (Tk itself only holds a C-level handle, not a Python ref).
        "pinned_imgs": {},
        "drawn": set(),
        "canvas_ids": {},
        "sel_idx": None,
    }

    def _tile_xy(idx):
        col = idx % COLS
        row = idx // COLS
        return PAD_G + col * (TILE_W + PAD_G), PAD_G + row * (TILE_H + PAD_G)

    def _select_tile(idx):
        old = _st["sel_idx"]
        if old is not None and old in _st["canvas_ids"]:
            rid, _, _ = _st["canvas_ids"][old]
            cv.itemconfig(rid, fill=BG_CARD, outline=BORDER_G)
        _st["sel_idx"] = idx
        gfx_key, path = _st["pairs"][idx]
        sel_var.set(gfx_key)
        sel_path[0] = path
        if idx in _st["canvas_ids"]:
            rid, _, _ = _st["canvas_ids"][idx]
            cv.itemconfig(rid, fill=SEL_BG, outline=BLUE)

    def _draw_tile(idx):
        if idx in _st["drawn"]:
            return
        _st["drawn"].add(idx)
        gfx_key, path = _st["pairs"][idx]
        x, y = _tile_xy(idx)
        is_sel = _st["sel_idx"] == idx
        rid = cv.create_rectangle(
            x,
            y,
            x + TILE_W,
            y + TILE_H,
            fill=SEL_BG if is_sel else BG_CARD,
            outline=BLUE if is_sel else BORDER_G,
            width=2,
            tags=("t", f"t{idx}"),
        )
        iid = cv.create_text(
            x + TILE_W // 2,
            y + 44,
            text="...",
            fill=TEXT_DIM,
            font=("Helvetica", 14),
            tags=("t", f"t{idx}"),
        )
        short = gfx_key
        short = (short[:16] + "…") if len(short) > 16 else short
        lid = cv.create_text(
            x + TILE_W // 2,
            y + TILE_H - 14,
            text=short,
            fill=TEXT_DIM,
            font=("Helvetica", 7),
            width=TILE_W - 8,
            tags=("t", f"t{idx}"),
        )
        _st["canvas_ids"][idx] = (rid, iid, lid)
        for item in (rid, iid, lid):
            cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
            cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, i=idx: [_select_tile(i), _do_select()],
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
        x, y = _tile_xy(idx)
        if img:
            new_iid = cv.create_image(
                x + TILE_W // 2,
                y + 44,
                anchor="center",
                image=img,
                tags=("t", f"t{idx}"),
            )
            _st["pinned_imgs"][path] = img
        else:
            new_iid = cv.create_text(
                x + TILE_W // 2,
                y + 34,
                text="?",
                fill=TEXT_DIM,
                font=("Helvetica", 20),
                tags=("t", f"t{idx}"),
            )
        _st["canvas_ids"][idx] = (rid, new_iid, lid)
        for item in (rid, new_iid, lid):
            cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
            cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, i=idx: [_select_tile(i), _do_select()],
            )

    def _bg_load(snap, indices):
        for i in indices:
            if i >= len(snap):
                break
            _, path = snap[i]
            pil = None
            alts = [path] + [
                os.path.splitext(path)[0] + ext
                for ext in (".png", ".tga", ".dds")
                if os.path.exists(os.path.splitext(path)[0] + ext)
                and os.path.splitext(path)[0] + ext != path
            ]
            for tp in alts:
                pil = _load_thumbnail(tp, 80, 70, preserve_aspect=True)
                if pil is not None:
                    break
            _safe_after(
                bwin,
                0,
                lambda i2=i, path2=path, pil2=pil: _store_image(i2, path2, pil2),
            )

    def _store_image(idx, path, pil):
        if (
            idx >= len(_st["pairs"])
            or _st["pairs"][idx][1] != path
            or path in _st["img_cache"]
        ):
            return
        _st["img_cache"][path] = (
            _PILImageTk.PhotoImage(pil) if pil is not None else None
        )
        _fill_image(idx)

    def _lazy_fill(*_):
        if not _st["pairs"]:
            return
        cv.update_idletasks()
        top2 = cv.canvasy(0)
        bottom2 = cv.canvasy(cv.winfo_height())
        visible = []
        for idx in range(len(_st["pairs"])):
            _, ty = _tile_xy(idx)
            if ty + TILE_H >= top2 and ty <= bottom2:
                _draw_tile(idx)
                visible.append(idx)
        last = max(visible) if visible else 0
        ahead = list(range(last + 1, min(last + 41, len(_st["pairs"]))))
        to_load = [
            i for i in (visible + ahead) if _st["pairs"][i][1] not in _st["img_cache"]
        ]
        if to_load:
            snap = list(_st["pairs"])
            threading.Thread(target=_bg_load, args=(snap, to_load), daemon=True).start()

    def _rebuild_grid(pairs):
        cv.delete("all")
        _st.update(
            {
                "pairs": pairs,
                "drawn": set(),
                "canvas_ids": {},
                "sel_idx": None,
                "pinned_imgs": {},
            }
        )
        sel_var.set("")
        sel_path[0] = None
        if not pairs:
            status_lbl.config(text=tr("gfx.images_count", "{count} images", count=0))
            return
        status_lbl.config(text=f"{len(pairs)} images")
        rows = (len(pairs) + COLS - 1) // COLS
        cv.configure(
            scrollregion=(
                0,
                0,
                PAD_G + COLS * (TILE_W + PAD_G),
                PAD_G + rows * (TILE_H + PAD_G),
            )
        )
        cv.yview_moveto(0)
        _safe_after_idle(bwin, _lazy_fill)

    def _collect_images(folder_path, prefix):
        ft = search_var.get().strip().lower()
        pairs = []
        seen_stems = set()
        for rd, dirs, fnames in os.walk(folder_path):
            dirs.sort()
            for fname in sorted(fnames):
                if not fname.lower().endswith((".dds", ".png", ".tga")):
                    continue
                if ft and ft not in fname.lower() and ft not in rd.lower():
                    continue
                stem = os.path.splitext(fname)[0]
                if stem in seen_stems:
                    continue
                seen_stems.add(stem)
                pairs.append((prefix + stem, os.path.join(rd, fname)))
        return pairs

    def _load_folder(idx):
        if idx < 0 or idx >= len(folder_groups):
            return
        lbl2, fpath, pfx = folder_groups[idx]
        status_lbl.config(text=tr("gfx.scanning", "scanning..."))
        bwin.update_idletasks()
        _rebuild_grid(_collect_images(fpath, pfx))

    def _on_folder_select(evt=None):
        s = folder_lb.curselection()
        if s:
            _load_folder(s[0])

    cv.bind("<Configure>", lambda e: _safe_after_idle(bwin, _lazy_fill))
    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        cv.bind(
            ev,
            lambda e: [
                cv.yview_scroll(
                    -1 if (e.delta > 0 if e.num not in (4, 5) else e.num == 4) else 1,
                    "units",
                ),
                _safe_after_idle(bwin, _lazy_fill),
            ],
        )
    folder_lb.bind("<<ListboxSelect>>", _on_folder_select)
    search_var.trace_add(
        "write",
        lambda *_: _safe_after(
            bwin,
            300,
            lambda: _on_folder_select() if folder_lb.curselection() else None,
        ),
    )

    hint_kws = gfx_hints or []
    pre_sel = 0
    for hi, (lbl2, _, _) in enumerate(folder_groups):
        if any(h.lower() in lbl2.lower() for h in hint_kws):
            pre_sel = hi
            break
    folder_lb.selection_set(pre_sel)
    _load_folder(pre_sel)


# ─────────────────────────────────────────────────────────────────
# Drag-to-place editor
# ─────────────────────────────────────────────────────────────────
def open_gfx_placement_editor(win, initial_items=None, on_confirm=None):
    """Drag icons/pictures on a mock decision panel and emit matching GFX code.

    ``initial_items`` is a list of dicts ``{gfx_key, abs_path, role, x, y, w, h}``.
    ``on_confirm(items, generated_code)`` fires on Confirm.
    """
    CANVAS_W = 460
    CANVAS_H = 320
    PANEL_BG = "#1a1f2e"
    PANEL_HDR = "#141929"
    PANEL_BORD = "#3a4a6a"

    pwin = tk.Toplevel(win)
    pwin.title(tr("gfx_placement.title", "GFX Placement Editor"))
    pwin.configure(bg=BG_DARK)
    pwin.geometry("900x620")
    pwin.resizable(True, True)
    pwin.grab_set()

    tk.Label(
        pwin,
        text=tr("gfx_placement.header", "GFX PLACEMENT EDITOR"),
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 10, "bold"),
        pady=6,
    ).pack(fill="x", padx=12)
    tk.Label(
        pwin,
        text=tr(
            "gfx_placement.description",
            "Drag images to position them. "
            "The tool writes the GFX code matching your layout.",
        ),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
    ).pack(fill="x", padx=12)
    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", pady=(4, 0))

    body = tk.Frame(pwin, bg=BG_DARK)
    body.pack(fill="both", expand=True)

    left_f = tk.Frame(body, bg=BG_DARK)
    left_f.pack(side="left", fill="both", expand=True, padx=8, pady=8)
    tk.Label(
        left_f,
        text=tr(
            "gfx_placement.preview_header",
            "  Decision panel preview  (drag GFX items to position)",
        ),
        bg=BG_DARK,
        fg=TEAL,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    cv_place = tk.Canvas(
        left_f,
        bg=PANEL_BG,
        width=CANVAS_W,
        height=CANVAS_H,
        highlightthickness=2,
        highlightbackground=PANEL_BORD,
        relief="flat",
    )
    cv_place.pack(padx=4, pady=4)

    cv_place.create_rectangle(0, 0, CANVAS_W, 36, fill=PANEL_HDR, outline="")
    cv_place.create_text(
        30,
        18,
        text="📁  Category Name",
        fill="#c8d4e0",
        font=("Palatino Linotype", 11, "bold"),
        anchor="w",
    )
    cv_place.create_line(0, 36, CANVAS_W, 36, fill=PANEL_BORD)
    cv_place.create_text(
        12,
        55,
        text="Category description text goes here...",
        fill="#6a7a8a",
        font=("Palatino Linotype", 9),
        anchor="w",
    )
    cv_place.create_line(0, 120, CANVAS_W, 120, fill=PANEL_BORD)
    for i, lbl in enumerate(["Decision Name 1", "Decision Name 2", "Decision Name 3"]):
        y = 130 + i * 32
        cv_place.create_rectangle(
            0, y, CANVAS_W, y + 30, fill="#131828" if i % 2 else "#161c2e", outline=""
        )
        cv_place.create_rectangle(
            8, y + 4, 30, y + 26, fill="#2a3550", outline="#3a4a6a"
        )
        cv_place.create_text(
            38,
            y + 15,
            text=lbl,
            fill="#c8d4e0",
            font=("Palatino Linotype", 10),
            anchor="w",
        )
        cv_place.create_oval(
            CANVAS_W - 20, y + 9, CANVAS_W - 8, y + 21, fill="#22c55e", outline=""
        )

    grid_on = tk.BooleanVar(value=True)
    _grid_ids = []

    def _draw_grid():
        for gid in _grid_ids:
            cv_place.delete(gid)
        _grid_ids.clear()
        if not grid_on.get():
            return
        for x in range(0, CANVAS_W, 20):
            _grid_ids.append(cv_place.create_line(x, 0, x, CANVAS_H, fill="#1d222d"))
        for y in range(0, CANVAS_H, 20):
            _grid_ids.append(cv_place.create_line(0, y, CANVAS_W, y, fill="#1d222d"))

    _draw_grid()
    grid_on.trace_add("write", lambda *_: _draw_grid())

    snap_on = tk.BooleanVar(value=True)
    GRID_SIZE = 20

    def _snap(v):
        return round(v / GRID_SIZE) * GRID_SIZE if snap_on.get() else v

    items = list(initial_items or [])
    _drag_state = {"active": None, "ox": 0, "oy": 0}

    def _load_img(path, max_w, max_h):
        try:
            if _PIL_OK and os.path.exists(path):
                alts = [path] + [
                    os.path.splitext(path)[0] + ext
                    for ext in (".png", ".tga", ".dds")
                    if os.path.exists(os.path.splitext(path)[0] + ext)
                    and os.path.splitext(path)[0] + ext != path
                ]
                for tp in alts:
                    try:
                        pil = _PILImage.open(tp).convert("RGBA")
                        rs = getattr(
                            _PILImage, "LANCZOS", getattr(_PILImage, "ANTIALIAS", 1)
                        )
                        pw, ph = pil.size
                        ratio = min(max_w / max(pw, 1), max_h / max(ph, 1), 1.0)
                        pil = pil.resize(
                            (max(1, int(pw * ratio)), max(1, int(ph * ratio))),
                            rs,
                        )
                        return _PILImageTk.PhotoImage(pil)
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def _render_item(item):
        if "canvas_id" in item:
            cv_place.delete(item["canvas_id"])
        if "label_id" in item:
            cv_place.delete(item["label_id"])
        if "border_id" in item:
            cv_place.delete(item["border_id"])
        x, y, w, h = item["x"], item["y"], item["w"], item["h"]
        bid = cv_place.create_rectangle(
            x,
            y,
            x + w,
            y + h,
            outline=GOLD if item["role"] == "picture" else BLUE,
            width=2,
            dash=(4, 2),
            fill="",
        )
        if item.get("img_ref"):
            cid = cv_place.create_image(
                x + w // 2,
                y + h // 2,
                image=item["img_ref"],
                anchor="center",
            )
        else:
            cid = cv_place.create_rectangle(
                x + 2,
                y + 2,
                x + w - 2,
                y + h - 2,
                fill="#2a3550",
                outline="",
            )
            cv_place.create_text(
                x + w // 2,
                y + h // 2,
                text="?",
                fill=TEXT_DIM,
                font=("Helvetica", 16),
            )
        short = item["gfx_key"][-18:] if len(item["gfx_key"]) > 18 else item["gfx_key"]
        lid = cv_place.create_text(
            x + w // 2,
            y + h + 10,
            text=short,
            fill=TEXT_DIM,
            font=("Helvetica", 7),
            width=w + 20,
        )
        item["canvas_id"] = cid
        item["label_id"] = lid
        item["border_id"] = bid
        for obj in (bid, cid):
            cv_place.tag_bind(
                obj, "<ButtonPress-1>", lambda e, it=item: _drag_start(e, it)
            )
            cv_place.tag_bind(obj, "<B1-Motion>", lambda e, it=item: _drag_move(e, it))
            cv_place.tag_bind(
                obj, "<ButtonRelease-1>", lambda e, it=item: _drag_end(e, it)
            )

    def _drag_start(e, item):
        _drag_state["active"] = item
        _drag_state["ox"] = e.x - item["x"]
        _drag_state["oy"] = e.y - item["y"]
        cv_place.tag_raise(item.get("canvas_id", ""))
        cv_place.tag_raise(item.get("border_id", ""))
        cv_place.tag_raise(item.get("label_id", ""))

    def _drag_move(e, item):
        if _drag_state["active"] is not item:
            return
        nx = e.x - _drag_state["ox"]
        ny = e.y - _drag_state["oy"]
        nx = max(0, min(nx, CANVAS_W - item["w"]))
        ny = max(0, min(ny, CANVAS_H - item["h"]))
        dx = nx - item["x"]
        dy = ny - item["y"]
        item["x"] = nx
        item["y"] = ny
        for obj_key in ("canvas_id", "border_id"):
            if item.get(obj_key):
                cv_place.move(item[obj_key], dx, dy)
        if item.get("label_id"):
            cv_place.move(item["label_id"], dx, dy)
        _update_code()

    def _drag_end(e, item):
        item["x"] = _snap(item["x"])
        item["y"] = _snap(item["y"])
        _render_item(item)
        _update_code()
        _drag_state["active"] = None

    def _add_item(gfx_key, abs_path, role="icon"):
        max_w, max_h = (60, 60) if role == "icon" else (120, 90)
        img = _load_img(abs_path, max_w, max_h)
        item = {
            "gfx_key": gfx_key,
            "abs_path": abs_path,
            "role": role,
            "x": 40,
            "y": 44,
            "w": max_w,
            "h": max_h,
            "img_ref": img,
        }
        used_positions = [(it["x"], it["y"]) for it in items]
        ox, oy = 40, 44
        while (ox, oy) in used_positions:
            ox += max_w + 10
        item["x"] = ox
        item["y"] = oy
        items.append(item)
        _render_item(item)
        _update_code()

    for it in items:
        if "img_ref" not in it:
            it["img_ref"] = _load_img(
                it.get("abs_path", ""), it.get("w", 60), it.get("h", 60)
            )
        _render_item(it)

    right_f = tk.Frame(body, bg=BG_PANEL, width=360)
    right_f.pack(side="left", fill="y", padx=(0, 8), pady=8)
    right_f.pack_propagate(False)

    tk.Label(
        right_f,
        text=tr("gfx_placement.add_items", "  ADD GFX ITEMS"),
        bg=BG_PANEL,
        fg=GOLD,
        font=("Helvetica", 9, "bold"),
        anchor="w",
        pady=4,
    ).pack(fill="x")
    tk.Frame(right_f, bg=BORDER_G, height=1).pack(fill="x")

    btn_row = tk.Frame(right_f, bg=BG_PANEL)
    btn_row.pack(fill="x", padx=8, pady=6)

    def _browse_and_add(role):
        def _on_sel(gfx_key, path):
            _add_item(gfx_key, path, role)
            _update_props_list()

        open_universal_gfx_browser(
            pwin,
            _on_sel,
            title=f"Pick GFX for {role}",
            gfx_hints=(
                ["decisions", "ideas"]
                if role == "icon"
                else ["decisions", "ideas", "interface"]
            ),
        )

    tk.Button(
        btn_row,
        text=tr("gfx_placement.add_icon", "+ Add Icon"),
        command=lambda: _browse_and_add("icon"),
        bg="#1a2842",
        fg=BLUE,
        relief="flat",
        font=("Helvetica", 9),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="left", padx=(0, 4))
    tk.Button(
        btn_row,
        text=tr("gfx_placement.add_picture", "+ Add Picture"),
        command=lambda: _browse_and_add("picture"),
        bg="#32302a",
        fg=GOLD,
        relief="flat",
        font=("Helvetica", 9),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="left")

    opt_row = tk.Frame(right_f, bg=BG_PANEL)
    opt_row.pack(fill="x", padx=8)
    tk.Checkbutton(
        opt_row,
        text=tr("common.grid", "Grid"),
        variable=grid_on,
        bg=BG_PANEL,
        fg=TEXT_DIM,
        activebackground=BG_PANEL,
        selectcolor=BG_CARD,
        font=("Helvetica", 9),
        cursor="hand2",
    ).pack(side="left")
    tk.Checkbutton(
        opt_row,
        text=tr("common.snap_to_grid", "Snap to grid"),
        variable=snap_on,
        bg=BG_PANEL,
        fg=TEXT_DIM,
        activebackground=BG_PANEL,
        selectcolor=BG_CARD,
        font=("Helvetica", 9),
        cursor="hand2",
    ).pack(side="left", padx=8)

    tk.Frame(right_f, bg=BORDER_G, height=1).pack(fill="x", padx=4, pady=4)

    tk.Label(
        right_f,
        text=tr("gfx_placement.placed_items", "  PLACED ITEMS"),
        bg=BG_PANEL,
        fg=TEAL,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    props_frame = tk.Frame(right_f, bg=BG_PANEL)
    props_frame.pack(fill="x", padx=6)

    def _update_props_list():
        for w in props_frame.winfo_children():
            w.destroy()
        for i, it in enumerate(items):
            row2 = tk.Frame(
                props_frame,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            row2.pack(fill="x", pady=2)
            role_color = BLUE if it["role"] == "icon" else GOLD
            tk.Label(
                row2,
                text=it["role"].upper(),
                bg=BG_CARD,
                fg=role_color,
                font=("Helvetica", 7),
                padx=4,
            ).pack(side="left")
            tk.Label(
                row2,
                text=it["gfx_key"][-22:],
                bg=BG_CARD,
                fg=TEXT,
                font=("Courier", 8),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            for lbl2, attr in [("x", "x"), ("y", "y"), ("w", "w"), ("h", "h")]:
                sv = tk.StringVar(value=str(it[attr]))

                def _on_dim(v, it2=it, a=attr, sv2=sv):
                    try:
                        it2[a] = int(sv2.get())
                        _render_item(it2)
                        _update_code()
                    except Exception:
                        pass

                sv.trace_add("write", _on_dim)
                tk.Label(
                    row2,
                    text=lbl2,
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    font=("Helvetica", 7),
                ).pack(side="left", padx=(4, 0))
                tk.Entry(
                    row2,
                    textvariable=sv,
                    bg=BG_DARK,
                    fg=TEXT,
                    font=("Courier", 8),
                    width=4,
                    relief="flat",
                    insertbackground=BLUE,
                ).pack(side="left")

            def _rm(i2=i):
                it2 = items[i2]
                for k in ("canvas_id", "label_id", "border_id"):
                    if it2.get(k):
                        cv_place.delete(it2[k])
                items.pop(i2)
                _update_props_list()
                _update_code()

            tk.Button(
                row2,
                text="✕",
                command=_rm,
                bg=BG_CARD,
                fg=RED,
                relief="flat",
                font=("Helvetica", 8),
                cursor="hand2",
                padx=4,
            ).pack(side="right")

    _update_props_list()

    tk.Frame(right_f, bg=BORDER_G, height=1).pack(fill="x", padx=4, pady=4)

    tk.Label(
        right_f,
        text=tr("gfx_placement.generated_code", "  GENERATED GFX CODE"),
        bg=BG_PANEL,
        fg=GREEN,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    code_text = tk.Text(
        right_f,
        bg="#080b10",
        fg=GREEN,
        insertbackground=BLUE,
        font=("Courier", 8),
        relief="flat",
        height=10,
        wrap="none",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    code_text.pack(fill="both", expand=True, padx=6, pady=4)

    def _update_code(*_):
        code_text.config(state="normal")
        code_text.delete("1.0", "end")
        lines = ["# ── GFX positioning  (interface/*.gfx)"]
        lines.append("# Place this in any interface/*.gfx file in your mod\n")
        for it in items:
            role = it["role"]
            gk = it["gfx_key"]
            x, y, w, h = it["x"], it["y"], it["w"], it["h"]
            if role == "icon":
                lines.append("spriteType = {\n")
                lines.append(f'\tname = "{gk}"\n')
                lines.append(
                    f'\ttexturefile = "gfx/interface/decisions/'
                    f'{gk.replace("GFX_decision_", "")}.dds"\n'
                )
                lines.append("}\n")
                lines.append("# icon position in containerWindowType:\n")
                lines.append("# iconType = {\n")
                lines.append('#     name = "icon"\n')
                lines.append(f'#     spriteType = "{gk}"\n')
                lines.append(f"#     position = {{ x={x} y={y} }}\n")
                lines.append("# }\n")
            else:
                lines.append("spriteType = {\n")
                lines.append(f'\tname = "{gk}"\n')
                stem = gk.replace("GFX_decision_category_", "").replace(
                    "GFX_decision_", ""
                )
                lines.append(f'\ttexturefile = "gfx/interface/decisions/{stem}.dds"\n')
                lines.append("\tnoOfFrames = 1\n")
                lines.append("}\n")
                lines.append("# picture position in containerWindowType:\n")
                lines.append("# iconType = {\n")
                lines.append('#     name = "picture"\n')
                lines.append(f'#     spriteType = "{gk}"\n')
                lines.append(f"#     position = {{ x={x} y={y} }}\n")
                lines.append(f"#     size = {{ width={w} height={h} }}\n")
                lines.append("# }\n")
            lines.append("\n")
        lines.append("# ── Decision category localisation note:\n")
        lines.append("# picture requires a _desc localisation key to render in-game\n")
        code_text.insert("1.0", "".join(lines))
        code_text.config(state="disabled")

    _update_code()

    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x")
    bot2 = tk.Frame(pwin, bg=BG_DARK)
    bot2.pack(fill="x", padx=10, pady=6)
    tk.Button(
        bot2,
        text=tr("common.cancel", "Cancel"),
        command=pwin.destroy,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=4,
        cursor="hand2",
    ).pack(side="right", padx=4)

    def _confirm():
        code = code_text.get("1.0", "end-1c")
        if on_confirm:
            on_confirm(list(items), code)
        pwin.destroy()

    tk.Button(
        bot2,
        text=tr("gfx_placement.confirm", "Confirm Placement"),
        command=_confirm,
        bg="#14532d",
        fg=GREEN,
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=5,
        cursor="hand2",
    ).pack(side="right")
    tk.Label(
        bot2,
        text=tr(
            "gfx_placement.positions_hint",
            "Positions are written to the GFX code panel",
        ),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
    ).pack(side="left", padx=4)


def _browse_flat_folder(win, folder, on_select, current_gfx):
    """Fallback lazy browser for :func:`open_focus_icon_browser`.

    Used when no mod is loaded: one already-chosen folder, no recursion into
    subfolders, always ``GFX_focus_``-prefixed keys.
    """
    all_files = sorted(
        (f, os.path.join(folder, f))
        for f in os.listdir(folder)
        if f.lower().endswith((".dds", ".png", ".tga"))
    )
    if not all_files:
        messagebox.showinfo(
            tr("dialog.no_files.title", "No Files"),
            tr("dialog.no_gfx_files", "No .dds/.png/.tga files found."),
        )
        return
    pairs = [("GFX_focus_" + os.path.splitext(f)[0], p) for f, p in all_files]
    COLS = 5
    TILE_W = 110
    TILE_H = 100
    PAD = 6
    fwin = tk.Toplevel(win)
    fwin.title(tr("gfx.browser.title", "GFX Browser"))
    fwin.configure(bg=BG_DARK)
    fwin.geometry("700x480")
    cvf = tk.Frame(fwin, bg=BG_PANEL)
    cvf.pack(fill="both", expand=True, padx=8, pady=8)
    cv = tk.Canvas(cvf, bg=BG_PANEL, highlightthickness=0)
    vsb = tk.Scrollbar(cvf, orient="vertical", command=cv.yview)
    cv.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    cv.pack(fill="both", expand=True)
    rows = (len(pairs) + COLS - 1) // COLS
    cv.configure(
        scrollregion=(
            0,
            0,
            PAD + COLS * (TILE_W + PAD),
            PAD + rows * (TILE_H + PAD),
        )
    )
    selected_var = tk.StringVar(value=current_gfx)
    bot = tk.Frame(fwin, bg=BG_DARK)
    bot.pack(fill="x", padx=8, pady=6)
    tk.Label(
        bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
    ).pack(side="left")
    tk.Button(
        bot,
        text=tr("common.cancel", "Cancel"),
        command=fwin.destroy,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=4,
        cursor="hand2",
    ).pack(side="right", padx=4)

    def _apply():
        on_select(selected_var.get())
        fwin.destroy()

    tk.Button(
        bot,
        text=tr("common.select", "Select"),
        command=_apply,
        bg="#14532d",
        fg="#0a0a0a",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=5,
        cursor="hand2",
    ).pack(side="right")

    _cache = LRUCache(512)
    _pinned = {}
    _drawn = set()
    _ids = {}

    def _txy(i):
        return PAD + (i % COLS) * (TILE_W + PAD), PAD + (i // COLS) * (TILE_H + PAD)

    def _fill(idx):
        if idx not in _ids:
            return
        rid, iid, lid = _ids[idx]
        gfx_key, path = pairs[idx]
        img = _cache.get(path)
        cv.delete(iid)
        x, y = _txy(idx)
        if img:
            n = cv.create_image(
                x + TILE_W // 2, y + 44, anchor="center", image=img, tags="tile"
            )
            _pinned[path] = img
        else:
            n = cv.create_text(
                x + TILE_W // 2,
                y + 30,
                text="?",
                fill=TEXT_DIM,
                font=("Helvetica", 20),
                tags="tile",
            )
        _ids[idx] = (rid, n, lid)
        for item in (rid, n, lid):
            cv.tag_bind(item, "<Button-1>", lambda e, k=gfx_key: selected_var.set(k))
            cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, k=gfx_key: [selected_var.set(k), _apply()],
            )

    def _draw(idx):
        if idx in _drawn:
            return
        _drawn.add(idx)
        gfx_key, path = pairs[idx]
        x, y = _txy(idx)
        rid = cv.create_rectangle(
            x,
            y,
            x + TILE_W,
            y + TILE_H,
            fill=BG_CARD,
            outline=BORDER_G,
            width=2,
            tags="tile",
        )
        iid = cv.create_text(
            x + TILE_W // 2,
            y + 44,
            text="...",
            fill=TEXT_DIM,
            font=("Helvetica", 14),
            tags="tile",
        )
        short = gfx_key.replace("GFX_focus_", "")
        short = (short[:16] + "...") if len(short) > 16 else short
        lid = cv.create_text(
            x + TILE_W // 2,
            y + TILE_H - 14,
            text=short,
            fill=TEXT_DIM,
            font=("Helvetica", 7),
            width=TILE_W - 8,
            tags="tile",
        )
        _ids[idx] = (rid, iid, lid)
        if path in _cache:
            _fill(idx)
        for item in (rid, iid, lid):
            cv.tag_bind(item, "<Button-1>", lambda e, k=gfx_key: selected_var.set(k))
            cv.tag_bind(
                item,
                "<Double-Button-1>",
                lambda e, k=gfx_key: [selected_var.set(k), _apply()],
            )

    def _bg(snap, idxs):
        for i in idxs:
            if i >= len(snap):
                break
            _, path = snap[i]
            pil = _load_thumbnail(path, 72, 72)
            _safe_after(
                fwin,
                0,
                lambda idx=i, image_path=path, image=pil: _store_image(
                    idx, image_path, image
                ),
            )

    def _store_image(idx, path, pil):
        if idx >= len(pairs) or pairs[idx][1] != path or path in _cache:
            return
        _cache[path] = _PILImageTk.PhotoImage(pil) if pil is not None else None
        _fill(idx)

    def _lazy(*_):
        top = cv.canvasy(0)
        bot_y = cv.canvasy(cv.winfo_height())
        vis = []
        for i in range(len(pairs)):
            _, ty = _txy(i)
            if ty + TILE_H >= top and ty <= bot_y:
                _draw(i)
                vis.append(i)
        last = max(vis) if vis else 0
        ahead = list(range(last + 1, min(last + 41, len(pairs))))
        to_load = [i for i in vis + ahead if pairs[i][1] not in _cache]
        if to_load:
            t = threading.Thread(target=_bg, args=(list(pairs), to_load), daemon=True)
            t.start()

    cv.bind("<Configure>", lambda e: _safe_after_idle(fwin, _lazy))
    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        cv.bind(
            ev,
            lambda e: [
                cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                _safe_after_idle(fwin, _lazy),
            ],
        )
    _safe_after_idle(fwin, _lazy)


# ─────────────────────────────────────────────────────────────────
# Focus icon browser (sidebar "Icon GFX name" field)
# ─────────────────────────────────────────────────────────────────
def open_focus_icon_browser(win, on_select, current_gfx="", mod=None):
    """Open the focus-goal icon picker for the sidebar's Icon GFX field.

    Narrower than :func:`open_universal_gfx_browser`: this dialog only ever
    browses ``gfx/interface/goals/`` (plus its subfolders), and every key it
    hands back is prefixed ``GFX_focus_``, the naming convention focus icons
    need. ``on_select(gfx_key)`` is called on Confirm (no path — this
    callsite only ever wants the name). ``current_gfx`` is the field's
    existing value: picking the same value back still enables Select, just
    with a dimmer highlight than picking something new.

    Falls back to a flat, non-recursive folder browse (``askdirectory``) via
    :func:`_browse_flat_folder` if no mod is loaded, or if the mod has no
    ``gfx/interface/goals/`` folder.
    """
    if mod is None:
        from hoi4cm.mod import MOD

        mod = MOD

    if not mod.loaded:
        folder = filedialog.askdirectory(
            title=tr("filedialog.select_icon_folder", "Select folder with icon files")
        )
        if folder:
            _browse_flat_folder(win, folder, on_select, current_gfx)
        return

    goals_root = os.path.join(mod.root, "gfx", "interface", "goals")
    if not os.path.isdir(goals_root):
        messagebox.showinfo(
            tr("dialog.not_found.title", "Not Found"),
            tr(
                "dialog.gfx_goals_not_found",
                "Could not find gfx/interface/goals/ in mod.",
            ),
        )
        return

    # ── Instant: just list directory names, no file counting ──
    folders = []
    loose = [
        f
        for f in os.listdir(goals_root)
        if f.lower().endswith((".dds", ".png", ".tga"))
    ]
    if loose:
        folders.append(("[goals root]", goals_root))
    for entry in sorted(os.listdir(goals_root)):
        full = os.path.join(goals_root, entry)
        if os.path.isdir(full):
            folders.append((entry, full))
    if not folders:
        messagebox.showinfo(
            tr("dialog.no_folders.title", "No Folders"),
            tr(
                "dialog.no_goal_subfolders",
                "No subfolders found in gfx/interface/goals/",
            ),
        )
        return

    gwin = tk.Toplevel(win)
    gwin.title(tr("gfx.browser.title", "GFX Browser"))
    gwin.configure(bg=BG_DARK)
    gwin.geometry("900x580")
    gwin.resizable(True, True)

    panes = tk.Frame(gwin, bg=BG_DARK)
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
        text=tr("gfx.filter", "Filter:"),
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
        text=tr("gfx.select_folder", "select a folder"),
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

    bot = tk.Frame(gwin, bg=BG_DARK)
    bot.pack(fill="x", padx=10, pady=6)
    selected_var = tk.StringVar(value="")
    _initial_gfx = current_gfx
    tk.Label(
        bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
    ).pack(side="left", padx=4)
    tk.Button(
        bot,
        text=tr("common.cancel", "Cancel"),
        command=gwin.destroy,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=4,
        cursor="hand2",
    ).pack(side="right", padx=4)

    def _apply():
        on_select(selected_var.get())
        gwin.destroy()

    _sel_btn = tk.Button(
        bot,
        text=tr("common.select", "Select"),
        command=_apply,
        bg="#1a3322",
        fg="#4b7a5e",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=5,
        cursor="arrow",
        state="disabled",
    )
    _sel_btn.pack(side="right")

    def _on_sel_change(*_):
        v = selected_var.get()
        if v and v != _initial_gfx:
            _sel_btn.config(bg="#14532d", fg="#0a0a0a", cursor="hand2", state="normal")
        elif v:
            _sel_btn.config(bg="#1e6b3a", fg="#c8f0d8", cursor="hand2", state="normal")
        else:
            _sel_btn.config(
                bg="#1a3322", fg="#4b7a5e", cursor="arrow", state="disabled"
            )

    selected_var.trace_add("write", _on_sel_change)

    # ── Grid constants ────────────────────────────────────────
    COLS = 5
    TILE_W = 110
    TILE_H = 100
    PAD = 6

    # ── State ─────────────────────────────────────────────────
    _st = {
        "pairs": [],  # [(gfx_key, path), ...]
        "img_cache": LRUCache(512),
        # Strong refs for every path with a live canvas image right now, see
        # open_universal_gfx_browser's identical comment for why this exists.
        "pinned_imgs": {},
        "drawn": set(),  # indices already rendered
        "canvas_ids": {},  # idx -> (rect_id, img_id or txt_id, lbl_id)
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
        """Draw placeholder immediately; image filled in by background thread."""
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
        short = gfx_key.replace("GFX_focus_", "").replace("GFX_goal_", "")
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
                lambda e, i=idx: [_select_tile(i), _apply()],
            )
        if path in _st["img_cache"]:
            _fill_image(idx)

    def _fill_image(idx):
        """Replace placeholder with actual image (called from main thread)."""
        if idx not in _st["canvas_ids"]:
            return
        rid, iid, lid = _st["canvas_ids"][idx]
        gfx_key, path = _st["pairs"][idx]
        img = _st["img_cache"].get(path)
        cv.delete(iid)
        x, y = _tile_xy(idx)
        if img:
            new_iid = cv.create_image(
                x + TILE_W // 2,
                y + 44,
                anchor="center",
                image=img,
                tags=("tile", f"t{idx}"),
            )
            _st["pinned_imgs"][path] = img
        else:
            new_iid = cv.create_text(
                x + TILE_W // 2,
                y + 30,
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
                lambda e, i=idx: [_select_tile(i), _apply()],
            )

    def _bg_load_images(pairs_snapshot, indices):
        """Background: load images for given indices, post update to main thread."""
        for idx in indices:
            if idx >= len(pairs_snapshot):
                break
            gfx_key, path = pairs_snapshot[idx]
            pil = _load_thumbnail(path, 72, 72)
            _safe_after(
                gwin,
                0,
                lambda i=idx, image_path=path, image=pil: _store_image(
                    i, image_path, image
                ),
            )

    def _store_image(idx, path, pil):
        if (
            idx >= len(_st["pairs"])
            or _st["pairs"][idx][1] != path
            or path in _st["img_cache"]
        ):
            return
        _st["img_cache"][path] = (
            _PILImageTk.PhotoImage(pil) if pil is not None else None
        )
        _fill_image(idx)

    def _lazy_fill(*_):
        """Draw placeholders for visible tiles; kick off background image load."""
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
            i for i in (visible + ahead) if _st["pairs"][i][1] not in _st["img_cache"]
        ]
        if to_load:
            snapshot = list(_st["pairs"])
            t = threading.Thread(
                target=_bg_load_images, args=(snapshot, to_load), daemon=True
            )
            t.start()

    def _rebuild(pairs):
        cv.delete("all")
        _st.update(
            {
                "pairs": pairs,
                "drawn": set(),
                "canvas_ids": {},
                "sel_idx": None,
                "pinned_imgs": {},
            }
        )
        # Keep img_cache across folders — avoids reloading same files
        if not pairs:
            status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
            return
        status_lbl.config(text=f"{len(pairs)} icons")
        rows = (len(pairs) + COLS - 1) // COLS
        total_h = PAD + rows * (TILE_H + PAD)
        total_w = PAD + COLS * (TILE_W + PAD)
        cv.configure(scrollregion=(0, 0, total_w, total_h))
        cv.yview_moveto(0)
        _safe_after_idle(gwin, _lazy_fill)

    def _collect_files(folder_path):
        """Fast file scan — no MOD.sprites lookup, just walk the folder."""
        pairs = []
        ft = search_var.get().lower()
        for root_d, dirs, fnames in os.walk(folder_path):
            dirs.sort()
            for fname in sorted(fnames):
                if not fname.lower().endswith((".dds", ".png", ".tga")):
                    continue
                if ft and ft not in fname.lower():
                    continue
                full = os.path.join(root_d, fname)
                stem = os.path.splitext(fname)[0]
                gfx_key = "GFX_focus_" + stem
                pairs.append((gfx_key, full))
        return pairs

    def _load_folder(folder_path):
        status_lbl.config(text=tr("gfx.scanning", "scanning..."))
        gwin.update_idletasks()
        pairs = _collect_files(folder_path)
        _rebuild(pairs)

    def _on_folder_select(evt):
        sel = folder_lb.curselection()
        if not sel:
            return
        _load_folder(folders[sel[0]][1])

    cv.bind("<Configure>", lambda e: _safe_after_idle(gwin, _lazy_fill))
    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        cv.bind(
            ev,
            lambda e: [
                cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                _safe_after_idle(gwin, _lazy_fill),
            ],
        )
    folder_lb.bind("<<ListboxSelect>>", _on_folder_select)
    search_var.trace_add(
        "write",
        lambda *_: _safe_after(
            gwin,
            300,
            lambda: _on_folder_select(None) if folder_lb.curselection() else None,
        ),
    )

    # Auto-select first folder
    if folders:
        folder_lb.selection_set(0)
        _load_folder(folders[0][1])


__all__ = [
    "open_universal_gfx_browser",
    "open_gfx_placement_editor",
    "open_focus_icon_browser",
]
