"""Module-level state shared between the wizard modules.

These were module-level globals in the monolith's tk-handling block.
Pulling them into one module keeps the wizard code free of cross-wizard
coupling and gives the App a single place to clear caches on mod reload.
"""

import re
import tkinter as tk

from hoi4cm.core import EFFECT_CATS, EFFECT_DEFS, effects_in_cat, tr
from hoi4cm.mod import notifying_workspace_files
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    GREEN,
    ORANGE,
    SEL_BG,
    TEXT,
    TEXT_DIM,
)

# ``notifying_workspace_files`` is imported from ``hoi4cm.mod`` here and
# re-exported for wizard convenience.


# ── Shared widget-read helpers ────────────────────────────────────
# Small ``.get()`` adapters used by the ``collect_*_state`` helpers so
# the seam between Tk widgets and the ``_generators`` stays DRY and
# testable.  Each accepts duck-typed fakes in tests (``hasattr(.get)``)
# and real ``tk.StringVar``/``tk.Text`` in the dialogs.


def svar_get(var, default=""):
    """Return ``var.get()`` coerced to ``str``, or ``default`` if missing/broken."""
    if var is None or not hasattr(var, "get"):
        return default
    try:
        val = var.get()
        return val if isinstance(val, str) else str(val)
    except Exception:
        return default


def text_get(widget, default=""):
    """Return ``widget.get("1.0", "end")`` stripped, with ``StringVar`` fallback."""
    if widget is None or not hasattr(widget, "get"):
        return default
    try:
        val = widget.get("1.0", "end")
    except TypeError:
        try:
            val = widget.get()
        except Exception:
            return default
    except Exception:
        return default
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


# ── Image cache registry ──────────────────────────────────────────
# Wizards register their own caches here so the App can invalidate
# everything on mod reload without poking into each module.
_app_img_caches = []


# ── Per-wizard caches (event wizard) ───────────────────────────────
_ev_gfx_cache: dict = {}  # gfx_name -> file path
_ev_imgsize_cache: dict = {}  # file path -> (w, h)
_app_img_caches.extend([_ev_gfx_cache, _ev_imgsize_cache])


# ── Pre-compiled regex used by the additional-income wizard ────────
# Pulls the localisation-key token out of a quoted HOI4 string.
_LOC_KEY_RE = re.compile(r'\s+(\S+?)(?::\d+)?\s*"')


