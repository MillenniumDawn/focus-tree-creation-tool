"""Effects panel: the sidebar Effects tab, the effect browser popup and the
per-effect parameter form.

Extracted from the monolith as a mixin so the methods keep operating on ``App``
state via ``self``. Behaviour is identical. Note: ``_apply_md_visibility`` (in
the monolith) mutates ``EFFECT_CATS`` in place, so the browser here — which
imports the same shared list — always sees the current Millennium Dawn set.
"""

import json
import re
import tkinter as tk

from hoi4cm.core import EFFECT_CATS, EFFECT_DEFS, tr
from hoi4cm.mod import MOD
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


class EffectsMixin:
    """Effects tab, effect browser and parameter-form for :class:`App`."""

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
        tk.Label(
            top, text="🔍", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 12)
        ).pack(side="left", padx=(0, 6))
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
        status = tk.Label(
            foot, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 9)
        )
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
        parent = self._eb_win if (getattr(self, "_eb_win", None) and self._eb_win.winfo_exists()) else self
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
        self._push_undo("add effect")
        defn = EFFECT_DEFS.get(etype, {})
        if fields is None:
            fields = {fn: dv for fn, _, dv, _ in defn.get("fields", [])}
        self.selected.effects.append({"type": etype, "fields": dict(fields)})
        self._refresh_effects()

    def _refresh_effects(self):
        for w in self._eff_box.winfo_children():
            w.destroy()
        if not self.selected or not self.selected.effects:
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

    def _draw_eff_card(self, i, eff):
        etype = eff.get("type", "")
        defn = EFFECT_DEFS.get(etype, {})
        known = bool(defn)
        label = defn.get("label", etype) if known else etype
        cat = defn.get("cat", "raw") if known else "raw"
        hdr_bg = "#0d1117" if known else "#1a1020"
        lbl_fg = TEXT_DIM if known else ORANGE

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
                    suggestions = self._get_mod_suggestions(etype, fname)
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
                            lambda et=etype, fn=fname: self._get_mod_suggestions(
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
                            "Right-click canvas to place focus  •  Ctrl+drag to pan  •  Scroll to zoom"
                        ),
                    )
        else:
            # Unknown / imported effect — show all raw key=value fields as editable entries
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
        self.selected.effects.pop(idx)
        self._refresh_effects()

    def _live_eff_field(self, idx, fname, var):
        if self.selected and idx < len(self.selected.effects):
            self.selected.effects[idx].setdefault("fields", {})[fname] = var.get()

    def _live_eff_text(self, idx, fname, tw):
        if self.selected and idx < len(self.selected.effects):
            self.selected.effects[idx].setdefault("fields", {})[fname] = tw.get(
                "1.0", "end-1c"
            )

    def _render_effect(self, eff):
        """Render a single effect as HOI4 code (3-tab indent, inside completion_reward)."""
        t = eff.get("type", "")
        f = eff.get("fields", {})
        I = "\t\t\t"

        def block(name, pairs):
            inner = "\n".join(f"{I}\t{k} = {v}" for k, v in pairs)
            return f"{I}{name} = {{\n{inner}\n{I}}}"

        def g(key, default=""):
            return f.get(key, default)

        # ── Dispatch table: type → renderer ───────────────────────
        _DISPATCH = {
            "add_tech_bonus": lambda: block(
                "add_tech_bonus",
                [
                    ("name", g("name", "bonus")),
                    ("bonus", g("bonus", "0.5")),
                    ("uses", g("uses", "1")),
                    ("category", g("category", "infantry_weapons")),
                ],
            ),
            "add_popularity": lambda: block(
                "add_popularity",
                [
                    ("ideology", g("ideology", "democratic")),
                    ("popularity", g("popularity", "0.05")),
                ],
            )
            + f"\n{I}recalculate_party = yes",
            "set_politics": lambda: block(
                "set_politics",
                [
                    ("ruling_party", g("ruling_party", "democratic")),
                    ("elections_allowed", g("elections_allowed", "no")),
                ],
            ),
            "add_timed_idea": lambda: block(
                "add_timed_idea", [("idea", g("idea", "")), ("days", g("days", "180"))]
            ),
            "swap_ideas": lambda: block(
                "swap_ideas",
                [
                    ("remove_idea", g("remove_idea", "old_spirit")),
                    ("add_idea", g("add_idea", "new_spirit")),
                ],
            ),
            "declare_war_on": lambda: block(
                "declare_war_on",
                [
                    ("target", g("target", "TAG")),
                    ("type", g("type", "annex_everything")),
                ],
            ),
            "create_wargoal": lambda: block(
                "create_wargoal",
                [
                    ("type", g("type", "annex_everything")),
                    ("target", g("target", "TAG")),
                ],
            ),
            "annex_country": lambda: block(
                "annex_country",
                [
                    ("target", g("target", "TAG")),
                    ("transfer_troops", g("transfer_troops", "no")),
                ],
            ),
            "add_opinion_modifier": lambda: block(
                "add_opinion_modifier",
                [
                    ("target", g("target", "TAG")),
                    ("modifier", g("modifier", "my_opinion_mod")),
                ],
            ),
            "diplomatic_relation": lambda: block(
                "diplomatic_relation",
                [
                    ("country", g("country", "TAG")),
                    ("relation", g("relation", "guarantee")),
                    ("active", g("active", "yes")),
                ],
            ),
            "add_ai_strategy": lambda: block(
                "add_ai_strategy",
                [
                    ("type", g("type", "alliance")),
                    ("id", g("id", "TAG")),
                    ("value", g("value", "100")),
                ],
            ),
            "start_civil_war": lambda: block(
                "start_civil_war",
                [("ideology", g("ideology", "communism")), ("size", g("size", "0.5"))],
            ),
            "load_focus_tree": lambda: block(
                "load_focus_tree",
                [
                    ("tree", g("tree", "TAG_focus_tree")),
                    ("keep_completed", g("keep_completed", "yes")),
                ],
            ),
            "add_building_construction": lambda: block(
                "add_building_construction",
                [
                    ("type", g("type", "industrial_complex")),
                    ("level", g("level", "1")),
                    ("instant_build", g("instant_build", "no")),
                ],
            ),
            "create_unit": lambda: (
                f"{I}create_unit = {{\n"
                f"{I}\tdivision = \"name = \\\"{g('division_name','1st Infantry Division')}\\\" "
                f"division_template = \\\"{g('division_template','Infantry Division')}\\\" "
                f"start_experience_factor = {g('start_experience_factor','0.2')}\"\n"
                f"{I}\towner = {g('owner','ROOT')}\n"
                f"{I}}}"
            ),
            "set_technology": lambda: f'{I}set_technology = {{ {g("tech_id","infantry_weapons1")} = {"1" if g("researched","yes") == "yes" else "0"} }}',
            "modify_timed_idea": lambda: block(
                "modify_timed_idea",
                [("idea", g("idea", "my_spirit")), ("days", g("days", "30"))],
            ),
            "build_railway": lambda: block(
                "build_railway",
                [("level", g("level", "1")), ("path", g("path", "{ 1 2 3 }"))],
            ),
            "division_template": lambda: (
                f"{I}division_template = {{\n"
                f'{I}\tname = "{g("name","Infantry Division")}"\n'
                f"{I}\tregiments = {{\n"
                + "\n".join(
                    f"{I}\t\t{ln.strip()}"
                    for ln in g("regiments", "infantry = { x = 0 y = 0 }")
                    .strip()
                    .splitlines()
                    if ln.strip()
                )
                + f"\n{I}\t}}\n"
                f"{I}}}"
            ),
            "load_oob": lambda: f'{I}load_oob = "{g("file","TAG_1936")}"',
            "set_oob": lambda: f'{I}set_oob = "{g("file","TAG_1936")}"',
            "log": lambda: f'{I}log = "{g("text")}"',
            "set_variable": lambda: f'{I}set_variable = {{ {g("var","my_var")} = {g("value","0")} }}',
            "force_update_dynamic_modifier": lambda: f"{I}force_update_dynamic_modifier = yes",
            "unlock_decision_category_tooltip": lambda: f'{I}unlock_decision_category_tooltip = {g("category","TAG_decisions")}',
            "unlock_decision_tooltip": lambda: f'{I}unlock_decision_tooltip = {g("decision","TAG_decision")}',
            "ingame_update_setup": lambda: f"{I}ingame_update_setup = yes",
            # MD scripted effects
            "md_modify_treasury": lambda: (
                f"{I}set_temp_variable = {{ treasury_change = {g('amount','-10.00')} }}\n"
                f"{I}modify_treasury_effect = yes"
            ),
            "md_modify_debt": lambda: (
                f"{I}set_temp_variable = {{ debt_change = {g('amount','0.1')} }}\n"
                f"{I}modify_debt_effect = yes"
            ),
            "md_modify_international_investment": lambda: (
                f"{I}set_temp_variable = {{ int_investment_change = {g('amount','0.1')} }}\n"
                f"{I}modify_international_investment_effect = yes"
            ),
            "md_modify_corporate_tax": lambda: (
                f"{I}set_temp_variable = {{ corp_change = {g('amount','2')} }}\n"
                f"{I}modify_corporate_tax_rate_effect = yes"
            ),
            "md_modify_population_tax": lambda: (
                f"{I}set_temp_variable = {{ pop_change = {g('amount','2')} }}\n"
                f"{I}modify_population_tax_rate_effect = yes"
            ),
            "md_flat_productivity": lambda: (
                f"{I}set_temp_variable = {{ temp_productivity_change = {g('amount','0.025')} }}\n"
                f"{I}flat_productivity_change_effect = yes"
            ),
            "md_economic_cycle": lambda: f"{I}{g('cycle','stable_growth')} = yes",
            "md_gov_spending": lambda: f"{I}{g('action','increase_social_spending')} = yes",
            "md_build_random": lambda: (
                f"{I}set_temp_variable = {{ treasury_change = {g('treasury_change','-7.50')} }}\n"
                f"{I}modify_treasury_effect = yes\n"
                f"{I}{g('effect','one_random_industrial_complex')} = yes"
            ),
            "md_enrichment_facility": lambda: (
                f"{I}set_temp_variable = {{ temp_change = {g('count','1')} }}\n"
                f"{I}build_enrichment_facilities_effect = yes"
            ),
            "md_battery_park": lambda: (
                f"{I}set_temp_variable = {{ temp_change = {g('count','1')} }}\n"
                f"{I}build_battery_park_effect = yes"
            ),
            "md_coalition_add": lambda: (
                f"{I}set_temp_variable = {{ add_col_one = {g('party_index','5')} }}\n"
                f"{I}add_coalition_members_effect = yes"
            ),
            "md_coalition_remove": lambda: (
                f"{I}set_temp_variable = {{ remove_col_one = {g('party_index','5')} }}\n"
                f"{I}remove_coalition_members_effect = yes"
            ),
            "md_domestic_influence": lambda: (
                f"{I}set_temp_variable = {{ percent_change = {g('percent','10')} }}\n"
                f"{I}change_domestic_influence_percentage = yes"
            ),
            "md_eurosceptic_all": lambda: (
                f"{I}set_temp_variable = {{ modify_eurosceptic = {g('amount','-0.05')} }}\n"
                f"{I}EU_eurosceptic_change = yes"
            ),
            # MD Budget — individual yes-call entries
            "increase_centralization": lambda: f"{I}increase_centralization = yes",
            "decrease_centralization": lambda: f"{I}decrease_centralization = yes",
            "increase_social_spending": lambda: f"{I}increase_social_spending = yes",
            "decrease_social_spending": lambda: f"{I}decrease_social_spending = yes",
            "increase_education_budget": lambda: f"{I}increase_education_budget = yes",
            "decrease_education_budget": lambda: f"{I}decrease_education_budget = yes",
            "increase_healthcare_budget": lambda: f"{I}increase_healthcare_budget = yes",
            "decrease_healthcare_budget": lambda: f"{I}decrease_healthcare_budget = yes",
            "increase_policing_budget": lambda: f"{I}increase_policing_budget = yes",
            "decrease_policing_budget": lambda: f"{I}decrease_policing_budget = yes",
            "increase_exports": lambda: f"{I}increase_exports = yes",
            "decrease_exports": lambda: f"{I}decrease_exports = yes",
            "increase_military_spending": lambda: f"{I}increase_military_spending = yes",
            "decrease_military_spending": lambda: f"{I}decrease_military_spending = yes",
            "increase_economic_growth": lambda: f"{I}increase_economic_growth = yes",
            "decrease_economic_growth": lambda: f"{I}decrease_economic_growth = yes",
            "increase_corruption": lambda: f"{I}increase_corruption = yes",
            "decrease_corruption": lambda: f"{I}decrease_corruption = yes",
            "increase_Free_Market_Economy": lambda: f"{I}increase_Free_Market_Economy = yes",
            "increase_Planned_Economy": lambda: f"{I}increase_Planned_Economy = yes",
            "economic_boom": lambda: f"{I}economic_boom = yes",
            "stable_growth": lambda: f"{I}stable_growth = yes",
            "fast_growth": lambda: f"{I}fast_growth = yes",
            "recession": lambda: f"{I}recession = yes",
            "stagnation": lambda: f"{I}stagnation = yes",
            "depression": lambda: f"{I}depression = yes",
            # MD Politics
            "set_party_index_to_ruling_party": lambda: f"{I}set_party_index_to_ruling_party = yes",
            "recalculate_party": lambda: f"{I}recalculate_party = yes",
            "add_own_ideology_drift": lambda: f"{I}add_own_ideology_drift = yes",
            # MD Scripted
            "cyber_execute_operation": lambda: f"{I}cyber_execute_operation = yes",
            "modify_reform_expectance_effect": lambda: f"{I}modify_reform_expectance_effect = yes",
        }

        if t in _DISPATCH:
            return _DISPATCH[t]()

        # ── Faction opinion individual renderers ────────────────────
        _FACTION_OPINIONS = {
            "change_small_medium_business_owners_opinion",
            "change_industrial_conglomerates_opinion",
            "change_fossil_fuel_industry_opinion",
            "change_defense_industry_opinion",
            "change_maritime_industry_opinion",
            "change_international_bankers_opinion",
            "change_oligarchs_opinion",
            "change_farmers_opinion",
            "change_landowners_opinion",
            "change_labour_unions_opinion",
            "change_communist_cadres_opinion",
            "change_the_clergy_opinion",
            "change_the_ulema_opinion",
            "change_the_priesthood_opinion",
            "change_the_wahabi_ulema_opinion",
            "change_the_military_opinion",
            "change_intelligence_community_opinion",
            "change_the_donju_opinion",
            "change_saudi_royal_family_opinion",
            "change_foreign_jihadis_opinion",
            "change_iranian_quds_force_opinion",
            "change_chaebols_opinion",
            "change_wall_street_opinion",
            "change_all_internal_faction_opinion",
        }
        if t in _FACTION_OPINIONS:
            return (
                f"{I}set_temp_variable = {{ temp_opinion = {g('opinion','5')} }}\n"
                f"{I}{t} = yes"
            )

        # ── Multi-case handlers ────────────────────────────────────
        if t == "add_equipment_to_stockpile":
            pairs = [
                ("type", g("type", "infantry_equipment_1")),
                ("amount", g("amount", "500")),
            ]
            if g("producer", "").strip():
                pairs.append(("producer", g("producer")))
            return block("add_equipment_to_stockpile", pairs)

        if t in ("country_event", "news_event"):
            pairs = [("id", g("id", "my_event.1"))]
            d = g("days", "0").strip()
            if d and d != "0":
                pairs.append(("days", d))
            return block(t, pairs)

        if t in ("hidden_effect", "effect_tooltip"):
            raw = g("raw", "").strip()
            if not raw and "_list" in f:
                raw = "\n".join(
                    f"{I}\t{ik} = {iv}"
                    for item in f["_list"]
                    if isinstance(item, dict)
                    for ik, iv in item.items()
                    if not str(ik).startswith("_")
                )
            inner = "\n".join(f"{I}\t{ln}" for ln in raw.splitlines())
            return f"{I}{t} = {{\n{inner}\n{I}}}"

        if t == "_raw_block":
            raw = g("raw", "").strip()
            return "\n".join(f"{I}{ln}" for ln in raw.splitlines()) if raw else ""

        if t == "add_to_variable":
            vn = g("var", "AM_my_stat_var")
            val = g("value", "0.05")
            tt = g("tooltip", "").strip()
            base = f"{I}add_to_variable = {{ {vn} = {val}"
            return base + (f" tooltip = {tt} }}" if tt else " }")

        # ── Variable math — all use { var = value } block form ──────────
        _VAR_TWO_FIELD = {
            "subtract_from_variable",
            "multiply_variable",
            "divide_variable",
            "modulo_variable",
            "add_to_temp_variable",
            "subtract_from_temp_variable",
            "multiply_temp_variable",
            "divide_temp_variable",
            "modulo_temp_variable",
        }
        if t in _VAR_TWO_FIELD:
            return f"{I}{t} = {{ {g('var','my_var')} = {g('value','1')} }}"

        if t == "set_temp_variable":
            return f"{I}set_temp_variable = {{ {g('var','my_temp_var')} = {g('value','1')} }}"

        # single-arg variable ops (no block needed)
        if t in ("round_variable", "clear_variable"):
            return f"{I}{t} = {g('var','my_var')}"
        if t in ("round_temp_variable",):
            return f"{I}{t} = {g('var','my_temp_var')}"

        # clamp = { var = { min = X max = Y } }
        if t == "clamp_variable":
            return f"{I}clamp_variable = {{ {g('var','my_var')} = {{ min = {g('min','0')} max = {g('max','100')} }} }}"
        if t == "clamp_temp_variable":
            return f"{I}clamp_temp_variable = {{ {g('var','my_temp_var')} = {{ min = {g('min','0')} max = {g('max','100')} }} }}"

        # set_variable_to_random / randomize_variable = { var = { max = X } }
        if t in ("set_variable_to_random", "randomize_variable"):
            return f"{I}{t} = {{ {g('var','my_var')} = {{ max = {g('max','10')} }} }}"
        if t in ("set_temp_variable_to_random", "randomize_temp_variable"):
            return (
                f"{I}{t} = {{ {g('var','my_temp_var')} = {{ max = {g('max','10')} }} }}"
            )

        if t == "add_dynamic_modifier":
            out = [
                f"{I}add_dynamic_modifier = {{",
                f"{I}\tmodifier = {g('modifier','TAG_modifier')}",
            ]
            sc = g("scope", "").strip()
            dy = g("days", "").strip()
            if sc:
                out.append(f"{I}\tscope = {sc}")
            if dy:
                out.append(f"{I}\tdays = {dy}")
            out.append(f"{I}}}")
            return "\n".join(out)

        if t == "add_dynamic_modifier_with_tt":
            # Generates add_dynamic_modifier + adds_dynamic_modifier_tt tooltip together
            # Per skill rules: use adds_ when the block contains add_dynamic_modifier
            mod = g("modifier", "TAG_modifier")
            sc = g("scope", "").strip()
            dy = g("days", "").strip()
            out = [f"{I}add_dynamic_modifier = {{", f"{I}\tmodifier = {mod}"]
            if sc:
                out.append(f"{I}\tscope = {sc}")
            if dy:
                out.append(f"{I}\tdays = {dy}")
            out.append(f"{I}}}")
            out.append(f"{I}custom_effect_tooltip = {{")
            out.append(f"{I}\tlocalization_key = adds_dynamic_modifier_tt")
            out.append(f"{I}\tMODIFIER = {mod}")
            out.append(f"{I}}}")
            return "\n".join(out)

        if t == "remove_dynamic_modifier":
            return f"{I}remove_dynamic_modifier = {{\n{I}\tmodifier = {g('modifier','TAG_modifier')}\n{I}}}"

        if t == "dynamic_modifier_tooltip":
            loc_key = g("localization_key", "modifies_dynamic_modifier_tt")
            mod = g("MODIFIER", "TAG_modifier")
            return (
                f"{I}custom_effect_tooltip = {{\n"
                f"{I}\tlocalization_key = {loc_key}\n"
                f"{I}\tMODIFIER = {mod}\n{I}}}"
            )

        if t in ("custom_effect_tooltip", "custom_effect_tooltip_block"):
            if (
                f.get("_block_form")
                or "localization_key" in f
                or "MODIFIER" in f
                or t.endswith("_block")
            ):
                loc_key = g("localization_key", "modifies_dynamic_modifier_tt")
                # adds_dynamic_modifier_tt: block contains add_dynamic_modifier
                # modifies_dynamic_modifier_tt: block only changes variables (no add_dynamic_modifier)
                return (
                    f"{I}custom_effect_tooltip = {{\n"
                    f"{I}\tlocalization_key = {loc_key}\n"
                    f"{I}\tMODIFIER = {g('MODIFIER','TAG_modifier')}\n{I}}}"
                )
            return f"{I}custom_effect_tooltip = {g('tooltip','my_tooltip_key')}"

        if t in (
            "md_small_expenditure",
            "md_medium_expenditure",
            "md_large_expenditure",
        ):
            return f"{I}{t.replace('md_','')} = yes"

        if t == "md_build_state":
            effect = g("effect", "one_state_industrial_complex")
            state = g("state_id", "117")
            tchange = g("treasury_change", "-7.50")
            return (
                f"{I}set_temp_variable = {{ treasury_change = {tchange} }}\n"
                f"{I}modify_treasury_effect = yes\n"
                f"{I}{state} = {{\n"
                f"{I}\t{effect} = yes\n"
                f"{I}}}"
            )

        if t == "md_add_resource":
            rtype = g("resource_type", "steel")
            amount = g("amount", "4")
            tchange = g("treasury_change", "-3.75")
            return (
                f"{I}set_temp_variable = {{ treasury_change = {tchange} }}\n"
                f"{I}modify_treasury_effect = yes\n"
                f"{I}capital_scope = {{\n"
                f"{I}\tadd_resource = {{\n"
                f"{I}\t\ttype = {rtype}\n"
                f"{I}\t\tamount = {amount}\n"
                f"{I}\t}}\n"
                f"{I}}}"
            )

        if t == "md_party_popularity":
            return (
                f"{I}set_temp_variable = {{ party_index = {g('party_index','2')} }}\n"
                f"{I}set_temp_variable = {{ party_popularity_increase = {g('amount','0.10')} }}\n"
                f"{I}add_relative_party_popularity = yes"
            )

        if t == "md_change_ruling_party":
            return (
                f"{I}set_temp_variable = {{ rul_party_temp = {g('rul_party_temp','2')} }}\n"
                f"{I}change_ruling_party_effect = yes\n"
                f"{I}set_politics = {{\n{I}\truling_party = {g('ruling_party','western')}\n"
                f"{I}\telections_allowed = {g('elections_allowed','no')}\n{I}}}"
            )

        if t == "md_ban_party":
            return (
                f"{I}set_temp_variable = {{ party_index = {g('party_index','1')} }}\n"
                f"{I}ban_party_scripted_call = yes"
            )

        if t == "md_unban_party":
            return (
                f"{I}set_temp_variable = {{ party_index = {g('party_index','1')} }}\n"
                f"{I}unban_party_scripted_call = yes"
            )

        if t == "md_pp_loss":
            return f"{I}{g('duration','lose_pp_for_month')} = yes"

        if t == "md_faction_opinion":
            return (
                f"{I}set_temp_variable = {{ temp_opinion = {g('opinion','5')} }}\n"
                f"{I}{g('faction','change_the_military_opinion')} = yes"
            )

        if t == "md_influence_country":
            return (
                f"{I}set_temp_variable = {{ percent_change = {g('percent','5')} }}\n"
                f"{I}set_temp_variable = {{ tag_index = ROOT }}\n"
                f"{I}set_temp_variable = {{ influence_target = {g('target','GER')} }}\n"
                f"{I}change_influence_percentage = yes"
            )

        if t == "md_eurosceptic_target":
            return (
                f"{I}set_temp_variable = {{ modify_eurosceptic = {g('amount','0.05')} }}\n"
                f"{I}set_temp_variable = {{ modify_eurosceptic_target = {g('target','GER')} }}\n"
                f"{I}eurosceptic_change = yes"
            )

        if t == "md_cart_strength":
            return (
                f"{I}set_temp_variable = {{ cart_strength_change = {g('strength','2')} }}\n"
                f"{I}set_temp_variable = {{ cart_influence_change = {g('influence','2')} }}\n"
                f"{I}modify_cartel_variables_effect = yes"
            )

        if t == "md_relative_party_popularity":
            return (
                f"{I}set_temp_variable = {{ party_index = {g('party_index','1')} }}\n"
                f"{I}set_temp_variable = {{ party_popularity_increase = {g('amount','0.02')} }}\n"
                f"{I}set_temp_variable = {{ temp_outlook_increase = {g('temp_outlook_increase','0.02')} }}\n"
                f"{I}add_relative_party_popularity = yes"
            )

        if t.startswith("md_modifier_"):
            return f"{I}# MD MODIFIER (place inside idea modifier block):\n{I}# {g('modifier','')} = {g('value','0.05')}"

        # ── Scope / if / else blocks ───────────────────────────────
        _SCOPE_TYPES = {
            "if",
            "else_if",
            "else",
            "every_country",
            "every_state",
            "every_ally",
            "every_enemy_country",
            "every_faction_member",
            "every_subject_country",
            "every_neighbor_country",
            "every_allied_country",
            "every_other_country",
            "every_occupied_country",
            "every_possible_country",
            "every_controlled_state",
            "every_owned_state",
            "every_core_state",
            "every_neighbor_state",
            "every_army_leader",
            "every_navy_leader",
            "every_unit_leader",
            "every_character",
            "every_operative",
            "every_country_division",
            "every_state_division",
            "every_active_scientist",
            "every_scientist",
            "every_military_industrial_organization",
            "every_purchase_contract",
            "every_country_with_original_tag",
            "every_collection_element",
            "every_hostile_country",
            "global_every_army_leader",
            "random_country",
            "random_state",
            "random_ally",
            "random_neighbor_country",
            "random_owned_state",
            "random_controlled_state",
            "random_core_state",
            "random_owned_controlled_state",
            "random_neighbor_state",
            "random_allied_country",
            "random_other_country",
            "random_enemy_country",
            "random_occupied_country",
            "random_subject_country",
            "random_army_leader",
            "random_navy_leader",
            "random_unit_leader",
            "random_character",
            "random_operative",
            "random_active_scientist",
            "random_scientist",
            "random_military_industrial_organization",
            "random_purchase_contract",
            "random_country_division",
            "random_state_division",
            "random_country_with_original_tag",
            "random_scope_in_array",
            "random_hostile_country",
            "random_list",
            "random",
            "capital_scope",
            "overlord",
            "faction_leader",
            "party_leader",
            "while_loop_effect",
            "for_loop_effect",
            "for_each_loop",
            "for_each_scope_loop",
        }

        # ── Helper: coerce a Python value to a HOI4 scalar (no True/False/list/dict leaks)
        def _hoi4_val(v):
            if isinstance(v, bool):
                return "yes" if v else "no"
            return str(v)

        # ── Helper: recursively render a dict/list value into HOI4 script lines
        def _hoi4_render_value(k, v, indent):
            """Render a single key->value pair at the given tab indent. Returns list of lines.
            Handles: scalars, bools → yes/no, lists → repeated keys, dicts → nested block."""
            T = indent
            if isinstance(v, bool):
                return [f"{T}{k} = {'yes' if v else 'no'}"]
            if isinstance(v, (int, float)):
                return [f"{T}{k} = {v}"]
            if isinstance(v, str):
                return [f"{T}{k} = {v}"]
            if isinstance(v, list):
                out_lines = []
                for item in v:
                    if isinstance(item, dict):
                        out_lines.append(f"{T}{k} = {{")
                        for ik, iv in item.items():
                            if str(ik).startswith("_"):
                                continue
                            out_lines.extend(_hoi4_render_value(ik, iv, T + "\t"))
                        out_lines.append(f"{T}}}")
                    else:
                        out_lines.append(f"{T}{k} = {_hoi4_val(item)}")
                return out_lines
            if isinstance(v, dict):
                out_lines = [f"{T}{k} = {{"]
                for ik, iv in v.items():
                    if str(ik).startswith("_"):
                        continue
                    out_lines.extend(_hoi4_render_value(ik, iv, T + "\t"))
                out_lines.append(f"{T}}}")
                return out_lines
            # fallback — coerce anything else to string (should not happen)
            return [f"{T}{k} = {v}"]

        if t in _SCOPE_TYPES:

            out = [f"{I}{t} = {{"]
            limit_raw = str(g("limit", "")).strip()
            if limit_raw:
                out.append(f"{I}\tlimit = {{")
                inner = limit_raw.strip("{}").replace("'", '"')
                for ln in inner.splitlines():
                    ln = ln.strip().strip(",").strip()
                    if ln:
                        out.append(f"{I}\t\t{ln}")
                out.append(f"{I}\t}}")
            effect_raw = str(g("effect", "")).strip()
            if effect_raw:
                inner = effect_raw.strip("{}[]").replace("'", '"')
                for ln in inner.splitlines():
                    ln = ln.strip().strip(",")
                    if ln:
                        out.append(f"{I}\t{ln}")
            for k, v in f.items():
                if k in ("limit", "effect", "_list") or str(k).startswith("_"):
                    continue
                # Use the recursive renderer so lists/dicts/bools don't leak Python syntax
                if isinstance(v, (list, dict, bool)):
                    out.extend(_hoi4_render_value(k, v, f"{I}\t"))
                    continue
                vs = str(v).strip()
                if not vs:
                    continue
                if vs.startswith("{") and vs.endswith("}"):
                    inner2 = vs[1:-1].replace("'", '"').strip()
                    pairs = re.findall(r'"(\w+)"\s*[=:]\s*"([^"]*)"', inner2)
                    if pairs:
                        out.append(f"{I}\t{k} = {{")
                        for pk, pv in pairs:
                            out.append(f"{I}\t\t{pk} = {pv}")
                        out.append(f"{I}\t}}")
                    else:
                        out.append(f"{I}\t{k} = {vs}")
                else:
                    out.append(f"{I}\t{k} = {vs}")
            out.append(f"{I}}}")
            return "\n".join(out)

        # ── Generic fallback ───────────────────────────────────────
        defn = EFFECT_DEFS.get(t, {})
        fl = defn.get("fields", [])
        fname = fl[0][0] if fl else None
        if fname and len(fl) == 1:
            val = g(fname, "")
            if isinstance(val, (list, dict, bool)):
                rendered = _hoi4_render_value(fname, val, I)
                return "\n".join(rendered)
            val = str(val).strip()
            if val:
                return f"{I}{t} = {val}"
        raw_val = str(g("raw", "")).strip()
        if raw_val:
            return f"{I}{t} = {raw_val}"
        fields_clean = {
            k: v for k, v in f.items() if not str(k).startswith("_") and k != "raw"
        }
        if not fields_clean:
            return f"{I}{t} = yes"
        if len(fields_clean) == 1:
            k0, v0 = list(fields_clean.items())[0]
            if isinstance(v0, (list, dict, bool)):
                rendered = _hoi4_render_value(k0, v0, I)
                return "\n".join(rendered)
            if k0 in ("amount", "value", "flag", "tooltip", "category", "decision"):
                return f"{I}{t} = {v0}"
            return f"{I}{t} = {{ {k0} = {v0} }}"
        # Multi-field block — render each field recursively to handle nested structures
        inner_blocks = []
        for k, v in fields_clean.items():
            if isinstance(v, (list, dict, bool)):
                inner_blocks.extend(_hoi4_render_value(k, v, I + "\t"))
            else:
                inner_blocks.append(f"{I}\t{k} = {_hoi4_val(v)}")
        return f"{I}{t} = {{\n" + "\n".join(inner_blocks) + f"\n{I}}}"
