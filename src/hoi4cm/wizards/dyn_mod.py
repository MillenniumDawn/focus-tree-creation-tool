# ruff: noqa: E501, F821, UP031, E741, B007, B008, B023, S311
# This file was extracted from hoi4_content_maker.py. The wizard body
# retains the original monolith's style (long lines, ambiguous names,
# percent-format strings, nested helpers referenced before def). Tightening
# any of this is a separate refactor.

"""Dynamic Modifier builder wizard."""

import glob
import json
import os
import re
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox

from hoi4cm.core import (
    add_error,
    autosave_path,
    get_logger,
    read_file_with_encoding,
    sanitize_component,
    tr,
)
from hoi4cm.mod import MOD, find_loc_files
from hoi4cm.script.syntax import parse_script, serialize_block
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER_G,
    ORANGE,
    TEXT,
    TEXT_DIM,
    open_folder_gfx_browser,
    report_error,
)
from hoi4cm.wizards._generators import (
    _parse_dyn_mod_line,
    build_dyn_mod_output,
)
from hoi4cm.wizards._graphics import browser_folders, collect_image_pairs
from hoi4cm.wizards._saves import save_dyn_mod
from hoi4cm.wizards._shared import (
    make_scrolled_listbox,
    open_trigger_picker,
    pack_action_footer,
    svar_get,
    text_get,
)