# ── Effect picker popup (event + decision wizards) ─────────────────
def open_effect_picker(parent, target_text, on_insert=None):
    """Popup effect selector shared by the event and decision wizards.

    Inserts rendered HOI4 code into ``target_text`` (a ``tk.Text`` widget).
    ``on_insert``, if given, is called after a snippet is inserted (the
    event wizard uses it to refresh its live preview). Returns the popup
    ``Toplevel`` (tests drive it from there; wizard call sites ignore it).
    """
    pwin = tk.Toplevel(parent)
    pwin.title(tr("effect_picker.title", "Effect Picker"))
    pwin.configure(bg=BG_DARK)
    pwin.geometry("620x580")
    pwin.resizable(True, True)
    pwin.grab_set()

    # ── header ────────────────────────────────────────────────────
    hdr = tk.Frame(pwin, bg=BG_DARK)
    hdr.pack(fill="x", padx=10, pady=(8, 0))
    tk.Label(hdr, text="🔍", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 11)).pack(
        side="left", padx=(0, 4)
    )
    _search_ph = tr("focus.effects.search_placeholder", "Search effects...")
    eff_search_var = tk.StringVar(value=_search_ph)
    eff_search_ent = tk.Entry(
        hdr,
        textvariable=eff_search_var,
        bg=BG_CARD,
        fg=TEXT_DIM,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    eff_search_ent.pack(fill="x", expand=True, ipady=4)

    def _ph_in(e):
        if eff_search_var.get() == _search_ph:
            eff_search_var.set("")
            eff_search_ent.config(fg=TEXT)

    def _ph_out(e):
        if not eff_search_var.get():
            eff_search_var.set(_search_ph)
            eff_search_ent.config(fg=TEXT_DIM)

    eff_search_ent.bind("<FocusIn>", _ph_in)
    eff_search_ent.bind("<FocusOut>", _ph_out)

    # ── category + effect dropdown ─────────────────────────────────
    cat_row = tk.Frame(pwin, bg=BG_DARK)
    cat_row.pack(fill="x", padx=10, pady=(4, 0))
    tk.Label(
        cat_row,
        text=tr("common.category", "Category:"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
    ).pack(side="left")
    eff_cat = tk.StringVar(value=EFFECT_CATS[0])
    cat_menu = tk.OptionMenu(
        cat_row, eff_cat, *EFFECT_CATS, command=lambda _: _rebuild_dd()
    )
    cat_menu.config(
        bg=BG_CARD,
        fg=TEXT,
        activebackground=BORDER_G,
        font=("Helvetica", 9),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        width=12,
        anchor="w",
    )
    cat_menu["menu"].config(
        bg=BG_CARD, fg=TEXT, activebackground=BORDER_G, font=("Helvetica", 9)
    )
    cat_menu.pack(side="left", padx=4)

    eff_type = tk.StringVar()
    dd_frame = tk.Frame(cat_row, bg=BG_DARK)
    dd_frame.pack(side="left", fill="x", expand=True)

    def _rebuild_dd(items=None):
        for w in dd_frame.winfo_children():
            w.destroy()
        if items is None:
            items = effects_in_cat(eff_cat.get())
        if not items:
            return
        eff_type.set(items[0][0])
        om = tk.OptionMenu(dd_frame, eff_type, *[k for k, _ in items])
        menu = om["menu"]
        menu.delete(0, "end")
        for k, lbl in items:
            menu.add_command(
                label=f"{k}  —  {lbl}",
                command=lambda v=k: [eff_type.set(v), _refresh_fields()],
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
        _refresh_fields()

    def _filter_dd(*_):
        raw = eff_search_var.get()
        if raw == _search_ph or not raw.strip():
            _rebuild_dd()
            return
        q = raw.strip().lower()
        matches = [
            (k, v["label"])
            for k, v in EFFECT_DEFS.items()
            if q in k.lower()
            or q in v["label"].lower()
            or q in v.get("cat", "").lower()
        ]
        for w in dd_frame.winfo_children():
            w.destroy()
        if not matches:
            tk.Label(
                dd_frame,
                text=tr("focus.effects.none_found", "No effects found"),
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
            ).pack(anchor="w")
            return
        eff_type.set(matches[0][0])
        om = tk.OptionMenu(dd_frame, eff_type, *[k for k, _ in matches])
        menu = om["menu"]
        menu.delete(0, "end")
        for k, lbl in matches:
            cat = EFFECT_DEFS[k].get("cat", "")
            menu.add_command(
                label=f"[{cat}]  {k}  —  {lbl}",
                command=lambda v=k: [eff_type.set(v), _refresh_fields()],
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
            width=34,
        )
        om["menu"].config(
            bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 9)
        )
        om.pack(fill="x", expand=True)
        _refresh_fields()

    eff_search_var.trace_add("write", _filter_dd)
    eff_type.trace_add("write", lambda *_: _refresh_fields())

    # ── fields panel ───────────────────────────────────────────────
    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(6, 0))

    fields_outer = tk.Frame(pwin, bg=BG_PANEL)
    fields_outer.pack(fill="both", expand=True, padx=8, pady=4)

    fields_cv = tk.Canvas(fields_outer, bg=BG_PANEL, highlightthickness=0)
    fields_sb = tk.Scrollbar(fields_outer, orient="vertical", command=fields_cv.yview)
    fields_frm = tk.Frame(fields_cv, bg=BG_PANEL)
    fields_win = fields_cv.create_window((0, 0), window=fields_frm, anchor="nw")
    fields_cv.configure(yscrollcommand=fields_sb.set)
    fields_frm.bind(
        "<Configure>",
        lambda e: fields_cv.configure(scrollregion=fields_cv.bbox("all")),
    )
    fields_cv.bind(
        "<Configure>", lambda e: fields_cv.itemconfig(fields_win, width=e.width)
    )

    def _on_mousewheel(event):
        try:
            fields_cv.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    fields_cv.bind("<MouseWheel>", _on_mousewheel)
    fields_cv.pack(side="left", fill="both", expand=True)
    fields_sb.pack(side="right", fill="y")

    # live field value store: {field_name: StringVar or Text ref}
    _fvars = {}

    def _refresh_fields(*_):
        for w in fields_frm.winfo_children():
            w.destroy()
        _fvars.clear()
        key = eff_type.get()
        defn = EFFECT_DEFS.get(key, {})
        if not defn:
            tk.Label(
                fields_frm,
                text=tr(
                    "effect_picker.unknown_effect",
                    "  Unknown effect: {effect}\n  Will be inserted as raw snippet.",
                    effect=repr(key),
                ),
                bg=BG_PANEL,
                fg=ORANGE,
                font=("Helvetica", 9, "italic"),
                justify="left",
            ).pack(anchor="w", padx=8, pady=8)
            return

        tk.Label(
            fields_frm,
            text=f"  [{defn.get('cat', '')}]  {defn.get('label', key)}",
            bg=BG_PANEL,
            fg=TEXT,
            font=("Helvetica", 10, "bold"),
            anchor="w",
        ).pack(fill="x", padx=8, pady=(8, 2))
        tk.Frame(fields_frm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(0, 6))

        for fname, wtype, default, hint in defn.get("fields", []):
            row = tk.Frame(fields_frm, bg=BG_PANEL)
            row.pack(fill="x", padx=8, pady=3)
            tk.Label(
                row,
                text=f"{fname}:",
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=14,
                anchor="w",
            ).pack(side="left")

            if wtype == "multiline":
                t = tk.Text(
                    row,
                    bg=BG_CARD,
                    fg=TEXT,
                    insertbackground=BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    height=4,
                    wrap="none",
                )
                t.insert("1.0", default)
                t.pack(side="left", fill="x", expand=True, ipady=2)
                _fvars[fname] = ("text", t)

            elif wtype.startswith("dropdown:"):
                opts = wtype.split(":")[1].split(",")
                sv = tk.StringVar(value=default if default in opts else opts[0])
                om = tk.OptionMenu(row, sv, *opts)
                om.config(
                    bg=BG_CARD,
                    fg=TEXT,
                    activebackground=BORDER_G,
                    font=("Helvetica", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    anchor="w",
                )
                om["menu"].config(
                    bg=BG_CARD,
                    fg=TEXT,
                    activebackground=BORDER_G,
                    font=("Helvetica", 9),
                )
                om.pack(side="left", padx=2, fill="x", expand=True)
                _fvars[fname] = ("var", sv)

            else:
                sv = tk.StringVar(value=default)
                tk.Entry(
                    row,
                    textvariable=sv,
                    bg=BG_CARD,
                    fg=TEXT,
                    insertbackground=BLUE,
                    font=("Helvetica", 10),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                ).pack(side="left", fill="x", expand=True, ipady=3, padx=2)
                _fvars[fname] = ("var", sv)

            if hint:
                tk.Label(
                    row,
                    text=f"  {hint}",
                    bg=BG_PANEL,
                    fg=TEXT_DIM,
                    font=("Helvetica", 7, "italic"),
                    anchor="w",
                ).pack(side="left", padx=(4, 0))

    # ── render HOI4 snippet ────────────────────────────────────────
    def _render_snippet():
        key = eff_type.get().strip()
        defn = EFFECT_DEFS.get(key, {})
        if not defn:
            return f"\t{key} = yes\n"
        fields = defn.get("fields", [])
        if len(fields) == 1:
            fname, wtype, _, _ = fields[0]
            kind, ref = _fvars.get(fname, ("var", tk.StringVar()))
            val = (
                ref.get("1.0", "end-1c").strip()
                if kind == "text"
                else ref.get().strip()
            )
            return f"\t{key} = {val}\n"
        else:
            lines = [f"\t{key} = {{"]
            for fname, _wtype, _, _ in fields:
                kind, ref = _fvars.get(fname, ("var", tk.StringVar()))
                val = (
                    ref.get("1.0", "end-1c").strip()
                    if kind == "text"
                    else ref.get().strip()
                )
                lines.append(f"\t\t{fname} = {val}")
            lines.append("\t}")
            return "\n".join(lines) + "\n"

    # ── live preview ───────────────────────────────────────────────
    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8)
    prev_frame = tk.Frame(pwin, bg=BG_DARK)
    prev_frame.pack(fill="x", padx=8, pady=(4, 0))
    tk.Label(
        prev_frame,
        text=tr("effect_picker.preview", "  Preview:"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
    ).pack(anchor="w")
    prev_lbl = tk.Label(
        prev_frame,
        text="",
        bg=BG_DARK,
        fg=GREEN,
        font=("Courier", 9),
        anchor="w",
        justify="left",
        padx=8,
        pady=2,
    )
    prev_lbl.pack(fill="x")

    def _update_preview(*_):
        try:
            prev_lbl.config(text=_render_snippet())
        except Exception:
            pass

    # rebind all field changes to also update preview — wire after a small delay
    def _wire_preview_traces():
        for _fname, (kind, ref) in _fvars.items():
            if kind == "var":
                ref.trace_add("write", _update_preview)
            else:
                ref.bind("<KeyRelease>", _update_preview)
        _update_preview()

    pwin.after(50, _wire_preview_traces)

    # ── bottom bar ─────────────────────────────────────────────────
    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(4, 0))
    bot = tk.Frame(pwin, bg=BG_DARK)
    bot.pack(fill="x", padx=10, pady=6)

    tk.Button(
        bot,
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

    def _insert_effect():
        snippet = _render_snippet()
        target_text.insert("end", snippet)
        if on_insert is not None:
            on_insert()
        pwin.destroy()

    tk.Button(
        bot,
        text=tr("effect_picker.insert_effect", "+ Insert Effect"),
        command=_insert_effect,
        bg="#14532d",
        fg=GREEN,
        relief="flat",
        font=("Helvetica", 10, "bold"),
        padx=14,
        pady=5,
        cursor="hand2",
    ).pack(side="right")

    tk.Label(
        bot,
        text=tr("effect_picker.insert_hint", "Inserts snippet at end of effects box"),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
    ).pack(side="left", padx=4)

    # ── init ───────────────────────────────────────────────────────
    _rebuild_dd()
    return pwin


__all__ = [
    "_app_img_caches",
    "_ev_gfx_cache",
    "_ev_imgsize_cache",
    "_LOC_KEY_RE",
    "notifying_workspace_files",
    "open_effect_picker",
    "svar_get",
    "text_get",
]
