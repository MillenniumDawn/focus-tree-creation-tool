# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""MD Additional Income wizard."""

import os
import tkinter as tk
from tkinter import messagebox

from hoi4cm.core import (
    sanitize_component,
    tr,
)
from hoi4cm.mod import MOD
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BORDER_G,
    ORANGE,
    TEXT,
    TEXT_DIM,
)
from hoi4cm.wizards import _generators
from hoi4cm.wizards._shared import _LOC_KEY_RE, notifying_workspace_files


def _svar_get(var, default=""):
    if var is None or not hasattr(var, "get"):
        return default
    try:
        val = var.get()
        return val if isinstance(val, str) else str(val)
    except Exception:
        return default


def collect_additional_income_state(svars):
    """Collect additional-income wizard fields into plain strings.

    ``svars`` maps field names to ``tk.StringVar``-like objects
    (``.get()``). The returned dict is what ``_apply`` needs after
    stripping and normalising (``country_tag`` upper-cased, ``idea_id``
    sanitisation left to the caller).
    """

    def _get(key, default=""):
        return _svar_get(svars.get(key) if isinstance(svars, dict) else None, default)

    return {
        "idea_id": _get("idea_id").strip(),
        "country_tag": _get("country_tag").strip().upper(),
        "variable_name": _get("variable_name").strip(),
        "amount": _get("amount").strip(),
        "tooltip_key": _get("tooltip_key").strip(),
        "spirit_name": _get("spirit_name").strip(),
        "spirit_desc": _get("spirit_desc").strip(),
        "tooltip_text": _get("tooltip_text").strip(),
        "mode": _get("mode", "wire_only"),
        "formula_type": _get("formula_type", "fixed"),
    }


