"""Effects panel: the sidebar Effects tab, the effect browser popup and the
per-effect parameter form.

Extracted from the monolith as a mixin so the methods keep operating on ``App``
state via ``self``. Behaviour is identical. Note: ``_apply_md_visibility`` (in
the monolith) mutates ``EFFECT_CATS`` in place, so the browser here — which
imports the same shared list — always sees the current Millennium Dawn set.
"""

import json
import tkinter as tk
from typing import TYPE_CHECKING

from hoi4cm.core import EFFECT_CATS, EFFECT_DEFS, tr
from hoi4cm.mod import MOD
from hoi4cm.script.effects import render_effect
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BG_PANEL,
    BLUE,
    BORDER,
    BORDER_G,
    ORANGE,
    RED,
    SEL_BG,
    TEXT,
    TEXT_DIM,
)


def _augment_character_suggestions(suggestions, fname, *, loaded, character_ids):
    if not loaded or fname not in ("character", "advisor"):
        return suggestions
    return sorted(set(suggestions).union(character_ids))


def _augment_scripted_suggestions(
    suggestions,
    fname,
    *,
    loaded,
    scripted_effect_ids,
    scripted_trigger_ids,
    on_action_ids,
):
    if not loaded:
        return suggestions
    if fname in ("effect", "scripted_effect", "effect_name"):
        return sorted(set(suggestions).union(scripted_effect_ids))
    if fname in ("limit", "trigger", "scripted_trigger", "trigger_name"):
        return sorted(set(suggestions).union(scripted_trigger_ids))
    if fname in ("on_action", "on_actions"):
        return sorted(set(suggestions).union(on_action_ids))
    return suggestions


def _effects_signature(focus, effects):
    """Value signature of a focus's effects for the refresh-skip.

    Covers the focus id plus every type and field pair the cards render, so
    two signatures can only match when a rebuild would draw the same thing.
    Object ids are deliberately not part of it: CPython reuses addresses, so
    a freed focus's id comes back on an unrelated one and skips a rebuild
    that was needed. Values go in as `repr` so the signature holds no
    reference to the live dicts an in-place edit would mutate under it.
    """
    return (
        getattr(focus, "id", None),
        tuple(
            (
                eff.get("type"),
                tuple(sorted((k, repr(v)) for k, v in eff.get("fields", {}).items())),
            )
            for eff in effects
        ),
    )


