# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""Decision / Decision Category builder wizard."""

import copy
import json
import os
import re
import tempfile
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox

from hoi4cm.core import (
    append_scripted_loc,
    tr,
)
from hoi4cm.core.image import PIL_OK, PILImage, PILImageTk
from hoi4cm.core.logger import get_logger
from hoi4cm.mod import MOD
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER,
    BORDER_G,
    GOLD,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    SEL_BG,
    TEAL,
    TEXT,
    TEXT_DIM,
    open_gfx_placement_editor,
    open_universal_gfx_browser,
)
from hoi4cm.wizards._shared import (
    _app_img_caches,
)


def open_decision_wizard(app):
    """HOI4 Decision / Decision Category maker — matches mockup layout."""
    win = tk.Toplevel(app)
    win.title(tr("wizard.decision.title", "Decision Maker"))
    win.configure(bg=BG_DARK)
    win.geometry("1340x820")
    win.resizable(True, True)

    # ── Auto-save / undo infrastructure ─────────────────────────────────────
    _autosave_dir = tempfile.gettempdir()
    _autosave_path = os.path.join(_autosave_dir, "hoi4_cm_decision_autosave.json")
    _undo_stack = []  # list of (dm_cats snapshot, dm_decs snapshot)
    _undo_max = 30

    def _snapshot():
        """Push current state onto undo stack."""
        _undo_stack.append((copy.deepcopy(dm_cats), copy.deepcopy(dm_decs)))
        if len(_undo_stack) > _undo_max:
            _undo_stack.pop(0)

    def _do_undo():
        if not _undo_stack:
            _dm_status.config(
                text=tr("common.status.nothing_to_undo", "  !  Nothing to undo")
            )
            return
        cats_snap, decs_snap = _undo_stack.pop()
        dm_cats.clear()
        dm_cats.extend(cats_snap)
        dm_decs.clear()
        dm_decs.extend(decs_snap)
        _rebuild_tree()
        _rebuild_editor()
        _dm_status.config(text=tr("common.status.undo_applied", "  undo applied"))

    def _autosave():
        """Save current state to JSON sidecar."""
        try:
            data = {"cats": dm_cats, "decs": dm_decs}
            with open(_autosave_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_autosave():
        """Restore from autosave JSON if it exists."""
        if not os.path.isfile(_autosave_path):
            return False
        try:
            with open(_autosave_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("cats") and data.get("decs"):
                dm_cats.clear()
                dm_cats.extend(data["cats"])
                dm_decs.clear()
                dm_decs.extend(data["decs"])
                return True
        except Exception:
            pass
        return False

    def _on_dec_win_close():
        # _collect and other helpers may not yet be defined in the closure if the
        # window construction failed early — use a defensive lookup so we never
        # raise NameError during window teardown.
        try:
            _c_fn = _collect  # noqa: F821 - late-bound closure
        except NameError:
            _c_fn = None
        try:
            if _c_fn:
                _c_fn()
        except Exception:
            pass
        try:
            _as_fn = _autosave  # noqa: F821 - late-bound closure
        except NameError:
            _as_fn = None
        try:
            if _as_fn:
                _as_fn()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", _on_dec_win_close)

    # ── colour aliases matching mockup exactly ───────────────────────────────
    C_DARK = BG_DARK  # "#0d1117"
    C_PANEL = BG_PANEL  # "#161b27"
    C_CARD = BG_CARD  # "#1e2435"
    C_TEXT = TEXT  # "#e2e8f0"
    C_DIM = TEXT_DIM  # "#6b7280"
    C_BORD = BORDER  # "#2d3748"
    C_BORDG = BORDER_G  # "#374151"
    C_BLUE = BLUE  # "#3b82f6"
    C_GREEN = GREEN  # "#22c55e"
    C_GOLD = GOLD  # "#f0c040"
    C_RED = RED  # "#ef4444"
    C_ORANGE = ORANGE  # "#f97316"
    C_TEAL = TEAL  # "#2dd4bf"
    C_PURPLE = PURPLE  # "#a78bfa"

    # ── safe blended colours (pre-computed, no alpha appending) ─────────────
    # blend(fg, alpha, bg=#161b27):  used for tag bg, section hr, etc.
    GOLD_TAG_BG = "#2a2415"  # gold 22% on panel
    GOLD_TAG_BD = "#3d3420"  # gold 44%
    BLUE_TAG_BG = "#152038"  # blue 22%
    BLUE_TAG_BD = "#1e3252"  # blue 44%
    TEAL_TAG_BG = "#142b29"  # teal 22%
    TEAL_TAG_BD = "#1d4240"  # teal 44%
    PURP_TAG_BG = "#251e38"  # purple 22%
    PURP_TAG_BD = "#342d50"  # purple 44%
    ORAN_TAG_BG = "#2d1e10"  # orange 22%
    ORAN_TAG_BD = "#432c18"  # orange 44%
    RED_TAG_BG = "#2d1315"  # red 11%
    RED_TAG_BD = "#3d1c1e"  # red 33%
    SEL_BG_TREE = "#17254a"  # sel 33% on panel

    # ── data model ───────────────────────────────────────────────────────────
    dm_cats = []
    dm_decs = []
    sel = {"uid": None, "type": None}
    _uid_n = [0]

    def _uid():
        _uid_n[0] += 1
        return f"dm_{_uid_n[0]}"

    def _new_cat():
        return dict(
            uid=_uid(),
            cat_id="TAG_my_category",
            loc_name="My Category",
            loc_desc="",
            icon="",
            picture="",
            allowed="",
            visible="",
            priority="1",
            visible_when_empty=False,
            on_map_area=False,
            map_state="123",
            map_name="my_map_area",
            map_zoom="850",
            map_trigger="",
            scripted_gui="",
            highlight_states="",
        )

    def _new_dec(cat_uid=""):
        return dict(
            uid=_uid(),
            cat_uid=cat_uid,
            dec_id="TAG_my_decision",
            loc_name="My Decision",
            loc_desc="",
            icon="",
            allowed="",
            visible="",
            available="",
            cost_type="pp",
            cost="25",
            custom_cost_trigger="",
            custom_cost_text="",
            ai_hint_pp_cost="",
            cost_var="",
            cost_amount="",
            days_remove="",
            days_re_enable="",
            fire_only_once=False,
            fixed_random_seed=True,
            is_mission=False,
            mission_timeout="100",
            selectable_mission=True,
            is_good=False,
            activation="",
            timeout_effect="",
            war_with_on_timeout="",
            targeted="none",
            targets="",
            targets_dynamic=False,
            target_non_existing=False,
            target_array="",
            target_trigger="",
            target_root_trigger="",
            state_target_scope="yes",
            on_map_mode="map_and_decisions_view",
            war_complete_tag="",
            war_remove_tag="",
            war_target_complete=False,
            war_target_remove=False,
            complete_effect="",
            remove_effect="",
            cancel_effect="",
            cancel_trigger="",
            cancel_if_not_visible=False,
            modifier="",
            remove_trigger="",
            ai_will_do="base = 0",
            priority="1",
            chain="",
            highlight_states="",
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    def _get_cat(uid):
        return next((c for c in dm_cats if c["uid"] == uid), None)

    def _get_dec(uid):
        return next((d for d in dm_decs if d["uid"] == uid), None)

    def _decs_for(cat_uid):
        return [d for d in dm_decs if d["cat_uid"] == cat_uid]

    def _s(v):
        """Safely coerce any field value to a stripped string (guards against bool/int/None)."""
        if v is None:
            return ""
        if isinstance(v, bool):
            return ""
        return str(v).strip()

    def _dedup_cats():
        """Remove truly duplicate categories (same non-empty cat_id AND same uid duplicated),
        and remove any orphaned decisions whose cat_uid no longer exists."""
        # Only deduplicate if the SAME uid appears more than once
        # (don't merge different cats that happen to share a cat_id)
        seen_uids = set()
        unique_cats = []
        for c in dm_cats:
            if c["uid"] not in seen_uids:
                seen_uids.add(c["uid"])
                unique_cats.append(c)
        valid_uids = {c["uid"] for c in unique_cats}
        dm_cats[:] = unique_cats
        dm_decs[:] = [d for d in dm_decs if d["cat_uid"] in valid_uids]

    # ── TITLE BAR ────────────────────────────────────────────────────────────
    titlebar = tk.Frame(win, bg="#080b10", height=42)
    titlebar.pack(fill="x")
    titlebar.pack_propagate(False)
    tk.Label(
        titlebar,
        text=tr("wizard.decision.header", "DECISION MAKER"),
        bg="#080b10",
        fg=C_GOLD,
        font=("Courier", 13, "bold"),
    ).pack(side="left", padx=14)
    _dm_status = tk.Label(
        titlebar, text="", bg="#080b10", fg=C_DIM, font=("Helvetica", 9, "italic")
    )
    _dm_status.pack(side="right", padx=10)

    def _tbtn(text, cmd, color=C_BLUE):
        b = tk.Button(
            titlebar,
            text=text,
            command=cmd,
            bg=C_CARD,
            fg=color,
            relief="flat",
            font=("Courier", 9),
            cursor="hand2",
            padx=10,
            pady=4,
            highlightthickness=1,
            highlightbackground=color,
        )
        b.pack(side="left", padx=3, pady=6)
        return b

    _tbtn(
        tr("decision.new_category", "+ New Category"),
        lambda: (_collect(), _snapshot(), _add_cat()),
        C_GREEN,
    )
    _tbtn(
        tr("decision.new_decision", "+ New Decision"),
        lambda: (_collect(), _snapshot(), _add_dec()),
        C_BLUE,
    )
    _tbtn(
        tr("common.import_txt", "Import .txt"),
        lambda: (_snapshot(), _import_txt()),
        C_TEAL,
    )
    _tbtn(
        tr("common.import_yml_loc", "Import .yml loc"),
        lambda: _import_yml_loc(),
        C_TEAL,
    )
    _tbtn(
        tr("common.import_scripted_loc", "Import scripted_loc"),
        lambda: _import_scripted_loc(),
        C_TEAL,
    )
    if MOD.loaded:
        _tbtn(tr("common.browse_mod", "Browse Mod"), _browse_mod_decisions, C_TEAL)
    _tbtn(tr("common.export_txt", "Export .txt"), lambda: _export_txt(), C_GOLD)
    _tbtn(tr("common.copy_yml", "Copy .yml"), lambda: _copy_yml(), C_GOLD)
    _tbtn(tr("common.save_to_mod", "Save to Mod"), lambda: _save_to_mod(), C_GREEN)
    _tbtn(tr("common.undo", "↩ Undo"), lambda: _do_undo(), C_DIM)

    win.bind_all("<Control-z>", lambda e: _do_undo())
    win.bind_all("<Control-Z>", lambda e: _do_undo())

    def _key_delete(e=None):
        if sel["type"] == "dec" and sel["uid"]:
            _delete_dec(sel["uid"])
        elif sel["type"] == "cat" and sel["uid"]:
            _delete_cat(sel["uid"])

    win.bind_all("<Delete>", _key_delete)

    def _key_duplicate(e=None):
        if sel["type"] == "dec" and sel["uid"]:
            _duplicate_dec(sel["uid"])
        elif sel["type"] == "cat" and sel["uid"]:
            _duplicate_cat(sel["uid"])

    win.bind_all("<Control-d>", _key_duplicate)
    win.bind_all("<Control-D>", _key_duplicate)

    # Auto-save every 60 seconds while window is open
    def _periodic_autosave():
        try:
            _collect()
            _autosave()
        except Exception:
            pass
        try:
            win.after(60000, _periodic_autosave)
        except Exception:
            pass

    win.after(60000, _periodic_autosave)

    tk.Frame(win, bg=C_BORDG, height=1).pack(fill="x")

    # ── BODY (3 panes) ───────────────────────────────────────────────────────
    body = tk.Frame(win, bg=C_DARK)
    body.pack(fill="both", expand=True)
    paned = tk.PanedWindow(
        body,
        orient="horizontal",
        bg=C_BORDG,
        sashwidth=4,
        sashrelief="flat",
        handlesize=0,
    )
    paned.pack(fill="both", expand=True)

    # ════════════════════════════════════════════════════════════════════════
    # LEFT  ─ tree  (220 px)
    # ════════════════════════════════════════════════════════════════════════
    left_f = tk.Frame(paned, bg=C_PANEL)
    paned.add(left_f, minsize=180, width=230, stretch="never")

    hdr_row = tk.Frame(left_f, bg=C_DARK)
    hdr_row.pack(fill="x")
    tk.Label(
        hdr_row,
        text=tr("decision.tree_header", "  CATEGORIES & DECISIONS"),
        bg=C_DARK,
        fg=C_DIM,
        font=("Courier", 8),
        anchor="w",
        pady=6,
    ).pack(side="left", fill="x", expand=True)
    tk.Frame(left_f, bg=C_BORDG, height=1).pack(fill="x")

    # ── Search bar ──────────────────────────────────────────────────────────
    _tree_filter = tk.StringVar()
    search_row = tk.Frame(left_f, bg=C_PANEL)
    search_row.pack(fill="x", padx=4, pady=3)
    tk.Label(search_row, text="🔍", bg=C_PANEL, fg=C_DIM, font=("Helvetica", 9)).pack(
        side="left", padx=(2, 0)
    )
    filter_entry = tk.Entry(
        search_row,
        textvariable=_tree_filter,
        bg=C_CARD,
        fg=C_TEXT,
        insertbackground=C_BLUE,
        relief="flat",
        font=("Helvetica", 9),
        highlightthickness=1,
        highlightbackground=C_BORDG,
    )
    filter_entry.pack(side="left", fill="x", expand=True, ipady=3, padx=4)

    tk.Button(
        search_row,
        text="✕",
        command=lambda: _tree_filter.set(""),
        bg=C_PANEL,
        fg=C_DIM,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=2,
    ).pack(side="left")
    # Show All / Hide All quick buttons
    vis_row = tk.Frame(left_f, bg=C_PANEL)
    vis_row.pack(fill="x", padx=4, pady=2)
    tk.Label(
        vis_row,
        text=tr("common.preview", "Preview:"),
        bg=C_PANEL,
        fg=C_DIM,
        font=("Helvetica", 8),
    ).pack(side="left", padx=(2, 4))

    def _set_all_cats_visible(value):
        for c in dm_cats:
            cat_visible[c["uid"]] = value
        _rebuild_tree()
        _rebuild_editor()
        _rebuild_right()

    def _show_only_selected():
        target_uid = None
        if sel["type"] == "cat" and sel["uid"]:
            target_uid = sel["uid"]
        elif sel["type"] == "dec" and sel["uid"]:
            dec = _get_dec(sel["uid"])
            if dec:
                target_uid = dec["cat_uid"]
        if target_uid:
            for c in dm_cats:
                cat_visible[c["uid"]] = c["uid"] == target_uid
            _rebuild_tree()
            _rebuild_editor()
            _rebuild_right()

    tk.Button(
        vis_row,
        text=tr("decision.show_all", "Show All"),
        command=lambda: _set_all_cats_visible(True),
        bg=C_CARD,
        fg=C_TEAL,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=2,
    ).pack(side="left", padx=1)
    tk.Button(
        vis_row,
        text=tr("decision.hide_all", "Hide All"),
        command=lambda: _set_all_cats_visible(False),
        bg=C_CARD,
        fg=C_DIM,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=2,
    ).pack(side="left", padx=1)
    tk.Button(
        vis_row,
        text=tr("decision.solo", "Solo"),
        command=_show_only_selected,
        bg=C_CARD,
        fg=C_GOLD,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=2,
        highlightthickness=1,
        highlightbackground=GOLD_TAG_BD,
    ).pack(side="left", padx=1)
    tk.Frame(left_f, bg=C_BORDG, height=1).pack(fill="x")

    tree_cv = tk.Canvas(left_f, bg=C_PANEL, highlightthickness=0)
    tree_sb = tk.Scrollbar(left_f, orient="vertical", command=tree_cv.yview)
    tree_inner = tk.Frame(tree_cv, bg=C_PANEL)
    _tree_win = tree_cv.create_window((0, 0), window=tree_inner, anchor="nw")
    tree_cv.configure(yscrollcommand=tree_sb.set)
    tree_inner.bind(
        "<Configure>", lambda e: tree_cv.configure(scrollregion=tree_cv.bbox("all"))
    )
    tree_cv.bind("<Configure>", lambda e: tree_cv.itemconfig(_tree_win, width=e.width))
    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        tree_cv.bind(
            ev,
            lambda e: tree_cv.yview_scroll(
                -1 if (e.delta > 0 if e.num not in (4, 5) else e.num == 4) else 1,
                "units",
            ),
        )
    tree_sb.pack(side="right", fill="y")
    tree_cv.pack(fill="both", expand=True)

    tree_status = tk.Label(
        left_f, text="", bg=C_DARK, fg=C_DIM, font=("Helvetica", 8), anchor="w", pady=3
    )
    tree_status.pack(fill="x")
    tk.Frame(left_f, bg=C_BORDG, height=1).pack(fill="x")

    cat_expanded = {}
    cat_visible = {}  # uid -> bool; True=shown in preview & code, False=hidden
    _tree_filter.trace_add("write", lambda *_: _rebuild_tree())

    _tree_rows = {}  # uid -> (crow, lbar) for fast highlight updates

    def _update_tree_highlight():
        """Update tree row highlight colors without rebuilding."""
        for uid, (crow, lbar, inn, bg_sel, bg_norm) in _tree_rows.items():
            is_sel = sel["uid"] == uid
            try:
                crow.config(bg=bg_sel if is_sel else bg_norm)
                inn.config(bg=bg_sel if is_sel else bg_norm)
                lbar.config(bg=C_GOLD if is_sel else bg_norm)
            except Exception:
                pass

    def _rebuild_tree():
        _tree_rows.clear()
        for w in tree_inner.winfo_children():
            w.destroy()
        # Apply search filter
        filt = _tree_filter.get().strip().lower()
        for cat in dm_cats:
            decs = _decs_for(cat["uid"])
            # Filter: show cat if name matches OR any child dec matches
            if filt:
                cat_match = (
                    filt in cat["cat_id"].lower()
                    or filt in (cat["loc_name"] or "").lower()
                )
                dec_matches = [
                    d
                    for d in decs
                    if filt in d["dec_id"].lower()
                    or filt in (d["loc_name"] or "").lower()
                ]
                if not cat_match and not dec_matches:
                    continue  # hide this category entirely
                # If filtering, show only matching decs (or all if cat itself matches)
                if not cat_match:
                    decs = dec_matches
            exp = True if filt else cat_expanded.get(cat["uid"], True)
            is_sel = sel["uid"] == cat["uid"] and sel["type"] == "cat"

            # category row
            crow = tk.Frame(tree_inner, bg=C_PANEL, cursor="hand2")
            crow.pack(fill="x")
            bg_c = SEL_BG_TREE if is_sel else C_PANEL
            lbar = tk.Frame(crow, bg=C_GOLD if is_sel else C_PANEL, width=2)
            lbar.pack(side="left", fill="y")
            inn = tk.Frame(crow, bg=bg_c)
            inn.pack(fill="x", expand=True)
            tk.Label(
                inn,
                text="▼" if exp else "▶",
                bg=bg_c,
                fg=C_DIM,
                font=("Helvetica", 8),
                width=2,
            ).pack(side="left", padx=(6, 2), pady=6)
            # Try to show category icon GFX, fall back to folder emoji
            _cicon_key = cat.get("icon", "").strip()
            _cicon_img = _load_dec_icon(_cicon_key, 24) if _cicon_key else None
            if _cicon_img:
                _cicon_lbl = tk.Label(inn, image=_cicon_img, bg=bg_c)
                _cicon_lbl.image = _cicon_img  # keep ref
                _cicon_lbl.pack(side="left", padx=(0, 2))
            else:
                tk.Label(inn, text="📁", bg=bg_c, font=("Helvetica", 12)).pack(
                    side="left"
                )
            info = tk.Frame(inn, bg=bg_c)
            info.pack(side="left", fill="x", expand=True, padx=6, pady=4)
            _vis_fg = C_GOLD if cat_visible.get(cat["uid"], True) else C_DIM
            _cat_disp = _strip_loc_codes(cat["loc_name"] or cat["cat_id"])
            tk.Label(
                info,
                text=("🚫 " if not cat_visible.get(cat["uid"], True) else "")
                + _cat_disp,
                bg=bg_c,
                fg=_vis_fg,
                font=("Helvetica", 10),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                info,
                text=cat["cat_id"],
                bg=bg_c,
                fg=C_DIM,
                font=("Courier", 8),
                anchor="w",
            ).pack(fill="x")
            # visibility + count tag area
            vis = cat_visible.get(cat["uid"], True)
            # eye toggle button
            eye_btn = tk.Button(
                inn,
                text="👁" if vis else "🚫",
                bg=bg_c,
                fg=C_TEAL if vis else C_RED,
                relief="flat",
                font=("Helvetica", 10),
                cursor="hand2",
                padx=4,
                pady=0,
                highlightthickness=0,
                bd=0,
            )
            eye_btn.pack(side="right", padx=(0, 2), pady=4)

            def _toggle_vis(uid=cat["uid"]):
                cat_visible[uid] = not cat_visible.get(uid, True)
                _rebuild_tree()
                _rebuild_editor()
                _rebuild_right()

            eye_btn.config(command=_toggle_vis)
            # count tag
            tag_f = tk.Frame(
                inn,
                bg=GOLD_TAG_BG if vis else C_CARD,
                highlightthickness=1,
                highlightbackground=GOLD_TAG_BD if vis else C_BORDG,
            )
            tag_f.pack(side="right", padx=2, pady=6)
            tk.Label(
                tag_f,
                text=str(len(decs)),
                bg=GOLD_TAG_BG if vis else C_CARD,
                fg=C_GOLD if vis else C_DIM,
                font=("Courier", 9),
                padx=5,
                pady=1,
            ).pack()
            tk.Frame(tree_inner, bg=C_BORD, height=1).pack(fill="x")

            _tree_rows[cat["uid"]] = (crow, lbar, inn, SEL_BG_TREE, C_PANEL)

            def _on_cat(e, uid=cat["uid"]):
                cat_expanded[uid] = not cat_expanded.get(uid, True)
                sel["uid"] = uid
                sel["type"] = "cat"
                _rebuild_tree()
                _rebuild_editor()

            for w in (crow, inn, info, tag_f):
                w.bind("<Button-1>", _on_cat)
            lbar.bind("<Button-1>", _on_cat)

            if exp:
                for dec in decs:
                    is_dsel = sel["uid"] == dec["uid"] and sel["type"] == "dec"
                    drow = tk.Frame(tree_inner, bg=C_PANEL, cursor="hand2")
                    drow.pack(fill="x")
                    bg_d = SEL_BG_TREE if is_dsel else C_PANEL
                    dlbar = tk.Frame(drow, bg=C_BLUE if is_dsel else C_PANEL, width=2)
                    dlbar.pack(side="left", fill="y")
                    dinn = tk.Frame(drow, bg=bg_d)
                    dinn.pack(fill="x", expand=True)
                    # Try to show decision icon GFX, fall back to clipboard emoji
                    _dicon_key = dec.get("icon", "").strip()
                    _dicon_img = _load_dec_icon(_dicon_key, 20) if _dicon_key else None
                    if _dicon_img:
                        _dicon_lbl = tk.Label(dinn, image=_dicon_img, bg=bg_d)
                        _dicon_lbl.image = _dicon_img  # keep ref
                        _dicon_lbl.pack(side="left", padx=(28, 2), pady=5)
                    else:
                        tk.Label(dinn, text="📋", bg=bg_d, font=("Helvetica", 10)).pack(
                            side="left", padx=(28, 4), pady=5
                        )
                    dinfo = tk.Frame(dinn, bg=bg_d)
                    dinfo.pack(side="left", fill="x", expand=True, pady=4)
                    _dec_disp = _strip_loc_codes(dec["loc_name"] or dec["dec_id"])
                    tk.Label(
                        dinfo,
                        text=_dec_disp,
                        bg=bg_d,
                        fg=C_TEXT,
                        font=("Helvetica", 10),
                        anchor="w",
                    ).pack(fill="x")
                    # tag row
                    tagrow = tk.Frame(dinfo, bg=bg_d)
                    tagrow.pack(fill="x")
                    if dec["targeted"] != "none":
                        _tag(tagrow, "T", C_TEAL, TEAL_TAG_BG, TEAL_TAG_BD)
                    if dec["cost_type"] == "pp" and dec.get("cost", "").strip():
                        _tag(
                            tagrow, f'{dec["cost"]}PP', C_GOLD, GOLD_TAG_BG, GOLD_TAG_BD
                        )
                    if dec["chain"]:
                        _tag(
                            tagrow, dec["chain"][:8], C_PURPLE, PURP_TAG_BG, PURP_TAG_BD
                        )
                    tk.Frame(tree_inner, bg=C_BORD, height=1).pack(fill="x")
                    _tree_rows[dec["uid"]] = (drow, dlbar, dinn, SEL_BG_TREE, C_PANEL)

                    def _on_dec(e, uid=dec["uid"]):
                        sel["uid"] = uid
                        sel["type"] = "dec"
                        _update_tree_highlight()  # fast highlight, no rebuild
                        _rebuild_editor()

                    for w in (drow, dinn, dinfo, tagrow):
                        w.bind("<Button-1>", _on_dec)
                    dlbar.bind("<Button-1>", _on_dec)

        total_d = sum(len(_decs_for(c["uid"])) for c in dm_cats)
        tree_status.config(text=f"  {total_d} decisions  ·  {len(dm_cats)} categories")

    def _tag(parent, text, fg, bg, bd):
        f = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=bd)
        f.pack(side="left", padx=(0, 3), pady=1)
        tk.Label(f, text=text, bg=bg, fg=fg, font=("Courier", 8), padx=4, pady=0).pack()

    def _add_cat():
        c = _new_cat()
        dm_cats.append(c)
        sel["uid"] = c["uid"]
        sel["type"] = "cat"
        _rebuild_tree()
        _rebuild_editor()

    def _add_dec():
        if sel["type"] == "cat":
            cat_uid = sel["uid"]
        elif sel["type"] == "dec":
            cat_uid = (_get_dec(sel["uid"]) or {}).get("cat_uid", "")
        else:
            cat_uid = dm_cats[0]["uid"] if dm_cats else None
        if not cat_uid:
            messagebox.showwarning("No Category", "Add a category first.", parent=win)
            return
        d = _new_dec(cat_uid)
        dm_decs.append(d)
        sel["uid"] = d["uid"]
        sel["type"] = "dec"
        _rebuild_tree()
        _rebuild_editor()

    # ════════════════════════════════════════════════════════════════════════
    # MIDDLE  ─ editor  (420 px)
    # ════════════════════════════════════════════════════════════════════════
    mid_f = tk.Frame(paned, bg=C_PANEL)
    paned.add(mid_f, minsize=340, width=440, stretch="never")

    mid_hdr = tk.Label(
        mid_f,
        text=tr("decision.properties_header", "  DECISION PROPERTIES"),
        bg=C_DARK,
        fg=C_DIM,
        font=("Courier", 8),
        anchor="w",
        pady=6,
    )
    mid_hdr.pack(fill="x")
    tk.Frame(mid_f, bg=C_BORDG, height=1).pack(fill="x")

    mid_cv = tk.Canvas(mid_f, bg=C_PANEL, highlightthickness=0)
    mid_sb = tk.Scrollbar(mid_f, orient="vertical", command=mid_cv.yview)
    mid_frm = tk.Frame(mid_cv, bg=C_PANEL)
    _mid_w = mid_cv.create_window((0, 0), window=mid_frm, anchor="nw")
    mid_cv.configure(yscrollcommand=mid_sb.set)
    mid_frm.bind(
        "<Configure>", lambda e: mid_cv.configure(scrollregion=mid_cv.bbox("all"))
    )
    mid_cv.bind("<Configure>", lambda e: mid_cv.itemconfig(_mid_w, width=e.width))
    for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        mid_cv.bind(
            ev,
            lambda e: mid_cv.yview_scroll(
                -1 if (e.delta > 0 if e.num not in (4, 5) else e.num == 4) else 1,
                "units",
            ),
        )
    mid_sb.pack(side="right", fill="y")
    mid_cv.pack(fill="both", expand=True)

    # ── editor widget helpers (all target mid_frm) ───────────────────────────
    _evars = {}  # key -> tk var or Text widget
    _editor_hooks = (
        {}
    )  # name -> callable, called after _populate_editor to refresh dynamic sections

    def _sv(key, val):
        if key in _evars and isinstance(_evars[key], tk.StringVar):
            return _evars[key]  # already registered, return existing var
        v = tk.StringVar(value=str(val))
        _evars[key] = v
        v.trace_add("write", lambda *_: (_collect(), _rebuild_right()))
        return v

    def _bv(key, val):
        if key in _evars and isinstance(_evars[key], tk.BooleanVar):
            return _evars[key]
        v = tk.BooleanVar(value=bool(val))
        _evars[key] = v
        v.trace_add("write", lambda *_: (_collect(), _rebuild_right()))
        return v

    def _reg_text(key, widget, initial=""):
        if initial:
            widget.insert("1.0", str(initial))
        _evars[key] = widget
        widget.bind(
            "<KeyRelease>", lambda e: _collect() if widget.winfo_exists() else None
        )
        return widget

    PAD = dict(padx=14, pady=2)

    def _sec(label, color=C_GOLD):
        """Section header with coloured underline — matches SectionHeader in mockup."""
        f = tk.Frame(mid_frm, bg=C_PANEL)
        f.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(
            f,
            text=label.upper(),
            bg=C_PANEL,
            fg=color,
            font=("Courier", 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Frame(mid_frm, bg=color, height=1).pack(fill="x", padx=14, pady=(0, 4))

    def _field(label, var, mono=False, hint=""):
        """Labelled entry — matches Field component."""
        f = tk.Frame(mid_frm, bg=C_PANEL)
        f.pack(fill="x", **PAD)
        lbl_text = label.upper()
        tk.Label(
            f, text=lbl_text, bg=C_PANEL, fg=C_DIM, font=("Courier", 8), anchor="w"
        ).pack(fill="x")
        ent = tk.Entry(
            f,
            textvariable=var,
            bg=C_CARD,
            fg=C_TEXT,
            insertbackground=C_BLUE,
            font=("Courier" if mono else "Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=C_BORDG,
        )
        ent.pack(fill="x", ipady=4, pady=(2, 0))
        if hint:
            tk.Label(
                f, text=hint, bg=C_PANEL, fg=C_DIM, font=("Helvetica", 8, "italic")
            ).pack(fill="x")
        return ent

    def _toggle(label, var, hint_tag=None):
        """Toggle switch — matches Toggle component."""
        row = tk.Frame(mid_frm, bg=C_PANEL)
        row.pack(fill="x", padx=14, pady=3)
        # small checkbox styled as toggle
        chk = tk.Checkbutton(
            row,
            variable=var,
            bg=C_PANEL,
            activebackground=C_PANEL,
            selectcolor=C_GREEN,
            fg=C_DIM,
            font=("Helvetica", 9),
            cursor="hand2",
            relief="flat",
            bd=0,
        )
        chk.pack(side="left")
        tk.Label(row, text=label, bg=C_PANEL, fg=C_DIM, font=("Helvetica", 9)).pack(
            side="left"
        )
        if hint_tag:
            _inline_tag(row, hint_tag, C_ORANGE, ORAN_TAG_BG, ORAN_TAG_BD)
        var.trace_add("write", lambda *_: (_collect(), _rebuild_right()))

    def _inline_tag(parent, text, fg, bg, bd):
        f = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=bd)
        f.pack(side="left", padx=4)
        tk.Label(f, text=text, bg=bg, fg=fg, font=("Courier", 8), padx=4).pack()

    def _triggerblock(label, key, initial="", hint=None, rows=2):
        """Trigger / code textarea — matches TriggerBlock."""
        f = tk.Frame(mid_frm, bg=C_PANEL)
        f.pack(fill="x", **PAD)
        hrow = tk.Frame(f, bg=C_PANEL)
        hrow.pack(fill="x")
        tk.Label(
            hrow,
            text=label.upper(),
            bg=C_PANEL,
            fg=C_DIM,
            font=("Courier", 8),
            anchor="w",
        ).pack(side="left")
        if hint:
            _inline_tag(hrow, hint, C_TEAL, TEAL_TAG_BG, TEAL_TAG_BD)
        t = tk.Text(
            f,
            bg=C_CARD,
            fg=C_GREEN,
            insertbackground=C_BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=C_BORDG,
            height=rows,
            wrap="none",
            undo=True,
        )
        t.pack(fill="x", pady=(2, 0))
        return _reg_text(key, t, initial)

    def _effectblock(label, key, initial="", rows=4):
        """Effect textarea + Effect Picker button — matches TextArea with extra button."""
        f = tk.Frame(mid_frm, bg=C_PANEL)
        f.pack(fill="x", **PAD)
        tk.Label(
            f, text=label.upper(), bg=C_PANEL, fg=C_DIM, font=("Courier", 8), anchor="w"
        ).pack(fill="x")
        t = tk.Text(
            f,
            bg=C_CARD,
            fg=C_GREEN,
            insertbackground=C_BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=C_BORDG,
            height=rows,
            wrap="none",
            undo=True,
        )
        t.pack(fill="x", pady=(2, 0))
        brow = tk.Frame(f, bg=C_PANEL)
        brow.pack(fill="x", pady=(2, 0))
        tk.Button(
            brow,
            text=tr("effect_picker.button", "+ Effect Picker"),
            command=lambda tw=t: _open_effect_picker(tw),
            bg=C_CARD,
            fg=C_BLUE,
            relief="flat",
            font=("Courier", 8),
            cursor="hand2",
            padx=8,
            pady=2,
            highlightthickness=1,
            highlightbackground=BLUE_TAG_BD,
        ).pack(side="right")
        return _reg_text(key, t, initial)

    def _gfx_field(label, key, initial="", prefix_note="", warn=""):
        """GFX drop zone — matches GfxDropZone component."""
        f = tk.Frame(mid_frm, bg=C_PANEL)
        f.pack(fill="x", **PAD)
        tk.Label(
            f, text=label.upper(), bg=C_PANEL, fg=C_DIM, font=("Courier", 8), anchor="w"
        ).pack(fill="x", pady=(0, 2))
        drop_outer = tk.Frame(
            f, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
        )
        drop_outer.pack(fill="x")
        icon_lbl = tk.Label(
            drop_outer, text="🖼", bg=C_CARD, fg=C_DIM, font=("Helvetica", 14)
        )
        icon_lbl.pack(side="left", padx=6, pady=5)
        sv = _sv(key, initial)
        ent = tk.Entry(
            drop_outer,
            textvariable=sv,
            bg=C_CARD,
            fg=C_TEXT,
            insertbackground=C_BLUE,
            font=("Courier", 10),
            relief="flat",
            highlightthickness=0,
        )
        ent.pack(side="left", fill="x", expand=True, ipady=4)
        tk.Label(
            drop_outer,
            text=tr("gfx.drag_drop_hint", "<- drag .dds/.png/.tga"),
            bg=C_CARD,
            fg=C_DIM,
            font=("Helvetica", 7),
        ).pack(side="left", padx=3)

        def _browse():
            def _on_sel(gfx_key, path):
                sv.set(gfx_key)

            open_universal_gfx_browser(
                win,
                _on_sel,
                title=tr("gfx.browser_for", "GFX Browser - {label}", label=label),
                gfx_hints=["decisions", "ideas"],
            )

        tk.Button(
            drop_outer,
            text=tr("common.browse", "Browse"),
            command=_browse,
            bg=C_CARD,
            fg=C_PURPLE,
            relief="flat",
            font=("Courier", 8),
            cursor="hand2",
            padx=8,
            pady=4,
            highlightthickness=1,
            highlightbackground=PURP_TAG_BD,
        ).pack(side="right", padx=4)

        def _on_drop(e):
            try:
                files = win.tk.splitlist(e.data)
                if files:
                    stem = os.path.splitext(os.path.basename(files[0]))[0]
                    sv.set("GFX_decision_" + stem)
                    drop_outer.configure(highlightbackground=C_BORDG)
            except Exception:
                pass

        try:
            drop_outer.drop_target_register("DND_Files")
            drop_outer.dnd_bind("<<Drop>>", _on_drop)
        except Exception:
            pass
        if prefix_note:
            tk.Label(
                f,
                text="ℹ  " + prefix_note,
                bg=C_PANEL,
                fg=C_TEAL,
                font=("Helvetica", 8),
                anchor="w",
                wraplength=380,
            ).pack(fill="x")
        if warn:
            tk.Label(
                f,
                text="⚠  " + warn,
                bg=C_PANEL,
                fg=C_ORANGE,
                font=("Helvetica", 8),
                anchor="w",
                wraplength=380,
            ).pack(fill="x")

    def _warn_box(text, color=C_ORANGE, bg_override=None, bd_override=None):
        """Orange/red warning banner — matches orange/red info boxes in mockup."""
        bg = bg_override or ORAN_TAG_BG
        bd = bd_override or ORAN_TAG_BD
        f = tk.Frame(mid_frm, bg=bg, highlightthickness=1, highlightbackground=bd)
        f.pack(fill="x", padx=14, pady=3)
        tk.Label(
            f,
            text=text,
            bg=bg,
            fg=color,
            font=("Helvetica", 9),
            anchor="w",
            justify="left",
            wraplength=380,
            padx=8,
            pady=5,
        ).pack(fill="x")

    def _card_frame():
        """Indented card frame for sub-options — matches card border style."""
        f = tk.Frame(
            mid_frm, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
        )
        f.pack(fill="x", padx=14, pady=4)
        return f

    def _type_badge(parent, text, fg, bg, bd):
        f = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=bd)
        f.pack(side="left", padx=(0, 6))
        tk.Label(
            f, text=text, bg=bg, fg=fg, font=("Courier", 9, "bold"), padx=6, pady=2
        ).pack()

    # ── collect current editor state back into data model ────────────────────
    def _safe_evar_get(v):
        """Safely read an evar widget value — returns None if widget destroyed."""
        try:
            if isinstance(v, tk.Text):
                return v.get("1.0", "end-1c") if v.winfo_exists() else None
            return v.get()
        except Exception:
            return None

    def _collect():
        uid = sel["uid"]
        if sel["type"] == "cat":
            c = _get_cat(uid)
            if not c:
                return
            for k in (
                "cat_id",
                "loc_name",
                "loc_desc",
                "icon",
                "picture",
                "allowed",
                "visible",
                "priority",
                "map_state",
                "map_name",
                "map_zoom",
                "map_trigger",
                "scripted_gui",
            ):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        c[k] = val
            for k in ("visible_when_empty", "on_map_area"):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        c[k] = bool(val)
        elif sel["type"] == "dec":
            d = _get_dec(uid)
            if not d:
                return
            for k in (
                "dec_id",
                "loc_name",
                "loc_desc",
                "icon",
                "allowed",
                "visible",
                "available",
                "cost",
                "custom_cost_trigger",
                "custom_cost_text",
                "ai_hint_pp_cost",
                "cost_var",
                "cost_amount",
                "days_remove",
                "days_re_enable",
                "mission_timeout",
                "activation",
                "war_with_on_timeout",
                "targets",
                "target_array",
                "target_trigger",
                "target_root_trigger",
                "state_target_scope",
                "on_map_mode",
                "war_complete_tag",
                "war_remove_tag",
                "cancel_trigger",
                "modifier",
                "remove_trigger",
                "ai_will_do",
                "priority",
                "chain",
                "highlight_states",
            ):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        d[k] = val
            for k in (
                "fire_only_once",
                "fixed_random_seed",
                "is_mission",
                "selectable_mission",
                "is_good",
                "targets_dynamic",
                "target_non_existing",
                "cancel_if_not_visible",
                "war_target_complete",
                "war_target_remove",
            ):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        d[k] = bool(val)
            for k in ("cost_type", "targeted"):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        d[k] = val
            for k in (
                "complete_effect",
                "remove_effect",
                "cancel_effect",
                "timeout_effect",
            ):
                if k in _evars:
                    val = _safe_evar_get(_evars[k])
                    if val is not None:
                        d[k] = val

    # ── BUILD CATEGORY EDITOR ────────────────────────────────────────────────
    def _delete_cat(uid):
        """Delete a category and all its decisions (with confirmation)."""
        c = _get_cat(uid)
        if not c:
            return
        n = len(_decs_for(uid))
        msg = f"Delete category '{c['cat_id']}'"
        if n:
            msg += f" and its {n} decision{'s' if n!=1 else ''}?"
        else:
            msg += "?"
        if not messagebox.askyesno("Delete Category", msg, parent=win):
            return
        _collect()
        _snapshot()
        # dm_cats / dm_decs are closure-scoped lists — mutate in place
        dm_decs[:] = [d for d in dm_decs if d["cat_uid"] != uid]
        dm_cats[:] = [c for c in dm_cats if c["uid"] != uid]
        if dm_cats:
            sel["uid"] = dm_cats[0]["uid"]
            sel["type"] = "cat"
        else:
            sel["uid"] = None
            sel["type"] = None
        _rebuild_tree()
        _rebuild_editor()

    def _duplicate_cat(uid):
        """Duplicate a category with all its decisions."""
        _collect()
        _snapshot()
        c = _get_cat(uid)
        if not c:
            return
        nc = copy.deepcopy(c)
        nc["uid"] = str(uuid.uuid4())
        nc["cat_id"] = c["cat_id"] + "_copy"
        dm_cats.append(nc)
        for d in _decs_for(uid):
            nd = copy.deepcopy(d)
            nd["uid"] = str(uuid.uuid4())
            nd["cat_uid"] = nc["uid"]
            nd["dec_id"] = d["dec_id"] + "_copy"
            dm_decs.append(nd)
        sel["uid"] = nc["uid"]
        sel["type"] = "cat"
        _rebuild_tree()
        _rebuild_editor()

    def _delete_dec(uid):
        """Delete a single decision."""
        d = _get_dec(uid)
        if not d:
            return
        if not messagebox.askyesno(
            "Delete Decision", f"Delete decision '{d['dec_id']}'?", parent=win
        ):
            return
        _collect()
        _snapshot()
        cat_uid = d["cat_uid"]
        dm_decs[:] = [x for x in dm_decs if x["uid"] != uid]
        # Select sibling or parent cat
        siblings = _decs_for(cat_uid)
        if siblings:
            sel["uid"] = siblings[0]["uid"]
            sel["type"] = "dec"
        elif _get_cat(cat_uid):
            sel["uid"] = cat_uid
            sel["type"] = "cat"
        else:
            sel["uid"] = None
            sel["type"] = None
        _rebuild_tree()
        _rebuild_editor()

    def _duplicate_dec(uid):
        """Duplicate a decision."""
        _collect()
        _snapshot()
        d = _get_dec(uid)
        if not d:
            return
        nd = copy.deepcopy(d)
        nd["uid"] = str(uuid.uuid4())
        nd["dec_id"] = d["dec_id"] + "_copy"
        dm_decs.append(nd)
        sel["uid"] = nd["uid"]
        sel["type"] = "dec"
        _rebuild_tree()
        _rebuild_editor()

    def _build_cat_editor(cat):
        mid_hdr.config(
            text=tr("decision.category_properties_header", "  CATEGORY PROPERTIES")
        )
        tk.Label(mid_frm, text="", bg=C_PANEL, height=1).pack()
        # type badge + id + action buttons
        top = tk.Frame(mid_frm, bg=C_PANEL)
        top.pack(fill="x", padx=14, pady=(4, 8))
        _type_badge(top, "CATEGORY", C_GOLD, GOLD_TAG_BG, GOLD_TAG_BD)
        tk.Label(
            top, text=cat["cat_id"], bg=C_PANEL, fg=C_TEXT, font=("Courier", 11)
        ).pack(side="left")
        # Delete + Duplicate buttons (right-aligned)
        tk.Button(
            top,
            text=tr("common.duplicate", "Duplicate"),
            command=lambda: _duplicate_cat(cat["uid"]),
            bg=C_CARD,
            fg=C_TEAL,
            relief="flat",
            font=("Helvetica", 8),
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(side="right", padx=(4, 0))
        tk.Button(
            top,
            text=tr("common.delete", "Delete"),
            command=lambda: _delete_cat(cat["uid"]),
            bg=C_CARD,
            fg="#ef4444",
            relief="flat",
            font=("Helvetica", 8),
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(side="right", padx=(4, 0))

        _sec(tr("decision.section.identity", "Identity"), C_GOLD)
        _field(
            tr("decision.field.category_id", "Category ID"),
            _sv("cat_id", cat["cat_id"]),
            mono=True,
            hint="Used in decisions files:  my_category = { ... }",
        )
        _field(
            tr("decision.field.display_name_loc", "Display Name (localisation)"),
            _sv("loc_name", cat["loc_name"]),
            hint="Loc key shown in-game. Use §Y...§! for colour.",
        )
        _field(
            tr("decision.field.description_loc", "Description (localisation)"),
            _sv("loc_desc", cat["loc_desc"]),
            hint="Tooltip text shown when hovering the category.",
        )

        _sec(tr("decision.section.gfx_icon_picture", "GFX - Icon + Picture"), C_PURPLE)
        _gfx_field(
            tr("common.icon", "Icon"),
            "icon",
            cat["icon"],
            prefix_note="Auto-prefixed → GFX_decision_category_<n>  (or use full GFX_ name directly)",
        )
        _gfx_field(
            tr(
                "decision.field.picture_category_detail",
                "Picture (category detail panel)",
            ),
            "picture",
            cat["picture"],
            warn="Picture only renders if a localisation description is set above",
        )
        # Visual placement button
        prow = tk.Frame(mid_frm, bg=C_PANEL)
        prow.pack(fill="x", padx=14, pady=(4, 2))
        tk.Button(
            prow,
            text=tr("gfx_placement.open_visual_editor", "Visual Placement Editor ->"),
            command=lambda c=cat: _open_placement_cat(c),
            bg=GOLD_TAG_BG,
            fg=C_GOLD,
            relief="flat",
            font=("Courier", 9),
            cursor="hand2",
            padx=10,
            pady=5,
            highlightthickness=1,
            highlightbackground=GOLD_TAG_BD,
        ).pack(side="left")

        _sec(tr("decision.section.triggers", "Triggers"), C_TEAL)
        _triggerblock(
            "allowed  (checked ONCE at game start)",
            "allowed",
            cat["allowed"],
            hint="once-only",
        )
        _triggerblock(
            "visible  (checked every frame)",
            "visible",
            cat["visible"],
            hint="per-frame",
        )

        _sec(tr("decision.section.options", "Options"), C_BLUE)
        _field(
            tr("decision.field.priority", "Priority"),
            _sv("priority", cat["priority"]),
            mono=True,
            hint="Higher = closer to top.  Default = 1",
        )
        _toggle(
            "visible_when_empty — show category even with no visible decisions",
            _bv("visible_when_empty", cat["visible_when_empty"]),
        )
        on_map_v = _bv("on_map_area", cat["on_map_area"])
        _toggle("on_map_area — camera move button at top of list", on_map_v)
        _toggle(
            "scripted_gui — embed custom GUI panel in category",
            _bv("scripted_gui", False),
        )

        map_host = tk.Frame(mid_frm, bg=C_PANEL)
        map_host.pack(fill="x")

        def _toggle_map(*_):
            for w in map_host.winfo_children():
                w.destroy()
            if not on_map_v.get():
                return
            cf = tk.Frame(
                map_host, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
            )
            cf.pack(fill="x", padx=14, pady=4)
            tk.Label(
                cf,
                text="  ON MAP AREA CONFIG",
                bg=C_CARD,
                fg=C_TEAL,
                font=("Courier", 9, "bold"),
                pady=4,
                anchor="w",
            ).pack(fill="x")
            for lbl2, k2, dflt2, ht2 in [
                ("Target state", "map_state", cat["map_state"], "state ID"),
                ("Name (loc key)", "map_name", cat["map_name"], "localisation key"),
                (
                    "Zoom level",
                    "map_zoom",
                    cat["map_zoom"],
                    "50–3000  (lower = more zoomed in)",
                ),
            ]:
                r2 = tk.Frame(cf, bg=C_CARD)
                r2.pack(fill="x", padx=8, pady=1)
                tk.Label(
                    r2,
                    text=lbl2.upper(),
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                    anchor="w",
                ).pack(fill="x")
                tk.Entry(
                    r2,
                    textvariable=_sv(k2, dflt2),
                    bg=BG_DARK,
                    fg=C_TEXT,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                ).pack(fill="x", ipady=3, pady=(2, 4))
                if ht2:
                    tk.Label(
                        r2,
                        text=ht2,
                        bg=C_CARD,
                        fg=C_DIM,
                        font=("Helvetica", 8, "italic"),
                    ).pack(fill="x")
            tk.Label(
                cf,
                text="  TARGET_ROOT_TRIGGER",
                bg=C_CARD,
                fg=C_DIM,
                font=("Courier", 8),
                anchor="w",
                padx=8,
            ).pack(fill="x")
            mt = tk.Text(
                cf,
                bg=BG_DARK,
                fg=C_GREEN,
                insertbackground=C_BLUE,
                font=("Courier", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=C_BORDG,
                height=2,
                wrap="none",
            )
            mt.pack(fill="x", padx=8, pady=(2, 6))
            _reg_text("map_trigger", mt, cat.get("map_trigger", ""))

        on_map_v.trace_add("write", _toggle_map)
        _toggle_map()

    # ── BUILD DECISION EDITOR ────────────────────────────────────────────────
    def _build_dec_editor(dec):
        mid_hdr.config(text=tr("decision.properties_header", "  DECISION PROPERTIES"))
        tk.Label(mid_frm, text="", bg=C_PANEL, height=1).pack()
        # type badge row — DECISION + tags
        top = tk.Frame(mid_frm, bg=C_PANEL)
        top.pack(fill="x", padx=14, pady=(4, 8))
        _type_badge(top, "DECISION", C_BLUE, BLUE_TAG_BG, BLUE_TAG_BD)
        if dec["targeted"] != "none":
            _type_badge(top, "TARGETED", C_TEAL, TEAL_TAG_BG, TEAL_TAG_BD)
        if dec["is_mission"]:
            _type_badge(top, "MISSION", C_PURPLE, PURP_TAG_BG, PURP_TAG_BD)
        if dec["fire_only_once"]:
            _type_badge(top, "ONCE", C_ORANGE, ORAN_TAG_BG, ORAN_TAG_BD)
        tk.Label(
            top, text=dec["dec_id"], bg=C_PANEL, fg=C_TEXT, font=("Courier", 11)
        ).pack(side="left")
        tk.Button(
            top,
            text=tr("common.duplicate", "Duplicate"),
            command=lambda: _duplicate_dec(dec["uid"]),
            bg=C_CARD,
            fg=C_TEAL,
            relief="flat",
            font=("Helvetica", 8),
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(side="right", padx=(4, 0))
        tk.Button(
            top,
            text=tr("common.delete", "Delete"),
            command=lambda: _delete_dec(dec["uid"]),
            bg=C_CARD,
            fg="#ef4444",
            relief="flat",
            font=("Helvetica", 8),
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(side="right", padx=(4, 0))

        _sec(tr("decision.section.identity", "Identity"), C_GOLD)
        _field(
            tr("decision.field.decision_id", "Decision ID"),
            _sv("dec_id", dec["dec_id"]),
            mono=True,
            hint="Unique key, e.g. TAG_my_decision",
        )
        _field(
            tr("decision.field.display_name_loc", "Display Name (localisation)"),
            _sv("loc_name", dec["loc_name"]),
            hint="Loc key shown in-game. Use §Y...§! for colour.",
        )
        _field(
            tr(
                "decision.field.description_loc_optional",
                "Description (localisation, optional)",
            ),
            _sv("loc_desc", dec.get("loc_desc", "")),
        )
        _gfx_field(
            tr("common.icon", "Icon"),
            "icon",
            dec["icon"],
            prefix_note="Auto-prefixed → GFX_decision_<n>  (or full GFX_ name). Supports conditional icon blocks.",
        )
        _field(
            tr("decision.field.chain_group", "Chain / group tag (visual only)"),
            _sv("chain", dec["chain"]),
            mono=True,
        )

        _sec(tr("decision.section.triggers", "Triggers"), C_TEAL)
        _triggerblock(
            "allowed  (once-only at game start)",
            "allowed",
            dec["allowed"],
            hint="once-only",
        )
        _triggerblock(
            "visible  (per-frame — makes decision show)",
            "visible",
            dec["visible"],
            hint="per-frame",
        )
        _triggerblock(
            "available  (per-frame — enables or greys out)",
            "available",
            dec["available"],
            hint="per-frame",
        )

        _sec(tr("decision.section.cost", "Cost"), C_BLUE)
        use_custom_v = tk.BooleanVar(value=(dec["cost_type"] != "pp"))
        _evars["_use_custom"] = use_custom_v
        _toggle("Use custom cost (non-PP cost)", use_custom_v, hint_tag="visual only")

        cost_host = tk.Frame(mid_frm, bg=C_PANEL)
        cost_host.pack(fill="x")

        def _rebuild_cost(*_):
            if not cost_host.winfo_exists():
                return
            for w in cost_host.winfo_children():
                w.destroy()
            if not use_custom_v.get():
                _evars["cost_type"] = tk.StringVar(value="pp")
                # inline field inside cost_host
                cf = tk.Frame(cost_host, bg=C_PANEL)
                cf.pack(fill="x", **PAD)
                tk.Label(
                    cf,
                    text=tr("decision.cost_pp", "COST (POLITICAL POWER)"),
                    bg=C_PANEL,
                    fg=C_DIM,
                    font=("Courier", 8),
                ).pack(fill="x")
                sv2 = _sv("cost", dec["cost"])
                tk.Entry(
                    cf,
                    textvariable=sv2,
                    bg=C_CARD,
                    fg=C_TEXT,
                    insertbackground=C_BLUE,
                    font=("Courier", 10),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                ).pack(fill="x", ipady=4, pady=(2, 0))
                tk.Label(
                    cf,
                    text=tr("decision.cost_hint", "Can be a variable.  Default = 0"),
                    bg=C_PANEL,
                    fg=C_DIM,
                    font=("Helvetica", 8, "italic"),
                ).pack(fill="x")
            else:
                _evars["cost_type"] = tk.StringVar(value="custom")
                cf = tk.Frame(
                    cost_host,
                    bg=C_CARD,
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                )
                cf.pack(fill="x", padx=14, pady=4)
                # build trigger block inside card
                tk.Label(
                    cf,
                    text="CUSTOM_COST_TRIGGER",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                    padx=4,
                ).pack(fill="x", pady=(4, 0))
                ct = tk.Text(
                    cf,
                    bg=BG_DARK,
                    fg=C_GREEN,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    height=2,
                    wrap="none",
                )
                ct.pack(fill="x", padx=4, pady=2)
                _reg_text("custom_cost_trigger", ct, dec["custom_cost_trigger"])
                for lbl2, k2, dflt2, ht2 in [
                    (
                        "custom_cost_text (loc key)",
                        "custom_cost_text",
                        dec["custom_cost_text"],
                        "",
                    ),
                    (
                        "ai_hint_pp_cost",
                        "ai_hint_pp_cost",
                        dec["ai_hint_pp_cost"],
                        "Tell AI how much PP to save (optional)",
                    ),
                ]:
                    r2 = tk.Frame(cf, bg=C_CARD)
                    r2.pack(fill="x", padx=4, pady=1)
                    tk.Label(
                        r2, text=lbl2.upper(), bg=C_CARD, fg=C_DIM, font=("Courier", 8)
                    ).pack(fill="x")
                    tk.Entry(
                        r2,
                        textvariable=_sv(k2, dflt2),
                        bg=BG_DARK,
                        fg=C_TEXT,
                        insertbackground=C_BLUE,
                        font=("Courier", 9),
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=C_BORDG,
                    ).pack(fill="x", ipady=3, pady=(2, 4))
                    if ht2:
                        tk.Label(
                            r2,
                            text=ht2,
                            bg=C_CARD,
                            fg=C_DIM,
                            font=("Helvetica", 8, "italic"),
                        ).pack(fill="x")
                # warning banner inside card
                wb = tk.Frame(
                    cf,
                    bg=ORAN_TAG_BG,
                    highlightthickness=1,
                    highlightbackground=ORAN_TAG_BD,
                )
                wb.pack(fill="x", padx=4, pady=(2, 6))
                tk.Label(
                    wb,
                    text="⚠ Custom cost does NOT deduct anything automatically —\nadd hidden_effect in complete_effect to subtract manually",
                    bg=ORAN_TAG_BG,
                    fg=C_ORANGE,
                    font=("Helvetica", 8),
                    justify="left",
                    padx=6,
                    pady=4,
                ).pack(fill="x")

        use_custom_v.trace_add("write", _rebuild_cost)
        _rebuild_cost()

        _sec(tr("decision.section.timer", "Timer"), C_PURPLE)
        _field(
            tr(
                "decision.field.days_remove",
                "days_remove  (-1 = never auto-removes, blank = no timer)",
            ),
            _sv("days_remove", dec["days_remove"]),
            mono=True,
        )
        _field(
            tr(
                "decision.field.days_re_enable",
                "days_re_enable  (cooldown, blank = next day)",
            ),
            _sv("days_re_enable", dec["days_re_enable"]),
            mono=True,
        )
        _toggle(
            "fire_only_once — disappears after first use",
            _bv("fire_only_once", dec["fire_only_once"]),
        )
        _toggle(
            "fixed_random_seed — same random result each use (default ON)",
            _bv("fixed_random_seed", dec["fixed_random_seed"]),
        )

        _sec(tr("decision.section.mission_mode", "Mission Mode"), C_PURPLE)
        miss_v = _bv("is_mission", dec["is_mission"])
        _evars["_is_mission"] = miss_v
        _toggle(
            tr(
                "decision.toggle.mission_mode",
                "Turn into a MISSION (adds days_mission_timeout)",
            ),
            miss_v,
        )
        miss_host = tk.Frame(mid_frm, bg=C_PANEL)
        miss_host.pack(fill="x")

        def _rebuild_mission(*_):
            if not miss_host.winfo_exists():
                return
            for w in miss_host.winfo_children():
                w.destroy()
            if not miss_v.get():
                return
            cf = tk.Frame(
                miss_host, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
            )
            cf.pack(fill="x", padx=14, pady=4)
            # fields inside card
            for lbl2, k2, dflt2 in [
                ("days_mission_timeout", "mission_timeout", dec["mission_timeout"]),
            ]:
                r2 = tk.Frame(cf, bg=C_CARD)
                r2.pack(fill="x", padx=6, pady=2)
                tk.Label(
                    r2, text=lbl2.upper(), bg=C_CARD, fg=C_DIM, font=("Courier", 8)
                ).pack(fill="x")
                tk.Entry(
                    r2,
                    textvariable=_sv(k2, dflt2),
                    bg=BG_DARK,
                    fg=C_TEXT,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                ).pack(fill="x", ipady=3, pady=(2, 4))

            def _mtoggle(lbl3, k3, v3):
                rr = tk.Frame(cf, bg=C_CARD)
                rr.pack(fill="x", padx=6, pady=1)
                bv2 = _bv(k3, v3)
                tk.Checkbutton(
                    rr,
                    variable=bv2,
                    bg=C_CARD,
                    activebackground=C_CARD,
                    selectcolor=C_GREEN,
                    font=("Helvetica", 9),
                    cursor="hand2",
                ).pack(side="left")
                tk.Label(
                    rr, text=lbl3, bg=C_CARD, fg=C_DIM, font=("Helvetica", 9)
                ).pack(side="left")

            _mtoggle(
                tr(
                    "decision.toggle.selectable_mission",
                    "selectable_mission - player must click to activate",
                ),
                "selectable_mission",
                dec["selectable_mission"],
            )
            _mtoggle(
                tr(
                    "decision.toggle.is_good",
                    "is_good - swaps tooltip to show 'Effects when failed'",
                ),
                "is_good",
                dec["is_good"],
            )
            # activation trigger
            tk.Label(
                cf,
                text=tr(
                    "decision.field.activation",
                    "ACTIVATION  (REPLACES VISIBLE - CHECKED DAILY)",
                ),
                bg=C_CARD,
                fg=C_DIM,
                font=("Courier", 8),
                padx=6,
            ).pack(fill="x", pady=(4, 0))
            at = tk.Text(
                cf,
                bg=BG_DARK,
                fg=C_GREEN,
                insertbackground=C_BLUE,
                font=("Courier", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=C_BORDG,
                height=2,
                wrap="none",
            )
            at.pack(fill="x", padx=6, pady=2)
            _reg_text("activation", at, dec["activation"])
            # warning
            wb2 = tk.Frame(
                cf,
                bg=ORAN_TAG_BG,
                highlightthickness=1,
                highlightbackground=ORAN_TAG_BD,
            )
            wb2.pack(fill="x", padx=6, pady=(0, 2))
            tk.Label(
                wb2,
                text="⚠ visible = {} does NOTHING in missions — use activation instead",
                bg=ORAN_TAG_BG,
                fg=C_ORANGE,
                font=("Helvetica", 8),
                padx=4,
                pady=3,
            ).pack(fill="x")
            # timeout_effect
            tk.Label(
                cf,
                text=tr(
                    "decision.field.timeout_effect",
                    "TIMEOUT_EFFECT  (FIRES IF TIMER RUNS OUT)",
                ),
                bg=C_CARD,
                fg=C_DIM,
                font=("Courier", 8),
                padx=6,
            ).pack(fill="x", pady=(4, 0))
            te = tk.Text(
                cf,
                bg=BG_DARK,
                fg=C_GREEN,
                insertbackground=C_BLUE,
                font=("Courier", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=C_BORDG,
                height=2,
                wrap="none",
            )
            te.pack(fill="x", padx=6, pady=(2, 6))
            _reg_text("timeout_effect", te, dec.get("timeout_effect", ""))

        miss_v.trace_add("write", _rebuild_mission)
        _rebuild_mission()

        _sec(tr("decision.section.targeting", "Targeting"), C_TEAL)
        tgt_country_v = tk.BooleanVar(value=(dec["targeted"] == "country"))
        tgt_state_v = tk.BooleanVar(value=(dec["targeted"] == "state"))
        _evars["_tgt_country"] = tgt_country_v
        _evars["_tgt_state"] = tgt_state_v

        def _on_tgt_country(*_):
            if tgt_country_v.get():
                tgt_state_v.set(False)
            _sync_targeted()

        def _on_tgt_state(*_):
            if tgt_state_v.get():
                tgt_country_v.set(False)
            _sync_targeted()

        def _sync_targeted():
            if tgt_country_v.get():
                _evars["targeted"] = tk.StringVar(value="country")
            elif tgt_state_v.get():
                _evars["targeted"] = tk.StringVar(value="state")
            else:
                _evars["targeted"] = tk.StringVar(value="none")
            _rebuild_tgt()

        row_tgt = tk.Frame(mid_frm, bg=C_PANEL)
        row_tgt.pack(fill="x", padx=14, pady=3)
        tk.Checkbutton(
            row_tgt,
            variable=tgt_country_v,
            bg=C_PANEL,
            activebackground=C_PANEL,
            selectcolor=C_GREEN,
            font=("Helvetica", 9),
            cursor="hand2",
        ).pack(side="left")
        tk.Label(
            row_tgt,
            text=tr(
                "decision.targeted_country", "Targeted decision (FROM = target country)"
            ),
            bg=C_PANEL,
            fg=C_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        tgt_country_v.trace_add("write", _on_tgt_country)
        row_tst = tk.Frame(mid_frm, bg=C_PANEL)
        row_tst.pack(fill="x", padx=14, pady=3)
        tk.Checkbutton(
            row_tst,
            variable=tgt_state_v,
            bg=C_PANEL,
            activebackground=C_PANEL,
            selectcolor=C_GREEN,
            font=("Helvetica", 9),
            cursor="hand2",
        ).pack(side="left")
        tk.Label(
            row_tst,
            text=tr("decision.targeted_state", "State targeted (FROM = target state)"),
            bg=C_PANEL,
            fg=C_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        tgt_state_v.trace_add("write", _on_tgt_state)

        tgt_host = tk.Frame(mid_frm, bg=C_PANEL)
        tgt_host.pack(fill="x")
        tgt_sub_tab = tk.StringVar(value="countries")

        def _rebuild_tgt(*_):
            if not tgt_host.winfo_exists():
                return
            for w in tgt_host.winfo_children():
                w.destroy()
            targeted = (
                "country"
                if tgt_country_v.get()
                else ("state" if tgt_state_v.get() else "none")
            )
            _evars["targeted"] = tk.StringVar(value=targeted)
            if targeted == "none":
                # standard war warnings card
                cf = tk.Frame(
                    tgt_host,
                    bg=C_CARD,
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                )
                cf.pack(fill="x", padx=14, pady=4)
                war_c_v = _bv("war_target_complete", dec["war_complete_tag"] != "")
                war_r_v = _bv("war_target_remove", dec["war_remove_tag"] != "")

                def _mtog2(lbl3, bv2, parent=cf):
                    rr = tk.Frame(parent, bg=C_CARD)
                    rr.pack(fill="x", padx=6, pady=1)
                    tk.Checkbutton(
                        rr,
                        variable=bv2,
                        bg=C_CARD,
                        activebackground=C_CARD,
                        selectcolor=C_GREEN,
                        font=("Helvetica", 9),
                        cursor="hand2",
                    ).pack(side="left")
                    tk.Label(
                        rr, text=lbl3, bg=C_CARD, fg=C_DIM, font=("Helvetica", 9)
                    ).pack(side="left")

                _mtog2("war_with_on_complete = TAG", war_c_v)
                _mtog2("war_with_on_remove = TAG", war_r_v)
                war_host = tk.Frame(cf, bg=C_CARD)
                war_host.pack(fill="x", padx=6, pady=(0, 4))

                def _rebuild_war_tag(*_):
                    if not war_host.winfo_exists():
                        return
                    for w in war_host.winfo_children():
                        w.destroy()
                    if war_c_v.get() or war_r_v.get():
                        rr2 = tk.Frame(war_host, bg=C_CARD)
                        rr2.pack(fill="x", pady=1)
                        tk.Label(
                            rr2,
                            text="TARGET TAG",
                            bg=C_CARD,
                            fg=C_DIM,
                            font=("Courier", 8),
                        ).pack(fill="x")
                        tk.Entry(
                            rr2,
                            textvariable=_sv(
                                "war_complete_tag", dec["war_complete_tag"]
                            ),
                            bg=BG_DARK,
                            fg=C_TEXT,
                            insertbackground=C_BLUE,
                            font=("Courier", 9),
                            relief="flat",
                            highlightthickness=1,
                            highlightbackground=C_BORDG,
                        ).pack(fill="x", ipady=3, pady=(2, 4))

                war_c_v.trace_add("write", _rebuild_war_tag)
                war_r_v.trace_add("write", _rebuild_war_tag)
                _rebuild_war_tag()
                return
            # targeted card
            cf = tk.Frame(
                tgt_host, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
            )
            cf.pack(fill="x", padx=14, pady=4)
            # sub-tab row: targets={} | target_array | target_trigger
            tab_row = tk.Frame(cf, bg=C_CARD)
            tab_row.pack(fill="x", padx=6, pady=6)
            TABS = [
                ("countries", "targets = {}"),
                ("array", "target_array"),
                ("trigger", "target_trigger"),
            ]
            for tid2, tlbl2 in TABS:
                is_active = tgt_sub_tab.get() == tid2
                fb = tk.Frame(
                    tab_row,
                    bg=BLUE_TAG_BG if is_active else C_CARD,
                    highlightthickness=1,
                    highlightbackground=BLUE_TAG_BD if is_active else C_BORDG,
                )
                fb.pack(side="left", padx=(0, 4))

                def _mktab2(t=tid2):
                    tgt_sub_tab.set(t)
                    _rebuild_tgt()

                tk.Button(
                    fb,
                    text=tlbl2,
                    command=_mktab2,
                    bg=BLUE_TAG_BG if is_active else C_CARD,
                    fg=C_BLUE if is_active else C_DIM,
                    relief="flat",
                    font=("Courier", 9),
                    cursor="hand2",
                    padx=8,
                    pady=3,
                ).pack()
            # sub-tab content
            sub = tgt_sub_tab.get()
            if sub == "countries":
                r2 = tk.Frame(cf, bg=C_CARD)
                r2.pack(fill="x", padx=6, pady=2)
                tk.Label(
                    r2,
                    text="TARGETS = { TAG TAG TAG ... }",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                ).pack(fill="x")
                tk.Entry(
                    r2,
                    textvariable=_sv("targets", dec["targets"]),
                    bg=BG_DARK,
                    fg=C_TEXT,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                ).pack(fill="x", ipady=3, pady=(2, 4))

                def _mtog3(lbl3, k3, v3):
                    rr = tk.Frame(cf, bg=C_CARD)
                    rr.pack(fill="x", padx=6, pady=1)
                    bv2 = _bv(k3, v3)
                    tk.Checkbutton(
                        rr,
                        variable=bv2,
                        bg=C_CARD,
                        activebackground=C_CARD,
                        selectcolor=C_GREEN,
                        font=("Helvetica", 9),
                        cursor="hand2",
                    ).pack(side="left")
                    tk.Label(
                        rr, text=lbl3, bg=C_CARD, fg=C_DIM, font=("Helvetica", 9)
                    ).pack(side="left")

                _mtog3(
                    "targets_dynamic — include civil war / dynamic countries",
                    "targets_dynamic",
                    dec["targets_dynamic"],
                )
                _mtog3(
                    "target_non_existing — allow non-existing countries",
                    "target_non_existing",
                    dec["target_non_existing"],
                )
            elif sub == "array":
                r2 = tk.Frame(cf, bg=C_CARD)
                r2.pack(fill="x", padx=6, pady=2)
                tk.Label(
                    r2,
                    text="TARGET_ARRAY (GAME ARRAY NAME)",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                ).pack(fill="x")
                tk.Entry(
                    r2,
                    textvariable=_sv("target_array", dec["target_array"]),
                    bg=BG_DARK,
                    fg=C_TEXT,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                ).pack(fill="x", ipady=3, pady=(2, 4))
                tk.Label(
                    r2,
                    text="e.g. enemies, allies, controlled_states",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Helvetica", 8, "italic"),
                ).pack(fill="x")
            else:  # trigger
                tk.Label(
                    cf,
                    text="TARGET_TRIGGER  (ROOT = DECIDER, FROM = TARGET)",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                    padx=6,
                ).pack(fill="x", pady=(4, 0))
                tt = tk.Text(
                    cf,
                    bg=BG_DARK,
                    fg=C_GREEN,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    height=3,
                    wrap="none",
                )
                tt.pack(fill="x", padx=6, pady=(2, 4))
                _reg_text("target_trigger", tt, dec["target_trigger"])
            # target_root_trigger always visible
            tk.Label(
                cf,
                text="TARGET_ROOT_TRIGGER  (ROOT ONLY — RUNS BEFORE TARGET_TRIGGER FOR PERFORMANCE)",
                bg=C_CARD,
                fg=C_DIM,
                font=("Courier", 7),
                padx=6,
                wraplength=380,
            ).pack(fill="x", pady=(6, 0))
            rt = tk.Text(
                cf,
                bg=BG_DARK,
                fg=C_GREEN,
                insertbackground=C_BLUE,
                font=("Courier", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=C_BORDG,
                height=2,
                wrap="none",
            )
            rt.pack(fill="x", padx=6, pady=(2, 4))
            _reg_text("target_root_trigger", rt, dec["target_root_trigger"])
            if targeted == "state":
                r3 = tk.Frame(cf, bg=C_CARD)
                r3.pack(fill="x", padx=6, pady=2)
                tk.Label(
                    r3,
                    text="STATE_TARGET SCOPE",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Courier", 8),
                ).pack(fill="x")
                scope_opts = [
                    "yes",
                    "any_owned_state",
                    "any_controlled_state",
                    "any",
                    "europe",
                    "africa",
                    "north_america",
                    "south_america",
                    "asia",
                    "oceania",
                    "middle_east",
                ]
                sv_scope = _sv("state_target_scope", dec["state_target_scope"])
                om = tk.OptionMenu(r3, sv_scope, *scope_opts)
                om.config(
                    bg=BG_DARK,
                    fg=C_TEXT,
                    activebackground=C_BORDG,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    font=("Courier", 9),
                )
                om["menu"].config(bg=BG_DARK, fg=C_TEXT)
                om.pack(fill="x", pady=2)
                tk.Label(
                    r3,
                    text="any / any_owned_state / any_controlled_state / europe / africa ...",
                    bg=C_CARD,
                    fg=C_DIM,
                    font=("Helvetica", 8, "italic"),
                ).pack(fill="x")
                r4 = tk.Frame(cf, bg=C_CARD)
                r4.pack(fill="x", padx=6, pady=2)
                tk.Label(
                    r4, text="ON_MAP_MODE", bg=C_CARD, fg=C_DIM, font=("Courier", 8)
                ).pack(fill="x")
                mode_opts = ["map_only", "decision_view_only", "map_and_decisions_view"]
                sv_mode = _sv("on_map_mode", dec["on_map_mode"])
                om2 = tk.OptionMenu(r4, sv_mode, *mode_opts)
                om2.config(
                    bg=BG_DARK,
                    fg=C_TEXT,
                    activebackground=C_BORDG,
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    font=("Courier", 9),
                )
                om2["menu"].config(bg=BG_DARK, fg=C_TEXT)
                om2.pack(fill="x", pady=2)
            # war warnings (targeted)
            tk.Label(
                cf,
                text=tr(
                    "decision.field.war_warnings_targeted", "WAR WARNINGS (TARGETED)"
                ),
                bg=C_CARD,
                fg=C_RED,
                font=("Courier", 9, "bold"),
                padx=6,
                pady=(8, 2),
            ).pack(fill="x")

            def _wt(lbl3, k3, v3):
                rr = tk.Frame(cf, bg=C_CARD)
                rr.pack(fill="x", padx=6, pady=1)
                bv2 = _bv(k3, v3)
                tk.Checkbutton(
                    rr,
                    variable=bv2,
                    bg=C_CARD,
                    activebackground=C_CARD,
                    selectcolor=C_GREEN,
                    font=("Helvetica", 9),
                    cursor="hand2",
                ).pack(side="left")
                tk.Label(
                    rr, text=lbl3, bg=C_CARD, fg=C_DIM, font=("Helvetica", 9)
                ).pack(side="left")

            _wt(
                "war_with_target_on_complete — warn FROM on complete",
                "war_target_complete",
                dec["war_target_complete"],
            )
            _wt(
                "war_with_target_on_remove — warn FROM on remove",
                "war_target_remove",
                dec["war_target_remove"],
            )
            # small bottom pad
            tk.Label(cf, text="", bg=C_CARD, pady=3).pack()

        _rebuild_tgt()

        _sec(
            tr("decision.section.highlight_map", "Highlight States & Map Mode"), C_TEAL
        )
        tk.Label(
            mid_frm,
            text=tr(
                "decision.hint.highlight_map",
                "  Paste raw highlight_states block. For non-targeted decisions that show on map, also set on_map_mode.",
            ),
            bg=C_PANEL,
            fg=C_DIM,
            font=("Helvetica", 8, "italic"),
            wraplength=380,
        ).pack(fill="x", padx=14)
        _triggerblock(
            tr(
                "decision.field.highlight_states",
                "highlight_states  (optional - highlights states on map)",
            ),
            "highlight_states",
            dec.get("highlight_states", ""),
            rows=3,
        )
        # on_map_mode for non-targeted decisions — store in the shared "on_map_mode" field
        _field(
            tr(
                "decision.field.on_map_mode",
                "on_map_mode  (non-targeted, e.g. map_and_decisions_view - leave blank to omit)",
            ),
            _sv("on_map_mode", dec.get("on_map_mode", "")),
            mono=True,
        )

        _sec(tr("decision.section.effects", "Effects"), C_GREEN)
        _effectblock(
            tr(
                "decision.field.complete_effect",
                "complete_effect  (fires immediately on selection)",
            ),
            "complete_effect",
            dec["complete_effect"],
            rows=4,
        )

        # timer effects — shown only when days_remove is set
        timer_host = tk.Frame(mid_frm, bg=C_PANEL)
        timer_host.pack(fill="x")

        def _rebuild_timer_fx(*_):
            if not timer_host.winfo_exists():
                return
            for w in timer_host.winfo_children():
                w.destroy()
            dr = _evars.get("days_remove")
            val = (dr.get() if isinstance(dr, tk.StringVar) else "") if dr else ""
            if not val.strip():
                return

            # these are rendered directly into mid_frm via helpers but we need a
            # sub-frame approach — inline build:
            def _sub_effectblock(lbl3, k3, v3, rows2=3):
                sf = tk.Frame(timer_host, bg=C_PANEL)
                sf.pack(fill="x", **PAD)
                tk.Label(
                    sf, text=lbl3.upper(), bg=C_PANEL, fg=C_DIM, font=("Courier", 8)
                ).pack(fill="x")
                t2 = tk.Text(
                    sf,
                    bg=C_CARD,
                    fg=C_GREEN,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    height=rows2,
                    wrap="none",
                    undo=True,
                )
                t2.pack(fill="x", pady=(2, 0))
                br2 = tk.Frame(sf, bg=C_PANEL)
                br2.pack(fill="x", pady=(2, 0))
                tk.Button(
                    br2,
                    text=tr("effect_picker.button", "+ Effect Picker"),
                    command=lambda tw=t2: _open_effect_picker(tw),
                    bg=C_CARD,
                    fg=C_BLUE,
                    relief="flat",
                    font=("Courier", 8),
                    cursor="hand2",
                    padx=8,
                    pady=2,
                    highlightthickness=1,
                    highlightbackground=BLUE_TAG_BD,
                ).pack(side="right")
                _reg_text(k3, t2, v3)

            def _sub_trigblock(lbl3, k3, v3):
                sf = tk.Frame(timer_host, bg=C_PANEL)
                sf.pack(fill="x", **PAD)
                tk.Label(
                    sf, text=lbl3.upper(), bg=C_PANEL, fg=C_DIM, font=("Courier", 8)
                ).pack(fill="x")
                t2 = tk.Text(
                    sf,
                    bg=C_CARD,
                    fg=C_GREEN,
                    insertbackground=C_BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=C_BORDG,
                    height=2,
                    wrap="none",
                    undo=True,
                )
                t2.pack(fill="x", pady=(2, 0))
                _reg_text(k3, t2, v3)

            def _sub_toggle2(lbl3, k3, v3):
                rr = tk.Frame(timer_host, bg=C_PANEL)
                rr.pack(fill="x", padx=14, pady=3)
                bv2 = _bv(k3, v3)
                tk.Checkbutton(
                    rr,
                    variable=bv2,
                    bg=C_PANEL,
                    activebackground=C_PANEL,
                    selectcolor=C_GREEN,
                    font=("Helvetica", 9),
                    cursor="hand2",
                ).pack(side="left")
                tk.Label(
                    rr, text=lbl3, bg=C_PANEL, fg=C_DIM, font=("Helvetica", 9)
                ).pack(side="left")

            _sub_effectblock(
                tr(
                    "decision.field.remove_effect",
                    "remove_effect  (fires when timer ends)",
                ),
                "remove_effect",
                dec["remove_effect"],
            )
            _sub_effectblock(
                tr(
                    "decision.field.cancel_effect",
                    "cancel_effect  (fires on early cancel, no remove_effect)",
                ),
                "cancel_effect",
                dec["cancel_effect"],
                rows2=2,
            )
            _sub_trigblock(
                tr(
                    "decision.field.cancel_trigger",
                    "cancel_trigger  (cancels timer without remove_effect)",
                ),
                "cancel_trigger",
                dec["cancel_trigger"],
            )
            _sub_toggle2(
                tr(
                    "decision.toggle.cancel_if_not_visible",
                    "cancel_if_not_visible - auto-cancel when not visible",
                ),
                "cancel_if_not_visible",
                dec["cancel_if_not_visible"],
            )
            _sub_effectblock(
                tr("decision.field.modifier", "modifier  (active during timer)"),
                "modifier",
                dec["modifier"],
                rows2=2,
            )
            _sub_trigblock(
                tr(
                    "decision.field.remove_trigger",
                    "remove_trigger  (instantly fires remove_effect)",
                ),
                "remove_trigger",
                dec["remove_trigger"],
            )

        if "days_remove" in _evars:
            _evars["days_remove"].trace_add("write", _rebuild_timer_fx)
        _rebuild_timer_fx()

        # Register hooks for post-populate refresh
        _editor_hooks["rebuild_tgt"] = _rebuild_tgt
        _editor_hooks["rebuild_timer_fx"] = _rebuild_timer_fx
        _editor_hooks["rebuild_cost"] = _rebuild_cost
        _editor_hooks["rebuild_mission"] = _rebuild_mission

        _sec(tr("decision.section.ai", "AI"), C_ORANGE)
        # red warning banner
        rb = tk.Frame(
            mid_frm, bg=RED_TAG_BG, highlightthickness=1, highlightbackground=RED_TAG_BD
        )
        rb.pack(fill="x", padx=14, pady=(0, 4))
        tk.Label(
            rb,
            text=tr(
                "decision.warning.ai_will_do_required",
                "AI will NEVER take this decision by default - ai_will_do is required",
            ),
            bg=RED_TAG_BG,
            fg=C_RED,
            font=("Helvetica", 9),
            padx=6,
            pady=4,
        ).pack(fill="x")
        _triggerblock(
            tr(
                "decision.field.ai_will_do",
                "ai_will_do  (MTTH block - base + modifier triggers)",
            ),
            "ai_will_do",
            dec["ai_will_do"],
            rows=3,
        )
        _field(
            tr("decision.field.priority_raw", "priority"),
            _sv("priority", dec["priority"]),
            mono=True,
            hint="Higher = shown earlier in AI evaluation",
        )

    # ── rebuild_editor  (clears mid_frm and dispatches) ──────────────────────
    # Track what type is currently built so we know when to do a full rebuild
    _editor_state = {"type": None}  # "cat", "dec", or None

    def _set_var_silent(key, value):
        """Set a tkinter var without firing its write traces."""
        v = _evars.get(key)
        if v is None:
            return
        try:
            cbs = [(m, cb) for m, cb in v.trace_info() if "write" in m]
            for _m, cb in cbs:
                try:
                    v.trace_remove("write", cb)
                except Exception:
                    pass
            if isinstance(v, tk.BooleanVar):
                v.set(bool(value))
            else:
                v.set(str(value) if value is not None else "")
            for _m, cb in cbs:
                try:
                    v.trace_add("write", lambda *a, _cb=cb, _v=v: None)
                except Exception:
                    pass
        except Exception:
            try:
                if isinstance(v, tk.BooleanVar):
                    v.set(bool(value))
                else:
                    v.set(str(value) if value is not None else "")
            except Exception:
                pass

    def _set_text_silent(key, value):
        """Update a tk.Text widget in-place."""
        v = _evars.get(key)
        if not isinstance(v, tk.Text):
            return
        try:
            v.delete("1.0", "end")
            if value:
                v.insert("1.0", str(value))
        except Exception:
            pass

    def _populate_dec_editor(d):
        """Fast-path: populate existing dec editor without rebuilding any widgets."""
        # Simple string / text fields
        for k in (
            "dec_id",
            "loc_name",
            "loc_desc",
            "icon",
            "chain",
            "priority",
            "allowed",
            "visible",
            "available",
            "cost",
            "days_remove",
            "days_re_enable",
            "custom_cost_trigger",
            "custom_cost_text",
            "ai_hint_pp_cost",
            "mission_timeout",
            "activation",
            "targets",
            "target_array",
            "target_trigger",
            "target_root_trigger",
            "state_target_scope",
            "on_map_mode",
            "war_with_on_timeout",
            "war_complete_tag",
            "war_remove_tag",
            "cancel_trigger",
            "modifier",
            "remove_trigger",
            "highlight_states",
            "ai_will_do",
            "complete_effect",
            "remove_effect",
            "cancel_effect",
            "timeout_effect",
        ):
            val = d.get(k, "") or ""
            if k in _evars:
                v = _evars[k]
                if isinstance(v, tk.Text):
                    _set_text_silent(k, val)
                else:
                    _set_var_silent(k, val)
        # Bool flags (not structural — don't drive sub-section rebuilds)
        for k in (
            "fire_only_once",
            "fixed_random_seed",
            "selectable_mission",
            "is_good",
            "targets_dynamic",
            "target_non_existing",
            "cancel_if_not_visible",
            "war_target_complete",
            "war_target_remove",
        ):
            _set_var_silent(k, bool(d.get(k, False)))
        # Structural vars — set silently then fire hooks once
        _set_var_silent("_use_custom", d.get("cost_type", "pp") != "pp")
        targeted = d.get("targeted", "none")
        _set_var_silent("_tgt_country", targeted == "country")
        _set_var_silent("_tgt_state", targeted == "state")
        _set_var_silent("_is_mission", bool(d.get("is_mission", False)))
        # Fire sub-section rebuilds once cleanly
        for hook in (
            "rebuild_cost",
            "rebuild_mission",
            "rebuild_tgt",
            "rebuild_timer_fx",
        ):
            fn = _editor_hooks.get(hook)
            if fn:
                try:
                    fn()
                except Exception:
                    pass
        # Update badge row
        try:
            children = mid_frm.winfo_children()
            if len(children) > 1:
                top_frame = children[1]
                for w in top_frame.winfo_children():
                    w.destroy()
                _type_badge(top_frame, "DECISION", C_BLUE, BLUE_TAG_BG, BLUE_TAG_BD)
                if targeted != "none":
                    _type_badge(top_frame, "TARGETED", C_TEAL, TEAL_TAG_BG, TEAL_TAG_BD)
                if d.get("is_mission"):
                    _type_badge(
                        top_frame, "MISSION", C_PURPLE, PURP_TAG_BG, PURP_TAG_BD
                    )
                if d.get("fire_only_once"):
                    _type_badge(top_frame, "ONCE", C_ORANGE, ORAN_TAG_BG, ORAN_TAG_BD)
                tk.Label(
                    top_frame,
                    text=d["dec_id"],
                    bg=C_PANEL,
                    fg=C_TEXT,
                    font=("Courier", 11),
                ).pack(side="left")
        except Exception:
            pass

    def _populate_cat_editor(c):
        """Fast-path: populate existing cat editor widgets without rebuilding."""
        for k in (
            "cat_id",
            "loc_name",
            "loc_desc",
            "icon",
            "picture",
            "priority",
            "map_state",
            "map_name",
            "map_zoom",
            "scripted_gui",
            "highlight_states",
        ):
            val = c.get(k, "") or ""
            if k in _evars:
                v = _evars[k]
                if isinstance(v, tk.Text):
                    _set_text_silent(k, val)
                else:
                    _set_var_silent(k, val)
        for k in ("allowed", "visible", "map_trigger"):
            _set_text_silent(k, c.get(k, "") or "")
        _set_var_silent("visible_when_empty", bool(c.get("visible_when_empty", False)))
        _set_var_silent("on_map_area", bool(c.get("on_map_area", False)))

    def _rebuild_editor():
        _collect()  # save current edits before switching
        uid = sel["uid"]
        new_type = sel["type"]
        obj = (
            _get_cat(uid)
            if new_type == "cat"
            else (_get_dec(uid) if new_type == "dec" else None)
        )

        # Always do a full widget rebuild — fast because we skip _rebuild_right()
        for w in mid_frm.winfo_children():
            w.destroy()
        _evars.clear()
        _editor_hooks.clear()
        if new_type == "cat" and obj:
            _build_cat_editor(obj)
        elif new_type == "dec" and obj:
            _build_dec_editor(obj)
        else:
            tk.Label(
                mid_frm,
                text=tr(
                    "decision.empty_selection",
                    "\n  Select a category or decision\n  from the tree on the left.",
                ),
                bg=C_PANEL,
                fg=C_DIM,
                font=("Helvetica", 10),
                justify="center",
            ).pack(pady=40)
        _editor_state["type"] = new_type
        # Scroll editor back to top on selection change
        try:
            mid_cv.yview_moveto(0)
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    # RIGHT  ─ Preview / Chain / Code
    # ════════════════════════════════════════════════════════════════════════
    right_f = tk.Frame(paned, bg=C_DARK)
    paned.add(right_f, minsize=280, width=420, stretch="always")

    # tab bar
    tab_bar = tk.Frame(right_f, bg=C_PANEL)
    tab_bar.pack(fill="x")
    _rtab = tk.StringVar(value="preview")
    _tab_btns = {}
    for tid, tlbl in [
        ("preview", tr("common.preview", "Preview")),
        ("chain", tr("decision.tab.chain_view", "Chain View")),
        ("code", tr("tab.code", "Code")),
    ]:

        def _mktab(t=tid):
            _rtab.set(t)
            _update_tab_styles()
            _rebuild_right()

        b = tk.Button(
            tab_bar,
            text=tlbl,
            command=_mktab,
            bg=C_DARK,
            fg=C_TEXT,
            relief="flat",
            font=("Courier", 10),
            cursor="hand2",
            padx=14,
            pady=8,
            bd=0,
        )
        b.pack(side="left")
        _tab_btns[tid] = b
    tk.Button(
        tab_bar,
        text=tr("common.refresh", "Refresh"),
        command=lambda: _rebuild_right(),
        bg=C_CARD,
        fg=C_TEAL,
        relief="flat",
        font=("Courier", 8),
        cursor="hand2",
        padx=8,
        pady=2,
        highlightthickness=1,
        highlightbackground=C_TEAL,
    ).pack(side="right", padx=(0, 6), pady=4)
    tk.Label(
        tab_bar,
        text=tr("decision.preview.approximate_hint", "approximate in-game appearance"),
        bg=C_PANEL,
        fg=C_DIM,
        font=("Helvetica", 8, "italic"),
    ).pack(side="right", padx=10)
    tk.Frame(tab_bar, bg=C_BORDG, height=1).pack(side="bottom", fill="x")

    def _update_tab_styles():
        for tid2, b2 in _tab_btns.items():
            active = _rtab.get() == tid2
            b2.config(fg=C_TEXT if active else C_DIM, bg=C_DARK if active else C_PANEL)

    right_body = tk.Frame(right_f, bg=C_DARK)
    right_body.pack(fill="both", expand=True)

    _rr_job = [None]

    def _rebuild_right():
        # Debounce: cancel pending rebuild and schedule new one 80ms out
        if _rr_job[0] is not None:
            try:
                win.after_cancel(_rr_job[0])
            except Exception:
                pass

        def _do_rebuild():
            _rr_job[0] = None
            for w in right_body.winfo_children():
                w.destroy()
            t = _rtab.get()
            if t == "preview":
                _build_preview()
            elif t == "chain":
                _build_chain()
            elif t == "code":
                _build_code()
            _update_tab_styles()

        _rr_job[0] = win.after(80, _do_rebuild)

    # ── PREVIEW ──────────────────────────────────────────────────────────────
    # ── shared preview image cache: gfx_key -> PhotoImage|None ─────────────
    _dec_prev_img_cache = {}
    _app_img_caches.append(_dec_prev_img_cache)  # register for mod-reload invalidation

    # ── PIL / DDS capability check ────────────────────────────────────────
    _dds_supported = False
    if PIL_OK:
        try:
            from PIL import features as _pil_feat

            _dds_supported = _pil_feat.check_feature("libtiff") or True
            # Actually test by checking registered formats
            from PIL import Image as _tpil

            _dds_supported = (
                "DDS" in _tpil.registered_extensions().get(".dds", "").upper()
                if hasattr(_tpil, "registered_extensions")
                else False
            )
        except Exception:
            _dds_supported = False

    def _load_dec_icon(gfx_key, size=24):
        """Load a decision icon image, returns PhotoImage or None. Cached."""
        if not gfx_key or not PIL_OK:
            return None
        cache_key = (gfx_key, size)
        if cache_key in _dec_prev_img_cache:
            cached = _dec_prev_img_cache[cache_key]
            if cached is not None:
                return cached
            # cached None — retry in case mod was reloaded with new sprites
        # resolve path
        path = (
            MOD.decision_sprites.get(gfx_key)
            or MOD.idea_sprites.get(gfx_key)
            or MOD.sprites.get(gfx_key)
        )
        if not path:
            stem = gfx_key
            for pfx in ("GFX_decision_category_", "GFX_decision_", "GFX_idea_", "GFX_"):
                if gfx_key.startswith(pfx):
                    stem = gfx_key[len(pfx) :]
                    break
            if MOD.root:
                # Check flat subdirs first (fast)
                for sub in (
                    "gfx/interface/decisions",
                    "gfx/interface/decisions/categories",
                    "gfx/interface",
                    "gfx/interface/ideas",
                ):
                    for ext in (".dds", ".tga", ".png"):
                        p = os.path.join(MOD.root, sub.replace("/", os.sep), stem + ext)
                        if os.path.isfile(p):
                            path = p
                            break
                    if path:
                        break
                # Walk all subdirectories of gfx/interface/decisions/ (catches main/, country/ etc.)
                if not path:
                    dec_root = os.path.join(MOD.root, "gfx", "interface", "decisions")
                    if os.path.isdir(dec_root):
                        for _rd, _ds, _fs in os.walk(dec_root):
                            for ext in (".dds", ".tga", ".png"):
                                p = os.path.join(_rd, stem + ext)
                                if os.path.isfile(p):
                                    path = p
                                    break
                            if path:
                                break
        img = None
        if path:
            candidates = [path]
            # If .dds fails, try .png/.tga with same stem
            stem_no_ext = os.path.splitext(path)[0]
            for ext in (".png", ".tga", ".dds"):
                alt = stem_no_ext + ext
                if alt != path and os.path.isfile(alt):
                    candidates.append(alt)
            for cpath in candidates:
                try:
                    pil = PILImage.open(cpath).convert("RGBA")
                    rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                    pil = pil.resize((size, size), rs)
                    img = PILImageTk.PhotoImage(pil)
                    break
                except Exception as _ico_err:
                    get_logger("ico").warning(f"PIL failed {cpath}: {_ico_err}")
                    continue
        else:
            get_logger("ico").warning(
                f"no path for {gfx_key!r}  "
                f"(decision_sprites={len(MOD.decision_sprites)}, root={bool(MOD.root)})"
            )
        _dec_prev_img_cache[cache_key] = img
        return img

    def _load_cat_picture(gfx_key, w=64, h=64):
        """Load a category picture image. Cached."""
        if not gfx_key or not PIL_OK:
            return None
        cache_key = (gfx_key, w, h)
        if cache_key in _dec_prev_img_cache:
            cached = _dec_prev_img_cache[cache_key]
            if cached is not None:
                return cached
        # Try key as-is, then with common category prefixes
        path = (
            MOD.decision_sprites.get(gfx_key)
            or MOD.idea_sprites.get(gfx_key)
            or MOD.sprites.get(gfx_key)
            or MOD.decision_sprites.get("GFX_decision_cat_" + gfx_key.split("_")[-1])
        )
        if not path and MOD.root:
            stem = gfx_key
            for pfx in (
                "GFX_decision_category_",
                "GFX_decision_cat_",
                "GFX_decision_",
                "GFX_idea_",
                "GFX_",
            ):
                if gfx_key.startswith(pfx):
                    stem = gfx_key[len(pfx) :]
                    break
            for sub in (
                "gfx/interface/decisions",
                "gfx/interface/decisions/categories",
                "gfx/interface",
                "gfx/interface/ideas",
                "gfx",
            ):
                for ext in (".dds", ".tga", ".png"):
                    p = os.path.join(MOD.root, sub.replace("/", os.sep), stem + ext)
                    if os.path.isfile(p):
                        path = p
                        break
                if path:
                    break
        img = None
        if path:
            candidates = [path]
            stem_no_ext = os.path.splitext(path)[0]
            for ext in (".png", ".tga", ".dds"):
                alt = stem_no_ext + ext
                if alt != path and os.path.isfile(alt):
                    candidates.append(alt)
            for cpath in candidates:
                try:
                    pil = PILImage.open(cpath).convert("RGBA")
                    rs = getattr(PILImage, "LANCZOS", getattr(PILImage, "ANTIALIAS", 1))
                    pw, ph = pil.size
                    ratio = min(w / max(pw, 1), h / max(ph, 1))
                    pil = pil.resize(
                        (max(1, int(pw * ratio)), max(1, int(ph * ratio))), rs
                    )
                    img = PILImageTk.PhotoImage(pil)
                    break
                except Exception:
                    continue
        _dec_prev_img_cache[cache_key] = img
        return img

    # ── HOI4 loc renderer ────────────────────────────────────────────────────
    _HOI4_CLR = {
        "Y": "#e0c060",  # gold
        "R": "#e05050",  # red
        "G": "#50c878",  # green
        "B": "#5090e0",  # blue
        "W": "#e8e8e8",  # white/near-white
        "b": "#8ab4d4",  # light blue
        "g": "#80c080",  # light green
        "T": "#c060c0",  # teal/purple
        "H": "#e0a030",  # orange
        "L": "#aaaaaa",  # grey
    }

    def _strip_loc_codes(text):
        """Strip all HOI4 loc codes from a string for plain tree display."""
        import re as _re_s

        text = text.replace("\\n", " ").replace("\n", " ")
        text = _re_s.sub(r"§[A-Za-z0-9!]", "", text)  # §Y §2 §! etc
        text = _re_s.sub(
            r"\$([^$]{1,40})\$",  # $2The Gas$ → The Gas
            lambda m: _re_s.sub(r"^\d+", "", m.group(1)),
            text,
        )
        text = _re_s.sub(r"\[([A-Z]{2,5})\](\S+)", r"\2", text)  # [TAG]Word → Word
        text = _re_s.sub(
            r"\[([A-Z]{2,5}):[^\]]+\]", lambda m: m.group(1), text  # [TAG:X] → TAG
        )
        text = _re_s.sub(r"\[[^\]]{1,80}\]", "", text)  # remaining [tokens]
        return text.strip()

    def _hoi4_loc_widget(
        parent,
        text,
        bg,
        base_fg="#c8d4e0",
        font=("Palatino Linotype", 9),
        wraplength=300,
    ):
        """Render a HOI4 localisation string with colour codes and scripted loc
        tokens into a read-only tk.Text widget that matches the parent bg."""
        import re as _re

        # Convert literal \n escape sequences to real newlines
        text = text.replace("\\n", "\n").replace("\\\\n", "\n")
        # Strip trailing backslashes (common in raw HOI4 strings)
        text = text.rstrip("\\").strip()
        # Strip trailing backslashes (common in raw HOI4 strings)
        text = text.rstrip("\\").strip()

        # Estimate height needed: roughly 1 line per 45 chars of wraplength
        max(1, wraplength // 7)
        est_lines = max(2, text.count("\n") + len(text) // max(1, wraplength // 7 * 6))
        height = min(max(2, est_lines), 12)

        w = int(wraplength / 7)  # approx chars per line for Text width
        txt = tk.Text(
            parent,
            bg=bg,
            fg=base_fg,
            font=font,
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            width=w,
            height=height,
            cursor="arrow",
            state="normal",
            exportselection=False,
            spacing1=1,
            spacing2=1,
            spacing3=1,
        )
        txt.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Bind the widget width to parent to enable proper wrapping
        def _resize(e, t=txt):
            try:
                new_w = max(10, e.width // 7)
                t.config(width=new_w)
            except Exception:
                pass

        parent.bind("<Configure>", _resize, add=True)

        # Configure colour tags
        txt.tag_config("base", foreground=base_fg)
        for code, colour in _HOI4_CLR.items():
            txt.tag_config(f"clr_{code}", foreground=colour)
        txt.tag_config(
            "scrloc", foreground="#7ec8e3", font=(font[0], font[1], "italic")
        )
        txt.tag_config("var", foreground="#a78bfa", font=(font[0], font[1], "italic"))
        txt.tag_config("bold", font=(font[0], font[1], "bold"))

        # ── Tokenise and insert ──────────────────────────────────────────────
        # Tokens: §X colour codes, [Scope.Func] scripted loc, $var$ variables,

        # ── Single-pass tokeniser ───────────────────────────────────────
        # Handles: §Y colour  §2 number-colour  §!  [TAG:X]  [TAG]Word  $var$

        TOKEN = _re.compile(
            r"(§[A-Za-z0-9!]"  # §Y §2 §!
            r"|\[([A-Z]{2,5})\](\S*)"  # [TAG] optionally followed by a word
            r"|\[([^\]]{1,80})\]"  # [any:token]
            r"|\$([^$]{1,40})\$"  # $var$
            r")"
        )

        colour_stack = []

        def _cur_clr():
            return colour_stack[-1] if colour_stack else "base"

        def _resolve_tag(tag):
            return MOD.country_tag_names.get(tag, tag)

        pos = 0
        for m in TOKEN.finditer(text):
            # Insert any plain text before this token
            if m.start() > pos:
                txt.insert("end", text[pos : m.start()], (_cur_clr(),))
            pos = m.end()

            full, bare_tag, bare_word, bracket_inner, var_inner = (
                m.group(0),
                m.group(2),
                m.group(3),
                m.group(4),
                m.group(5),
            )

            if full.startswith("§"):
                code = full[1:]
                if code == "!":
                    if colour_stack:
                        colour_stack.pop()
                elif code in _HOI4_CLR:
                    colour_stack.append(f"clr_{code}")
                # number codes (§2 etc) — just suppress
                continue

            if bare_tag is not None:
                # [TAG]Word  or  [TAG] (standalone)
                word = bare_word or bare_tag  # fallback to tag itself
                name = MOD.country_tag_names.get(bare_tag, None)
                label = f"\U0001f3f3 {name or word}"
                txt.insert("end", label, ("scrloc",))
                continue

            if bracket_inner is not None:
                inner = bracket_inner
                # Match TAG:Func  OR  TAG·Func  (·  = middle-dot from old renderer)
                mc = _re.match(r"([A-Z]{2,5})[:·\.](\w+)", inner)
                if mc:
                    tag = mc.group(1)
                    name = MOD.country_tag_names.get(tag, None)
                    label = name or tag
                else:
                    label = inner[:20]
                txt.insert("end", label, ("scrloc",))
                continue

            if var_inner is not None:
                # $2The Gas Pipeline$ → strip leading digits
                clean = _re.sub(r"^\d+", "", var_inner)
                txt.insert("end", clean, ("var",))
                continue

        # Any trailing plain text
        if pos < len(text):
            txt.insert("end", text[pos:], (_cur_clr(),))

        txt.config(state="disabled")
        return txt

    def _build_preview():
        _collect()
        # ── DDS warning banner ────────────────────────────────────────────────
        if (
            PIL_OK
            and not _dds_supported
            and MOD.loaded
            and MOD.decision_sprites
            and not getattr(_build_preview, "_dds_warned", False)
        ):
            # Check if any sprites are .dds — show warning only once per session
            has_dds = any(
                str(v).lower().endswith(".dds")
                for v in list(MOD.decision_sprites.values())[:20]
            )
            if has_dds:
                _build_preview._dds_warned = True
                warn_f = tk.Frame(right_body, bg="#3a1a00")
                warn_f.pack(fill="x")
                tk.Label(
                    warn_f,
                    text=tr(
                        "decision.warning.dds_support",
                        "Icons are .dds files - install 'pillow-dds' for full GFX support: pip install pillow-dds",
                    ),
                    bg="#3a1a00",
                    fg="#f59e0b",
                    font=("Helvetica", 8),
                    pady=4,
                    padx=8,
                ).pack(anchor="w")

        # ── scrollable container ──────────────────────────────────────────────
        cv = tk.Canvas(right_body, bg=C_DARK, highlightthickness=0)
        sb = tk.Scrollbar(right_body, orient="vertical", command=cv.yview)
        frm = tk.Frame(cv, bg=C_DARK)
        wid = cv.create_window((0, 0), window=frm, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        frm.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(wid, width=e.width))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                ev,
                lambda e: cv.yview_scroll(
                    -1 if (e.delta > 0 if e.num not in (4, 5) else e.num == 4) else 1,
                    "units",
                ),
            )
        sb.pack(side="right", fill="y")
        cv.pack(fill="both", expand=True)

        # Keep image refs alive (prevent GC)
        _img_refs = []

        CHAIN_ICONS = {"hacking": "💻", "drugs": "🧪", "currency": "💵", "default": "⚖"}

        for cat in dm_cats:
            if not cat_visible.get(cat["uid"], True):
                continue
            decs = _decs_for(cat["uid"])

            # ── Category panel ────────────────────────────────────────────────
            panel = tk.Frame(
                frm, bg="#1a1f2e", highlightthickness=1, highlightbackground="#3a4a6a"
            )
            panel.pack(fill="x", padx=10, pady=8)
            panel._img_refs = []  # keep images alive per-panel

            # ── Header: icon + name ───────────────────────────────────────────
            hdr = tk.Frame(panel, bg="#141929")
            hdr.pack(fill="x")
            # category icon (32x32)
            icon_key = cat.get("icon", "").strip()
            cat_img = _load_dec_icon(icon_key, 32) if icon_key else None
            if cat_img:
                panel._img_refs.append(cat_img)
                ic_lbl = tk.Label(hdr, image=cat_img, bg="#141929", width=32, height=32)
            else:
                ic_lbl = tk.Frame(hdr, bg="#2a3550", width=32, height=32)
                ic_lbl.pack_propagate(False)
            ic_lbl.pack(side="left", padx=8, pady=6)
            # Right-click to copy GFX key
            if icon_key:

                def _ctx_cat_icon(e, k=icon_key):
                    m = tk.Menu(
                        win,
                        tearoff=0,
                        bg=C_CARD,
                        fg=C_TEXT,
                        activebackground=C_BLUE,
                        font=("Helvetica", 9),
                    )
                    m.add_command(
                        label=f"Copy GFX key: {k}",
                        command=lambda: [
                            win.clipboard_clear(),
                            win.clipboard_append(k),
                        ],
                    )
                    m.post(e.x_root, e.y_root)

                ic_lbl.bind("<Button-3>", _ctx_cat_icon)
            cat_display_name = cat["loc_name"] or cat["cat_id"]
            _hoi4_loc_widget(
                hdr,
                cat_display_name,
                bg="#141929",
                base_fg="#c8d4e0",
                font=("Palatino Linotype", 12, "bold"),
                wraplength=320,
            )
            tk.Frame(panel, bg="#2a3550", height=1).pack(fill="x")

            # ── Desc row: picture + description ──────────────────────────────
            pic_key = cat.get("picture", "").strip()
            desc_txt = cat.get("loc_desc", "").strip()
            if pic_key or desc_txt:
                pic_row = tk.Frame(panel, bg="#1a1f2e")
                pic_row.pack(fill="x", padx=10, pady=8)
                if pic_key:
                    pic_box = tk.Frame(
                        pic_row,
                        bg="#2a3550",
                        highlightthickness=1,
                        highlightbackground="#3a4a6a",
                        width=64,
                        height=64,
                    )
                    pic_box.pack(side="left", padx=(0, 10))
                    pic_box.pack_propagate(False)
                    cat_pic = _load_cat_picture(pic_key, 64, 64)
                    if cat_pic:
                        panel._img_refs.append(cat_pic)
                        tk.Label(pic_box, image=cat_pic, bg="#2a3550").pack(expand=True)
                    else:
                        # Show placeholder, try async load
                        ph = tk.Label(
                            pic_box, text="🎖", bg="#2a3550", font=("Helvetica", 24)
                        )
                        ph.pack(expand=True)

                        def _async_cat_pic(
                            key=pic_key, box=pic_box, ph_lbl=ph, refs=panel._img_refs
                        ):
                            import threading

                            def _worker():
                                img = _load_cat_picture(key, 64, 64)

                                def _paint():
                                    if not box.winfo_exists():
                                        return
                                    if img:
                                        ph_lbl.destroy()
                                        lbl = tk.Label(box, image=img, bg="#2a3550")
                                        lbl.pack(expand=True)
                                        refs.append(img)

                                try:
                                    box.after(0, _paint)
                                except Exception:
                                    pass

                            threading.Thread(target=_worker, daemon=True).start()

                        win.after(10, _async_cat_pic)
                if desc_txt:
                    _hoi4_loc_widget(
                        pic_row,
                        desc_txt,
                        bg="#1a1f2e",
                        base_fg="#8a9ab0",
                        font=("Palatino Linotype", 9),
                        wraplength=300,
                    )
            tk.Frame(panel, bg="#2a3550", height=1).pack(fill="x")

            # ── Decision rows (lightweight: use tk.Canvas per row for speed) ─
            for i, dec in enumerate(decs):
                bg_d = "#161c2e" if i % 2 == 0 else "#131828"
                drow = tk.Frame(panel, bg=bg_d, cursor="hand2")
                drow.pack(fill="x")

                # icon (24x24 image or emoji fallback)
                dec_icon_key = dec.get("icon", "").strip()
                # auto-expand short icon names
                if dec_icon_key and not dec_icon_key.startswith("GFX_"):
                    dec_icon_key = "GFX_decision_" + dec_icon_key
                dec_img = _load_dec_icon(dec_icon_key, 24) if dec_icon_key else None

                icon_box = tk.Frame(
                    drow,
                    bg="#2a3550",
                    highlightthickness=1,
                    highlightbackground="#3a4a6a",
                    width=26,
                    height=26,
                )
                icon_box.pack(side="left", padx=(10, 6), pady=4)
                icon_box.pack_propagate(False)
                if dec_icon_key:

                    def _ctx_dec_icon(e, k=dec_icon_key):
                        m = tk.Menu(
                            win,
                            tearoff=0,
                            bg=C_CARD,
                            fg=C_TEXT,
                            activebackground=C_BLUE,
                            font=("Helvetica", 9),
                        )
                        m.add_command(
                            label=f"Copy GFX key: {k}",
                            command=lambda: [
                                win.clipboard_clear(),
                                win.clipboard_append(k),
                            ],
                        )
                        m.post(e.x_root, e.y_root)

                    icon_box.bind("<Button-3>", _ctx_dec_icon)
                if dec_img:
                    panel._img_refs.append(dec_img)
                    tk.Label(icon_box, image=dec_img, bg="#2a3550").pack(expand=True)
                else:
                    ic = CHAIN_ICONS.get(dec.get("chain", "").lower(), "⚖")
                    fallback = tk.Label(
                        icon_box, text=ic, bg="#2a3550", font=("Helvetica", 9)
                    )
                    fallback.pack(expand=True)
                    if dec_icon_key:

                        def _async_dec_icon(
                            key=dec_icon_key,
                            box=icon_box,
                            fb=fallback,
                            refs=panel._img_refs,
                        ):
                            import threading

                            def _worker():
                                # Resolve path (same logic as _load_dec_icon)
                                _path = (
                                    MOD.decision_sprites.get(key)
                                    or MOD.idea_sprites.get(key)
                                    or MOD.sprites.get(key)
                                )
                                if not _path:
                                    _stem = key
                                    for _pfx in (
                                        "GFX_decision_category_",
                                        "GFX_decision_",
                                        "GFX_idea_",
                                        "GFX_",
                                    ):
                                        if key.startswith(_pfx):
                                            _stem = key[len(_pfx) :]
                                            break
                                    if MOD.root:
                                        for _sub in (
                                            "gfx/interface/decisions",
                                            "gfx/interface/decisions/categories",
                                            "gfx/interface",
                                            "gfx/interface/ideas",
                                        ):
                                            for _ext in (".dds", ".tga", ".png"):
                                                _p = os.path.join(
                                                    MOD.root,
                                                    _sub.replace("/", os.sep),
                                                    _stem + _ext,
                                                )
                                                if os.path.isfile(_p):
                                                    _path = _p
                                                    break
                                            if _path:
                                                break
                                        if not _path:
                                            _dr = os.path.join(
                                                MOD.root,
                                                "gfx",
                                                "interface",
                                                "decisions",
                                            )
                                            if os.path.isdir(_dr):
                                                for _rd, _, _fs in os.walk(_dr):
                                                    for _ext in (
                                                        ".dds",
                                                        ".tga",
                                                        ".png",
                                                    ):
                                                        _p = os.path.join(
                                                            _rd, _stem + _ext
                                                        )
                                                        if os.path.isfile(_p):
                                                            _path = _p
                                                            break
                                                    if _path:
                                                        break
                                if not _path:
                                    return
                                # Load PIL image in background (safe), create PhotoImage on main thread
                                try:
                                    _pil = PILImage.open(_path).convert("RGBA")
                                    _rs = getattr(
                                        PILImage,
                                        "LANCZOS",
                                        getattr(PILImage, "ANTIALIAS", 1),
                                    )
                                    _pil = _pil.resize((24, 24), _rs)
                                except Exception:
                                    return

                                def _paint():
                                    if not box.winfo_exists():
                                        return
                                    try:
                                        img = PILImageTk.PhotoImage(_pil)
                                        _dec_prev_img_cache[(key, 24)] = img
                                        fb.destroy()
                                        lbl = tk.Label(box, image=img, bg="#2a3550")
                                        lbl.pack(expand=True)
                                        refs.append(img)
                                    except Exception:
                                        pass

                                try:
                                    box.after(0, _paint)
                                except Exception:
                                    pass

                            threading.Thread(target=_worker, daemon=True).start()

                        win.after(10, _async_dec_icon)

                # decision name — render with HOI4 loc codes
                targeted = dec.get("targeted", "none")
                prefix = "↗ " if targeted != "none" else ""
                raw_name = dec["loc_name"] or dec["dec_id"]
                name_txt = prefix + raw_name
                name_lbl = _hoi4_loc_widget(
                    drow,
                    name_txt,
                    bg=bg_d,
                    base_fg="#c8d4e0",
                    font=("Palatino Linotype", 10),
                    wraplength=240,
                )

                # cost
                cost_widgets = []
                if dec["cost_type"] == "pp" and dec.get("cost", "").strip():
                    lpp = tk.Label(drow, text="🏛", bg=bg_d, font=("Helvetica", 9))
                    lpp.pack(side="left", padx=(0, 1))
                    lco = tk.Label(
                        drow,
                        text=dec["cost"],
                        bg=bg_d,
                        fg="#e0c060",
                        font=("Courier", 9),
                    )
                    lco.pack(side="left", padx=(0, 6))
                    cost_widgets = [lpp, lco]

                # availability indicator (green = available, grey = unknown)
                ind = tk.Frame(drow, bg="#22c55e", width=12, height=12)
                ind.pack(side="right", padx=(2, 8), pady=8)

                # ── click → select in editor ──
                def _on_prev_click(e, uid=dec["uid"]):
                    sel["uid"] = uid
                    sel["type"] = "dec"
                    _update_tree_highlight()
                    _rebuild_editor()
                    return "break"  # prevent Text widget from getting focus

                for w in [drow, icon_box, ind] + cost_widgets:
                    w.bind("<Button-1>", _on_prev_click)
                # tk.Text needs special binding to prevent caret/selection
                try:
                    name_lbl.bind("<Button-1>", _on_prev_click)
                    name_lbl.config(cursor="hand2")
                except Exception:
                    pass

                if i < len(decs) - 1:
                    tk.Frame(panel, bg="#1e2840", height=1).pack(fill="x")

    # ── CHAIN VIEW ────────────────────────────────────────────────────────────
    def _build_chain():
        _collect()
        cv = tk.Canvas(right_body, bg=C_DARK, highlightthickness=0)
        sb = tk.Scrollbar(right_body, orient="vertical", command=cv.yview)
        frm = tk.Frame(cv, bg=C_DARK)
        wid = cv.create_window((0, 0), window=frm, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        frm.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(wid, width=e.width))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                ev,
                lambda e: cv.yview_scroll(
                    -1 if (e.delta > 0 if e.num not in (4, 5) else e.num == 4) else 1,
                    "units",
                ),
            )
        sb.pack(side="right", fill="y")
        cv.pack(fill="both", expand=True)

        tk.Label(
            frm,
            text=tr(
                "decision.chain.description",
                "  Decision chains - decisions sharing a chain tag are visualised as a group",
            ),
            bg=C_DARK,
            fg=C_DIM,
            font=("Helvetica", 8, "italic"),
            pady=8,
        ).pack(fill="x")

        all_decs = [d for cat in dm_cats for d in _decs_for(cat["uid"])]
        chains = {}
        for d in all_decs:
            c = d.get("chain", "").strip() or "misc"
            if c not in chains:
                chains[c] = []
            chains[c].append(d)

        CCOLORS = {
            "hacking": C_BLUE,
            "drugs": C_ORANGE,
            "currency": C_GOLD,
            "misc": C_DIM,
        }
        clist = list(chains.items())
        for ci, (chain, decs) in enumerate(clist):
            cc = CCOLORS.get(
                chain, [C_BLUE, C_TEAL, C_ORANGE, C_PURPLE, C_GREEN][ci % 5]
            )
            tk.Label(
                frm,
                text=f"  ── {chain.upper()} CHAIN  ({len(decs)} decisions)",
                bg=C_DARK,
                fg=cc,
                font=("Courier", 9, "bold"),
                anchor="w",
            ).pack(fill="x", padx=10, pady=(10, 4))

            for _i, dec in enumerate(decs):
                row = tk.Frame(frm, bg=C_DARK)
                row.pack(fill="x", padx=16, pady=1)
                # connector dot
                dot_f = tk.Frame(row, bg=C_DARK, width=20)
                dot_f.pack(side="left", fill="y")
                dot_f.pack_propagate(False)
                tk.Canvas(
                    dot_f, bg=C_DARK, highlightthickness=0, width=20, height=30
                ).pack(fill="y", expand=True)
                # card
                card = tk.Frame(
                    row, bg=C_CARD, highlightthickness=1, highlightbackground=cc
                )
                card.pack(side="left", fill="x", expand=True, pady=1)
                tk.Label(
                    card,
                    text=dec["loc_name"] or dec["dec_id"],
                    bg=C_CARD,
                    fg=C_TEXT,
                    font=("Courier", 10),
                    anchor="w",
                    padx=10,
                    pady=5,
                ).pack(fill="x")
                tag_row = tk.Frame(card, bg=C_CARD)
                tag_row.pack(fill="x", padx=10, pady=(0, 5))
                _tag(
                    tag_row,
                    "targeted" if dec["targeted"] != "none" else "standard",
                    C_TEAL if dec["targeted"] != "none" else C_DIM,
                    TEAL_TAG_BG if dec["targeted"] != "none" else C_CARD,
                    TEAL_TAG_BD if dec["targeted"] != "none" else C_BORDG,
                )
                if dec["cost_type"] == "pp" and dec.get("cost", "").strip():
                    _tag(tag_row, f'PP {dec["cost"]}', C_GOLD, GOLD_TAG_BG, GOLD_TAG_BD)
                _tag(tag_row, dec["dec_id"], C_DIM, C_DARK, C_BORDG)

        # Chain assignment card
        asgn = tk.Frame(
            frm, bg=C_CARD, highlightthickness=1, highlightbackground=C_BORDG
        )
        asgn.pack(fill="x", padx=10, pady=14)
        tk.Label(
            asgn,
            text=tr("decision.chain.assignment", "  CHAIN ASSIGNMENT"),
            bg=C_CARD,
            fg=C_GOLD,
            font=("Courier", 9, "bold"),
            pady=4,
        ).pack(anchor="w")
        tk.Label(
            asgn,
            text=tr(
                "decision.chain.assignment_hint",
                "  Assign decisions to chains to track sequences. Chains are stored as comments - no engine impact.",
            ),
            bg=C_CARD,
            fg=C_DIM,
            font=("Helvetica", 9),
            wraplength=360,
            justify="left",
        ).pack(fill="x", padx=6)
        inp_row = tk.Frame(asgn, bg=C_CARD)
        inp_row.pack(fill="x", padx=6, pady=8)
        chain_inp = tk.Entry(
            inp_row,
            bg=C_DARK,
            fg=C_TEXT,
            insertbackground=C_BLUE,
            font=("Courier", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=C_BORDG,
        )
        chain_inp.insert(0, "chain name...")
        chain_inp.pack(side="left", fill="x", expand=True, ipady=4)
        tk.Button(
            inp_row,
            text=tr("decision.chain.new", "+ New Chain"),
            bg=TEAL_TAG_BG,
            fg=C_TEAL,
            relief="flat",
            font=("Courier", 9),
            cursor="hand2",
            padx=10,
            pady=4,
            highlightthickness=1,
            highlightbackground=TEAL_TAG_BD,
        ).pack(side="right", padx=4)

    # ── CODE VIEW ────────────────────────────────────────────────────────────
    def _build_code():
        _collect()
        # sub-tabs
        sub_f = tk.Frame(right_body, bg=C_PANEL)
        sub_f.pack(fill="x")
        ctab_v = tk.StringVar(value="decisions")
        cv = tk.Canvas(right_body, bg=C_DARK, highlightthickness=0)
        sb = tk.Scrollbar(right_body, orient="vertical", command=cv.yview)
        sb_h = tk.Scrollbar(right_body, orient="horizontal")
        code_t = tk.Text(
            cv,
            bg="#080b10",
            fg="#a8b4c0",
            insertbackground=C_BLUE,
            font=("Courier", 9),
            relief="flat",
            wrap="none",
            undo=True,
            highlightthickness=0,
            xscrollcommand=sb_h.set,
        )
        sb_h.config(command=code_t.xview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        # Pack sb_h before cv so horizontal scrollbar sits below the canvas
        sb_h.pack(side="bottom", fill="x")
        cv.pack(fill="both", expand=True)
        cwin = cv.create_window((0, 0), window=code_t, anchor="nw")
        code_t.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(cwin, width=e.width))

        # ── Syntax highlighting config ────────────────────────────────────────
        code_t.tag_config("kw_block", foreground="#569cd6")  # block keywords
        code_t.tag_config("kw_value", foreground="#4ec9b0")  # yes/no values
        code_t.tag_config("kw_number", foreground="#b5cea8")  # numbers
        code_t.tag_config("kw_comment", foreground="#6a9955")  # # comments
        code_t.tag_config("kw_string", foreground="#ce9178")  # "strings"
        code_t.tag_config("kw_gfx", foreground="#dcdcaa")  # GFX_ references
        code_t.tag_config("kw_scope", foreground="#c586c0")  # scope keywords
        _HL_BLOCKS = re.compile(
            r"\b(allowed|visible|available|trigger|effect|"
            r"modifier|complete_effect|remove_effect|cancel_effect|"
            r"timeout_effect|ai_will_do|immediate|on_map_area|"
            r"activation|highlight_states|targets|war_with_on_timeout|"
            r"remove_trigger|cancel_trigger|target_trigger|"
            r"target_root_trigger|defined_text|text)\b"
        )
        _HL_SCOPES = re.compile(
            r"\b(country_event|news_event|state_event|unit_leader_event|"
            r"character_event|ROOT|FROM|PREV|THIS|any_country|"
            r"every_country|random_country|owner|controller)\b"
        )
        _HL_YESNO = re.compile(r"\byes\b|\bno\b")
        _HL_NUMBER = re.compile(r"(?<![\w])(-?\d+\.?\d*)(?![\w])")
        _HL_COMMENT = re.compile(r"#[^\n]*")
        _HL_STRING = re.compile(r'"[^"\n]*"')
        _HL_GFX = re.compile(r"\bGFX_[\w]+")

        def _apply_highlight(event=None):
            for tag in (
                "kw_block",
                "kw_value",
                "kw_number",
                "kw_comment",
                "kw_string",
                "kw_gfx",
                "kw_scope",
            ):
                code_t.tag_remove(tag, "1.0", "end")
            text = code_t.get("1.0", "end")

            def _mark(pattern, tag):
                for m in pattern.finditer(text):
                    s = f"1.0 + {m.start()} chars"
                    e = f"1.0 + {m.end()} chars"
                    code_t.tag_add(tag, s, e)

            _mark(_HL_COMMENT, "kw_comment")
            _mark(_HL_STRING, "kw_string")
            _mark(_HL_BLOCKS, "kw_block")
            _mark(_HL_SCOPES, "kw_scope")
            _mark(_HL_GFX, "kw_gfx")
            _mark(_HL_YESNO, "kw_value")
            _mark(_HL_NUMBER, "kw_number")

        # Debounced — run highlight 400ms after last keystroke
        _hl_job = [None]

        def _sched_highlight(e=None):
            if _hl_job[0]:
                win.after_cancel(_hl_job[0])
            _hl_job[0] = win.after(400, _apply_highlight)

        code_t.bind("<KeyRelease>", _sched_highlight)

        # Wrap toggle button added to bot later
        _wrap_mode = [False]  # False=no wrap, True=word wrap

        def _toggle_wrap():
            _wrap_mode[0] = not _wrap_mode[0]
            code_t.config(wrap="word" if _wrap_mode[0] else "none")
            wrap_btn.config(
                text=(
                    tr("common.unwrap", "Unwrap")
                    if _wrap_mode[0]
                    else tr("common.wrap", "Wrap")
                )
            )

        def _load(tab):
            code_t.config(state="normal")
            code_t.delete("1.0", "end")
            if tab == "decisions":
                code_t.insert("1.0", _gen_decisions_file())
            elif tab == "categories":
                code_t.insert("1.0", _gen_categories_file())
            elif tab == "yml":
                code_t.insert("1.0", _gen_yml())
            elif tab == "scripted_loc":
                code_t.insert("1.0", _gen_scripted_loc())

        for tid2, tlbl2 in [
            ("decisions", "decisions .txt"),
            ("categories", "categories .txt"),
            ("yml", "localisation .yml"),
            ("scripted_loc", "scripted_loc .txt"),
        ]:

            def _mksub(t=tid2):
                ctab_v.set(t)
                _load(t)
                for b2 in sub_f.winfo_children():
                    if isinstance(b2, tk.Button):
                        b2.config(fg=C_TEXT if b2.cget("text") == tlbl2 else C_DIM)

            b3 = tk.Button(
                sub_f,
                text=tlbl2,
                command=_mksub,
                bg=C_PANEL,
                fg=C_DIM,
                relief="flat",
                font=("Courier", 9),
                cursor="hand2",
                padx=12,
                pady=5,
            )
            b3.pack(side="left")
        bot = tk.Frame(right_body, bg=C_DARK)
        bot.pack(fill="x", before=cv)

        def _apply_code_edits():
            """Re-import whatever is in the code editor back into dm_cats/dm_decs."""
            import re as _re2

            raw = code_t.get("1.0", "end-1c").strip()
            if not raw:
                _dm_status.config(
                    text=tr("decision.status.nothing_to_apply", "  x  Nothing to apply")
                )
                return
            tab = ctab_v.get()
            if tab not in ("decisions", "scripted_loc"):
                _dm_status.config(
                    text=tr(
                        "decision.status.only_code_tabs_apply",
                        "  !  Only 'decisions .txt' and 'scripted_loc .txt' edits can be applied",
                    )
                )
                return
            if tab == "scripted_loc":
                if MOD.edit_scripted_loc_file:
                    try:
                        with open(
                            MOD.edit_scripted_loc_file, "w", encoding="utf-8"
                        ) as _f:
                            _f.write(raw)
                        _dm_status.config(
                            text=f"  ✓  Scripted loc saved to {os.path.basename(MOD.edit_scripted_loc_file)}"
                        )
                    except Exception as _ex:
                        _dm_status.config(text=f"  ✗  Save error: {_ex}")
                else:
                    win.clipboard_clear()
                    win.clipboard_append(raw)
                    _dm_status.config(
                        text=tr(
                            "decision.status.copied_no_scripted_loc",
                            "  ok  Copied (no scripted loc file set in Edit Targets)",
                        )
                    )
                return

            # ── Parse the raw decisions text directly (no monkeypatch) ──────
            def _extract_block2(text, start_pos=0):
                depth = 0
                j = start_pos
                while j < len(text):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            return text[start_pos + 1 : j], j
                    j += 1
                return text[start_pos + 1 :], len(text) - 1

            def _find_blocks2(text):
                blocks = []
                i = 0
                while i < len(text):
                    if text[i] == "#":
                        while i < len(text) and text[i] != "\n":
                            i += 1
                        continue
                    m = _re2.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", text[i:])
                    if m:
                        name = m.group(1)
                        brace_pos = i + m.end() - 1
                        inner, end_j = _extract_block2(text, brace_pos)
                        blocks.append((name, inner, text[i : end_j + 1]))
                        i = end_j + 1
                        continue
                    i += 1
                return blocks

            def _get_block2(text, key):
                m = _re2.search(rf"\b{_re2.escape(key)}\s*=\s*\{{", text)
                if not m:
                    return None
                inner, _ = _extract_block2(text, m.end() - 1)
                return inner.strip()

            def _get_value2(text, key):
                m = _re2.search(rf"\b{_re2.escape(key)}\s*=\s*([^\s{{}}#\n]+)", text)
                return m.group(1).strip() if m else None

            def _get_yn2(text, key):
                v = _get_value2(text, key)
                return v == "yes" if v else None

            _snapshot()
            old_cats = list(dm_cats)
            old_decs = list(dm_decs)
            dm_cats.clear()
            dm_decs.clear()
            imported = 0
            try:
                for cat_name, cat_inner, _ in _find_blocks2(raw):
                    if cat_name in ("add_namespace", "namespace"):
                        continue
                    c = _new_cat()
                    c["cat_id"] = cat_name
                    c["loc_name"] = cat_name  # preserve existing loc name if we can
                    # try to keep existing loc_name if cat already existed
                    existing_cat = next(
                        (ec for ec in old_cats if ec["cat_id"] == cat_name), None
                    )
                    if existing_cat:
                        c["loc_name"] = existing_cat["loc_name"]
                        c["loc_desc"] = existing_cat["loc_desc"]
                    for _fld, _key in [
                        ("icon", "icon"),
                        ("picture", "picture"),
                        ("scripted_gui", "scripted_gui"),
                    ]:
                        v = _get_value2(cat_inner, _key)
                        if v:
                            c[_fld] = v
                    for _fld, _key in [
                        ("allowed", "allowed"),
                        ("visible", "visible"),
                        ("highlight_states", "highlight_states"),
                        ("map_trigger", "target_root_trigger"),
                    ]:
                        v = _get_block2(cat_inner, _key)
                        if v is not None:
                            c[_fld] = v
                    pv = _get_value2(cat_inner, "priority")
                    if pv:
                        c["priority"] = pv
                    if _get_yn2(cat_inner, "visible_when_empty"):
                        c["visible_when_empty"] = True
                    oma = _get_block2(cat_inner, "on_map_area")
                    if oma is not None:
                        c["on_map_area"] = True
                        sv = _get_value2(oma, "state")
                        c["map_state"] = sv or ""
                        nv = _get_value2(oma, "name")
                        c["map_name"] = nv or ""
                        zv = _get_value2(oma, "zoom")
                        c["map_zoom"] = zv or "850"
                    dm_cats.append(c)

                    for dec_name, dec_inner, _ in _find_blocks2(cat_inner):
                        d = _new_dec(c["uid"])
                        d["dec_id"] = dec_name
                        d["loc_name"] = dec_name
                        existing_dec = next(
                            (ed for ed in old_decs if ed["dec_id"] == dec_name), None
                        )
                        if existing_dec:
                            d["loc_name"] = existing_dec["loc_name"]
                            d["loc_desc"] = existing_dec["loc_desc"]
                        sv_map = {
                            "cost": "cost",
                            "days_remove": "days_remove",
                            "days_re_enable": "days_re_enable",
                            "priority": "priority",
                            "icon": "icon",
                            "mission_timeout": "days_mission_timeout",
                            "target_array": "target_array",
                        }
                        for dkey, hkey in sv_map.items():
                            v = _get_value2(dec_inner, hkey or dkey)
                            if v and dkey in d:
                                d[dkey] = v
                        iv = _get_value2(dec_inner, "icon")
                        if iv:
                            d["icon"] = iv
                        for _fld, _key in [
                            ("allowed", "allowed"),
                            ("visible", "visible"),
                            ("available", "available"),
                            ("complete_effect", "complete_effect"),
                            ("remove_effect", "remove_effect"),
                            ("cancel_effect", "cancel_effect"),
                            ("cancel_trigger", "cancel_trigger"),
                            ("modifier", "modifier"),
                            ("remove_trigger", "remove_trigger"),
                            ("timeout_effect", "timeout_effect"),
                            ("activation", "activation"),
                            ("highlight_states", "highlight_states"),
                            ("target_trigger", "target_trigger"),
                            ("target_root_trigger", "target_root_trigger"),
                            ("targets", "targets"),
                            ("target_array", "target_array"),
                            ("ai_will_do", "ai_will_do"),
                        ]:
                            v = _get_block2(dec_inner, _key)
                            if v is not None:
                                d[_fld] = v
                        for _fld, _key in [
                            ("fire_only_once", "fire_only_once"),
                            ("fixed_random_seed", "fixed_random_seed"),
                            ("is_mission", "is_mission"),
                            ("selectable_mission", "selectable_mission"),
                            ("is_good", "is_good"),
                            ("cancel_if_not_visible", "cancel_if_not_visible"),
                            ("targets_dynamic", "targets_dynamic"),
                            ("target_non_existing", "target_non_existing"),
                        ]:
                            yn = _get_yn2(dec_inner, _key)
                            if yn is not None:
                                d[_fld] = yn
                        ct = _get_value2(dec_inner, "days_remove")
                        if ct:
                            d["days_remove"] = ct
                        d["cost_type"] = "pp"
                        cst = _get_value2(dec_inner, "cost")
                        if cst:
                            d["cost"] = cst
                        dm_decs.append(d)
                        imported += 1

                _dedup_cats()
                _rebuild_tree()
                _rebuild_editor()
                try:
                    _build_preview()
                except Exception:
                    pass
                _autosave()
                _dm_status.config(
                    text=f"  ✓  Applied — {len(dm_cats)} categories, {imported} decisions parsed from code"
                )
            except Exception as _ex:
                import traceback as _tb

                dm_cats[:] = old_cats
                dm_decs[:] = old_decs
                _dm_status.config(text=f"  ✗  Parse error: {_ex}")
                _tb.print_exc()

        tk.Button(
            bot,
            text=tr("decision.code.apply_edits", "Apply edits"),
            command=_apply_code_edits,
            bg=C_CARD,
            fg=C_GREEN,
            relief="flat",
            font=("Courier", 9, "bold"),
            cursor="hand2",
            padx=10,
            pady=3,
            highlightthickness=1,
            highlightbackground=C_GREEN,
        ).pack(side="left", padx=6, pady=3)
        tk.Label(
            bot,
            text=tr(
                "decision.code.edit_hint",
                "Edit code directly then click Apply to save changes",
            ),
            bg=C_DARK,
            fg=C_DIM,
            font=("Helvetica", 8, "italic"),
        ).pack(side="left")
        tk.Button(
            bot,
            text=tr("common.copy_to_clipboard", "Copy to Clipboard"),
            command=lambda: [
                win.clipboard_clear(),
                win.clipboard_append(code_t.get("1.0", "end-1c")),
                _dm_status.config(text=tr("common.status.copied", "  ok  Copied")),
            ],
            bg=C_CARD,
            fg=C_DIM,
            relief="flat",
            font=("Courier", 9),
            cursor="hand2",
            padx=10,
            pady=3,
        ).pack(side="right", padx=6, pady=3)
        wrap_btn = tk.Button(
            bot,
            text=tr("common.wrap", "Wrap"),
            command=_toggle_wrap,
            bg=C_CARD,
            fg=C_DIM,
            relief="flat",
            font=("Courier", 9),
            cursor="hand2",
            padx=10,
            pady=3,
        )
        wrap_btn.pack(side="right", padx=2, pady=3)
        # Line/char count label
        _line_lbl = tk.Label(
            bot, text="", bg=C_DARK, fg=C_DIM, font=("Helvetica", 8), anchor="e"
        )
        _line_lbl.pack(side="right", padx=8)

        def _update_line_count(e=None):
            txt = code_t.get("1.0", "end-1c")
            lines = txt.count("\n") + 1
            chars = len(txt)
            _line_lbl.config(text=f"{lines} lines · {chars} chars")

        code_t.bind(
            "<KeyRelease>",
            lambda e: (_sched_highlight(e), _update_line_count(e)),
            add=True,
        )
        _load("decisions")
        _apply_highlight()
        _update_line_count()

    # ── PLACEMENT EDITOR shortcut ────────────────────────────────────────────
    def _open_placement_cat(cat):
        existing = []
        if cat.get("icon"):
            p = MOD.idea_sprites.get(cat["icon"], MOD.sprites.get(cat["icon"], ""))
            existing.append(
                {
                    "gfx_key": cat["icon"],
                    "abs_path": p,
                    "role": "icon",
                    "x": 8,
                    "y": 6,
                    "w": 24,
                    "h": 24,
                }
            )
        if cat.get("picture"):
            p = MOD.idea_sprites.get(
                cat["picture"], MOD.sprites.get(cat["picture"], "")
            )
            existing.append(
                {
                    "gfx_key": cat["picture"],
                    "abs_path": p,
                    "role": "picture",
                    "x": 8,
                    "y": 44,
                    "w": 120,
                    "h": 90,
                }
            )

        def _on_confirm(placed, code):
            for it in placed:
                if it["role"] == "icon" and "icon" in _evars:
                    _evars["icon"].set(it["gfx_key"])
                elif it["role"] == "picture" and "picture" in _evars:
                    _evars["picture"].set(it["gfx_key"])
            _collect()
            _rebuild_right()

        open_gfx_placement_editor(win, initial_items=existing, on_confirm=_on_confirm)

    # ════════════════════════════════════════════════════════════════════════
    # CODE GENERATION
    # ════════════════════════════════════════════════════════════════════════
    def _gen_scripted_loc():
        """Generate scripted_localisation defined_text blocks for all decisions/cats."""
        out = [
            "# ================================================================",
            "# FILE: common/scripted_localisation/TAG_scripted_loc.txt",
            "# ================================================================",
            "# These defined_text blocks let you reference decision/category names",
            "# dynamically in localisation via [GetVariableName]",
            "# ================================================================\n",
        ]
        for cat in dm_cats:
            cid = cat["cat_id"].strip()
            if not cid:
                continue
            out.append("defined_text = {")
            out.append(f"\tname = GET_{cid}_name")
            out.append("\ttext = {")
            out.append(f"\t\tlocalization_key = {cid}")
            out.append("\t}")
            out.append("}\n")
            if cat.get("loc_desc", "").strip():
                out.append("defined_text = {")
                out.append(f"\tname = GET_{cid}_desc")
                out.append("\ttext = {")
                out.append(f"\t\tlocalization_key = {cid}_desc")
                out.append("\t}")
                out.append("}\n")
            for dec in _decs_for(cat["uid"]):
                did = dec["dec_id"].strip()
                if not did:
                    continue
                out.append("defined_text = {")
                out.append(f"\tname = GET_{did}_name")
                out.append("\ttext = {")
                out.append(f"\t\tlocalization_key = {did}")
                out.append("\t}")
                out.append("}\n")
                if dec.get("loc_desc", "").strip():
                    out.append("defined_text = {")
                    out.append(f"\tname = GET_{did}_desc")
                    out.append("\ttext = {")
                    out.append(f"\t\tlocalization_key = {did}_desc")
                    out.append("\t}")
                    out.append("}\n")
        return "\n".join(out)

    def _indent(text, n=1):
        tab = "\t" * n
        return "\n".join(tab + l if l.strip() else l for l in text.splitlines())

    def _gen_decision_txt(dec):
        """Generate a single decision block at 1-tab indent inside its category block.

        Vanilla HOI4 rules learned from real decisions:
        - Decision body = 1 tab indent
        - Block content  = 3 tabs (user types relative, we add 3 tabs prefix)
        - state_target = yes  (for both country AND state targeted via target_array/state_target)
        - state_target = <scope>  when a specific scope keyword is chosen (any_controlled_state etc)
        - cancel_trigger / cancel_effect / modifier / remove_effect / remove_trigger /
          cancel_if_not_visible are NOT gated behind days_remove — they appear whenever set
        - highlight_states is a raw block the user pastes in
        - ai_hint_pp_cost is written when custom cost AND the field is non-empty
        """
        T1 = "\t"
        T2 = "\t\t"
        lines = [f"{T1}{dec['dec_id']} = {{"]

        # ── allowed ──────────────────────────────────────────────────────────
        if _s(dec["allowed"]):
            lines.append(f"{T2}allowed = {{\n{_indent(_s(dec['allowed']),3)}\n{T2}}}")

        # ── icon (always second, after allowed) ───────────────────────────────
        if _s(dec["icon"]):
            _icon_val = _s(dec["icon"])
            if _icon_val and not _icon_val.startswith("GFX_"):
                _icon_val = f"GFX_decision_{_icon_val}"
            lines.append(f"{T2}icon = {_icon_val}")

        # ── targeting ────────────────────────────────────────────────────────
        tgt_var = _evars.get("targeted")
        targeted = (
            tgt_var.get()
            if isinstance(tgt_var, tk.StringVar)
            else dec.get("targeted", "none")
        )
        if targeted != "none":
            if _s(dec["target_root_trigger"]):
                lines.append(
                    f"{T2}target_root_trigger = {{\n{_indent(_s(dec['target_root_trigger']),3)}\n{T2}}}"
                )
            if _s(dec["target_trigger"]):
                lines.append(
                    f"{T2}target_trigger = {{\n{_indent(_s(dec['target_trigger']),3)}\n{T2}}}"
                )
            # state_target
            if targeted == "state":
                scope = _s(dec.get("state_target_scope", "any"))
                # vanilla uses "state_target = yes" OR "state_target = <scope>"
                if scope in ("yes", "any", ""):
                    lines.append(f"{T2}state_target = yes")
                else:
                    lines.append(f"{T2}state_target = {scope}")
                lines.append(
                    f"{T2}on_map_mode = {dec.get('on_map_mode','map_and_decisions_view')}"
                )
            elif targeted == "country":
                # country targeted: state_target = yes is NOT used
                pass
            # targets list (country tags or state IDs)
            if _s(dec["targets"]):
                lines.append(f"{T2}targets = {{ {_s(dec['targets'])} }}")
            if dec.get("targets_dynamic"):
                lines.append(f"{T2}targets_dynamic = yes")
            if dec.get("target_non_existing"):
                lines.append(f"{T2}target_non_existing = yes")
            if _s(dec["target_array"]):
                lines.append(f"{T2}target_array = {_s(dec['target_array'])}")
                # when using target_array with state_target, always need on_map_mode
                if targeted == "country" and _s(dec.get("on_map_mode", "")):
                    lines.append(f"{T2}on_map_mode = {_s(dec['on_map_mode'])}")

        # ── visible / available ──────────────────────────────────────────────
        if _s(dec["visible"]):
            lines.append(f"{T2}visible = {{\n{_indent(_s(dec['visible']),3)}\n{T2}}}")
        if _s(dec["available"]):
            lines.append(
                f"{T2}available = {{\n{_indent(_s(dec['available']),3)}\n{T2}}}"
            )

        # ── highlight_states ─────────────────────────────────────────────────
        if _s(dec.get("highlight_states", "")):
            hs = _s(dec["highlight_states"])
            # user may or may not wrap in highlight_states = { }
            if not hs.startswith("highlight_states"):
                lines.append(f"{T2}highlight_states = {{\n{_indent(hs,3)}\n{T2}}}")
            else:
                lines.append(_indent(hs, 2))

        # ── on_map_mode (non-targeted) ───────────────────────────────────────
        # For non-targeted decisions that still use highlight_states + on_map_mode
        if targeted == "none" and _s(dec.get("on_map_mode", "")):
            lines.append(f"{T2}on_map_mode = {_s(dec['on_map_mode'])}")

        # ── mission fields ───────────────────────────────────────────────────
        if dec.get("is_mission"):
            lines.append(
                f"{T2}days_mission_timeout = {dec.get('mission_timeout','100')}"
            )
            if dec.get("selectable_mission"):
                lines.append(f"{T2}selectable_mission = yes")
            if dec.get("is_good"):
                lines.append(f"{T2}is_good = yes")
            if _s(dec.get("activation", "")):
                lines.append(
                    f"{T2}activation = {{\n{_indent(_s(dec['activation']),3)}\n{T2}}}"
                )

        # ── cost ─────────────────────────────────────────────────────────────
        cost_type_var = _evars.get("cost_type")
        ct_val = (
            cost_type_var.get()
            if isinstance(cost_type_var, tk.StringVar)
            else dec.get("cost_type", "pp")
        )
        if ct_val == "pp":
            if _s(dec.get("cost", "")):
                lines.append(f"{T2}cost = {_s(dec['cost'])}")
        else:  # custom cost
            if _s(dec.get("ai_hint_pp_cost", "")):
                lines.append(f"{T2}ai_hint_pp_cost = {_s(dec['ai_hint_pp_cost'])}")
            if _s(dec.get("custom_cost_trigger", "")):
                lines.append(
                    f"{T2}custom_cost_trigger = {{\n{_indent(_s(dec['custom_cost_trigger']),3)}\n{T2}}}"
                )
            if _s(dec.get("custom_cost_text", "")):
                lines.append(f"{T2}custom_cost_text = {_s(dec['custom_cost_text'])}")

        # ── timer ────────────────────────────────────────────────────────────
        if _s(dec.get("days_remove", "")):
            lines.append(f"{T2}days_remove = {_s(dec['days_remove'])}")
        if _s(dec.get("days_re_enable", "")):
            lines.append(f"{T2}days_re_enable = {_s(dec['days_re_enable'])}")
        if dec.get("fire_only_once"):
            lines.append(f"{T2}fire_only_once = yes")
        if not dec.get("fixed_random_seed", True):
            lines.append(f"{T2}fixed_random_seed = no")

        # ── war warnings ─────────────────────────────────────────────────────
        if targeted != "none":
            if dec.get("war_target_complete"):
                lines.append(f"{T2}war_with_target_on_complete = yes")
            if dec.get("war_target_remove"):
                lines.append(f"{T2}war_with_target_on_remove = yes")
        else:
            if _s(dec.get("war_complete_tag", "")):
                lines.append(
                    f"{T2}war_with_on_complete = {_s(dec['war_complete_tag'])}"
                )
            if _s(dec.get("war_remove_tag", "")):
                lines.append(f"{T2}war_with_on_remove = {_s(dec['war_remove_tag'])}")

        # ── modifier (NOT gated behind days_remove — can appear standalone) ──
        if _s(dec.get("modifier", "")):
            lines.append(f"{T2}modifier = {{\n{_indent(_s(dec['modifier']),3)}\n{T2}}}")

        # ── effects — all ungated (remove_effect, cancel_effect, etc) ────────
        if _s(dec.get("complete_effect", "")):
            # Inject log line if not already present (standardizer requirement)
            ce = _s(dec["complete_effect"])
            if "log = " not in ce:
                dec_id = _s(dec["dec_id"])
                log_line = (
                    f'\t\t\tlog = "[GetDateText]: [Root.GetName]: Decision {dec_id}"'
                )
                ce = log_line + ("\n" + _indent(ce.strip(), 3) if ce.strip() else "")
            else:
                ce = _indent(ce.strip(), 3)
            lines.append(f"{T2}complete_effect = {{\n{ce}\n{T2}}}")
        elif _s(dec.get("dec_id", "")):
            # Always emit complete_effect with log even if empty, for standardizer compliance
            dec_id = _s(dec["dec_id"])
            lines.append(f"{T2}complete_effect = {{")
            lines.append(
                f'\t\t\tlog = "[GetDateText]: [Root.GetName]: Decision {dec_id}"'
            )
            lines.append(f"{T2}}}")

        if dec.get("is_mission") and _s(dec.get("timeout_effect", "")):
            lines.append(
                f"{T2}timeout_effect = {{\n{_indent(_s(dec['timeout_effect']),3)}\n{T2}}}"
            )

        if _s(dec.get("remove_effect", "")):
            re_txt = _s(dec["remove_effect"])
            if "log = " not in re_txt:
                dec_id = _s(dec["dec_id"])
                log_line = (
                    f'\t\t\tlog = "[GetDateText]: [Root.GetName]: Decision {dec_id}"'
                )
                re_txt = log_line + (
                    "\n" + _indent(re_txt.strip(), 3) if re_txt.strip() else ""
                )
            else:
                re_txt = _indent(re_txt.strip(), 3)
            lines.append(f"{T2}remove_effect = {{\n{re_txt}\n{T2}}}")

        if _s(dec.get("cancel_trigger", "")):
            lines.append(
                f"{T2}cancel_trigger = {{\n{_indent(_s(dec['cancel_trigger']),3)}\n{T2}}}"
            )

        if _s(dec.get("cancel_effect", "")):
            lines.append(
                f"{T2}cancel_effect = {{\n{_indent(_s(dec['cancel_effect']),3)}\n{T2}}}"
            )

        if dec.get("cancel_if_not_visible"):
            lines.append(f"{T2}cancel_if_not_visible = yes")

        if _s(dec.get("remove_trigger", "")):
            lines.append(
                f"{T2}remove_trigger = {{\n{_indent(_s(dec['remove_trigger']),3)}\n{T2}}}"
            )

        # ── AI ───────────────────────────────────────────────────────────────
        if _s(dec.get("ai_will_do", "")):
            lines.append(
                f"{T2}ai_will_do = {{\n{_indent(_s(dec['ai_will_do']),3)}\n{T2}}}"
            )

        if _s(dec.get("priority", "")) not in ("", "1"):
            lines.append(f"{T2}priority = {_s(dec['priority'])}")

        lines.append(f"{T1}}}")
        return "\n".join(lines)

    def _gen_decisions_file():
        _collect()
        out = [
            "# ================================================================",
            "# FILE: common/decisions/TAG_decisions.txt",
            "# ================================================================\n",
        ]
        for cat in dm_cats:
            decs = _decs_for(cat["uid"])
            if not decs:
                continue
            out.append(f"{cat['cat_id']} = {{")
            for dec in decs:
                out.append("\n" + _gen_decision_txt(dec))
            out.append("}\n")
        result = "\n".join(out)
        return result

    def _gen_categories_file():
        _collect()
        T1 = "\t"
        T2 = "\t\t"
        out = [
            "# ================================================================",
            "# FILE: common/decisions/categories/TAG_categories.txt",
            "# ================================================================\n",
        ]
        for cat in dm_cats:
            out.append(f"{cat['cat_id']} = {{")
            if _s(cat["allowed"]):
                out.append(f"{T1}allowed = {{\n{_indent(_s(cat['allowed']),2)}\n{T1}}}")
            if _s(cat["visible"]):
                out.append(f"{T1}visible = {{\n{_indent(_s(cat['visible']),2)}\n{T1}}}")
            if _s(cat["icon"]):
                out.append(f"{T1}icon = {_s(cat['icon'])}")
            if _s(cat["picture"]):
                out.append(f"{T1}picture = {_s(cat['picture'])}")
            if _s(cat["priority"]) not in ("", "1"):
                out.append(f"{T1}priority = {_s(cat['priority'])}")
            if cat.get("visible_when_empty"):
                out.append(f"{T1}visible_when_empty = yes")
            if _s(cat.get("scripted_gui", "")):
                out.append(f"{T1}scripted_gui = {_s(cat['scripted_gui'])}")
            if _s(cat.get("highlight_states", "")):
                hs = _s(cat["highlight_states"])
                if not hs.startswith("highlight_states"):
                    out.append(f"{T1}highlight_states = {{\n{_indent(hs,2)}\n{T1}}}")
                else:
                    out.append(_indent(hs, 1))
            if cat["on_map_area"]:
                out.append(f"{T1}on_map_area = {{")
                out.append(f"{T2}state = {_s(cat.get('map_state',''))}")
                out.append(f"{T2}name = {_s(cat.get('map_name',''))}")
                out.append(f"{T2}zoom = {_s(cat.get('map_zoom','850'))}")
                if _s(cat.get("map_trigger", "")):
                    out.append(
                        f"{T2}target_root_trigger = {{\n{_indent(_s(cat['map_trigger']),3)}\n{T2}}}"
                    )
                out.append(f"{T1}}}")
            out.append("}\n")
        return "\n".join(out)

    def _gen_yml():
        _collect()
        lines = ["l_english:"]
        for cat in dm_cats:
            cid = _s(cat["cat_id"])
            if cid:
                lines.append(f' {cid}: "{cat["loc_name"]}"')
                if _s(cat.get("loc_desc", "")):
                    lines.append(f' {cid}_desc: "{_s(cat["loc_desc"])}"')
            for dec in _decs_for(cat["uid"]):
                did = _s(dec["dec_id"])
                if did:
                    lines.append(f' {did}: "{dec["loc_name"]}"')
                    if _s(dec.get("loc_desc", "")):
                        lines.append(f' {did}_desc: "{_s(dec["loc_desc"])}"')
        return "\n".join(lines) + "\n"

    # ── import / export ───────────────────────────────────────────────────────
    def _browse_mod_decisions():
        import glob as _glob

        if not MOD.loaded or not MOD.root:
            messagebox.showinfo(
                tr("dialog.no_mod_loaded.title", "No Mod Loaded"),
                tr(
                    "decision.dialog.load_mod_to_browse",
                    "Load a mod first to browse existing decisions.",
                ),
                parent=win,
            )
            return
        dec_dir = os.path.join(MOD.root, "common", "decisions")
        if not os.path.isdir(dec_dir):
            messagebox.showinfo(
                tr("dialog.not_found.title", "Not Found"),
                tr(
                    "decision.dialog.no_decisions_dir",
                    "No common/decisions/ directory found in mod.",
                ),
                parent=win,
            )
            return
        files = sorted(_glob.glob(os.path.join(dec_dir, "*.txt")))
        if not files:
            messagebox.showinfo(
                tr("dialog.no_files_found.title", "No Files Found"),
                tr(
                    "decision.dialog.no_decision_files",
                    "No .txt files found in common/decisions/.",
                ),
                parent=win,
            )
            return

        dlg = tk.Toplevel(win)
        dlg.title(tr("decision.browse_mod_decisions.title", "Browse Mod Decisions"))
        dlg.configure(bg=BG_DARK)
        dlg.geometry("520x440")
        dlg.resizable(True, True)
        dlg.grab_set()
        tk.Label(
            dlg,
            text=tr("decision.browse_mod_decisions.header", "BROWSE MOD DECISIONS"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=8,
        ).pack(fill="x", padx=12)
        tk.Label(
            dlg,
            text=tr(
                "decision.browse_mod_decisions.hint",
                "Select a file to import. Already-loaded decisions are preserved.",
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
            selectmode="extended",
        )
        sb = tk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for fp in files:
            lb.insert("end", f"  {os.path.basename(fp)}")

        def _do_import():
            sel = lb.curselection()
            if not sel:
                return
            selected = [files[i] for i in sel]
            # Check for duplicate category IDs before importing
            import re as _re2

            existing_cat_ids = {c["cat_id"] for c in dm_cats}
            new_cats = []
            for fp in selected:
                try:
                    with open(fp, encoding="utf-8-sig", errors="replace") as f:
                        raw = f.read()
                    for m in _re2.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", raw):
                        cid = m.group(1)
                        if (
                            cid not in ("add_namespace", "namespace")
                            and cid in existing_cat_ids
                        ):
                            new_cats.append(cid)
                except Exception:
                    pass
            if new_cats:
                dupes = ", ".join(sorted(set(new_cats)))
                if not messagebox.askyesno(
                    tr(
                        "decision.dialog.duplicate_categories.title",
                        "Duplicate Categories",
                    ),
                    f"These category IDs already exist:\n{dupes}\n\n"
                    + tr(
                        "decision.dialog.duplicate_categories.body",
                        "Import anyway? (duplicates will be added as new entries)",
                    ),
                    parent=dlg,
                ):
                    return
            dlg.destroy()
            _snapshot()
            _import_txt(_paths=selected)

        lb.bind("<Double-Button-1>", lambda e: _do_import())
        bot_dlg = tk.Frame(dlg, bg=BG_DARK, pady=6)
        bot_dlg.pack(fill="x")
        tk.Button(
            bot_dlg,
            text=tr("common.import_selected", "Import Selected"),
            command=_do_import,
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

    def _import_txt(_paths=None):
        import os as _os
        import re as _re

        paths = _paths or filedialog.askopenfilenames(
            parent=win,
            title="Import decisions .txt (+ optionally loc .yml)",
            filetypes=[
                ("HOI4 files", "*.txt *.yml"),
                ("TXT", "*.txt"),
                ("YML", "*.yml"),
                ("All", "*.*"),
            ],
        )
        if not paths:
            return

        # Auto-set edit target to the first imported .txt so Save overwrites in place
        _first_txt = next((p for p in paths if p.lower().endswith(".txt")), None)
        if _first_txt:
            MOD.edit_decisions_file = _first_txt
            # Try to auto-detect matching categories file in common/decisions/categories/
            _base = _os.path.basename(_first_txt)
            _folder = _os.path.dirname(_first_txt)
            _cat_path = _os.path.join(_folder, "categories", _base)
            if _os.path.isfile(_cat_path):
                MOD.edit_decisions_cat_file = _cat_path

        # ── helper: extract a named block from text, return (inner_text, full_text) ──
        def _extract_block(text, start_pos=0):
            """Given text starting at '{', return content between braces."""
            depth = 0
            j = start_pos
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start_pos + 1 : j], j
                j += 1
            return text[start_pos + 1 :], len(text) - 1

        def _find_blocks(text):
            """Find all top-level key = { ... } blocks, skipping comments."""
            blocks = []
            i = 0
            while i < len(text):
                if text[i] == "#":
                    while i < len(text) and text[i] != "\n":
                        i += 1
                    continue
                m = _re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{", text[i:])
                if m:
                    name = m.group(1)
                    brace_pos = i + m.end() - 1
                    inner, end_j = _extract_block(text, brace_pos)
                    blocks.append((name, inner, text[i : end_j + 1]))
                    i = end_j + 1
                    continue
                i += 1
            return blocks

        def _get_block(text, key):
            """Extract inner content of first occurrence of key = { ... } in text."""
            m = _re.search(rf"\b{_re.escape(key)}\s*=\s*\{{", text)
            if not m:
                return None
            inner, _ = _extract_block(text, m.end() - 1)
            return inner.strip()

        def _get_value(text, key):
            """Get scalar value: key = value (not a block)."""
            m = _re.search(rf"\b{_re.escape(key)}\s*=\s*([^\s{{}}#\n]+)", text)
            return m.group(1).strip() if m else None

        def _get_yes_no(text, key):
            v = _get_value(text, key)
            return v == "yes" if v else None

        # ── load localisation from .yml files ──
        loc = {}
        for path in paths:
            if path.lower().endswith(".yml"):
                try:
                    with open(path, encoding="utf-8-sig", errors="replace") as f:
                        for line in f:
                            lm = _re.match(r'\s+([\w]+):(?:\d+)?\s+"(.*?)"', line)
                            if lm:
                                loc[lm.group(1)] = lm.group(2)
                except Exception:
                    pass

        # Also try to auto-load loc from same folder as first .txt
        txt_paths = [p for p in paths if p.lower().endswith(".txt")]
        if txt_paths and not any(p.lower().endswith(".yml") for p in paths):
            folder = os.path.dirname(txt_paths[0])
            # walk up to find localisation folder
            for _ in range(5):
                loc_dir = os.path.join(folder, "localisation")
                if os.path.isdir(loc_dir):
                    for fn in os.listdir(loc_dir):
                        if fn.endswith(".yml") or fn.endswith("_l_english.yml"):
                            try:
                                with open(
                                    os.path.join(loc_dir, fn),
                                    encoding="utf-8-sig",
                                    errors="replace",
                                ) as f:
                                    for line in f:
                                        lm = _re.match(
                                            r'\s+([\w]+):(?:\d+)?\s+"(.*?)"', line
                                        )
                                        if lm:
                                            loc[lm.group(1)] = lm.group(2)
                            except Exception:
                                pass
                    break
                folder = os.path.dirname(folder)

        imported = 0
        for path in txt_paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    raw = f.read()
            except Exception as e:
                messagebox.showerror("Import Error", str(e), parent=win)
                continue

            for cat_name, cat_inner, _ in _find_blocks(raw):
                if cat_name in ("add_namespace", "namespace"):
                    continue
                c = _new_cat()
                c["cat_id"] = cat_name
                c["loc_name"] = loc.get(cat_name, cat_name)
                c["loc_desc"] = loc.get(cat_name + "_desc", "")
                # Parse category fields
                for _field, _key in [
                    ("icon", "icon"),
                    ("picture", "picture"),
                    ("scripted_gui", "scripted_gui"),
                ]:
                    v = _get_value(cat_inner, _key)
                    if v:
                        c[_field] = v
                for _field, _key in [
                    ("allowed", "allowed"),
                    ("visible", "visible"),
                    ("highlight_states", "highlight_states"),
                    ("map_trigger", "target_root_trigger"),
                ]:
                    v = _get_block(cat_inner, _key)
                    if v is not None:
                        c[_field] = v
                pv = _get_value(cat_inner, "priority")
                if pv:
                    c["priority"] = pv
                if _get_yes_no(cat_inner, "visible_when_empty"):
                    c["visible_when_empty"] = True
                # on_map_area
                oma = _get_block(cat_inner, "on_map_area")
                if oma is not None:
                    c["on_map_area"] = True
                    sv = _get_value(oma, "state")
                    c["map_state"] = sv or ""
                    nv = _get_value(oma, "name")
                    c["map_name"] = nv or ""
                    zv = _get_value(oma, "zoom")
                    c["map_zoom"] = zv or "850"
                dm_cats.append(c)

                for dec_name, dec_inner, _ in _find_blocks(cat_inner):
                    d = _new_dec(c["uid"])
                    d["dec_id"] = dec_name
                    d["loc_name"] = loc.get(dec_name, dec_name)
                    d["loc_desc"] = loc.get(dec_name + "_desc", "")

                    # ── scalar fields ──
                    for _field, _key in [("priority", "priority"), ("chain", "")]:
                        pass  # handled below
                    sv_map = {
                        "cost": "cost",
                        "days_remove": "days_remove",
                        "days_re_enable": "days_re_enable",
                        "priority": "priority",
                        "icon": "icon",
                        "mission_timeout": "days_mission_timeout",
                        "target_array": "target_array",
                    }
                    for dkey, hkey in sv_map.items():
                        v = _get_value(dec_inner, hkey or dkey)
                        if v and dkey in d:
                            d[dkey] = v
                    # icon direct key
                    iv = _get_value(dec_inner, "icon")
                    if iv:
                        d["icon"] = iv

                    # ── boolean flags ──
                    if _get_yes_no(dec_inner, "fire_only_once") is True:
                        d["fire_only_once"] = True
                    if _re.search(r"\bfire_only_once\b", dec_inner):
                        d["fire_only_once"] = True
                    if _get_yes_no(dec_inner, "fixed_random_seed") is False:
                        d["fixed_random_seed"] = False
                    if _get_yes_no(dec_inner, "is_mission") is True:
                        d["is_mission"] = True
                    if _get_yes_no(dec_inner, "selectable_mission") is False:
                        d["selectable_mission"] = False
                    if _get_yes_no(dec_inner, "is_good") is True:
                        d["is_good"] = True
                    if _get_yes_no(dec_inner, "cancel_if_not_visible") is True:
                        d["cancel_if_not_visible"] = True
                    if _get_yes_no(dec_inner, "targets_dynamic") is True:
                        d["targets_dynamic"] = True
                    if _get_yes_no(dec_inner, "target_non_existing") is True:
                        d["target_non_existing"] = True

                    # ── cost type detection ──
                    if _re.search(r"\bcustom_cost_trigger\b", dec_inner):
                        d["cost_type"] = "custom"
                        ccb = _get_block(dec_inner, "custom_cost_trigger")
                        if ccb:
                            d["custom_cost_trigger"] = ccb
                        cct = _get_value(dec_inner, "custom_cost_text")
                        if cct:
                            d["custom_cost_text"] = cct
                        ahp = _get_value(dec_inner, "ai_hint_pp_cost")
                        if ahp:
                            d["ai_hint_pp_cost"] = ahp
                    else:
                        cv = _get_value(dec_inner, "cost")
                        if cv:
                            d["cost"] = cv
                            d["cost_type"] = "pp"

                    # ── block fields ──
                    block_map = {
                        "allowed": "allowed",
                        "visible": "visible",
                        "available": "available",
                        "cancel_trigger": "cancel_trigger",
                        "complete_effect": "complete_effect",
                        "remove_effect": "remove_effect",
                        "cancel_effect": "cancel_effect",
                        "timeout_effect": "timeout_effect",
                        "ai_will_do": "ai_will_do",
                        "modifier": "modifier",
                        "remove_trigger": "remove_trigger",
                        "activation": "activation",
                        "highlight_states": "highlight_states",
                        "target_trigger": "target_trigger",
                        "target_root_trigger": "target_root_trigger",
                        "war_with_on_timeout": "war_with_on_timeout",
                    }
                    for dkey, hkey in block_map.items():
                        v = _get_block(dec_inner, hkey)
                        if v is not None and dkey in d:
                            d[dkey] = v

                    # ── targeting detection ──
                    if _re.search(r"\btarget_array\b|\btargets\b", dec_inner):
                        d["targeted"] = "country"
                        tv = _get_value(dec_inner, "targets")
                        if tv:
                            d["targets"] = tv
                    if _re.search(r"\bstate_target\b", dec_inner):
                        d["targeted"] = "state"
                    if d["targeted"] != "none":
                        on_mm = _get_value(dec_inner, "on_map_mode")
                        if on_mm:
                            d["on_map_mode"] = on_mm
                        st_scope = _get_value(dec_inner, "state_target")
                        if st_scope and st_scope != "yes":
                            d["state_target_scope"] = st_scope
                        ta = _get_value(dec_inner, "target_array")
                        if ta:
                            d["target_array"] = ta

                    dm_decs.append(d)
                    imported += 1

        _autosave()
        _dm_status.config(text=f"  ✓  Imported {imported} decisions — rebuilding...")
        win.update_idletasks()
        _rebuild_tree()
        win.after(
            50,
            lambda: (
                _rebuild_editor(),
                _dm_status.config(text=f"  ✓  Imported {imported} decisions"),
            ),
        )

    def _import_scripted_loc():
        """Load a scripted_localisation .txt and apply loc keys to existing decisions/cats."""
        import re as _rsl

        paths = filedialog.askopenfilenames(
            parent=win,
            title="Import scripted_localisation .txt files",
            filetypes=[("HOI4 txt", "*.txt"), ("All", "*.*")],
        )
        if not paths:
            return
        # Build map: defined_text name -> localization_key (from first text block)
        sloc_map = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    raw = f.read()
                for m in _rsl.finditer(
                    r"defined_text\s*=\s*\{[^}]*?name\s*=\s*(\S+)[^}]*?"
                    r"localization_key\s*=\s*(\S+)",
                    raw,
                    _rsl.DOTALL,
                ):
                    sloc_map[m.group(1)] = m.group(2)
            except Exception:
                pass
        if not sloc_map:
            _dm_status.config(text="  ⚠  No defined_text blocks found")
            return
        updated = 0
        # Match GET_{id}_name -> loc_name key, GET_{id}_desc -> loc_desc key
        for c in dm_cats:
            cid = c["cat_id"].strip()
            key_name = f"GET_{cid}_name"
            if key_name in sloc_map:
                c["loc_name"] = sloc_map[key_name]
                updated += 1
            key_desc = f"GET_{cid}_desc"
            if key_desc in sloc_map:
                c["loc_desc"] = sloc_map[key_desc]
        for d in dm_decs:
            did = d["dec_id"].strip()
            key_name = f"GET_{did}_name"
            if key_name in sloc_map:
                d["loc_name"] = sloc_map[key_name]
                updated += 1
            key_desc = f"GET_{did}_desc"
            if key_desc in sloc_map:
                d["loc_desc"] = sloc_map[key_desc]
        _dm_status.config(text=f"  ✓  Scripted loc applied — {updated} entries matched")
        win.after(30, lambda: (_rebuild_tree(), _rebuild_editor()))

    def _import_yml_loc():
        """Load a localisation .yml and apply names/descs to existing decisions/cats."""
        import re as _re2

        paths = filedialog.askopenfilenames(
            parent=win,
            title="Import localisation .yml files",
            filetypes=[("YML localisation", "*.yml"), ("All", "*.*")],
        )
        if not paths:
            return
        loc2 = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        lm = _re2.match(r'\s+([\w]+):(?:\d+)?\s+"(.*?)"', line)
                        if lm:
                            loc2[lm.group(1)] = lm.group(2)
            except Exception as e:
                messagebox.showerror("YML Error", str(e), parent=win)
                return
        updated = 0
        for c in dm_cats:
            if c["cat_id"] in loc2:
                c["loc_name"] = loc2[c["cat_id"]]
                updated += 1
            if c["cat_id"] + "_desc" in loc2:
                c["loc_desc"] = loc2[c["cat_id"] + "_desc"]
        for d in dm_decs:
            if d["dec_id"] in loc2:
                d["loc_name"] = loc2[d["dec_id"]]
                updated += 1
            if d["dec_id"] + "_desc" in loc2:
                d["loc_desc"] = loc2[d["dec_id"] + "_desc"]
        _dm_status.config(text=f"  ✓  Localisation applied — {updated} entries matched")
        win.after(30, lambda: (_rebuild_tree(), _rebuild_editor()))

    def _export_txt():
        _collect()
        path = filedialog.asksaveasfilename(
            parent=win,
            title="Export decisions .txt",
            defaultextension=".txt",
            filetypes=[("HOI4 decisions", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(_gen_decisions_file())
            cat_path = path.replace(".txt", "_categories.txt")
            with open(cat_path, "w", encoding="utf-8") as f:
                f.write(_gen_categories_file())
            _dm_status.config(text="  ✓  Exported")
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=win)

    def _copy_yml():
        _collect()
        win.clipboard_clear()
        win.clipboard_append(_gen_yml())
        _dm_status.config(
            text=tr("common.status.yml_copied", "  ok  YML copied to clipboard")
        )

    def _save_to_mod():
        _collect()
        if not dm_cats:
            messagebox.showwarning("Empty", "No categories to save.", parent=win)
            return
        if MOD.root and os.path.isdir(MOD.root):
            mod_root = MOD.root
        else:
            mod_root = filedialog.askdirectory(
                parent=win, title="Select MOD ROOT folder"
            )
            if not mod_root:
                return
        ns = dm_cats[0]["cat_id"].split("_")[0] if dm_cats else "TAG"
        saved = []
        errs = []
        # Prefer the imported/user-set edit target so we overwrite the source file in place
        if MOD.edit_decisions_file and os.path.isfile(MOD.edit_decisions_file):
            dec_path = MOD.edit_decisions_file
        else:
            dec_path = os.path.join(
                mod_root, "common", "decisions", f"{ns}_decisions.txt"
            )
        os.makedirs(os.path.dirname(dec_path), exist_ok=True)
        try:
            with open(dec_path, "w", encoding="utf-8") as f:
                f.write(_gen_decisions_file())
            try:
                saved.append(os.path.relpath(dec_path, mod_root))
            except ValueError:
                saved.append(dec_path)
        except Exception as e:
            errs.append(str(e))
        # Categories file — use the matching edit target if set, else default
        if MOD.edit_decisions_cat_file and os.path.isfile(MOD.edit_decisions_cat_file):
            cat_path = MOD.edit_decisions_cat_file
        else:
            cat_path = os.path.join(
                mod_root, "common", "decisions", "categories", f"{ns}_categories.txt"
            )
        os.makedirs(os.path.dirname(cat_path), exist_ok=True)
        try:
            with open(cat_path, "w", encoding="utf-8") as f:
                f.write(_gen_categories_file())
            try:
                saved.append(os.path.relpath(cat_path, mod_root))
            except ValueError:
                saved.append(cat_path)
        except Exception as e:
            errs.append(str(e))
        yml_path = (
            MOD.edit_loc_file
            if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file)
            else os.path.join(
                mod_root, "localisation", "english", f"{ns}_decisions_l_english.yml"
            )
        )
        os.makedirs(os.path.dirname(yml_path), exist_ok=True)
        try:
            import re as _re_loc2

            # Read existing keys
            existing_loc_keys = set()
            if os.path.isfile(yml_path):
                with open(yml_path, encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        m = _re_loc2.match(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', line)
                        if m:
                            existing_loc_keys.add(m.group(1))
            else:
                with open(yml_path, "w", encoding="utf-8-sig") as f:
                    f.write("l_english:\n")
            new_lines = [
                l
                for l in _gen_yml().splitlines()
                if l.strip() and not l.strip().startswith("l_english")
            ]
            # Only add lines whose key isn't already in the file
            to_write = []
            for ln in new_lines:
                m = _re_loc2.match(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', ln)
                if m and m.group(1) in existing_loc_keys:
                    continue
                to_write.append(ln)
            if to_write:
                with open(yml_path, "a", encoding="utf-8-sig") as f:
                    f.write("\n".join(to_write) + "\n")
            saved.append(
                os.path.relpath(yml_path, mod_root) + f"  (+{len(to_write)} keys)"
            )
        except Exception as e:
            errs.append(str(e))
        # ── SCRIPTED LOC ─────────────────────────────────────────────────
        if MOD.edit_scripted_loc_file:
            sloc_blocks = []
            for cat in dm_cats:
                cid = cat["cat_id"].strip()
                if cid:
                    sloc_blocks.append(
                        {"name": f"GET_{cid}_name", "texts": [], "default": cid}
                    )
                for dec in _decs_for(cat["uid"]):
                    did = dec["dec_id"].strip()
                    if did:
                        sloc_blocks.append(
                            {"name": f"GET_{did}_name", "texts": [], "default": did}
                        )
            append_scripted_loc(
                MOD.edit_scripted_loc_file, sloc_blocks, saved, errs, mod_root
            )

        msg = "Saved:\n" + "\n".join(saved)
        if errs:
            msg += "\n\nErrors:\n" + "\n".join(errs)
        messagebox.showinfo("Saved to Mod", msg, parent=win)
        _dm_status.config(text=tr("common.status.saved_to_mod", "  ok  Saved to mod"))

    # ── init ─────────────────────────────────────────────────────────────────
    # ── Autosave restore prompt ──────────────────────────────────────────────
    def _try_restore():
        if os.path.isfile(_autosave_path):
            try:
                import json as _j

                with open(_autosave_path, encoding="utf-8") as f:
                    data = _j.load(f)
                n_cats = len(data.get("cats", []))
                n_decs = len(data.get("decs", []))
                if n_cats > 0 or n_decs > 0:
                    if messagebox.askyesno(
                        "Restore autosave",
                        f"An autosave was found with {n_cats} categories and {n_decs} decisions.\nRestore it?",
                        parent=win,
                    ):
                        dm_cats.clear()
                        dm_cats.extend(data["cats"])
                        dm_decs.clear()
                        dm_decs.extend(data["decs"])
                        _dedup_cats()
                        # Select first cat and rebuild everything now that data is loaded
                        if dm_cats:
                            sel["uid"] = dm_cats[0]["uid"]
                            sel["type"] = "cat"
                        _rebuild_tree()
                        _rebuild_editor()
                        _rebuild_right()
            except Exception:
                pass

    if not dm_cats:
        win.after(50, _try_restore)
    else:
        # Data already present (passed in externally) — just build
        sel["uid"] = dm_cats[0]["uid"]
        sel["type"] = "cat"
        _rebuild_tree()
        _rebuild_editor()
        _rebuild_right()