def open_additional_income_wizard(app):
    """MD Additional Income Wizard — creates/links a spirit and wires up all 3 money system files."""
    win = tk.Toplevel(app)
    win.title(tr("wizard.additional_income.title", "MD Additional Income Wizard"))
    win.configure(bg=BG_DARK)
    win.geometry("700x740")
    win.resizable(True, True)
    win.grab_set()

    # ── Header ───────────────────────────────────────────────────────────
    hdr = tk.Frame(win, bg="#0d2b1a", pady=8)
    hdr.pack(fill="x")
    tk.Label(
        hdr,
        text=tr("wizard.additional_income.header", "Additional Income Wizard"),
        bg="#0d2b1a",
        fg="#4ade80",
        font=("Helvetica", 13, "bold"),
    ).pack(side="left", padx=12)
    tk.Label(
        hdr,
        text=tr(
            "wizard.additional_income.subtitle",
            "Wires up 00_money_system.txt · money_scripted_localization.txt · MD_money_l_english.yml",
        ),
        bg="#0d2b1a",
        fg=TEXT_DIM,
        font=("Helvetica", 8),
    ).pack(side="left", padx=4)
    tk.Button(
        hdr,
        text="✕",
        command=win.destroy,
        bg="#0d2b1a",
        fg=TEXT_DIM,
        relief="flat",
        font=("Helvetica", 10),
        cursor="hand2",
    ).pack(side="right", padx=10)

    # ── Scrollable body ──────────────────────────────────────────────────
    body_outer = tk.Frame(win, bg=BG_DARK)
    body_outer.pack(fill="both", expand=True, padx=12, pady=8)

    def _lbl(parent, text, bold=False, dim=False):
        fg = TEXT_DIM if dim else TEXT
        font = ("Helvetica", 9, "bold") if bold else ("Helvetica", 9)
        tk.Label(parent, text=text, bg=BG_PANEL, fg=fg, font=font, anchor="w").pack(
            fill="x", pady=(6, 1)
        )

    def _field(parent, label, default, hint="", width=36):
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=2)
        tk.Label(
            row,
            text=label,
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            width=22,
            anchor="w",
        ).pack(side="left")
        var = tk.StringVar(value=default)
        e = tk.Entry(
            row,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            font=("Courier", 9),
            relief="flat",
            width=width,
            highlightthickness=1,
            highlightbackground=BORDER_G,
            insertbackground=TEXT,
        )
        e.pack(side="left", padx=4)
        if hint:
            tk.Label(
                row,
                text=hint,
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(side="left", padx=4)
        return var

    def _sep(parent):
        tk.Frame(parent, bg=BORDER_G, height=1).pack(fill="x", pady=6)

    # ── Section card ─────────────────────────────────────────────────────
    card = tk.Frame(
        body_outer, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER_G
    )
    card.pack(fill="both", expand=True)
    inner = tk.Frame(card, bg=BG_PANEL)
    inner.pack(fill="both", expand=True, padx=12, pady=8)

    # ── SECTION 1: Income Source Identity ────────────────────────────────
    tk.Label(
        inner,
        text=tr("income.section.identity", "  INCOME SOURCE IDENTITY"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Frame(inner, bg=BORDER_G, height=1).pack(fill="x", pady=(2, 6))

    _lbl(
        inner,
        tr("income.hint.identity", "The idea/spirit that gates this income source."),
    )
    v_idea_id = _field(
        inner,
        tr("income.field.idea_spirit_id", "Idea / Spirit ID"),
        "HKG_free_trade_bonus",
        "e.g. HKG_free_trade_bonus",
    )
    v_country_tag = _field(
        inner,
        tr("income.field.country_tag", "Country Tag"),
        "HKG",
        tr("income.hint.country_tag", "3-letter tag, e.g. HKG"),
    )

    _sep(inner)
    tk.Label(
        inner,
        text=tr("income.section.rate", "  INCOME RATE"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Frame(inner, bg=BORDER_G, height=1).pack(fill="x", pady=(2, 6))

    _lbl(
        inner,
        tr(
            "income.hint.rate",
            "Variable and amount used inside calculate_additional_income_rate.",
        ),
    )
    v_variable_name = _field(
        inner,
        tr("income.field.variable_name", "Variable Name"),
        "HKG_trade_income_gain",
        "e.g. HKG_trade_income_gain",
    )

    # ── Formula Type ───────────────────────────────────────────────────────
    formula_var = tk.StringVar(value="fixed")
    ftype_frm = tk.Frame(inner, bg=BG_PANEL)
    ftype_frm.pack(fill="x", pady=(4, 2))
    tk.Label(
        ftype_frm,
        text=tr("income.field.formula_type", "Formula Type:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=22,
        anchor="w",
    ).pack(side="left")
    for _val, _lbl_txt in [
        ("fixed", tr("income.formula.fixed", "Fixed rate  (e.g. 0.05 = +5%)")),
        (
            "gdp_pct",
            tr("income.formula.gdp_pct", "% of GDP  (e.g. 0.004 = 0.4% GDP/week)"),
        ),
        (
            "population",
            tr(
                "income.formula.population",
                "Per-capita  (e.g. 0.00016 x population_total)",
            ),
        ),
    ]:
        tk.Radiobutton(
            ftype_frm,
            text=_lbl_txt,
            variable=formula_var,
            value=_val,
            bg=BG_PANEL,
            fg=TEXT,
            selectcolor=BG_CARD,
            font=("Helvetica", 9),
            activebackground=BG_PANEL,
        ).pack(side="left", padx=6)

    # Dynamic hint label below formula selector
    hint_lbl = tk.Label(
        inner, text="", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 8), anchor="w"
    )
    hint_lbl.pack(fill="x", padx=4, pady=(0, 4))

    _FORMULA_HINTS = {
        "fixed": tr(
            "income.formula_hint.fixed",
            "Amount = fixed rate added to additional_income_rate.  e.g. 0.05",
        ),
        "gdp_pct": tr(
            "income.formula_hint.gdp_pct",
            "Amount = multiplier applied to gdp_total each week.  e.g. 0.004 (~20% of GDP/year)",
        ),
        "population": tr(
            "income.formula_hint.population",
            "Amount = multiplier applied to population_total.  e.g. 0.00016 (~$160 per million people)",
        ),
    }

    def _update_hint(*_):
        hint_lbl.config(text="  " + _FORMULA_HINTS.get(formula_var.get(), ""))

    formula_var.trace_add("write", _update_hint)
    _update_hint()

    v_amount = _field(
        inner,
        tr("income.field.amount_multiplier", "Amount / Multiplier"),
        "0.05",
        tr("income.hint.amount_multiplier", "value depends on formula type above"),
    )
    v_tooltip_key = _field(
        inner,
        tr("income.field.tooltip_key", "Tooltip Key"),
        "HKG_trade_income_TT",
        tr("income.hint.tooltip_key", "shown in spirit modifier section"),
    )

    _sep(inner)
    tk.Label(
        inner,
        text=tr(
            "income.section.spirit_details",
            "  SPIRIT / IDEA DETAILS  (for the idea file)",
        ),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Frame(inner, bg=BORDER_G, height=1).pack(fill="x", pady=(2, 6))

    _lbl(
        inner,
        tr(
            "income.hint.spirit_details",
            "These fill the localisation and idea block. You can edit the generated file after.",
        ),
    )
    v_spirit_name = _field(
        inner,
        tr("income.field.spirit_display_name", "Spirit Display Name"),
        "Free Trade Bonus",
        tr("income.hint.shown_in_game", "shown in-game"),
    )
    v_spirit_desc = _field(
        inner,
        tr("income.field.spirit_description", "Spirit Description"),
        "Our open trade policies generate additional government revenue.",
        "",
        width=48,
    )

    _sep(inner)
    tk.Label(
        inner,
        text=tr("income.section.tooltip_text", "  LOCALISATION TOOLTIP TEXT"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 8, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Frame(inner, bg=BORDER_G, height=1).pack(fill="x", pady=(2, 6))

    _lbl(
        inner,
        tr(
            "income.hint.tooltip_text",
            "Text shown in the Additional Income Revenues tooltip breakdown.",
        ),
    )
    v_tooltip_text = _field(
        inner,
        tr("income.field.tooltip_display_text", "Tooltip Display Text"),
        "+5% Additional Income from Free Trade",
        "",
        width=48,
    )

    _sep(inner)

    # ── file status display ───────────────────────────────────────────────
    status_frm = tk.Frame(
        inner, bg="#050810", highlightthickness=1, highlightbackground=BORDER_G
    )
    status_frm.pack(fill="x", pady=4)
    status_lbl = tk.Label(
        status_frm,
        text=tr(
            "income.status.load_mod_first",
            "  Load a mod first to enable automatic file editing.",
        ),
        bg="#050810",
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        anchor="w",
        justify="left",
        wraplength=620,
    )
    status_lbl.pack(fill="x", padx=6, pady=4)

    def _refresh_status():
        if not MOD.loaded or not MOD.root:
            status_lbl.config(
                text=tr(
                    "income.status.no_mod_loaded",
                    "  !  No mod loaded - load your mod first.",
                ),
                fg=ORANGE,
            )
            return
        MOD._scan_md_money_files()
        lines = []
        lines.append(f"  Mod: {MOD.root}")
        lines.append(
            f"  00_money_system.txt       {'✅ found' if MOD.md_money_system_file else '❌ not found'}"
        )
        lines.append(
            f"  money_scripted_loc.txt    {'✅ found  — ' + os.path.basename(MOD.md_money_scripted_loc_file) if MOD.md_money_scripted_loc_file else '❌ not found (will create)'}"
        )
        lines.append(
            f"  MD_money_l_english.yml    {'✅ found' if MOD.md_money_yml_file else '❌ not found (will create)'}"
        )
        status_lbl.config(text="\n".join(lines), fg=TEXT_DIM)

    _refresh_status()
    tk.Button(
        inner,
        text=tr("income.refresh_file_status", "Refresh File Status"),
        command=_refresh_status,
        bg=BG_CARD,
        fg=TEXT_DIM,
        font=("Helvetica", 8),
        relief="flat",
        padx=6,
        pady=2,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(anchor="e", pady=(2, 0))

    # ── Mode: create new spirit OR just wire existing ─────────────────────
    _sep(inner)
    mode_var = tk.StringVar(value="wire_only")
    mode_frm = tk.Frame(inner, bg=BG_PANEL)
    mode_frm.pack(fill="x", pady=2)
    tk.Label(
        mode_frm,
        text=tr("income.field.action", "Action:"),
        bg=BG_PANEL,
        fg=TEXT_DIM,
        font=("Helvetica", 9),
        width=22,
        anchor="w",
    ).pack(side="left")
    tk.Radiobutton(
        mode_frm,
        text=tr(
            "income.action.wire_only",
            "Wire up money system files only (spirit already exists)",
        ),
        variable=mode_var,
        value="wire_only",
        bg=BG_PANEL,
        fg=TEXT,
        selectcolor=BG_CARD,
        font=("Helvetica", 9),
        activebackground=BG_PANEL,
    ).pack(side="left", padx=4)
    tk.Radiobutton(
        mode_frm,
        text=tr("income.action.also_spirit", "Also generate spirit code snippet"),
        variable=mode_var,
        value="also_spirit",
        bg=BG_PANEL,
        fg=TEXT,
        selectcolor=BG_CARD,
        font=("Helvetica", 9),
        activebackground=BG_PANEL,
    ).pack(side="left", padx=4)

    # ── Results area ──────────────────────────────────────────────────────
    result_frm = tk.Frame(
        inner, bg="#050810", highlightthickness=1, highlightbackground=BORDER_G
    )
    result_frm.pack(fill="both", expand=True, pady=(6, 0))
    result_txt = tk.Text(
        result_frm,
        bg="#050810",
        fg="#8aad8a",
        font=("Courier", 8),
        relief="flat",
        height=8,
        state="disabled",
        wrap="word",
    )
    result_sb = tk.Scrollbar(result_frm, orient="vertical", command=result_txt.yview)
    result_txt.config(yscrollcommand=result_sb.set)
    result_sb.pack(side="right", fill="y")
    result_txt.pack(fill="both", expand=True, padx=4, pady=4)

    def _set_result(text, color="#8aad8a"):
        result_txt.config(state="normal")
        result_txt.delete("1.0", "end")
        result_txt.insert("1.0", text)
        result_txt.config(fg=color, state="disabled")

    # ── Apply button ──────────────────────────────────────────────────────
    def _apply():
        state = collect_additional_income_state(
            {
                "idea_id": v_idea_id,
                "country_tag": v_country_tag,
                "variable_name": v_variable_name,
                "amount": v_amount,
                "tooltip_key": v_tooltip_key,
                "spirit_name": v_spirit_name,
                "spirit_desc": v_spirit_desc,
                "tooltip_text": v_tooltip_text,
                "mode": mode_var,
                "formula_type": formula_var,
            }
        )
        idea_id = state["idea_id"]
        country_tag = state["country_tag"]
        variable_name = state["variable_name"]
        amount = state["amount"]
        tooltip_key = state["tooltip_key"]
        spirit_name = state["spirit_name"]
        spirit_desc = state["spirit_desc"]
        tooltip_text = state["tooltip_text"]
        mode = state["mode"]
        formula_type = state["formula_type"]

        if not idea_id or not variable_name or not amount or not tooltip_key:
            messagebox.showwarning(
                tr("dialog.missing_fields.title", "Missing Fields"),
                tr(
                    "income.dialog.missing_fields.body",
                    "Please fill in Idea ID, Variable Name, Amount, and Tooltip Key.",
                ),
                parent=win,
            )
            return

        # idea_id becomes an output filename below — keep it a safe segment.
        idea_id = sanitize_component(idea_id, fallback="new_idea")

        if not MOD.loaded or not MOD.root:
            messagebox.showwarning(
                tr("dialog.no_mod_loaded.title", "No Mod Loaded"),
                tr(
                    "income.dialog.no_mod_loaded.body",
                    "Load your mod first (File > Load Mod) so the tool can edit the money system files.",
                ),
                parent=win,
            )
            return

        output_lines = []

        # ── Run the 3-file writer ─────────────────────────────────────
        saved, errs = app._apply_md_additional_income(
            idea_id, variable_name, amount, tooltip_key, formula_type=formula_type
        )
        output_lines.append("── Money System Files ──────────────────────")
        output_lines.extend(saved)
        if errs:
            output_lines.append("")
            output_lines.append("⚠ Warnings / manual steps:")
            output_lines.extend(errs)

        # ── Also write localisation for tooltip ──────────────────────
        if tooltip_text and tooltip_key:
            loc_path = (
                MOD.edit_loc_file
                if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file)
                else os.path.join(
                    MOD.root, "localisation", "english", f"{idea_id}_l_english.yml"
                )
            )
            try:
                existing_keys = set()
                if os.path.isfile(loc_path):
                    with open(loc_path, encoding="utf-8-sig", errors="replace") as fp:
                        for line in fp:
                            m = _LOC_KEY_RE.match(line)
                            if m:
                                existing_keys.add(m.group(1))
                os.makedirs(os.path.dirname(loc_path), exist_ok=True)
                wf = notifying_workspace_files(MOD, MOD.root)
                to_write = {}
                if tooltip_key not in existing_keys:
                    to_write[tooltip_key] = (
                        f"$$[?{variable_name}|+3] from §Y${idea_id}$§!\\n"
                    )
                if not os.path.isfile(loc_path):
                    wf.write_text(loc_path, "l_english:\n", encoding="utf-8-sig")
                if to_write:
                    wf.append_text(
                        loc_path,
                        "".join(f' {k}: "{v}"\n' for k, v in to_write.items()),
                        encoding="utf-8-sig",
                    )
                    output_lines.append(
                        f"✅ {os.path.relpath(loc_path, MOD.root)}  — wrote tooltip localisation"
                    )
            except Exception as e:
                output_lines.append(f"❌ Tooltip localisation: {e}")

        # ── Generate spirit code snippet ──────────────────────────────
        if mode == "also_spirit":
            output_lines.append("")
            output_lines.append(
                "── Spirit Code Snippet (paste into your ideas file) ──"
            )
            snippet = _generators.build_income_spirit_snippet(
                idea_id=idea_id,
                country_tag=country_tag,
                variable_name=variable_name,
                tooltip_key=tooltip_key,
                spirit_name=spirit_name,
                spirit_desc=spirit_desc,
            )
            output_lines.append(snippet)

            # Copy to clipboard
            win.clipboard_clear()
            win.clipboard_append(snippet)
            output_lines.append("(Spirit snippet copied to clipboard)")

        _set_result("\n".join(output_lines), "#4ade80" if not errs else ORANGE)

    btn_row = tk.Frame(inner, bg=BG_PANEL)
    btn_row.pack(fill="x", pady=(8, 2))
    tk.Button(
        btn_row,
        text=tr("income.apply_wire_money", "Apply - Wire Up Money System Files"),
        command=_apply,
        bg="#14532d",
        fg="#4ade80",
        font=("Helvetica", 10, "bold"),
        relief="flat",
        pady=8,
        cursor="hand2",
        highlightthickness=0,
    ).pack(fill="x")