class EffectsMixin:
    """Effects tab, effect browser and parameter-form for :class:`App`."""

    if TYPE_CHECKING:

        def _get_mod_suggestions(self, etype: str, fname: str) -> list[str]: ...

    def _build_sidebar_effects(self, p, _make_scroll_panel):
        # ── TAB 2: Effects ─────────────────────────────────────────────
        eff_frm_outer = _make_scroll_panel(p)
        self._sb_frm_eff = eff_frm_outer

        # A single button opens the full effect browser popup; the sidebar
        # itself stays focused on the effects you've already added.
        self._mk_btn(
            eff_frm_outer,
            tr("focus.effects.add", "＋  Add Effect"),
            self._open_effect_browser,
            fg="#4ade80",
            bg="#14532d",
            font_size=10,
            pady=8,
        ).pack(fill="x", padx=10, pady=(10, 6))

        # ── Added effects ─────────────────────────────────────────────
        tk.Frame(eff_frm_outer, bg=BORDER_G, height=1).pack(
            fill="x", padx=10, pady=(2, 0)
        )
        tk.Label(
            eff_frm_outer,
            text=tr("focus.effects.added", "ADDED EFFECTS"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            anchor="w",
            padx=10,
        ).pack(fill="x", pady=(6, 2))

        # Container for effect cards (referenced by _refresh_effects).
        self._eff_box = tk.Frame(eff_frm_outer, bg=BG_PANEL)
        self._eff_box.pack(fill="x", padx=10, pady=(0, 8))

    def _center_window(self, win, w=None, h=None, over=None):
        """Position a Toplevel centered on screen (or centered over `over`)."""
        win.update_idletasks()
        if not w:
            w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
        if not h:
            h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
        if over is not None and over.winfo_exists() and over.winfo_width() > 1:
            x = over.winfo_rootx() + (over.winfo_width() - w) // 2
            y = over.winfo_rooty() + (over.winfo_height() - h) // 2
        else:
            x = (win.winfo_screenwidth() - w) // 2
            y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _open_effect_browser(self):
        """Popup browser: categories + searchable effect cards. Picking a card
        opens a parameter form for that effect."""
        if not self.selected:
            self._hint(tr("dialog.select_focus_first", "Select a focus first."))
            return
        existing = getattr(self, "_eb_win", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return

        win = tk.Toplevel(self)
        self._eb_win = win
        win.title(tr("focus.effects.browser_title", "Add Effect"))
        win.configure(bg=BG_DARK)
        win.geometry("720x560")
        win.minsize(560, 380)
        win.transient(self)

        cats = ["All"] + list(EFFECT_CATS)

        # ── Search row ─────────────────────────────────────────────
        top = tk.Frame(win, bg=BG_DARK)
        top.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(top, text="🔍", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 12)).pack(
            side="left", padx=(0, 6)
        )
        search_var = tk.StringVar()
        search = tk.Entry(
            top,
            textvariable=search_var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 11),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        search.pack(side="left", fill="x", expand=True, ipady=6)

        # ── Body: categories | effect cards ────────────────────────
        body = tk.Frame(win, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=12)

        cat_lb = tk.Listbox(
            body,
            bg=BG_CARD,
            fg=TEXT,
            selectbackground=SEL_BG,
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            font=("Helvetica", 10),
            width=18,
            activestyle="none",
            exportselection=False,
        )
        cat_lb.pack(side="left", fill="y")
        for c in cats:
            cat_lb.insert("end", c)
        cat_lb.selection_set(0)

        card_wrap = tk.Frame(body, bg=BG_DARK)
        card_wrap.pack(side="left", fill="both", expand=True, padx=(10, 0))
        card_cv = tk.Canvas(card_wrap, bg=BG_PANEL, highlightthickness=0)
        card_sb = tk.Scrollbar(card_wrap, orient="vertical", command=card_cv.yview)
        card_holder = tk.Frame(card_cv, bg=BG_PANEL)
        card_win = card_cv.create_window((0, 0), window=card_holder, anchor="nw")
        card_cv.configure(yscrollcommand=card_sb.set)
        card_holder.bind(
            "<Configure>", lambda e: card_cv.configure(scrollregion=card_cv.bbox("all"))
        )
        card_cv.bind(
            "<Configure>", lambda e: card_cv.itemconfig(card_win, width=e.width)
        )

        def _wheel(e):
            card_cv.yview_scroll(int(-1 * (e.delta / 120)), "units")

        card_cv.bind("<MouseWheel>", _wheel)
        card_sb.pack(side="right", fill="y")
        card_cv.pack(side="left", fill="both", expand=True)

        # ── Footer ─────────────────────────────────────────────────
        foot = tk.Frame(win, bg=BG_DARK)
        foot.pack(fill="x", padx=12, pady=12)
        status = tk.Label(foot, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 9))
        status.pack(side="left")
        self._eb_status = status
        self._mk_btn(foot, tr("common.close", "Close"), win.destroy).pack(side="right")

        def _cur_cat():
            sel = cat_lb.curselection()
            return cats[sel[0]] if sel else "All"

        CAP = 60

        def _refill(*_):
            for w in card_holder.winfo_children():
                w.destroy()
            q = search_var.get().lower().strip()
            cat = _cur_cat()
            shown = 0
            total = 0
            for k, v in EFFECT_DEFS.items():
                if cat != "All" and v.get("cat") != cat:
                    continue
                if q and q not in k.lower() and q not in v["label"].lower():
                    continue
                total += 1
                if shown < CAP:
                    self._eff_browser_card(card_holder, k, v, _wheel)
                    shown += 1
            if total == 0:
                tk.Label(
                    card_holder,
                    text=tr("focus.effects.none_found", "No effects match."),
                    bg=BG_PANEL,
                    fg=TEXT_DIM,
                    font=("Helvetica", 10, "italic"),
                    anchor="w",
                ).pack(fill="x", padx=6, pady=8)
            elif total > CAP:
                tk.Label(
                    card_holder,
                    text=tr(
                        "focus.effects.more",
                        "+{n} more — refine your search",
                        n=total - CAP,
                    ),
                    bg=BG_PANEL,
                    fg=TEXT_DIM,
                    font=("Helvetica", 9, "italic"),
                    anchor="w",
                ).pack(fill="x", padx=6, pady=(4, 8))
            card_cv.yview_moveto(0)
            status.config(text=tr("focus.effects.count", "{n} effect(s)", n=total))

        cat_lb.bind("<<ListboxSelect>>", _refill)
        search_var.trace_add("write", _refill)
        win.bind("<Escape>", lambda e: win.destroy())

        _refill()
        self._center_window(win, 720, 560)
        search.focus_set()

    def _effect_desc(self, defn):
        """A short human explanation of an effect from its note / field hints."""
        note = defn.get("_note")
        if note:
            return note
        fields = defn.get("fields", [])
        if not fields:
            return tr("focus.effects.no_params", "No parameters.")
        if len(fields) == 1 and fields[0][3]:
            return fields[0][3]
        return tr(
            "focus.effects.params_list",
            "Parameters: {p}",
            p=", ".join(f[0] for f in fields),
        )

    def _eff_browser_card(self, parent, key, defn, on_wheel=None):
        """A clickable effect card that opens the parameter form for `key`."""
        card = tk.Frame(
            parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER
        )
        card.pack(fill="x", padx=4, pady=3)
        head = tk.Frame(card, bg=BG_CARD)
        head.pack(fill="x", padx=8, pady=(6, 0))
        lbl_name = tk.Label(
            head,
            text=defn["label"],
            bg=BG_CARD,
            fg=TEXT,
            font=("Helvetica", 10, "bold"),
            anchor="w",
        )
        lbl_name.pack(side="left")
        lbl_cat = tk.Label(
            head,
            text=defn.get("cat", ""),
            bg=BG_CARD,
            fg=BLUE,
            font=("Helvetica", 7, "bold"),
            anchor="e",
        )
        lbl_cat.pack(side="right")
        lbl_code = tk.Label(
            card, text=key, bg=BG_CARD, fg=TEXT_DIM, font=("Courier", 8), anchor="w"
        )
        lbl_code.pack(fill="x", padx=8)
        lbl_desc = tk.Label(
            card,
            text=self._effect_desc(defn),
            bg=BG_CARD,
            fg="#94a3b8",
            font=("Helvetica", 8),
            anchor="w",
            justify="left",
            wraplength=380,
        )
        lbl_desc.pack(fill="x", padx=8, pady=(1, 6))

        cells = [card, head, lbl_name, lbl_cat, lbl_code, lbl_desc]

        def _set_bg(color):
            for w in cells:
                try:
                    w.config(bg=color)
                except tk.TclError:
                    pass

        def _open(_=None):
            self._open_effect_params(key)

        for w in cells:
            w.config(cursor="hand2")
            w.bind("<Button-1>", _open)
            w.bind("<Enter>", lambda e: _set_bg(BG_HOVER))
            w.bind("<Leave>", lambda e: _set_bg(BG_CARD))
            if on_wheel is not None:
                w.bind("<MouseWheel>", on_wheel)

    def _open_effect_params(self, key):
        """Popup form for one effect's parameters; confirms add to the focus."""
        defn = EFFECT_DEFS.get(key, {})
        fields = defn.get("fields", [])
        # No-parameter effects are added straight away.
        if not fields:
            self._add_effect_type(key)
            self._flash_added(defn.get("label", key))
            return

        pop = tk.Toplevel(self)
        pop.title(defn.get("label", key))
        pop.configure(bg=BG_DARK)
        parent = (
            self._eb_win
            if (getattr(self, "_eb_win", None) and self._eb_win.winfo_exists())
            else self
        )
        pop.transient(parent)
        pop.resizable(False, False)

        tk.Label(
            pop,
            text=defn.get("label", key),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 12, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(
            pop, text=key, bg=BG_DARK, fg=TEXT_DIM, font=("Courier", 8), anchor="w"
        ).pack(fill="x", padx=14)
        note = defn.get("_note")
        if note:
            tk.Label(
                pop,
                text=note,
                bg=BG_DARK,
                fg="#94a3b8",
                font=("Helvetica", 9),
                anchor="w",
                justify="left",
                wraplength=380,
            ).pack(fill="x", padx=14, pady=(4, 0))
        tk.Frame(pop, bg=BORDER_G, height=1).pack(fill="x", padx=14, pady=(8, 4))

        form = tk.Frame(pop, bg=BG_DARK)
        form.pack(fill="both", expand=True, padx=14, pady=4)
        getters = {}
        for fname, wtype, default, hint in fields:
            row = tk.Frame(form, bg=BG_DARK)
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=fname,
                bg=BG_DARK,
                fg=TEXT,
                font=("Helvetica", 9, "bold"),
                anchor="w",
            ).pack(fill="x")
            if wtype.startswith("dropdown:"):
                opts = wtype.split(":", 1)[1].split(",")
                var = tk.StringVar(value=default if default in opts else opts[0])
                om = tk.OptionMenu(row, var, *opts)
                om.config(
                    bg=BG_CARD,
                    fg=TEXT,
                    activebackground=BG_HOVER,
                    font=("Helvetica", 10),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    anchor="w",
                )
                om["menu"].config(
                    bg=BG_CARD, fg=TEXT, activebackground=SEL_BG, font=("Helvetica", 10)
                )
                om.pack(fill="x", pady=(2, 0))
                getters[fname] = var.get
            else:
                var = tk.StringVar(value=default)
                ent = tk.Entry(
                    row,
                    textvariable=var,
                    bg=BG_CARD,
                    fg=TEXT,
                    insertbackground=BLUE,
                    font=("Helvetica", 10),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                )
                ent.pack(fill="x", ipady=3, pady=(2, 0))
                getters[fname] = var.get
            if hint:
                tk.Label(
                    row,
                    text=hint,
                    bg=BG_DARK,
                    fg=TEXT_DIM,
                    font=("Helvetica", 8, "italic"),
                    anchor="w",
                    justify="left",
                    wraplength=380,
                ).pack(fill="x")

        footer = tk.Frame(pop, bg=BG_DARK)
        footer.pack(fill="x", padx=14, pady=(6, 12))

        def _confirm(_=None):
            values = {fn: g() for fn, g in getters.items()}
            self._add_effect_type(key, values)
            self._flash_added(defn.get("label", key))
            pop.destroy()

        self._mk_btn(footer, tr("common.cancel", "Cancel"), pop.destroy).pack(
            side="right"
        )
        self._mk_btn(
            footer,
            tr("focus.effects.add_this", "＋  Add Effect"),
            _confirm,
            fg="#4ade80",
            bg="#14532d",
        ).pack(side="right", padx=(0, 8))
        pop.bind("<Return>", _confirm)
        pop.bind("<Escape>", lambda e: pop.destroy())
        self._center_window(pop, over=parent if parent is not self else None)

        def _grab():
            try:
                if pop.winfo_exists():
                    pop.grab_set()
            except tk.TclError:
                pass  # window not viewable yet — modality is a nicety, skip

        pop.after(50, _grab)

    def _add_effect_type(self, etype, fields=None):
        """Append an effect to the selected focus.

        `fields` (from the parameter form) overrides the per-field defaults when
        provided; otherwise the effect's defaults are used.
        """
        if not self.selected:
            self._hint(tr("dialog.select_focus_first", "Select a focus first."))
            return
        self._push_undo("add effect", touched_ids=(self.selected.id,))
        defn = EFFECT_DEFS.get(etype, {})
        if fields is None:
            fields = {fn: dv for fn, _, dv, _ in defn.get("fields", [])}
        self.selected.effects.append({"type": etype, "fields": dict(fields)})
        self._refresh_effects()
        self._focus_list_cache.invalidate()
        self._invalidate_focus_list_structure()

    def _refresh_effects(self, force=False):
        effects = self.selected.effects if self.selected else []
        sig = _effects_signature(self.selected, effects)
        if (
            not force
            and MOD.sidebar_refresh_skip
            and getattr(self, "_effects_sig", None) == sig
        ):
            return
        self._effects_sig = sig
        for w in self._eff_box.winfo_children():
            w.destroy()
        if not effects:
            tk.Label(
                self._eff_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w")
            return
        for i, eff in enumerate(self.selected.effects):
            self._draw_eff_card(i, eff)

    def _get_effect_suggestions(self, etype, fname):
        suggestions = _augment_character_suggestions(
            self._get_mod_suggestions(etype, fname),
            fname,
            loaded=MOD.loaded,
            character_ids=MOD.character_ids,
        )
        return _augment_scripted_suggestions(
            suggestions,
            fname,
            loaded=MOD.loaded,
            scripted_effect_ids=MOD.scripted_effect_ids,
            scripted_trigger_ids=MOD.scripted_trigger_ids,
            on_action_ids=MOD.on_action_ids,
        )

    def _draw_eff_card(self, i, eff):
        etype = eff.get("type", "")
        defn = EFFECT_DEFS.get(etype, {})
        known = bool(defn)
        label = defn.get("label", etype) if known else etype
        cat = defn.get("cat", "raw") if known else "raw"
        hdr_bg = "#0d1117" if known else "#1a1020"

        ef = tk.Frame(
            self._eff_box,
            bg=BG_CARD,
            highlightthickness=1,
            highlightbackground=BORDER_G if known else ORANGE,
        )
        ef.pack(fill="x", pady=3)
        hdr = tk.Frame(ef, bg=hdr_bg)
        hdr.pack(fill="x")
        # Accent strip + order number on the left.
        tk.Frame(hdr, bg=(BLUE if known else ORANGE), width=3).pack(
            side="left", fill="y"
        )
        tk.Label(
            hdr,
            text=str(i + 1),
            bg=hdr_bg,
            fg=TEXT_DIM,
            font=("Courier", 8, "bold"),
            padx=6,
        ).pack(side="left")
        tk.Label(
            hdr,
            text=label,
            bg=hdr_bg,
            fg=(TEXT if known else ORANGE),
            font=("Helvetica", 9, "bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True, pady=4)
        tk.Label(
            hdr,
            text=cat,
            bg=hdr_bg,
            fg=(BLUE if known else ORANGE),
            font=("Helvetica", 7, "bold"),
            padx=6,
        ).pack(side="left")
        tk.Button(
            hdr,
            text="✕",
            command=lambda idx=i: self._rm_effect(idx),
            bg=hdr_bg,
            fg=RED,
            activebackground=hdr_bg,
            activeforeground="#ff8888",
            relief="flat",
            font=("Georgia", 10),
            cursor="hand2",
            padx=6,
            bd=0,
            highlightthickness=0,
        ).pack(side="right", fill="y")

        def _entry_row(parent, key, val, idx, fkey):
            """Render an editable key=value row."""
            row = tk.Frame(parent, bg=BG_CARD)
            row.pack(fill="x", padx=4, pady=1)
            # key label (editable only for raw effects)
            if not known:
                kvar = tk.StringVar(value=key)
                ke = tk.Entry(
                    row,
                    textvariable=kvar,
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    insertbackground=BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    width=12,
                )
                ke.pack(side="left", ipady=2, padx=(0, 2))

                def _on_key_change(*a, old=key, kv=kvar, efidx=idx):
                    if self.selected and efidx < len(self.selected.effects):
                        fields = self.selected.effects[efidx].setdefault("fields", {})
                        if old in fields:
                            fields[kv.get()] = fields.pop(old)

                kvar.trace_add("write", _on_key_change)
            else:
                tk.Label(
                    row,
                    text=f"{key}:",
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    font=("Georgia", 8),
                    width=14,
                    anchor="w",
                ).pack(side="left")
            # value entry
            vvar = tk.StringVar(
                value=str(val) if not isinstance(val, dict) else json.dumps(val)
            )
            ve = tk.Entry(
                row,
                textvariable=vvar,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Helvetica", 10),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            ve.pack(side="left", fill="x", expand=True, ipady=2, padx=2)
            vvar.trace_add(
                "write",
                lambda *a, efidx=idx, fn=fkey, v=vvar: self._live_eff_field(
                    efidx, fn, v
                ),
            )

        if known:
            # Render structured fields from EFFECT_DEFS
            for fname, wtype, default, hint in defn.get("fields", []):
                saved = eff.get("fields", {}).get(fname, default)
                ff = tk.Frame(ef, bg=BG_CARD)
                ff.pack(fill="x", padx=6, pady=1)
                tk.Label(
                    ff,
                    text=f"{fname}:",
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    font=("Helvetica", 9),
                    width=10,
                    anchor="w",
                ).pack(side="left")
                if wtype == "multiline":
                    t = tk.Text(
                        ff,
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
                    t.insert("1.0", saved)
                    t.pack(side="left", fill="x", expand=True, ipady=2)
                    t.bind(
                        "<KeyRelease>",
                        lambda e, idx=i, fn=fname, tw=t: self._live_eff_text(
                            idx, fn, tw
                        ),
                    )
                elif wtype.startswith("dropdown:"):
                    opts = wtype.split(":")[1].split(",")
                    var = tk.StringVar(value=saved if saved in opts else opts[0])
                    om = tk.OptionMenu(ff, var, *opts)
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
                    var.trace_add(
                        "write",
                        lambda *a, idx=i, fn=fname, v=var: self._live_eff_field(
                            idx, fn, v
                        ),
                    )
                else:
                    var = tk.StringVar(value=saved)
                    suggestions = self._get_effect_suggestions(etype, fname)
                    ent = tk.Entry(
                        ff,
                        textvariable=var,
                        bg=BG_CARD,
                        fg=TEXT,
                        insertbackground=BLUE,
                        font=("Helvetica", 10),
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=BORDER_G,
                    )
                    ent.pack(side="left", padx=2, ipady=2, fill="x", expand=True)
                    var.trace_add(
                        "write",
                        lambda *a, idx=i, fn=fname, v=var: self._live_eff_field(
                            idx, fn, v
                        ),
                    )
                    # Wire autocomplete if mod has data for this field
                    if suggestions or MOD.loaded:
                        self._attach_autocomplete(
                            ent,
                            var,
                            lambda et=etype, fn=fname: self._get_effect_suggestions(
                                et, fn
                            ),
                        )
                if hint:
                    hl = tk.Label(
                        ff,
                        text="?",
                        bg=BG_CARD,
                        fg=TEXT_DIM,
                        font=("Helvetica", 8),
                        cursor="question_arrow",
                    )
                    hl.pack(side="left", padx=2)
                    hl.bind("<Enter>", lambda e, h=hint: self._hint(h))
                    hl.bind(
                        "<Leave>",
                        lambda e: self._hint(
                            "Right-click canvas to place focus  •  "
                            "Ctrl+drag to pan  •  Scroll to zoom"
                        ),
                    )
        else:
            # Unknown / imported effect — show raw key=value fields as editable entries
            fields = eff.get("fields", {})
            # _raw_block: verbatim HOI4 code — show as editable multiline code box
            if etype == "_raw_block":
                raw_val = fields.get("raw", "")
                tk.Label(
                    ef,
                    text=tr(
                        "focus.effects.raw_imported",
                        "  raw HOI4  (imported verbatim - editable):",
                    ),
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    font=("Helvetica", 8, "italic"),
                ).pack(anchor="w", padx=6, pady=(2, 0))
                raw_txt = tk.Text(
                    ef,
                    bg="#0d1117",
                    fg="#a8d8a8",
                    insertbackground=BLUE,
                    font=("Courier", 9),
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=ORANGE,
                    height=max(2, min(raw_val.count("\n") + 2, 8)),
                    wrap="none",
                )
                raw_txt.insert("1.0", raw_val)
                raw_txt.pack(fill="x", padx=6, pady=(0, 4))

                def _on_raw_edit(e, efidx=i, tw=raw_txt):
                    # Only update the data field — do NOT trigger a canvas redraw.
                    # (Redrawing mid-edit causes zoom resets and phantom arrow lines
                    # because prerequisite data may be in a partially edited state.)
                    if self.selected and efidx < len(self.selected.effects):
                        self.selected.effects[efidx]["fields"]["raw"] = tw.get(
                            "1.0", "end"
                        ).strip()

                raw_txt.bind("<KeyRelease>", _on_raw_edit)
            elif not fields:
                tk.Label(
                    ef,
                    text=tr(
                        "focus.effects.no_fields", "  (no fields - exported as-is)"
                    ),
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    font=("Georgia", 8, "italic"),
                ).pack(anchor="w", padx=6)
            else:
                for fkey, fval in list(fields.items()):
                    if fkey.startswith("_"):
                        continue
                    _entry_row(ef, fkey, fval, i, fkey)

            # add-field button for raw effects
            def _add_raw_field(efidx=i, box=ef):
                if self.selected and efidx < len(self.selected.effects):
                    fields = self.selected.effects[efidx].setdefault("fields", {})
                    nk = f"key{len(fields)}"
                    fields[nk] = "value"
                    self._refresh_effects()

            tk.Button(
                ef,
                text=tr("focus.effects.add_field", "+ add field"),
                command=_add_raw_field,
                bg=BG_CARD,
                fg=TEXT_DIM,
                relief="flat",
                font=("Helvetica", 8),
                cursor="hand2",
                pady=1,
            ).pack(anchor="w", padx=6, pady=(0, 3))

    def _rm_effect(self, idx):
        if not self.selected:
            return
        self._push_undo("remove effect", touched_ids=(self.selected.id,))
        self.selected.effects.pop(idx)
        self._refresh_effects()
        self._focus_list_cache.invalidate()
        self._invalidate_focus_list_structure()

    def _live_eff_field(self, idx, fname, var):
        if self.selected and idx < len(self.selected.effects):
            self.selected.effects[idx].setdefault("fields", {})[fname] = var.get()

    def _live_eff_text(self, idx, fname, tw):
        if self.selected and idx < len(self.selected.effects):
            self.selected.effects[idx].setdefault("fields", {})[fname] = tw.get(
                "1.0", "end-1c"
            )

    def _render_effect(self, eff):
        return render_effect(eff)
