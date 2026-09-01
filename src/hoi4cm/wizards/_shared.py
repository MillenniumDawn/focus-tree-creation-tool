"""Module-level state shared between the wizard modules.

These were module-level globals in the monolith's tk-handling block.
Pulling them into one module keeps the wizard code free of cross-wizard
coupling and gives the App a single place to clear caches on mod reload.
"""

import re
import tkinter as tk

from hoi4cm.core import (
    EFFECT_CATS,
    EFFECT_DEFS,
    TRIGGER_CATS,
    TRIGGER_DEFS,
    tr,
)
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


def render_script_snippet(key, definition, values, *, is_trigger=False):
    """Render a catalogue entry from its field values without Tk widgets."""
    if not definition:
        return f"\t{key} = yes\n"
    fields = definition.get("fields", [])
    if is_trigger and not fields:
        return f"\t{key} = yes\n"

    if is_trigger and len(fields) == 1 and not definition.get("_block"):
        value = values.get(fields[0][0], "").strip()
        if value.startswith(("<", ">", "=")):
            return f"\t{key} {value}\n"

    if definition.get("_block") or len(fields) != 1:
        lines = [f"\t{key} = {{"]
        if definition.get("_block") and len(fields) == 1:
            content = values.get(fields[0][0], "").strip()
            lines.extend(f"\t\t{line}" for line in content.splitlines())
        else:
            for fname, _wtype, _default, _hint in fields:
                value = values.get(fname, "").strip()
                operator = (
                    " " if is_trigger and value.startswith(("<", ">", "=")) else " = "
                )
                lines.append(f"\t\t{fname}{operator}{value}")
        lines.append("\t}")
        return "\n".join(lines) + "\n"
    return f"\t{key} = {values.get(fields[0][0], '').strip()}\n"


# ── Script picker popups (event, decision and condition wizards) ────────────
def open_script_picker(
    parent,
    target_text,
    definitions,
    categories,
    *,
    picker_name="Effect",
    on_insert=None,
):
    """Open a catalogue picker that inserts a script snippet into a Text.

    The browser and field form are shared by effects and triggers. Keeping the
    target widget as an explicit argument means each button inserts only into
    the field that opened it, without replacing existing text.
    """
    pwin = tk.Toplevel(parent)
    picker_key = picker_name.lower()
    pwin.title(tr(f"{picker_key}_picker.title", f"{picker_name} Picker"))
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
    search_key = (
        "focus.effects.search_placeholder"
        if picker_key == "effect"
        else f"{picker_key}_picker.search_placeholder"
    )
    _search_ph = tr(search_key, f"Search {picker_name.lower()}s...")
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
    eff_cat = tk.StringVar(value=categories[0])
    cat_menu = tk.OptionMenu(
        cat_row, eff_cat, *categories, command=lambda _: _rebuild_dd()
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
            items = [
                (key, definition["label"])
                for key, definition in definitions.items()
                if definition.get("cat") == eff_cat.get()
            ]
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
            for k, v in definitions.items()
            if q in k.lower()
            or q in v["label"].lower()
            or q in v.get("cat", "").lower()
        ]
        for w in dd_frame.winfo_children():
            w.destroy()
        if not matches:
            none_key = (
                "focus.effects.none_found"
                if picker_key == "effect"
                else f"{picker_key}_picker.none_found"
            )
            tk.Label(
                dd_frame,
                text=tr(none_key, f"No {picker_name.lower()}s found"),
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
            cat = definitions[k].get("cat", "")
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
        except tk.TclError:
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
        defn = definitions.get(key, {})
        if not defn:
            if picker_key == "effect":
                unknown_text = tr(
                    "effect_picker.unknown_effect",
                    "\n".join(
                        (
                            "  Unknown effect: {effect}",
                            "  Will be inserted as raw snippet.",
                        )
                    ),
                    effect=repr(key),
                )
            else:
                unknown_text = tr(
                    "trigger_picker.unknown_trigger",
                    "\n".join(
                        (
                            "  Unknown trigger: {trigger}",
                            "  Will be inserted as raw snippet.",
                        )
                    ),
                    trigger=repr(key),
                )
            tk.Label(
                fields_frm,
                text=unknown_text,
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
        defn = definitions.get(key, {})
        values = {}
        for fname in (field[0] for field in defn.get("fields", [])):
            kind, ref = _fvars.get(fname, ("var", tk.StringVar()))
            values[fname] = (
                ref.get("1.0", "end-1c").strip()
                if kind == "text"
                else ref.get().strip()
            )
        return render_script_snippet(
            key, defn, values, is_trigger=picker_key == "trigger"
        )

    # ── live preview ───────────────────────────────────────────────
    tk.Frame(pwin, bg=BORDER_G, height=1).pack(fill="x", padx=8)
    prev_frame = tk.Frame(pwin, bg=BG_DARK)
    prev_frame.pack(fill="x", padx=8, pady=(4, 0))
    tk.Label(
        prev_frame,
        text=tr(f"{picker_key}_picker.preview", "  Preview:"),
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
        except tk.TclError:
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
        text=tr(
            (
                "effect_picker.insert_effect"
                if picker_key == "effect"
                else f"{picker_key}_picker.insert_item"
            ),
            f"+ Insert {picker_name}",
        ),
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
        text=tr(
            (
                "effect_picker.insert_hint"
                if picker_key == "effect"
                else f"{picker_key}_picker.insert_hint"
            ),
            f"Inserts snippet at end of {picker_name.lower()}s box",
        ),
        bg=BG_DARK,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "italic"),
    ).pack(side="left", padx=4)

    # ── init ───────────────────────────────────────────────────────
    _rebuild_dd()
    return pwin


def open_effect_picker(parent, target_text, on_insert=None):
    """Open the shared effect picker."""
    return open_script_picker(
        parent,
        target_text,
        EFFECT_DEFS,
        EFFECT_CATS,
        picker_name="Effect",
        on_insert=on_insert,
    )


def open_trigger_picker(parent, target_text, on_insert=None):
    """Open the shared trigger picker for a condition Text widget."""
    return open_script_picker(
        parent,
        target_text,
        TRIGGER_DEFS,
        TRIGGER_CATS,
        picker_name="Trigger",
        on_insert=on_insert,
    )


__all__ = [
    "_app_img_caches",
    "_ev_gfx_cache",
    "_ev_imgsize_cache",
    "_LOC_KEY_RE",
    "notifying_workspace_files",
    "open_effect_picker",
    "open_script_picker",
    "open_trigger_picker",
    "render_script_snippet",
    "svar_get",
    "text_get",
]