def collect_dyn_mod_state(svars, text_widgets):
    """Collect dynamic-modifier form state into kwargs for ``build_dyn_mod_output``."""
    scope = svar_get(svars.get("scope") if isinstance(svars, dict) else None, "country")
    if not scope.strip():
        scope = "country"
    return {
        "mod_id": svar_get(svars.get("mod_id") if isinstance(svars, dict) else None),
        "scope": scope,
        "icon": svar_get(svars.get("icon") if isinstance(svars, dict) else None),
        "enable": text_get(
            text_widgets.get("enable") if isinstance(text_widgets, dict) else None
        ),
        "mods_raw": text_get(
            text_widgets.get("mods") if isinstance(text_widgets, dict) else None
        ),
        "const": text_get(
            text_widgets.get("const") if isinstance(text_widgets, dict) else None
        ),
        "loc_name": svar_get(
            svars.get("loc_name") if isinstance(svars, dict) else None
        ),
        "loc_desc": svar_get(
            svars.get("loc_desc") if isinstance(svars, dict) else None
        ),
    }


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
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            get_logger("dyn_mod").debug("autosave failed: %s", exc, exc_info=True)
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
        mod_root = getattr(MOD, "root", "") or ""
        ideas_path = getattr(MOD, "path_ideas_gfx", "") or ""
        ideas_root = os.path.join(mod_root, ideas_path) if MOD.loaded else None
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
                tr("dialog.no_folders.title", "No Folders"),
                tr(
                    "dialog.no_ideas_gfx_folders",
                    "No image files or subfolders found in the ideas GFX path.",
                ),
                parent=win,
            )
            return
        open_folder_gfx_browser(
            win,
            title=tr(
                "gfx.browser.ideas_dynamic_title",
                "GFX Browser  -  Ideas / Dynamic Modifier",
            ),
            folders=folders,
            collect_pairs=lambda folder_path, search: collect_image_pairs(
                folder_path, "GFX_idea_", search=search.strip(), catalog=catalog
            ),
            on_select=v_icon.set,
            label_prefixes=("GFX_idea_", "GFX_focus_"),
            image_size=(80, 70),
            preserve_aspect=True,
        )

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
    tk.Button(
        frm,
        text=tr("trigger_picker.button", "+ Insert trigger"),
        command=lambda: open_trigger_picker(win, v_enable, on_insert=_preview),
        bg=BG_CARD,
        fg=BLUE,
        relief="flat",
        font=("Helvetica", 8),
        cursor="hand2",
        padx=6,
        pady=1,
        highlightthickness=1,
        highlightbackground=BORDER_G,
    ).pack(anchor="e", padx=12, pady=(0, 2))

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
    _dm_raw_override: list[str | None] = [None]

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
                        changes.append(
                            tr(
                                "dynamic_modifier.change.modifier_id",
                                "Modifier ID → {value}",
                                value=repr(new_id),
                            )
                        )
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
                            changes.append(
                                tr(
                                    "dynamic_modifier.change.enable_updated",
                                    "enable trigger updated",
                                )
                            )
                        enable_buf = []
                        continue
                enable_buf.append(ln)
                continue

            m = re.match(r"scope\s*=\s*(\w+)", s)
            if m:
                if m.group(1) != v_scope.get():
                    v_scope.set(m.group(1))
                    changes.append(
                        tr(
                            "dynamic_modifier.change.scope",
                            "Scope → {value}",
                            value=repr(m.group(1)),
                        )
                    )
                continue
            m = re.match(r"icon\s*=\s*(\S+)", s)
            if m:
                if m.group(1) != v_icon.get():
                    v_icon.set(m.group(1))
                    changes.append(
                        tr(
                            "dynamic_modifier.change.icon_gfx",
                            "Icon GFX → {value}",
                            value=repr(m.group(1)),
                        )
                    )
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
                        tr(
                            "dynamic_modifier.warning.constant_modifier",
                            "Constant modifier {modifier} = {value} "
                            "— check Constant Modifiers field",
                            modifier=key,
                            value=val,
                        )
                    )
                except ValueError:
                    warnings.append(
                        tr(
                            "dynamic_modifier.warning.variable_modifier",
                            "Variable modifier {modifier} = {value} "
                            "— check Variable Modifiers field",
                            modifier=key,
                            value=val,
                        )
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
                            changes.append(
                                tr(
                                    "dynamic_modifier.change.description",
                                    "Description → {value}",
                                    value=repr(val),
                                )
                            )
                    elif "_tt" not in key:
                        if val != v_loc_name.get():
                            v_loc_name.set(val)
                            changes.append(
                                tr(
                                    "dynamic_modifier.change.display_name",
                                    "Display name → {value}",
                                    value=repr(val),
                                )
                            )

        _dm_lock_lbl.config(
            text=tr("common.raw_override_active", "raw override active"), fg=ORANGE
        )

        parts = []
        if changes:
            parts.append(
                tr(
                    "dynamic_modifier.review.fields_updated",
                    "Fields updated from your code:",
                )
                + "\n"
                + "\n".join(f"  • {c}" for c in changes)
            )
        if warnings:
            parts.append(
                tr(
                    "dynamic_modifier.review.check_fields",
                    "Please check these fields manually:",
                )
                + "\n"
                + "\n".join(f"  ⚠ {w}" for w in warnings)
            )
        if not changes and not warnings:
            parts.append(
                tr(
                    "dynamic_modifier.review.no_changes",
                    "No field changes detected. Raw override saved.",
                )
            )
        parts.append(
            "\n"
            + tr(
                "dynamic_modifier.review.exports_as_shown",
                "The output will export exactly as shown in the preview.",
            )
        )

        messagebox.showinfo(
            tr("dialog.saved_review.title", "Saved — Review Changes"),
            "\n\n".join(parts),
            parent=win,
        )

    def _dm_show_preview():
        try:
            text = _dm_get_output()
        # intentional: generator may raise any Exception
        except Exception as exc:  # noqa: BLE001
            get_logger("dyn_mod").error("Preview build failed: %s", exc, exc_info=True)
            add_error(
                f"Dynamic modifier preview failed: {exc}\n{traceback.format_exc()}"
            )
            return
        try:
            preview.config(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", text)
            if not _dm_edit_mode[0]:
                preview.config(state="disabled")
        except tk.TclError:
            pass

    _dm_edit_btn.config(command=_dm_toggle_edit)
    _dm_save_raw_btn.config(command=_dm_save_raw)

    # Real builder + line parser live in _generators.py (headless-testable).
    def _parse_mod_line(ln):
        return _parse_dyn_mod_line(ln)

    def _build_output():
        state = collect_dyn_mod_state(
            {
                "mod_id": v_id,
                "scope": v_scope,
                "icon": v_icon,
                "loc_name": v_loc_name,
                "loc_desc": v_loc_desc,
            },
            {"enable": v_enable, "mods": v_mods, "const": v_const},
        )
        return build_dyn_mod_output(**state, loc_language=MOD.loc_language)

    def _preview(*_):
        if _dm_edit_mode[0]:
            return
        if _dm_raw_override[0] is not None:
            return
        try:
            text = _build_output()
        # intentional: builder may raise any Exception
        except Exception as exc:  # noqa: BLE001
            get_logger("dyn_mod").error("Preview build failed: %s", exc, exc_info=True)
            add_error(
                f"Dynamic modifier preview failed: {exc}\n{traceback.format_exc()}"
            )
            return
        try:
            preview.config(state="normal")
            preview.delete("1.0", "end")
            preview.insert("1.0", text)
            preview.config(state="disabled")
        except tk.TclError:
            pass

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
            title=tr(
                "filedialog.dynamic_modifier_mod_root",
                "Select your MOD ROOT folder "
                "(the folder that contains common/, localisation/, …)",
            )
        )
        if not mod_root:
            return

        results, errors = save_dyn_mod(
            MOD,
            mod_root,
            mid=mid,
            icon=icon,
            name=name,
            desc=desc,
            scope=scope,
            enable=enable,
            mod_entries=mod_entries,
            const_lines=const_lines,
        )

        # ── Summary ───────────────────────────────────────────
        if errors:
            report_error(
                "\n".join(errors),
                title=tr(
                    "dynamic_modifier.dialog.generation_errors.title",
                    "Errors during file generation",
                ),
            )

        lines = [
            tr("dynamic_modifier.summary.mod_root", "Mod root: {path}", path=mod_root)
            + "\n"
        ]
        for rel, action, note in results:
            note_str = f"  ({note})" if note else ""
            lines.append(f"  [{action}]  {rel}{note_str}")
        lines += [
            "",
            tr("dynamic_modifier.summary.next_steps", "Next steps:"),
            tr(
                "dynamic_modifier.summary.step_copy_snippet",
                "  1. Copy snippet from _focus_snippets/ into your focus .txt",
            ),
            tr(
                "dynamic_modifier.summary.step_add_effect",
                "  2. Add add_dynamic_modifier effect to activate the modifier",
            ),
            tr(
                "dynamic_modifier.summary.step_add_icon",
                "  3. Add icon .dds to gfx/interface/ideas/ if needed",
            ),
            tr(
                "dynamic_modifier.summary.step_restart",
                "  4. Restart HOI4 (dynamic modifiers require full restart)",
            ),
        ]
        messagebox.showinfo(
            (
                tr("dynamic_modifier.dialog.done.title", "Done")
                if not errors
                else tr(
                    "dynamic_modifier.dialog.done_with_errors.title",
                    "Done (with errors)",
                )
            ),
            "\n".join(lines),
        )

    def _browse_mod_dynmods():
        if not MOD.loaded or not MOD.root:
            messagebox.showinfo(
                tr("dialog.no_mod_loaded.title", "No Mod Loaded"),
                tr(
                    "dynamic_modifier.dialog.load_mod_to_browse",
                    "Load a mod first to browse existing dynamic modifiers.",
                ),
                parent=win,
            )
            return
        dm_dir = os.path.join(MOD.root, "common", "dynamic_modifiers")
        if not os.path.isdir(dm_dir):
            messagebox.showinfo(
                tr("dialog.not_found.title", "Not Found"),
                tr(
                    "dynamic_modifier.dialog.no_directory",
                    "No common/dynamic_modifiers/ directory found in mod.",
                ),
                parent=win,
            )
            return

        # Scan all files for modifier IDs
        mods = []  # list of (modifier_id, file_path)
        for fp in sorted(glob.glob(os.path.join(dm_dir, "*.txt"))):
            try:
                src, encoding = read_file_with_encoding(fp)
                if not src:
                    continue
                parsed = parse_script(src)
                for k, v in parsed.items():
                    if k not in ("_values", "=") and isinstance(v, dict):
                        mods.append((k, fp))
            except OSError, ValueError, RuntimeError:
                pass

        if not mods:
            messagebox.showinfo(
                tr("dynamic_modifier.dialog.no_modifiers.title", "No Modifiers Found"),
                tr(
                    "dynamic_modifier.dialog.no_modifiers.body",
                    "No dynamic modifier definitions found.",
                ),
                parent=win,
            )
            return

        dlg = tk.Toplevel(win)
        dlg.title(tr("dynamic_modifier.browse.title", "Browse Mod Dynamic Modifiers"))
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
        lb = make_scrolled_listbox(frm)
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
                src, encoding = read_file_with_encoding(fp)
                if src is None or encoding is None:
                    report_error(
                        tr(
                            "dynamic_modifier.error.read_modifier",
                            "Could not read modifier '{name}'",
                            name=modifier_id,
                        ),
                        parent=dlg,
                        title=tr("dialog.read_error.title", "Read Error"),
                    )
                    return
                parsed = parse_script(src)
                blk = parsed.get(modifier_id, {})
                if not isinstance(blk, dict):
                    report_error(
                        tr(
                            "dynamic_modifier.error.parse_modifier",
                            "Could not parse modifier '{name}'",
                            name=modifier_id,
                        ),
                        parent=dlg,
                        title=tr("dialog.parse_error.title", "Parse Error"),
                    )
                    return
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                report_error(
                    str(exc),
                    exc,
                    parent=dlg,
                    title=tr("dialog.parse_error.title", "Parse Error"),
                )
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
            for loc_path in find_loc_files(MOD.root, language=MOD.loc_language):
                try:
                    loc_src, encoding = read_file_with_encoding(loc_path)
                    if loc_src is None:
                        continue
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
                except OSError, ValueError, UnicodeDecodeError:
                    pass
            v_loc_name.set(loc_name)
            v_loc_desc.set(loc_desc)

            _preview()
            dlg.destroy()
            app._hint(
                tr(
                    "dynamic_modifier.hint.loaded",
                    "Loaded dynamic modifier '{name}' from {file}",
                    name=modifier_id,
                    file=os.path.basename(fp),
                )
            )

        lb.bind("<Double-Button-1>", lambda e: _load_selected())
        pack_action_footer(
            dlg, tr("common.load_selected", "Load Selected"), _load_selected
        )

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
