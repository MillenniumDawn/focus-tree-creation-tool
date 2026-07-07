# ruff: noqa: E501, UP031
# This file was extracted from hoi4_content_maker.py. The dialog body
# retains the original monolith's style (long translated-string lines,
# a percent-format log line). Tightening any of this is a separate refactor.

"""Settings dialog: GFX paths, MD detection, extra dirs, locale, etc."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from hoi4cm.core.config import CONFIG_PATH
from hoi4cm.core.i18n import I18N_LANGS, get_language, set_language, tr
from hoi4cm.core.paths import default_hoi4_mod_dir
from hoi4cm.mod import MOD
from hoi4cm.ui.theme import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    GOLD,
    GREEN,
    RED,
    TEXT,
    TEXT_DIM,
)

# Built-in vanilla HOI4 tag names, used as the "Load Vanilla HOI4 Tags" quick-fill.
VANILLA_COUNTRY_TAGS = {
    "GER": "Germany",
    "SOV": "Soviet Union",
    "ENG": "United Kingdom",
    "FRA": "France",
    "USA": "United States",
    "ITA": "Italy",
    "JAP": "Japan",
    "CHI": "China",
    "SPR": "Republican Spain",
    "NAT": "Nationalist Spain",
    "POL": "Poland",
    "HUN": "Hungary",
    "ROM": "Romania",
    "BUL": "Bulgaria",
    "YUG": "Yugoslavia",
    "GRE": "Greece",
    "TUR": "Turkey",
    "IRQ": "Iraq",
    "IRN": "Iran",
    "SAU": "Saudi Arabia",
    "EGY": "Egypt",
    "ETH": "Ethiopia",
    "SOM": "Somalia",
    "ERI": "Eritrea",
    "SYR": "Syria",
    "HEZ": "Hezbollastan",
    "PER": "Persia",
    "CAN": "Canada",
    "AST": "Australia",
    "NZL": "New Zealand",
    "SAF": "South Africa",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "SWE": "Sweden",
    "NOR": "Norway",
    "DEN": "Denmark",
    "FIN": "Finland",
    "POR": "Portugal",
    "BEL": "Belgium",
    "HOL": "Netherlands",
    "SWI": "Switzerland",
    "CZE": "Czechoslovakia",
    "AUS": "Austria",
    "YEM": "Yemen",
    "AFG": "Afghanistan",
}

# (preset name, path_goals, path_ideas_gfx) — offered as one-click buttons
# under "GFX PATHS".
GFX_PATH_PRESETS = [
    (
        "Vanilla HOI4",
        os.path.join("gfx", "interface", "goals"),
        os.path.join("gfx", "interface", "ideas"),
    ),
    (
        "Millennium Dawn",
        os.path.join("gfx", "interface", "goals"),
        os.path.join("Millennium_Dawn", "gfx", "interface", "ideas"),
    ),
]

# Preview text shown for each loc_token_style setting.
TOKEN_STYLE_PREVIEWS = {
    "colon": "🏳 Soviet Union  ←  [SOV:NameWithFlag] resolved via tag name map",
    "dot": "🏳 SOV  ←  [SOV.GetName] (dot-style)",
    "both": "🏳 Soviet Union  ←  tries [TAG:X] first, then [TAG.X]",
}


def relativize_to_mod_root(path, mod_root):
    """Rewrite an absolute path under mod_root as mod-relative, else leave it alone."""
    if mod_root and path.startswith(mod_root):
        return os.path.relpath(path, mod_root)
    return path


def loc_token_preview_text(style):
    """Preview string for a given loc_token_style setting value."""
    return TOKEN_STYLE_PREVIEWS.get(style, "")


def parse_event_dim_profile(country_w, country_h, news_w, news_h):
    """Parse the four dimension-entry strings into an event_dim_profiles value.

    Raises ValueError if any of the four values isn't an integer.
    """
    cw, ch = int(country_w), int(country_h)
    nw, nh = int(news_w), int(news_h)
    return {"country": (cw, ch), "news": (nw, nh)}


def open_settings(app):
    """Settings panel — GFX paths, MD detection, extra dirs."""
    win = tk.Toplevel(app)
    win.title(tr("settings.title", "Settings"))
    win.configure(bg=BG_DARK)
    win.geometry("600x580")
    win.resizable(True, True)
    win.grab_set()

    tk.Label(
        win,
        text=tr("settings.header", "SETTINGS"),
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 11, "bold"),
        pady=10,
    ).pack(fill="x", padx=14)
    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

    sc = tk.Canvas(win, bg=BG_PANEL, highlightthickness=0)
    sb = tk.Scrollbar(win, orient="vertical", command=sc.yview)
    frm = tk.Frame(sc, bg=BG_PANEL)
    sc.create_window((0, 0), window=frm, anchor="nw")
    sc.configure(yscrollcommand=sb.set)
    frm.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
    sc.bind(
        "<Configure>",
        lambda e: (
            sc.itemconfig(sc.find_withtag("all")[0], width=e.width)
            if sc.find_withtag("all")
            else None
        ),
    )
    sb.pack(side="right", fill="y")
    sc.pack(fill="both", expand=True)

    def _sec(text):
        tk.Frame(frm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(10, 2))
        tk.Label(
            frm,
            text=text,
            bg=BG_PANEL,
            fg=TEXT,
            font=("Helvetica", 9, "bold"),
            anchor="w",
            padx=10,
            pady=3,
        ).pack(fill="x")

    def _lbl(text, fg=TEXT_DIM):
        tk.Label(
            frm,
            text=text,
            bg=BG_PANEL,
            fg=fg,
            font=("Helvetica", 8),
            anchor="w",
            padx=14,
        ).pack(fill="x")

    def _path_row(label, attr):
        row = tk.Frame(frm, bg=BG_PANEL)
        row.pack(fill="x", padx=10, pady=3)
        tk.Label(
            row,
            text=label,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=18,
            anchor="w",
        ).pack(side="left")
        var = tk.StringVar(value=getattr(MOD, attr, ""))
        e = tk.Entry(
            row,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        e.pack(side="left", fill="x", expand=True, ipady=3)

        def _on_change(*a, _attr=attr, _var=var):
            setattr(MOD, _attr, _var.get())
            MOD.save_config()

        var.trace_add("write", _on_change)

        def _browse(v=var):
            start = (
                os.path.join(MOD.root, v.get())
                if MOD.root and os.path.isdir(os.path.join(MOD.root, v.get()))
                else (
                    MOD.root
                    if MOD.root and os.path.isdir(MOD.root)
                    else os.path.expanduser("~")
                )
            )
            d = filedialog.askdirectory(
                title=tr("filedialog.select_folder", "Select folder"),
                initialdir=start,
            )
            if not d:
                return
            v.set(relativize_to_mod_root(d, MOD.root))

        tk.Button(
            row,
            text=tr("common.browse", "Browse"),
            command=_browse,
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 8),
            padx=8,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(side="left", padx=(4, 0))

    _sec(tr("settings.language.section", "LANGUAGE"))
    lang_row = tk.Frame(frm, bg=BG_PANEL)
    lang_row.pack(fill="x", padx=10, pady=4)
    tk.Label(
        lang_row,
        text=tr("settings.language.label", "UI language:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=18,
        anchor="w",
    ).pack(side="left")
    lang_var = tk.StringVar(value=get_language() or "en")
    lang_combo = ttk.Combobox(
        lang_row,
        textvariable=lang_var,
        state="readonly",
        values=list(I18N_LANGS.keys()),
        width=16,
    )
    lang_combo.pack(side="left")
    lang_name = tk.Label(
        lang_row,
        text=I18N_LANGS.get(lang_var.get(), ""),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        padx=8,
    )
    lang_name.pack(side="left")

    def _apply_lang(*_):
        old = get_language()
        new = lang_var.get()
        set_language(new)
        lang_name.config(text=I18N_LANGS.get(new, ""))
        if old != new:
            messagebox.showinfo(
                tr("settings.language.changed.title", "Language Changed"),
                tr(
                    "settings.language.changed.body",
                    "Language saved. Restart the app to refresh all existing UI text.",
                ),
                parent=win,
            )

    lang_combo.bind("<<ComboboxSelected>>", _apply_lang)

    _sec(tr("settings.mod_detection", "MOD DETECTION"))
    md_color = "#a78bfa" if MOD.is_md else TEXT_DIM
    _lbl(
        tr(
            "settings.loaded_mod",
            "  Loaded mod:   {mod}",
            mod=(MOD.mod_name or tr("common.none", "None")),
        ),
        fg=md_color,
    )
    _lbl(
        (
            tr(
                "settings.md_detected_yes",
                "  MD detected:  YES  -  MD categories and effects are visible",
            )
            if MOD.is_md
            else tr(
                "settings.md_detected_no",
                "  MD detected:  NO   -  MD categories hidden",
            )
        ),
        fg=md_color,
    )
    _lbl(
        tr(
            "settings.detection_checks",
            "  Detection checks: folder name, descriptor.mod content.",
        )
    )
    _lbl(tr("settings.override_manually", "  You can also override manually:"))

    ovr_row = tk.Frame(frm, bg=BG_PANEL)
    ovr_row.pack(fill="x", padx=10, pady=6)

    def _force(is_md):
        MOD.is_md = is_md
        app._apply_md_visibility()
        lbl_status.config(
            text=tr(
                "settings.md_overridden",
                "  Overridden:  MD = {state}",
                state=("ON" if is_md else "OFF"),
            ),
            fg="#a78bfa" if is_md else "#4ade80",
        )

    tk.Button(
        ovr_row,
        text=tr("settings.force_md_on", "Force MD ON"),
        command=lambda: _force(True),
        bg="#2d1a4a",
        fg="#a78bfa",
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(side="left", padx=4)
    tk.Button(
        ovr_row,
        text=tr("settings.force_md_off", "Force MD OFF  (Vanilla)"),
        command=lambda: _force(False),
        bg="#1a2c1a",
        fg="#4ade80",
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(side="left", padx=4)
    lbl_status = tk.Label(
        frm,
        text="",
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        anchor="w",
        padx=14,
    )
    lbl_status.pack(fill="x")

    # ── MOD PATH ─────────────────────────────────────────────
    _sec(tr("settings.mod_load_path", "MOD LOAD PATH"))
    _lbl(
        tr(
            "settings.mod_load_path.hint1",
            "  Where the Mod button opens by default.",
        )
    )
    _lbl(
        tr(
            "settings.mod_load_path.hint2",
            "  Leave blank to use the HOI4 mod folder automatically.",
        )
    )

    _default_hoi4 = default_hoi4_mod_dir()
    if not hasattr(MOD, "custom_mod_path"):
        MOD.custom_mod_path = ""

    mp_row = tk.Frame(frm, bg=BG_PANEL)
    mp_row.pack(fill="x", padx=10, pady=3)
    tk.Label(
        mp_row,
        text=tr("settings.mod_folder", "Mod folder:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=14,
        anchor="w",
    ).pack(side="left")
    mp_var = tk.StringVar(value=MOD.custom_mod_path or _default_hoi4)
    mp_ent = tk.Entry(
        mp_row,
        textvariable=mp_var,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Courier", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    mp_ent.pack(side="left", fill="x", expand=True, ipady=3)

    def _on_mp_change(*a):
        MOD.custom_mod_path = mp_var.get()
        MOD.save_config()

    mp_var.trace_add("write", _on_mp_change)

    def _browse_mod_path():
        d = filedialog.askdirectory(
            title=tr(
                "filedialog.select_default_mod_folder", "Select default mod folder"
            ),
            initialdir=(
                mp_var.get() if os.path.isdir(mp_var.get()) else os.path.expanduser("~")
            ),
        )
        if d:
            mp_var.set(d)

    def _reset_mod_path():
        mp_var.set(_default_hoi4)

    mp_btn_row = tk.Frame(frm, bg=BG_PANEL)
    mp_btn_row.pack(fill="x", padx=10, pady=(0, 4))
    tk.Button(
        mp_btn_row,
        text=tr("common.browse", "Browse"),
        command=_browse_mod_path,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left", padx=(0, 4))
    tk.Button(
        mp_btn_row,
        text=tr("settings.reset_hoi4_default", "Reset to HOI4 Default"),
        command=_reset_mod_path,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left")
    _lbl(
        tr(
            "settings.current_hoi4_default",
            "  Current HOI4 default:  {path}",
            path=_default_hoi4,
        )
    )

    # ── GFX PATHS ─────────────────────────────────────────────────
    _sec(tr("settings.gfx_paths", "GFX PATHS  (relative to mod root)"))
    _lbl(
        tr(
            "settings.focus_icon_gfx_hint",
            "  Focus icon GFX  (gfx/interface/goals/):",
        )
    )
    _path_row(tr("settings.goals_path", "Goals path:"), "path_goals")
    _lbl(
        tr(
            "settings.idea_gfx_hint",
            "  Idea / National Spirit GFX  (gfx/interface/ideas/):",
        )
    )
    _path_row(tr("settings.ideas_gfx_path", "Ideas GFX path:"), "path_ideas_gfx")
    _lbl(tr("settings.reload_hint", "  Changes take effect when you reload the mod."))

    # Preset buttons
    pre_row = tk.Frame(frm, bg=BG_PANEL)
    pre_row.pack(fill="x", padx=10, pady=4)
    tk.Label(
        pre_row,
        text=tr("settings.presets", "Presets:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(side="left", padx=(0, 8))

    for pname, pg, pi in GFX_PATH_PRESETS:

        def _apply(g=pg, i=pi):
            MOD.path_goals = g
            MOD.path_ideas_gfx = i
            MOD.save_config()
            messagebox.showinfo(
                tr("dialog.preset_applied.title", "Preset Applied"),
                tr(
                    "dialog.preset_applied.body",
                    "Paths updated.\nReload mod to apply.",
                ),
                parent=win,
            )

        tk.Button(
            pre_row,
            text=pname,
            command=_apply,
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 8),
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=2)

    # ── EVENT PICTURE GFX ────────────────────────────────────────
    _sec(
        tr(
            "settings.event_picture_gfx_path",
            "EVENT PICTURE GFX PATH  (relative to mod root)",
        )
    )
    _lbl(
        tr(
            "settings.event_picture_gfx_hint",
            "  Folder containing .dds event pictures (vanilla: gfx/event_pictures/):",
        )
    )
    _path_row(tr("settings.event_pictures", "Event pictures:"), "path_event_pictures")
    _lbl(
        tr(
            "settings.event_gfx_picker_hint",
            "  Changes take effect immediately in the Event Maker GFX picker.",
        )
    )

    # ── EVENT DIMENSION PROFILES ──────────────────────────────────
    _sec(tr("settings.event_picture_profiles", "EVENT PICTURE DIMENSION PROFILES"))
    _lbl(
        tr(
            "settings.event_picture_profiles.hint1",
            "  Define expected pixel dimensions for each profile.",
        )
    )
    _lbl(
        tr(
            "settings.event_picture_profiles.vanilla_hint",
            "  Vanilla: country_event=210x176 px,  news_event=397x165 px",
        )
    )
    _lbl(
        tr(
            "settings.event_picture_profiles.hint2",
            "  Add mod profiles below so the Event Maker can validate your custom GFX.",
        )
    )

    # Active profile selector
    prof_sel_row = tk.Frame(frm, bg=BG_PANEL)
    prof_sel_row.pack(fill="x", padx=10, pady=4)
    tk.Label(
        prof_sel_row,
        text=tr("settings.active_profile", "Active profile:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=16,
        anchor="w",
    ).pack(side="left")
    _prof_var = tk.StringVar(value=MOD.event_dim_active_profile)
    _prof_cb = ttk.Combobox(
        prof_sel_row,
        textvariable=_prof_var,
        state="readonly",
        width=22,
        font=("Helvetica", 9),
    )
    _prof_cb.pack(side="left", padx=4)

    def _refresh_prof_list():
        names = sorted(MOD.event_dim_profiles.keys())
        _prof_cb["values"] = names
        if _prof_var.get() not in names and names:
            _prof_var.set(names[0])

    def _on_prof_select(evt=None):
        MOD.event_dim_active_profile = _prof_var.get()
        MOD.save_config()
        _refresh_prof_list()
        _refresh_profiles_box()

    _prof_cb.bind("<<ComboboxSelected>>", _on_prof_select)
    _refresh_prof_list()

    # Profiles list
    profiles_box = tk.Frame(frm, bg=BG_PANEL)
    profiles_box.pack(fill="x", padx=10, pady=2)

    def _refresh_profiles_box():
        for w in profiles_box.winfo_children():
            w.destroy()
        for pname, dims in sorted(MOD.event_dim_profiles.items()):
            cw, ch = dims.get("country", (210, 176))
            nw, nh = dims.get("news", (397, 165))
            is_active = pname == MOD.event_dim_active_profile
            row = tk.Frame(
                profiles_box,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground="#4ade80" if is_active else BORDER_G,
            )
            row.pack(fill="x", pady=2)
            badge = "  ✓ ACTIVE  " if is_active else "           "
            tk.Label(
                row,
                text=badge,
                bg=BG_CARD,
                fg="#4ade80" if is_active else TEXT_DIM,
                font=("Helvetica", 8, "bold"),
                width=10,
            ).pack(side="left")
            tk.Label(
                row,
                text=f"{pname}",
                bg=BG_CARD,
                fg=TEXT,
                font=("Helvetica", 9, "bold"),
                width=18,
                anchor="w",
            ).pack(side="left")
            tk.Label(
                row,
                text=f"country={cw}×{ch}  news={nw}×{nh}",
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Courier", 8),
            ).pack(side="left", padx=8)
            if pname != "vanilla":
                tk.Button(
                    row,
                    text="✕",
                    command=lambda p=pname: _delete_profile(p),
                    bg=BG_CARD,
                    fg=RED,
                    relief="flat",
                    font=("Helvetica", 9),
                    cursor="hand2",
                    padx=4,
                ).pack(side="right")

    def _delete_profile(pname):
        if pname == "vanilla":
            return
        MOD.event_dim_profiles.pop(pname, None)
        if MOD.event_dim_active_profile == pname:
            MOD.event_dim_active_profile = "vanilla"
            _prof_var.set("vanilla")
        MOD.save_config()
        _refresh_prof_list()
        _refresh_profiles_box()

    _refresh_profiles_box()

    # Add new profile
    _lbl(tr("settings.add_custom_profile", "  Add custom profile:"))
    new_prof_row = tk.Frame(frm, bg=BG_PANEL)
    new_prof_row.pack(fill="x", padx=10, pady=4)

    np_name = tk.StringVar(value="My Mod")
    np_cw = tk.StringVar(value="420")
    np_ch = tk.StringVar(value="176")
    np_nw = tk.StringVar(value="794")
    np_nh = tk.StringVar(value="330")

    def _lbl_s(parent, text, w=None):
        kw = {"bg": BG_PANEL, "fg": TEXT_DIM, "font": ("Helvetica", 8)}
        if w:
            kw["width"] = w
        tk.Label(parent, text=text, **kw).pack(side="left", padx=2)

    def _ent_s(parent, var, width=6):
        tk.Entry(
            parent,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            font=("Helvetica", 9),
            width=width,
        ).pack(side="left", padx=2)

    _lbl_s(new_prof_row, "Name:")
    _ent_s(new_prof_row, np_name, 14)
    _lbl_s(new_prof_row, "  country:")
    _ent_s(new_prof_row, np_cw, 5)
    _lbl_s(new_prof_row, "×")
    _ent_s(new_prof_row, np_ch, 5)
    _lbl_s(new_prof_row, "  news:")
    _ent_s(new_prof_row, np_nw, 5)
    _lbl_s(new_prof_row, "×")
    _ent_s(new_prof_row, np_nh, 5)

    def _add_profile():
        name = np_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Profile name cannot be empty.", parent=win)
            return
        try:
            profile = parse_event_dim_profile(
                np_cw.get(), np_ch.get(), np_nw.get(), np_nh.get()
            )
        except ValueError:
            messagebox.showerror("Error", "Dimensions must be integers.", parent=win)
            return
        MOD.event_dim_profiles[name] = profile
        MOD.event_dim_active_profile = name
        _prof_var.set(name)
        MOD.save_config()
        _refresh_prof_list()
        _refresh_profiles_box()

    tk.Button(
        frm,
        text=tr("settings.add_profile", "+ Add Profile"),
        command=_add_profile,
        bg=BG_CARD,
        fg="#4ade80",
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(anchor="w", padx=10, pady=(0, 6))

    # ── EXTRA GFX DIRS ────────────────────────────────────────────
    _sec(tr("settings.extra_gfx_dirs", "EXTRA GFX DIRECTORIES  (absolute paths)"))
    _lbl(
        tr(
            "settings.extra_gfx_dirs.hint1",
            "  Scanned in addition to the paths above.",
        )
    )
    _lbl(
        tr(
            "settings.extra_gfx_dirs.hint2",
            "  Useful for pointing at vanilla HOI4 gfx from within a mod.",
        )
    )

    extra_box = tk.Frame(frm, bg=BG_PANEL)
    extra_box.pack(fill="x", padx=10, pady=4)

    def _refresh_extra():
        for w in extra_box.winfo_children():
            w.destroy()
        if not MOD.custom_gfx_dirs:
            tk.Label(
                extra_box,
                text=tr("settings.none_added", "  None added."),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w")
            return
        for i, d in enumerate(list(MOD.custom_gfx_dirs)):
            row = tk.Frame(
                extra_box,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=d,
                bg=BG_CARD,
                fg=TEXT,
                font=("Courier", 8),
                anchor="w",
                padx=6,
            ).pack(side="left", fill="x", expand=True)
            tk.Button(
                row,
                text="X",
                command=lambda idx=i: [
                    MOD.custom_gfx_dirs.pop(idx),
                    MOD.save_config(),
                    _refresh_extra(),
                ],
                bg=BG_CARD,
                fg=RED,
                relief="flat",
                font=("Georgia", 9),
                cursor="hand2",
                padx=4,
            ).pack(side="right")

    _refresh_extra()

    def _add_dir():
        d = filedialog.askdirectory(
            title=tr("filedialog.select_extra_gfx_folder", "Select extra GFX folder")
        )
        if d and d not in MOD.custom_gfx_dirs:
            MOD.custom_gfx_dirs.append(d)
            MOD.save_config()
            _refresh_extra()

    tk.Button(
        frm,
        text=tr("settings.add_extra_gfx_folder", "+ Add Extra GFX Folder"),
        command=_add_dir,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(anchor="w", padx=10, pady=4)

    # ── LOGS ──────────────────────────────────────────────────────
    _sec(tr("settings.session_log", "SESSION LOG"))
    _lbl(
        tr(
            "settings.session_log.hint",
            "  All errors and warnings captured during this session.",
        )
    )

    log_box_frame = tk.Frame(
        frm, bg="#0a0f18", highlightthickness=1, highlightbackground=BORDER_G
    )
    log_box_frame.pack(fill="x", padx=10, pady=4)

    log_sb = tk.Scrollbar(log_box_frame, orient="vertical")
    log_txt = tk.Text(
        log_box_frame,
        bg="#0a0f18",
        fg="#c9d1d9",
        font=("Courier", 8),
        relief="flat",
        wrap="none",
        height=10,
        state="disabled",
        yscrollcommand=log_sb.set,
        selectbackground="#1e3a6e",
    )
    log_sb.config(command=log_txt.yview)
    log_sb.pack(side="right", fill="y")
    log_txt.pack(fill="x", expand=True)

    log_txt.tag_configure("ts", foreground="#374151")
    log_txt.tag_configure("err", foreground="#f87171")
    log_txt.tag_configure("ok", foreground="#4ade80")
    log_txt.tag_configure("sep", foreground="#21262d")
    log_txt.tag_configure("tb", foreground="#c9d1d9")

    def _refresh_log():
        log_txt.config(state="normal")
        log_txt.delete("1.0", "end")
        entries = app._error_entries
        if not entries:
            log_txt.insert(
                "end",
                tr(
                    "settings.no_errors_recorded",
                    "  No errors recorded - running clean.\n",
                ),
                "ok",
            )
        else:
            for ts, msg in entries:
                log_txt.insert("end", "[%s]  " % ts, "ts")
                lines = msg.splitlines()
                log_txt.insert("end", lines[0] + "\n", "err")
                for line in lines[1:]:
                    log_txt.insert("end", line + "\n", "tb")
                log_txt.insert("end", "─" * 72 + "\n", "sep")
        log_txt.config(state="disabled")
        log_txt.see("end")

    _refresh_log()

    log_btn_row = tk.Frame(frm, bg=BG_PANEL)
    log_btn_row.pack(fill="x", padx=10, pady=(0, 6))

    tk.Button(
        log_btn_row,
        text=tr("common.refresh", "Refresh"),
        command=_refresh_log,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left", padx=(0, 4))
    tk.Button(
        log_btn_row,
        text=tr("settings.open_full_log", "Open Full Log Window"),
        command=app._show_error_log,
        bg=BG_CARD,
        fg=TEXT,
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left", padx=(0, 4))

    def _clear_log():
        app._error_entries.clear()
        if hasattr(app, "_errlog_btn"):
            app._errlog_btn.config(
                text=tr("menu.error_log", "Log"), fg="#6e7681", bg="#161b22"
            )
        _refresh_log()

    tk.Button(
        log_btn_row,
        text=tr("common.clear", "Clear"),
        command=_clear_log,
        bg="#450a0a",
        fg="#f87171",
        relief="flat",
        font=("Helvetica", 9),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left")

    # ── COUNTRY TAG NAMES ─────────────────────────────────────────
    _sec(
        tr(
            "settings.country_tag_names",
            "COUNTRY TAG NAMES  (for Decision Maker preview)",
        )
    )
    _lbl(
        tr(
            "settings.country_tag_names.hint1",
            "  Map TAG codes to display names shown in the preview.",
        )
    )
    _lbl(
        tr(
            "settings.country_tag_names.hint2",
            "  e.g.  SOV -> Soviet Union,  ERI -> Eritrea,  GER -> Germany",
        )
    )

    tag_table = tk.Frame(frm, bg=BG_PANEL)
    tag_table.pack(fill="x", padx=10, pady=4)

    def _refresh_tag_table():
        for w in tag_table.winfo_children():
            w.destroy()
        tags = dict(MOD.country_tag_names)
        if not tags:
            tk.Label(
                tag_table,
                text=tr(
                    "settings.no_tag_mappings",
                    "  No tag mappings defined. Add below or load vanilla defaults.",
                ),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(anchor="w")
        else:
            hdr = tk.Frame(tag_table, bg=BG_DARK)
            hdr.pack(fill="x", pady=(0, 2))
            for txt, w in [
                ("TAG", 6),
                ("->", 3),
                (tr("settings.display_name", "Display Name"), 22),
                ("", 4),
            ]:
                tk.Label(
                    hdr,
                    text=txt,
                    bg=BG_DARK,
                    fg=TEXT_DIM,
                    font=("Courier", 8, "bold"),
                    width=w,
                    anchor="w",
                ).pack(side="left", padx=2)
            for tag in sorted(tags.keys()):
                name = tags[tag]
                row = tk.Frame(
                    tag_table,
                    bg=BG_CARD,
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                )
                row.pack(fill="x", pady=1)
                # Editable tag
                tv = tk.StringVar(value=tag)
                nv = tk.StringVar(value=name)
                te = tk.Entry(
                    row,
                    textvariable=tv,
                    bg=BG_CARD,
                    fg=GOLD,
                    insertbackground=GOLD,
                    font=("Courier", 9, "bold"),
                    relief="flat",
                    width=6,
                    highlightthickness=0,
                )
                te.pack(side="left", padx=(4, 2), ipady=2)
                tk.Label(
                    row, text="→", bg=BG_CARD, fg=TEXT_DIM, font=("Helvetica", 9)
                ).pack(side="left")
                ne = tk.Entry(
                    row,
                    textvariable=nv,
                    bg=BG_CARD,
                    fg=TEXT,
                    insertbackground=TEXT,
                    font=("Helvetica", 9),
                    relief="flat",
                    width=24,
                    highlightthickness=0,
                )
                ne.pack(side="left", padx=(2, 4), fill="x", expand=True, ipady=2)

                def _save_row(old_tag=tag, tv=tv, nv=nv):
                    new_tag = tv.get().strip().upper()
                    new_name = nv.get().strip()
                    if not new_tag:
                        return
                    # Remove old key, add updated
                    MOD.country_tag_names.pop(old_tag, None)
                    if new_name:
                        MOD.country_tag_names[new_tag] = new_name
                    MOD.save_config()

                te.bind("<FocusOut>", lambda e, f=_save_row: f())
                ne.bind("<FocusOut>", lambda e, f=_save_row: f())
                te.bind("<Return>", lambda e, f=_save_row: f())
                ne.bind("<Return>", lambda e, f=_save_row: f())
                tk.Button(
                    row,
                    text="✕",
                    command=lambda t=tag: [
                        MOD.country_tag_names.pop(t, None),
                        MOD.save_config(),
                        _refresh_tag_table(),
                    ],
                    bg=BG_CARD,
                    fg=RED,
                    relief="flat",
                    font=("Helvetica", 9),
                    cursor="hand2",
                    padx=4,
                ).pack(side="right")

    _refresh_tag_table()

    # Add new tag row
    add_tag_row = tk.Frame(frm, bg=BG_PANEL)
    add_tag_row.pack(fill="x", padx=10, pady=4)
    new_tag_v = tk.StringVar()
    new_name_v = tk.StringVar()
    tk.Label(
        add_tag_row,
        text=tr("settings.tag", "TAG:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    ).pack(side="left")
    tk.Entry(
        add_tag_row,
        textvariable=new_tag_v,
        bg=BG_CARD,
        fg=GOLD,
        insertbackground=GOLD,
        font=("Courier", 9, "bold"),
        relief="flat",
        width=7,
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", padx=(2, 8), ipady=3)
    tk.Label(
        add_tag_row,
        text=tr("settings.name", "Name:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    ).pack(side="left")
    tk.Entry(
        add_tag_row,
        textvariable=new_name_v,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=TEXT,
        font=("Helvetica", 9),
        relief="flat",
        width=22,
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(side="left", padx=(2, 8), ipady=3)

    def _add_tag_entry():
        t = new_tag_v.get().strip().upper()
        n = new_name_v.get().strip()
        if not t or not n:
            messagebox.showwarning(
                tr("dialog.missing_data.title", "Missing data"),
                tr("dialog.tag_name_required", "Both TAG and Name are required."),
                parent=win,
            )
            return
        MOD.country_tag_names[t] = n
        MOD.save_config()
        new_tag_v.set("")
        new_name_v.set("")
        _refresh_tag_table()

    tk.Button(
        add_tag_row,
        text=tr("common.add", "+ Add"),
        command=_add_tag_entry,
        bg=BG_CARD,
        fg=GREEN,
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=10,
        pady=3,
        cursor="hand2",
    ).pack(side="left", padx=(0, 6))

    # Quick-fill vanilla button
    def _fill_vanilla():
        count = 0
        for t, n in VANILLA_COUNTRY_TAGS.items():
            if t not in MOD.country_tag_names:
                MOD.country_tag_names[t] = n
                count += 1
        MOD.save_config()
        _refresh_tag_table()
        messagebox.showinfo(
            tr("dialog.vanilla_tags.title", "Vanilla Tags"),
            tr(
                "dialog.vanilla_tags.body",
                "Added {count} vanilla TAG mappings.",
                count=count,
            ),
            parent=win,
        )

    tk.Button(
        frm,
        text=tr("settings.load_vanilla_tags", "Load Vanilla HOI4 Tags"),
        command=_fill_vanilla,
        bg="#1a2c1a",
        fg="#4ade80",
        relief="flat",
        font=("Helvetica", 9, "bold"),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(anchor="w", padx=10, pady=(0, 4))
    tk.Button(
        frm,
        text=tr("settings.clear_all_tags", "Clear All Tags"),
        command=lambda: [
            MOD.country_tag_names.clear(),
            MOD.save_config(),
            _refresh_tag_table(),
        ],
        bg="#2d0a0a",
        fg=RED,
        relief="flat",
        font=("Helvetica", 9),
        padx=12,
        pady=4,
        cursor="hand2",
    ).pack(anchor="w", padx=10, pady=(0, 8))

    # ── LOC TOKEN STYLE ────────────────────────────────────────────
    _sec(
        tr(
            "settings.loc_token_style",
            "LOCALISATION TOKEN STYLE  (Decision Maker preview)",
        )
    )
    _lbl(
        tr(
            "settings.loc_token_style.hint1",
            "  Tells the preview how to parse scripted loc tokens in decision names.",
        )
    )
    _lbl(
        tr(
            "settings.loc_token_style.hint2",
            "  Colon-style  [SOV:NameWithFlag]  - used by most vanilla decisions.",
        )
    )
    _lbl(
        tr(
            "settings.loc_token_style.hint3",
            "  Dot-style    [SOV.GetName]        - used by some mods.",
        )
    )

    tok_row = tk.Frame(frm, bg=BG_PANEL)
    tok_row.pack(fill="x", padx=10, pady=6)
    _tok_var = tk.StringVar(value=getattr(MOD, "loc_token_style", "colon"))

    def _on_tok_change(*_):
        MOD.loc_token_style = _tok_var.get()
        MOD.save_config()

    for val, label, hint in [
        (
            "colon",
            tr("settings.loc_token_style.colon", "Colon-style   [TAG:NameWithFlag]"),
            tr(
                "settings.loc_token_style.colon_hint",
                "Standard HOI4 vanilla format",
            ),
        ),
        (
            "dot",
            tr("settings.loc_token_style.dot", "Dot-style     [TAG.GetName]"),
            tr(
                "settings.loc_token_style.dot_hint",
                "Some modded/scripted loc format",
            ),
        ),
        (
            "both",
            tr("settings.loc_token_style.both", "Both styles"),
            tr(
                "settings.loc_token_style.both_hint",
                "Try colon first, fall back to dot",
            ),
        ),
    ]:
        rb_row = tk.Frame(tok_row, bg=BG_PANEL)
        rb_row.pack(anchor="w", pady=1)
        tk.Radiobutton(
            rb_row,
            variable=_tok_var,
            value=val,
            text=label,
            bg=BG_PANEL,
            fg=TEXT,
            selectcolor=BG_CARD,
            activebackground=BG_PANEL,
            font=("Courier", 9),
            cursor="hand2",
            command=_on_tok_change,
        ).pack(side="left")
        tk.Label(
            rb_row,
            text=f"  — {hint}",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
        ).pack(side="left")

    # Live preview
    tok_prev = tk.Frame(
        frm, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_G
    )
    tok_prev.pack(fill="x", padx=10, pady=(0, 8))
    tk.Label(
        tok_prev,
        text=tr("settings.preview_token_parsing", "  Preview token parsing:"),
        bg=BG_CARD,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(anchor="w", padx=6, pady=(4, 0))
    tok_prev_lbl = tk.Label(
        tok_prev,
        text="",
        bg=BG_CARD,
        fg="#7ec8e3",
        font=("Courier", 9),
        anchor="w",
        padx=12,
        pady=4,
    )
    tok_prev_lbl.pack(fill="x")

    def _update_tok_preview(*_):
        tok_prev_lbl.config(text="  " + loc_token_preview_text(_tok_var.get()))

    _tok_var.trace_add("write", _update_tok_preview)
    _update_tok_preview()

    # ── BOTTOM BAR ────────────────────────────────────────────────
    tk.Frame(frm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(12, 2))
    tk.Label(
        frm,
        text=tr("settings.saved_to", "  Settings saved to:  {path}", path=CONFIG_PATH),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 7, "italic"),
        anchor="w",
        padx=10,
        pady=4,
    ).pack(fill="x")
    tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")
    bot_bar = tk.Frame(win, bg=BG_DARK)
    bot_bar.pack(fill="x")
    tk.Button(
        bot_bar,
        text=tr("settings.save_and_close", "Save & Close"),
        command=lambda: [MOD.save_config(), win.destroy()],
        bg="#14532d",
        fg="#4ade80",
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=16,
        pady=6,
        cursor="hand2",
    ).pack(side="right", padx=12, pady=6)
    tk.Button(
        bot_bar,
        text=tr("common.close", "Close"),
        command=win.destroy,
        bg=BG_CARD,
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 10),
        padx=16,
        pady=6,
        cursor="hand2",
    ).pack(side="right", padx=4, pady=6)
