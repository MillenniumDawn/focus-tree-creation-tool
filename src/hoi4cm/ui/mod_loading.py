"""Mod loading + Millennium Dawn detection glue.

Extracted from the monolith as a mixin; the methods keep operating on ``App``
state via ``self`` (so behaviour is identical). ``_apply_md_visibility`` stays
in the monolith because it rebinds the module-global ``EFFECT_CATS`` — the
methods here call it via ``self``.
"""

import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from hoi4cm.core import default_hoi4_mod_dir, tr
from hoi4cm.mod import MOD
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BLUE,
    BORDER,
    BORDER_G,
    GREEN,
    SEL_BG,
    TEXT,
    TEXT_DIM,
    _safe_after,
)
from hoi4cm.wizards import _shared as _wiz_shared

# Alias used by the moved methods (matches the monolith's alias).
_default_hoi4_mod_dir = default_hoi4_mod_dir


class ModLoadingMixin:
    """Mod picking/scanning, post-load prompt and MD additional-income setup."""

    def _load_mod_path(self, root):
        """Load a mod directly from a known path (used by Recent Mods menu)."""
        if not root or not os.path.isdir(root):
            messagebox.showerror(
                tr("dialog.mod_not_found.title", "Mod Not Found"),
                tr(
                    "dialog.mod_not_found.body",
                    "The folder no longer exists:\n{path}",
                    path=root,
                ),
                parent=self,
            )
            # Remove stale entry
            if hasattr(MOD, "_recent_mods") and root in MOD._recent_mods:
                MOD._recent_mods.remove(root)
                MOD.save_config()
            return
        # Reuse _load_mod flow by temporarily monkeypatching the dialog
        orig = __import__("tkinter.filedialog", fromlist=["askdirectory"]).askdirectory
        import tkinter.filedialog as _fd

        _fd.askdirectory = lambda **kw: root
        try:
            self._load_mod()
        finally:
            _fd.askdirectory = orig

    def _load_mod(self):
        _hoi4_mod_dir = _default_hoi4_mod_dir()
        _custom = getattr(MOD, "custom_mod_path", "")
        _init_dir = (
            _custom
            if _custom and os.path.isdir(_custom)
            else _hoi4_mod_dir
            if os.path.isdir(_hoi4_mod_dir)
            else os.path.expanduser("~")
        )
        root = filedialog.askdirectory(
            title=tr(
                "filedialog.select_mod_root",
                "Select Mod Root Folder (contains common/, events/, gfx/, ... )",
            ),
            initialdir=_init_dir,
        )
        if not root:
            return

        # ── Record in recent mods ─────────────────────────────────────────────
        if not hasattr(MOD, "_recent_mods"):
            MOD._recent_mods = []
        if root in MOD._recent_mods:
            MOD._recent_mods.remove(root)
        MOD._recent_mods.insert(0, root)
        MOD._recent_mods = MOD._recent_mods[:8]  # keep 8 most recent
        MOD.save_config()

        # Progress window
        pw = tk.Toplevel(self)
        pw.title(tr("mod.loading.title", "Loading Mod..."))
        pw.configure(bg=BG_DARK)
        pw.geometry("420x140")
        pw.resizable(False, False)
        pw.grab_set()
        pw.protocol("WM_DELETE_WINDOW", lambda: None)  # block close during load

        tk.Label(
            pw,
            text=tr("mod.loading.scanning", "Scanning mod folder..."),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 10, "bold"),
            pady=12,
        ).pack()
        prog_lbl = tk.Label(pw, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 9))
        prog_lbl.pack()
        bar_frame = tk.Frame(pw, bg=BORDER_G, height=6, width=380)
        bar_frame.pack(pady=8)
        bar_fill = tk.Frame(bar_frame, bg=BLUE, height=6, width=0)
        bar_fill.place(x=0, y=0, height=6)
        status_lbl = tk.Label(
            pw, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 8, "italic")
        )
        status_lbl.pack()

        def progress(i, total, label):
            pct = int((i / total) * 380) if total else 380
            _safe_after(
                pw,
                0,
                lambda i=i, t=total, l=label, p=pct: [
                    prog_lbl.config(
                        text=tr(
                            "mod.loading.step",
                            "Step {step}/{total}: {label}",
                            step=i,
                            total=t,
                            label=l,
                        )
                    ),
                    bar_fill.place_configure(width=p),
                    pw.update_idletasks(),
                ],
            )

        def worker():
            MOD.scan(root, progress_cb=progress)
            _safe_after(pw, 0, lambda: self._on_mod_loaded(pw, root))

        threading.Thread(target=worker, daemon=True).start()

    def _on_mod_loaded(self, pw, root):
        pw.grab_release()
        pw.destroy()
        mod_name = os.path.basename(root)
        md_badge = "  ⚡MD" if MOD.is_md else ""
        self._mod_lbl.config(
            text="📂 %s%s  |  %s" % (mod_name, md_badge, MOD.summary()),
            fg="#a78bfa" if MOD.is_md else GREEN,
        )
        self._apply_md_visibility()
        self._refresh_mod_dropdowns()
        self._update_statusbar()
        # Invalidate all focus draw caches so mod images render on next frame
        for f in self.focuses.values():
            f._draw_key = None
            f._items = []
        self.cv.delete("focus")
        self._redraw_now()
        # Clear all wizard image caches so new mod GFX loads fresh. The live
        # caches live in hoi4cm.wizards._shared (the event and decision wizards
        # register theirs there), not in this module.
        for _c in _wiz_shared._app_img_caches:
            _c.clear()
        # Load first sprite as a quick PIL sanity check
        test_names = list(MOD.sprites.keys())[:1]
        for tn in test_names:
            MOD.get_image(tn)

        sample = list(MOD.sprites.keys())[:5]
        sample_txt = (
            "\n".join("  " + n for n in sample)
            if sample
            else tr("mod.loaded.no_sample_gfx", "  (none - check interface/*.gfx)")
        )
        sampled_items = list(MOD.sprites.items())[:50]
        missing_items = [(k, p) for k, p in sampled_items if not os.path.exists(p)]
        if missing_items:
            _lines = []
            for _k, _p in missing_items[:5]:
                _lines.append("  %s\n    path: %s" % (_k, _p))
            _more = (
                (" (+ %d more)" % (len(missing_items) - 5))
                if len(missing_items) > 5
                else ""
            )
            disk_note = "\n\n" + tr(
                "mod.loaded.missing_textures",
                "WARNING: {missing}/{total} sampled textures not on disk{more}\nThis is likely a missing asset in the mod, not a tool error.\nMissing GFX entries:\n{entries}",
                missing=len(missing_items),
                total=len(sampled_items),
                more=_more,
                entries="\n".join(_lines),
            )
        else:
            disk_note = ""
        err_note = ""
        if MOD._img_errors:
            err_note = (
                "\n\n"
                + tr("mod.loaded.image_errors", "Image errors (first 3):")
                + "\n"
                + "\n".join(MOD._img_errors[:3])
            )
        messagebox.showinfo(
            tr("dialog.mod_loaded.title", "Mod Loaded"),
            tr(
                "dialog.mod_loaded.body",
                "Mod: {mod}\n\n{summary}\n\nSample GFX names:\n{sample}{disk_note}{err_note}",
                mod=mod_name,
                summary=MOD.summary().replace("  •  ", "\n"),
                sample=sample_txt,
                disk_note=disk_note,
                err_note=err_note,
            ),
        )
        # Prompt user to pick edit targets for ideas/events files
        self.after(150, self._show_post_load_prompt)

    def _show_post_load_prompt(self):
        """Dialog to pick which existing ideas/events files to append new content to."""
        if not (MOD.loaded and MOD.root):
            messagebox.showinfo(
                tr("dialog.no_mod.title", "No Mod"),
                tr("dialog.no_mod.body", "Please load a mod first."),
                parent=self,
            )
            return
        root = MOD.root
        ideas_dir = os.path.join(root, "common", "ideas")
        events_dir = os.path.join(root, "events")
        idea_files = (
            sorted([f for f in os.listdir(ideas_dir) if f.endswith(".txt")])
            if os.path.isdir(ideas_dir)
            else []
        )
        event_files = (
            sorted([f for f in os.listdir(events_dir) if f.endswith(".txt")])
            if os.path.isdir(events_dir)
            else []
        )

        dlg = tk.Toplevel(self)
        dlg.title(tr("edit_targets.title", "Set Edit Targets"))
        dlg.configure(bg=BG_DARK)
        # Cap height to screen height - 80px so the dialog always fits
        _sh = dlg.winfo_screenheight()
        dlg.geometry("640x%d" % min(700, _sh - 80))
        dlg.resizable(True, True)
        dlg.grab_set()

        # ── Header (pinned, not scrolled) ─────────────────────────────────
        tk.Label(
            dlg,
            text=tr("edit_targets.header", "  SET EDIT TARGETS"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=10,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            dlg,
            text=tr(
                "edit_targets.description",
                "  Choose which existing files new content will be appended to.\n  New content is always placed at the END of the file - nothing existing is changed.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=10)
        tk.Frame(dlg, bg=BORDER_G, height=1).pack(fill="x", pady=(6, 0))

        # ── Bottom bar (packed BEFORE scrollable body so it's always visible) ──
        tk.Frame(dlg, bg=BORDER_G, height=1).pack(fill="x", side="bottom")
        bot = tk.Frame(dlg, bg=BG_DARK)
        bot.pack(fill="x", padx=14, pady=10, side="bottom")

        # ── Scrollable body ────────────────────────────────────────────────
        _body_outer = tk.Frame(dlg, bg=BG_DARK)
        _body_outer.pack(fill="both", expand=True)
        _body_vsb = tk.Scrollbar(_body_outer, orient="vertical")
        _body_vsb.pack(side="right", fill="y")
        _body_cv = tk.Canvas(
            _body_outer, bg=BG_DARK, highlightthickness=0, yscrollcommand=_body_vsb.set
        )
        _body_cv.pack(side="left", fill="both", expand=True)
        _body_vsb.config(command=_body_cv.yview)
        body = tk.Frame(_body_cv, bg=BG_DARK)
        _body_win = _body_cv.create_window((0, 0), window=body, anchor="nw")

        def _body_configure(e):
            _body_cv.configure(scrollregion=_body_cv.bbox("all"))

        def _body_width(e):
            _body_cv.itemconfig(_body_win, width=e.width)

        body.bind("<Configure>", _body_configure)
        _body_cv.bind("<Configure>", _body_width)

        def _on_mousewheel(e):
            # Only scroll outer canvas if the event widget is NOT a Listbox
            if not isinstance(e.widget, tk.Listbox):
                _body_cv.yview_scroll(int(-1 * (e.delta / 120)), "units")

        dlg.bind_all("<MouseWheel>", _on_mousewheel)
        dlg.bind(
            "<Destroy>",
            lambda e: dlg.unbind_all("<MouseWheel>") if e.widget is dlg else None,
        )

        # inner padding frame so content isn't flush against the canvas edge
        body_pad = tk.Frame(body, bg=BG_DARK)
        body_pad.pack(fill="both", expand=True, padx=14, pady=10)
        body = body_pad  # sections use this as their parent

        ideas_path_var = tk.StringVar(value=MOD.edit_ideas_file)
        events_path_var = tk.StringVar(value=MOD.edit_events_file)
        focus_path_var = tk.StringVar(value=MOD.edit_focus_file)
        loc_path_var = tk.StringVar(value=MOD.edit_loc_file)
        scripted_loc_path_var = tk.StringVar(value=MOD.edit_scripted_loc_file)

        def _make_section(
            parent,
            title,
            path_var,
            file_list,
            browse_dir,
            browse_title,
            browse_ftypes=(("HOI4 txt", "*.txt"), ("All", "*.*")),
        ):
            """Build a section with entry + browse + quick-pick listbox."""
            tk.Label(
                parent,
                text=title,
                bg=BG_DARK,
                fg=TEXT,
                font=("Helvetica", 9, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(10, 2))
            row = tk.Frame(parent, bg=BG_DARK)
            row.pack(fill="x")
            ent = tk.Entry(
                row,
                textvariable=path_var,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Courier", 9),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            ent.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 4))

            def _browse(pv=path_var, bd=browse_dir, bt=browse_title, ft=browse_ftypes):
                p = filedialog.askopenfilename(
                    parent=dlg,
                    title=bt,
                    initialdir=bd if os.path.isdir(bd) else root,
                    filetypes=ft,
                )
                if p:
                    pv.set(p)

            tk.Button(
                row,
                text=tr("common.browse", "Browse"),
                command=_browse,
                bg=BG_CARD,
                fg=TEXT_DIM,
                relief="flat",
                font=("Helvetica", 9),
                cursor="hand2",
                padx=8,
                pady=3,
            ).pack(side="right")
            if file_list:
                tk.Label(
                    parent,
                    text=tr(
                        "edit_targets.quick_pick",
                        "  Quick-pick (double-click to select):",
                    ),
                    bg=BG_DARK,
                    fg=TEXT_DIM,
                    font=("Helvetica", 8, "italic"),
                    anchor="w",
                ).pack(fill="x", pady=(4, 0))
                lbf = tk.Frame(parent, bg=BG_DARK)
                lbf.pack(fill="x")
                lb = tk.Listbox(
                    lbf,
                    bg=BG_CARD,
                    fg=TEXT_DIM,
                    selectbackground=SEL_BG,
                    selectforeground=TEXT,
                    font=("Courier", 9),
                    height=min(4, len(file_list)),
                    relief="flat",
                    bd=0,
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                    activestyle="none",
                )
                sb = tk.Scrollbar(lbf, orient="vertical", command=lb.yview)
                lb.configure(yscrollcommand=sb.set)
                sb.pack(side="right", fill="y")
                lb.pack(side="left", fill="x", expand=True)
                for f in file_list:
                    lb.insert("end", "  " + f)
                # Highlight current selection if it matches
                cur = os.path.basename(path_var.get())
                for i, f in enumerate(file_list):
                    if f == cur:
                        lb.selection_set(i)
                        lb.see(i)
                        break

                def _pick(evt, fl=file_list, bd=browse_dir, pv=path_var):
                    s = lb.curselection()
                    if s:
                        pv.set(os.path.join(bd, fl[s[0]]))

                lb.bind("<<ListboxSelect>>", _pick)
            # Show "none set" hint if empty
            hint_var = tk.StringVar()

            def _update_hint(*_):
                v = path_var.get().strip()
                if v and os.path.isfile(v):
                    hint_var.set("  ✓  " + os.path.basename(v))
                elif v:
                    hint_var.set(
                        tr(
                            "edit_targets.file_not_found",
                            "  WARNING: File not found - new file will be created",
                        )
                    )
                else:
                    hint_var.set(
                        tr(
                            "edit_targets.leave_blank",
                            "  -  Leave blank to create a new file on save",
                        )
                    )

            path_var.trace_add("write", _update_hint)
            _update_hint()
            tk.Label(
                parent,
                textvariable=hint_var,
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
                anchor="w",
            ).pack(fill="x")

        _make_section(
            body,
            tr(
                "edit_targets.ideas_file",
                "Ideas / National Spirits file  (new spirits appended at end):",
            ),
            ideas_path_var,
            idea_files,
            ideas_dir,
            tr("filedialog.select_ideas_txt", "Select Ideas .txt file"),
        )
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)
        _make_section(
            body,
            tr(
                "edit_targets.events_file",
                "Events file  (new events appended at end, existing content untouched):",
            ),
            events_path_var,
            event_files,
            events_dir,
            tr("filedialog.select_events_txt", "Select Events .txt file"),
        )

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)

        # ── auto-detect national_focus files in the mod ───────────────
        focus_files = []
        focus_dir = ""
        if MOD.root and os.path.isdir(MOD.root):
            _fd = os.path.join(MOD.root, "common", "national_focus")
            if os.path.isdir(_fd):
                focus_dir = _fd
                focus_files = sorted(
                    f for f in os.listdir(_fd) if f.lower().endswith(".txt")
                )

        _make_section(
            body,
            tr(
                "edit_targets.focus_file",
                "Focus Tree file  (overwritten in-place on Export):",
            ),
            focus_path_var,
            focus_files,
            focus_dir or (MOD.root or ""),
            tr(
                "filedialog.select_national_focus_txt",
                "Select national_focus .txt file",
            ),
        )

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)

        # ── auto-detect loc files in the mod ──────────────────────────
        loc_files = []
        loc_dir = ""
        if MOD.root and os.path.isdir(MOD.root):
            _ld = os.path.join(MOD.root, "localisation")
            if os.path.isdir(_ld):
                loc_dir = _ld
                loc_files = sorted(
                    f
                    for f in os.listdir(_ld)
                    if f.lower().endswith(".yml") and "english" in f.lower()
                )
                if not loc_files:
                    loc_files = sorted(
                        f for f in os.listdir(_ld) if f.lower().endswith(".yml")
                    )

        _make_section(
            body,
            tr(
                "edit_targets.loc_file",
                "Localisation file  (new loc entries appended at end, english):",
            ),
            loc_path_var,
            loc_files,
            loc_dir or (MOD.root or ""),
            tr("filedialog.select_localisation_yml", "Select localisation .yml file"),
            browse_ftypes=(("YML localisation", "*.yml"), ("All", "*.*")),
        )

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=6)

        # ── auto-detect scripted_localisation files ───────────────────
        sloc_files = []
        sloc_dir = ""
        if MOD.root and os.path.isdir(MOD.root):
            _sld = os.path.join(MOD.root, "common", "scripted_localisation")
            if os.path.isdir(_sld):
                sloc_dir = _sld
                sloc_files = sorted(
                    f for f in os.listdir(_sld) if f.lower().endswith(".txt")
                )

        _make_section(
            body,
            tr(
                "edit_targets.scripted_loc_file",
                "Scripted Localisation file  (new defined_text blocks appended):",
            ),
            scripted_loc_path_var,
            sloc_files,
            sloc_dir or (MOD.root or ""),
            tr(
                "filedialog.select_scripted_localisation_txt",
                "Select scripted_localisation .txt file",
            ),
            browse_ftypes=(("HOI4 txt", "*.txt"), ("All", "*.*")),
        )

        # ── Bottom bar buttons (bot frame already created above the scroll area) ──
        tk.Label(
            bot,
            text=tr(
                "edit_targets.footer_hint",
                "You can change these any time via Set Edit Targets in the toolbar.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
        ).pack(side="left")

        def _skip():
            dlg.grab_release()
            dlg.destroy()

        def _confirm():
            MOD.edit_ideas_file = ideas_path_var.get().strip()
            MOD.edit_events_file = events_path_var.get().strip()
            MOD.edit_focus_file = focus_path_var.get().strip()
            MOD.edit_loc_file = loc_path_var.get().strip()
            MOD.edit_scripted_loc_file = scripted_loc_path_var.get().strip()
            # Auto-detect namespace from events file
            MOD.edit_events_ns = ""
            if MOD.edit_events_file and os.path.isfile(MOD.edit_events_file):
                try:
                    with open(
                        MOD.edit_events_file, encoding="utf-8", errors="replace"
                    ) as f:
                        raw = f.read(4096)
                    m = re.search(r"add_namespace\s*=\s*(\S+)", raw)
                    MOD.edit_events_ns = (
                        m.group(1).strip()
                        if m
                        else os.path.splitext(os.path.basename(MOD.edit_events_file))[0]
                    )
                except Exception:
                    pass
            # Update mod label
            parts = []
            if MOD.edit_ideas_file:
                parts.append("ideas: " + os.path.basename(MOD.edit_ideas_file))
            if MOD.edit_events_file:
                parts.append("events: " + os.path.basename(MOD.edit_events_file))
            if MOD.edit_focus_file:
                parts.append("focus: " + os.path.basename(MOD.edit_focus_file))
            if MOD.edit_loc_file:
                parts.append("loc: " + os.path.basename(MOD.edit_loc_file))
            if MOD.edit_scripted_loc_file:
                parts.append("sloc: " + os.path.basename(MOD.edit_scripted_loc_file))
            if parts and hasattr(self, "_mod_lbl"):
                base = self._mod_lbl.cget("text").split("  |  edit:")[0]
                self._mod_lbl.config(text=base + "  |  edit: " + "  +  ".join(parts))
            dlg.grab_release()
            dlg.destroy()

        tk.Button(
            bot,
            text=tr("common.skip", "Skip"),
            command=_skip,
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 10),
            cursor="hand2",
            padx=12,
            pady=5,
        ).pack(side="right", padx=4)
        tk.Button(
            bot,
            text=tr("common.confirm", "Confirm"),
            command=_confirm,
            bg="#14532d",
            fg="#c8f0d8",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            cursor="hand2",
            padx=16,
            pady=5,
        ).pack(side="right")

    def _refresh_mod_dropdowns(self):
        """Update all dynamic dropdowns that depend on mod data."""
        # Refresh the GFX picker dropdown if visible
        if hasattr(self, "_gfx_dd") and self._gfx_dd:
            sprite_names = sorted(MOD.sprites.keys())
            if sprite_names:
                menu = self._gfx_dd["menu"]
                menu.delete(0, "end")
                for name in sprite_names:
                    menu.add_command(
                        label=name, command=lambda n=name: self._set_gfx(n)
                    )
        # Rebuild effect cards if open (they may have mod-aware dropdowns)
        if self.selected:
            self._refresh_effects()

    def _apply_md_additional_income(
        self, idea_id, variable_name, amount, tooltip_key, formula_type="fixed"
    ):
        """
        Execute the full 5-step MD Additional Income workflow automatically:
        1. Edit 00_money_system.txt → insert into calculate_additional_income_rate
        2. Edit money_scripted_localization.txt → append defined_text block
        3. Edit MD_money_l_english.yml → append [additional_income_summary_X] to ADDITIONAL_INCOME_REVENUES_TOOLTIP
        Returns (list_of_saved_paths, list_of_errors)
        """
        saved, errs = [], []

        if not MOD.root or not MOD.loaded:
            errs.append("No mod loaded — load your mod first via File → Load Mod.")
            return saved, errs

        # Re-scan money files in case they weren't found on initial scan
        MOD._scan_md_money_files()

        # ── Step 1: 00_money_system.txt ──────────────────────────────
        money_sys = MOD.md_money_system_file
        if not money_sys:
            money_sys = os.path.join(
                MOD.root, "common", "scripted_effects", "00_money_system.txt"
            )
        step1_done = False
        if os.path.isfile(money_sys):
            try:
                with open(money_sys, encoding="utf-8-sig", errors="replace") as fp:
                    sys_text = fp.read()
                # Check if already present
                if (
                    f"has_idea = {idea_id}" in sys_text
                    and f"{variable_name}" in sys_text
                ):
                    saved.append(
                        f"00_money_system.txt — already contains '{idea_id}' entry (skipped)"
                    )
                    step1_done = True
                else:
                    # Build the inner set/multiply lines based on formula type
                    if formula_type == "gdp_pct":
                        set_lines = (
                            f"\t\tset_variable = {{ {variable_name} = gdp_total }}\n"
                            f"\t\tmultiply_variable = {{ {variable_name} = {amount} }}\n"
                        )
                    elif formula_type == "population":
                        set_lines = (
                            f"\t\tset_variable = {{ {variable_name} = population_total }}\n"
                            f"\t\tmultiply_variable = {{ {variable_name} = {amount} }}\n"
                        )
                    else:  # fixed
                        set_lines = (
                            f"\t\tset_variable = {{ {variable_name} = {amount} }}\n"
                        )
                    inject_block = (
                        f"\n\tif = {{\n"
                        f"\t\tlimit = {{ has_idea = {idea_id} }}\n"
                        f"{set_lines}"
                        f"\t\tadd_to_variable = {{ additional_income_rate = {variable_name} }}\n"
                        f"\t}}"
                    )

                    # Find calculate_additional_income_rate block
                    m = re.search(
                        r"calculate_additional_income_rate\s*=\s*\{", sys_text
                    )
                    if m:
                        # Find its closing brace
                        depth = 0
                        i = m.end() - 1
                        while i < len(sys_text):
                            if sys_text[i] == "{":
                                depth += 1
                            elif sys_text[i] == "}":
                                depth -= 1
                                if depth == 0:
                                    break
                            i += 1
                        # Insert before the closing brace (no extra tab before closing brace)
                        sys_text = sys_text[:i] + inject_block + "\n" + sys_text[i:]
                        with open(money_sys, "w", encoding="utf-8") as fp:
                            fp.write(sys_text)
                        rel = os.path.relpath(money_sys, MOD.root)
                        saved.append(
                            f"✅ {rel}  — injected '{idea_id}' into calculate_additional_income_rate"
                        )
                        step1_done = True
                    else:
                        errs.append(
                            f"⚠ Could not find 'calculate_additional_income_rate' in {os.path.basename(money_sys)}. Insert manually."
                        )
            except Exception as e:
                errs.append(f"❌ 00_money_system.txt: {e}")
        else:
            errs.append(
                "⚠ 00_money_system.txt not found at expected path. Insert manually:\n"
                "  common/scripted_effects/00_money_system.txt → calculate_additional_income_rate"
            )

        # ── Step 2: money_scripted_localization.txt ───────────────────
        sloc = MOD.md_money_scripted_loc_file
        if not sloc:
            sloc_dir = os.path.join(MOD.root, "common", "scripted_localisation")
            os.makedirs(sloc_dir, exist_ok=True)
            sloc = os.path.join(sloc_dir, "money_scripted_localization.txt")
        try:
            existing_sloc = ""
            if os.path.isfile(sloc):
                with open(sloc, encoding="utf-8-sig", errors="replace") as fp:
                    existing_sloc = fp.read()
            summary_name = f"additional_income_summary_{idea_id}"
            if summary_name in existing_sloc:
                saved.append(
                    f"money_scripted_localization.txt — '{summary_name}' already present (skipped)"
                )
            else:
                defined_text = (
                    f"\ndefined_text = {{\n"
                    f"\tname = {summary_name}\n"
                    f"\ttext = {{\n"
                    f"\t\ttrigger = {{ has_idea = {idea_id} }}\n"
                    f'\t\tlocalization_key = "{tooltip_key}"\n'
                    f"\t}}\n"
                    f"}}\n"
                )
                with open(sloc, "a", encoding="utf-8") as fp:
                    fp.write(defined_text)
                rel = os.path.relpath(sloc, MOD.root)
                saved.append(f"✅ {rel}  — appended '{summary_name}'")
        except Exception as e:
            errs.append(f"❌ money_scripted_localization.txt: {e}")

        # ── Step 3: MD_money_l_english.yml ───────────────────────────
        yml = MOD.md_money_yml_file
        if not yml:
            yml_dir = os.path.join(MOD.root, "localisation", "english")
            os.makedirs(yml_dir, exist_ok=True)
            yml = os.path.join(yml_dir, "MD_money_l_english.yml")
        try:
            summary_token = f"[additional_income_summary_{idea_id}]"
            tooltip_loc_key = "ADDITIONAL_INCOME_REVENUES_TOOLTIP"
            yml_text = ""
            if os.path.isfile(yml):
                with open(yml, encoding="utf-8-sig", errors="replace") as fp:
                    yml_text = fp.read()
            if summary_token in yml_text:
                saved.append(
                    f"MD_money_l_english.yml — '{summary_token}' already present (skipped)"
                )
            else:
                # Find ADDITIONAL_INCOME_REVENUES_TOOLTIP and append token before closing quote

                pattern = re.compile(
                    r"(" + re.escape(tooltip_loc_key) + r'(?::\d+)?\s*")(.*?)(")',
                    re.DOTALL,
                )
                m2 = pattern.search(yml_text)
                if m2:
                    new_yml = (
                        yml_text[: m2.start(3)]
                        + f"\\n{summary_token}"
                        + yml_text[m2.start(3) :]
                    )
                    with open(yml, "w", encoding="utf-8-sig") as fp:
                        fp.write(new_yml)
                    rel = os.path.relpath(yml, MOD.root)
                    saved.append(
                        f"✅ {rel}  — appended '{summary_token}' to {tooltip_loc_key}"
                    )
                else:
                    # Key not found — append as new entry at end of file
                    with open(yml, "a", encoding="utf-8-sig") as fp:
                        if not yml_text:
                            fp.write("l_english:\n")
                        fp.write(f' {tooltip_loc_key}: "{summary_token}\\n"\n')
                    rel = os.path.relpath(yml, MOD.root)
                    saved.append(
                        f"✅ {rel}  — appended new '{tooltip_loc_key}' entry (key not found, added at end)"
                    )
        except Exception as e:
            errs.append(f"❌ MD_money_l_english.yml: {e}")

        return saved, errs
