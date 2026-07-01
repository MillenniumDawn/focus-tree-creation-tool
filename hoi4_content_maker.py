# =================================================================
#  Content Maker for Hearts of Iron 4
#  HOI4 Content Maker
#  Version 2.0  |  Millennium Dawn Team
# =================================================================
#
#  COPYRIGHT NOTICE
#  Copyright (c) 2025 Millennium Dawn Team. All Rights Reserved.
#
#  This software, including all source code, assets, and
#  associated files, is the exclusive intellectual property
#  of the Millennium Dawn Team ("the Author").
#
#  PROPRIETARY LICENCE — ALL RIGHTS RESERVED
#
#  This software is NOT open-source and is NOT free to use
#  without explicit written permission from the Author.
#
#  Without prior written authorisation you may NOT:
#    - Copy, reproduce, or redistribute this software
#      or any portion of its source code
#    - Modify, adapt, or create derivative works
#    - Use this software commercially or include it in
#      any other project, product, or distribution
#    - Share, upload, or publish this software in source
#      or compiled form on any platform
#
#  Permitted use is limited to:
#    - Personal, private, non-commercial use by the
#      individual who obtained the software directly
#      from the Author
#
#  Unauthorised use, duplication, or distribution of this
#  software, in whole or in part, is strictly prohibited
#  and may result in civil and/or criminal penalties under
#  applicable copyright law.
#
#  CONTACT
#  For licensing enquiries, permissions, or general contact:
#    millenniumdawnteam@gmail.com
#
# =================================================================

"""
Content Maker for Hearts of Iron 4
HOI4 Content Maker  —  v2.0  |  Millennium Dawn Team

Copyright (c) 2025 Millennium Dawn Team. All Rights Reserved.

Wiki    : https://hoi4.paradoxwikis.com/National_focus_modding
Requires: Python 3.9+  (tkinter built-in, no pip install needed)
Run     : python hoi4_focus_maker.py

Controls:
  Right-click canvas   = place a new focus
  Left-click + drag    = move a focus
  Ctrl + drag / MMB    = pan the canvas
  Scroll wheel         = zoom in / out
  Ctrl + Z             = undo last action
"""

import os as _os
import sys as _sys

_SRC = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")
if _os.path.isdir(_SRC) and _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

from hoi4_logger import log, log_startup
from hoi4cm.core import (
    CONFIG_PATH,
    EFFECT_CATS,
    EFFECT_DEFS,
    I18N_LANGS,
    EmptyFocusTreeError,
    Focus,
    add_error,
    build_focuses,
    default_hoi4_mod_dir,
    dict_to_raw,
    effects_in_cat,
    export_focus_tree,
    get_error_entries,
    get_language,
    install_excepthook,
    parse_focus_tree,
    set_error_callback,
    set_language,
    show_splash,
    tr,
)

# Back-compat alias used in _load_mod and _open_settings
_default_hoi4_mod_dir = default_hoi4_mod_dir
from hoi4cm.mod import MOD
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.mod_loading import ModLoadingMixin
from hoi4cm.ui.effects_panel import EffectsMixin
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BG_PANEL,
    BLUE,
    BORDER,
    BORDER_G,
    BOX,
    CANVAS_BG,
    FC_BG,
    FC_BORDER,
    FC_SEL,
    FC_SEL_BD,
    GOLD,
    GOLD_LT,
    GREEN,
    ICONS,
    MUTEX_COL,
    ORANGE,
    PREREQ_COL,
    RED,
    SEL_BG,
    TEXT,
    TEXT_DIM,
    XGRID,
    YELLOW,
    YGRID,
    Tooltip,
    _safe_after,
    _safe_after_idle,
)
from hoi4cm.wizards import (
    open_additional_income_wizard,
    open_decision_wizard,
    open_dyn_mod_wizard,
    open_event_wizard,
    open_national_spirit_wizard,
)
from hoi4cm.wizards import _shared as _wiz_shared

log_startup()

# Re-import os/sys for the rest of the file (the _os/_sys aliases above
# were only for the sys.path shim).
import os
import sys


def _enable_windows_dpi_awareness():
    """Prevent Windows from bitmap-scaling the Tk UI on high-DPI displays."""
    if sys.platform != "win32" or os.environ.get("HOI4CM_DISABLE_DPI_AWARENESS"):
        return
    try:
        import ctypes

        try:
            result = ctypes.windll.shcore.SetProcessDpiAwareness(
                2
            )  # per-monitor DPI aware
            if result == 0:
                log.info("Windows DPI awareness enabled: per-monitor")
                return
            if result & 0xFFFFFFFF == 0x80070005:  # E_ACCESSDENIED: already set
                log.info("Windows DPI awareness already set")
                return
        except Exception:
            pass
        try:
            if ctypes.windll.user32.SetProcessDPIAware():
                log.info("Windows DPI awareness enabled: system")
        except Exception:
            pass
    except Exception as e:
        log.warning(f"Windows DPI awareness setup skipped: {e}")


_enable_windows_dpi_awareness()
log.info("Importing tkinter...")
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

log.info("tkinter imported OK")
import bisect
import collections
import copy
import json
import re
import subprocess
import threading


def _apply_tk_dpi_scaling(root):
    """Align Tk point-size scaling with the current monitor DPI."""
    if sys.platform != "win32":
        return
    try:
        dpi = root.winfo_fpixels("1i")
        if dpi > 0:
            root.tk.call("tk", "scaling", dpi / 72.0)
            log.info(f"Tk scaling set from monitor DPI: {dpi:.1f}")
    except Exception as e:
        log.warning(f"Tk DPI scaling setup skipped: {e}")


# ── Auto-install Pillow if missing ───────────────────────────────────
log.info("Importing Pillow...")
try:
    from PIL import Image as _PILImage
    from PIL import ImageTk as _PILImageTk

    _PIL_OK = True
    log.info("Pillow imported OK")
except ImportError:
    _PIL_OK = False
    _frozen = getattr(sys, "frozen", False)
    if _frozen:
        log.warning("Pillow not available in frozen binary — skipping auto-install")
    else:
        try:
            log.info("Pillow missing, attempting pip install...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "Pillow"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            from PIL import Image as _PILImage
            from PIL import ImageTk as _PILImageTk

            _PIL_OK = True
            log.info("Pillow installed and imported OK")
        except Exception:
            log.warning("Pillow auto-install failed")
            _PIL_OK = False

class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk):
    CANVAS_MIN_SIZE = 10
    CANVAS_EXPAND_STEP = 5

    def __init__(self):
        log.info("App.__init__: calling tk.Tk.__init__...")
        super().__init__()
        _apply_tk_dpi_scaling(self)
        log.info("App.__init__: tk.Tk initialized")
        self.title(
            tr(
                "app.title.no_tree",
                "HOI4 Content Maker  -  no tree  [Wiki Accurate v2]",
            )
        )
        # Restore saved geometry if available, else use default
        saved_geom = getattr(MOD, "_saved_geometry", "")
        self.geometry(saved_geom if saved_geom else "1440x880")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.focuses = {}
        # Inclusive cell bounds of the usable canvas (grid indices).
        self._canvas_min = [0, 0]
        self._canvas_max = [self.CANVAS_MIN_SIZE - 1, self.CANVAS_MIN_SIZE - 1]
        self.selected = None
        self._multi_sel = set()  # set of fids in multi-select
        self._multisel_mode = False  # True when multi-select mode active
        self._default_focus_prefix = ""  # set by tag detection
        self.mutex_src = None
        self.mutex_mode = False
        self._lines = []
        self._temp_line = None
        self.offset = [80, 60]
        self._pan_start = None
        self.zoom = 1.5
        self._drag = {}
        self._redraw_pending = False
        self._redraw_job = None
        self._lines_job = None  # throttle handle for line redraws during drag
        self._grid_img = None
        self._grid_item = None
        self._grid_key = None
        self._sash_x = 0
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self._build_ui()
        self._redraw()

    def _on_app_close(self):
        try:
            MOD.save_config()
        except Exception:
            pass
        self.destroy()
        os._exit(0)

    # ── TOP BAR ─────────────────────────────────────────────────
    # ── Widget factories (use for all new UI code) ───────────────────
    def _mk_btn(
        self,
        parent,
        text,
        cmd=None,
        fg=None,
        bg=None,
        font_size=9,
        bold=True,
        padx=10,
        pady=4,
        tip=None,
    ):
        """Flat hand-cursor button. Returns the Button widget."""
        b = tk.Button(
            parent,
            text=text,
            command=cmd or (lambda: None),
            bg=bg or BG_CARD,
            fg=fg or TEXT,
            activebackground=BORDER_G,
            activeforeground=TEXT,
            font=("Helvetica", font_size, "bold" if bold else "normal"),
            relief="flat",
            padx=padx,
            pady=pady,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            bd=0,
        )
        if tip:
            Tooltip(b, tip)
        return b

    def _mk_lbl(
        self,
        parent,
        text,
        fg=None,
        bg=None,
        font_size=9,
        bold=False,
        dim=False,
        anchor="w",
        padx=6,
        pady=2,
    ):
        """Standard label, dim or normal."""
        return tk.Label(
            parent,
            text=text,
            bg=bg or BG_PANEL,
            fg=fg or (TEXT_DIM if dim else TEXT),
            font=("Helvetica", font_size, "bold" if bold else "normal"),
            anchor=anchor,
            padx=padx,
            pady=pady,
        )

    def _mk_entry(self, parent, var, width=None):
        """Standard dark entry bound to StringVar."""
        kw = dict(
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        if width:
            kw["width"] = width
        return tk.Entry(parent, **kw)

    def _mk_hsep(self, parent, padx=6, pady=4):
        """1px horizontal separator."""
        f = tk.Frame(parent, bg=BORDER_G, height=1)
        f.pack(fill="x", padx=padx, pady=pady)
        return f

    def _build_ui(self):
        """Orchestrate full UI construction."""
        self._init_error_log()
        self._undo_max = 60
        self._undo_stack = collections.deque(maxlen=self._undo_max)
        self._tree_id = tk.StringVar(value="TAG_focus_tree")
        # Continuous focus position — stored as integers when read from file
        self._cfp_x = None  # None = no value read; use fallback on export
        self._cfp_y = None
        self._cfp_x_var = tk.StringVar(value="")
        self._cfp_y_var = tk.StringVar(value="")
        # shared_focus and joint_focus lines preserved from import
        self._shared_focuses = []
        self._joint_focuses = []
        # Extra loaded trees (shared/joint trees loaded alongside the main tree)
        self._extra_trees = []  # list of dicts: {type, file_path, tree_id, cfp_x, cfp_y, shared_focuses, joint_focuses, country_tag, focus_ids}
        toolbar = tk.Frame(self, bg=BG_DARK)
        toolbar.pack(fill="x")
        self._build_menubar(toolbar)
        self._build_toolbar_row2(toolbar)
        self._build_keybinds()
        self._build_layout()

    def _build_menubar(self, toolbar):
        """Build menu bar with File/Edit/View/Tools dropdowns."""
        # ── MENU BAR ──────────────────────────────────────────────
        menubar = tk.Frame(toolbar, bg="#080b10", height=30)
        menubar.pack(fill="x")
        menubar.pack_propagate(False)
        tk.Frame(menubar, bg=BORDER_G, height=1).place(relx=0, rely=1, relwidth=1)

        # Branding
        tk.Label(
            menubar,
            text=tr("app.brand", "HOI4 CONTENT MAKER"),
            bg="#080b10",
            fg=TEXT_DIM,
            font=("Helvetica", 9, "bold"),
            padx=12,
        ).pack(side="left")
        tk.Frame(menubar, bg=BORDER_G, width=1, height=18).pack(side="left", padx=2)

        # ── Menu helpers ──────────────────────────────────────────
        self._open_menu_win = [None]  # [current Toplevel or None]
        self._open_menu_btn = [None]  # [button that opened it]

        def _close_menu():
            w = self._open_menu_win[0]
            b = self._open_menu_btn[0]
            if w:
                try:
                    w.destroy()
                except Exception:
                    pass
            self._open_menu_win[0] = None
            self._open_menu_btn[0] = None
            if b:
                try:
                    b.config(bg="#080b10", fg=TEXT_DIM)
                except Exception:
                    pass

        def _menu_btn(parent, label, items):
            btn = tk.Button(
                parent,
                text=label,
                bg="#080b10",
                fg=TEXT_DIM,
                font=("Helvetica", 9, "bold"),
                relief="flat",
                padx=10,
                pady=0,
                cursor="hand2",
                bd=0,
                activebackground="#1a2030",
                activeforeground=TEXT,
            )
            btn.pack(side="left")

            def _open(b=btn):
                # If this menu is already open, close it
                if self._open_menu_btn[0] is b:
                    _close_menu()
                    return
                _close_menu()
                b.config(bg="#1a2030", fg=TEXT)
                # Build a Toplevel dropdown
                b.update_idletasks()
                rx = b.winfo_rootx()
                ry = b.winfo_rooty() + b.winfo_height()
                drop = tk.Toplevel(self)
                drop.wm_overrideredirect(True)
                drop.configure(bg="#0d1218")
                drop.attributes("-topmost", True)
                # build contents
                inner = tk.Frame(
                    drop,
                    bg="#0d1218",
                    highlightthickness=1,
                    highlightbackground=BORDER_G,
                )
                inner.pack(fill="both", expand=True)
                min_w = 340
                for item in items:
                    if item is None:
                        tk.Frame(inner, bg=BORDER_G, height=1).pack(
                            fill="x", padx=0, pady=2
                        )
                    elif isinstance(item, str):
                        tk.Label(
                            inner,
                            text=item.upper(),
                            bg="#0d1218",
                            fg=TEXT_DIM,
                            font=("Helvetica", 8, "bold"),
                            anchor="w",
                            padx=16,
                            pady=3,
                        ).pack(fill="x")
                    else:
                        lbl_i, cmd_i, *rest = item
                        kbd = rest[0] if len(rest) > 0 else ""
                        tip_txt = rest[1] if len(rest) > 1 else ""
                        item_bg_n = "#0d1218"
                        item_bg_h = "#141c2a"
                        row_f = tk.Frame(inner, bg=item_bg_n)
                        row_f.pack(fill="x")

                        def _make_cmd(c=cmd_i):
                            def _do():
                                _close_menu()
                                if c:
                                    self.after(10, c)

                            return _do

                        # main label + kbd shortcut row
                        top_row = tk.Frame(row_f, bg=item_bg_n)
                        top_row.pack(fill="x")
                        ib = tk.Button(
                            top_row,
                            text=lbl_i,
                            command=_make_cmd(),
                            bg=item_bg_n,
                            fg=TEXT_DIM,
                            font=("Helvetica", 9, "bold"),
                            relief="flat",
                            anchor="w",
                            padx=16,
                            pady=4,
                            cursor="hand2",
                            bd=0,
                            activebackground=item_bg_h,
                            activeforeground=TEXT,
                        )
                        ib.pack(side="left", fill="x", expand=True)
                        if kbd:
                            tk.Label(
                                top_row,
                                text=kbd,
                                bg=item_bg_n,
                                fg="#3a4a60",
                                font=("Courier", 8),
                                padx=12,
                            ).pack(side="right")
                        # tooltip description line (dim, indented)
                        if tip_txt:
                            tip_lbl = tk.Label(
                                row_f,
                                text=tip_txt,
                                bg=item_bg_n,
                                fg="#3d5068",
                                font=("Helvetica", 8),
                                anchor="w",
                                padx=26,
                                pady=0,
                            )
                            tip_lbl.pack(fill="x")
                        else:
                            tip_lbl = None
                        # hover: highlight entire row including tip
                        all_widgets = [row_f, top_row, ib] + (
                            [tip_lbl] if tip_lbl else []
                        )

                        def _enter(e, ws=all_widgets, kl=top_row, tl=tip_lbl, ib_=ib):
                            for w in ws:
                                w.config(bg=item_bg_h)
                            ib_.config(fg=TEXT)
                            if tl:
                                tl.config(fg="#6b849a")

                        def _leave(e, ws=all_widgets, tl=tip_lbl, ib_=ib):
                            for w in ws:
                                w.config(bg=item_bg_n)
                            ib_.config(fg=TEXT_DIM)
                            if tl:
                                tl.config(fg="#3d5068")

                        for w in all_widgets:
                            w.bind("<Enter>", _enter)
                            w.bind("<Leave>", _leave)
                # position and show
                drop.update_idletasks()
                dw = max(drop.winfo_reqwidth(), min_w)
                dh = drop.winfo_reqheight()
                drop.geometry(f"{dw}x{dh}+{rx}+{ry}")
                # close on any click outside
                drop.bind(
                    "<FocusOut>",
                    lambda e: self.after(
                        100,
                        lambda: _close_menu()
                        if self._open_menu_win[0] is drop
                        else None,
                    ),
                )
                self._open_menu_win[0] = drop
                self._open_menu_btn[0] = b

            btn.config(command=_open)
            btn.bind(
                "<Enter>",
                lambda e, b=btn: b.config(fg=TEXT)
                if self._open_menu_btn[0] is not b
                else None,
            )
            btn.bind(
                "<Leave>",
                lambda e, b=btn: b.config(fg=TEXT_DIM, bg="#080b10")
                if self._open_menu_btn[0] is not b
                else None,
            )
            return btn

        # ── FILE MENU ─────────────────────────────────────────────
        _menu_btn(
            menubar,
            tr("menu.file", "File"),
            [
                tr("menu.section.project", "Project"),
                (
                    tr("menu.new_tree", "New Tree"),
                    self._new_tree_dialog,
                    "Ctrl+N",
                    tr(
                        "menu.new_tree.tip",
                        "Start fresh - set country tag and auto-prefix all focus IDs.",
                    ),
                ),
                (
                    tr("menu.save_project", "Save Project"),
                    self._save,
                    "Ctrl+S",
                    tr(
                        "menu.save_project.tip",
                        "Save as .json so you can reopen and keep editing later.",
                    ),
                ),
                (
                    tr("menu.load_project", "Load Project"),
                    self._load,
                    "Ctrl+O",
                    tr(
                        "menu.load_project.tip",
                        "Open a previously saved .json project file.",
                    ),
                ),
                None,
                tr("menu.section.recent", "Recent"),
                *(
                    [(tr("menu.no_recent_files", "  (no recent files)"), None)]
                    if not getattr(MOD, "_recent_mods", [])
                    else [
                        (f"  {r}", lambda p=r: self._load_mod_path(p))
                        for r in (getattr(MOD, "_recent_mods", []) or [])
                    ]
                ),
                None,
                tr("menu.section.import_export", "Import / Export"),
                (
                    tr("menu.export_txt", "Export .txt"),
                    self._export,
                    "Ctrl+E",
                    tr(
                        "menu.export_txt.tip",
                        "Write HOI4-ready script to a .txt file for your mod folder.",
                    ),
                ),
                (
                    tr("menu.export_mod", "Export to Mod"),
                    self._export,
                    "Ctrl+Shift+E",
                    tr(
                        "menu.export_mod.tip",
                        "Write directly into your loaded mod's national_focus folder.",
                    ),
                ),
                (
                    tr("menu.import_txt", "Import .txt"),
                    self._import_txt,
                    "",
                    tr(
                        "menu.import_txt.tip",
                        "Read an existing HOI4 focus tree .txt and populate the canvas.",
                    ),
                ),
                (
                    tr("menu.import_drawio", "Import Draw.io"),
                    self._import_drawio,
                    "",
                    tr(
                        "menu.import_drawio.tip",
                        "Convert a Draw.io diagram into focus nodes and prerequisite arrows.",
                    ),
                ),
            ],
        )

        # ── EDIT MENU ─────────────────────────────────────────────
        _menu_btn(
            menubar,
            tr("menu.edit", "Edit"),
            [
                (
                    tr("menu.undo", "Undo"),
                    self._undo,
                    "Ctrl+Z",
                    tr(
                        "menu.undo.tip",
                        "Revert the last canvas action (move, add, delete, edit).",
                    ),
                ),
                None,
                (
                    tr("menu.duplicate_focus", "Duplicate Focus"),
                    self._duplicate_focus,
                    "",
                    tr(
                        "menu.duplicate_focus.tip",
                        "Copy the selected focus - gets a _copy suffix, shifted one column right.",
                    ),
                ),
                (
                    tr("menu.bulk_rename_prefix", "Bulk Rename Prefix"),
                    self._bulk_rename_dialog,
                    "",
                    tr(
                        "menu.bulk_rename_prefix.tip",
                        "Replace a prefix across all focus IDs, prerequisites and mutex links at once.",
                    ),
                ),
                None,
                (
                    tr("menu.select_all", "Select All"),
                    self._select_all_focuses,
                    "Ctrl+A",
                    tr(
                        "menu.select_all.tip",
                        "Enable multi-select and mark every focus on the canvas.",
                    ),
                ),
                (
                    tr("menu.delete_selected", "Delete Selected"),
                    self._delete_selected,
                    "Del",
                    tr(
                        "menu.delete_selected.tip",
                        "Remove all multi-selected focuses after confirmation.",
                    ),
                ),
            ],
        )

        # ── VIEW MENU ─────────────────────────────────────────────
        _menu_btn(
            menubar,
            tr("menu.view", "View"),
            [
                (
                    tr("menu.toggle_grid", "Toggle Grid"),
                    self._toggle_grid,
                    "G",
                    tr(
                        "menu.toggle_grid.tip",
                        "Show or hide the background snap grid on the canvas.",
                    ),
                ),
                (
                    tr("menu.toggle_minimap", "Toggle Minimap"),
                    self._toggle_minimap,
                    "M",
                    tr(
                        "menu.toggle_minimap.tip",
                        "Show or hide the minimap overview in the bottom-right corner.",
                    ),
                ),
                (
                    tr("menu.toggle_focus_list", "Toggle Focus List"),
                    self._toggle_focus_list,
                    "F",
                    tr(
                        "menu.toggle_focus_list.tip",
                        "Collapse or expand the left-side focus list panel.",
                    ),
                ),
                None,
                (
                    tr("menu.fit_all_focuses", "Fit All Focuses"),
                    self._fit_all,
                    "0",
                    tr(
                        "menu.fit_all_focuses.tip",
                        "Zoom and pan so every focus on the canvas is visible at once.",
                    ),
                ),
            ],
        )

        # ── TOOLS MENU ────────────────────────────────────────────
        _menu_btn(
            menubar,
            tr("menu.tools", "Tools"),
            [
                (
                    tr("menu.national_spirit_builder", "National Spirit Builder"),
                    self._national_spirit_wizard,
                    "",
                    tr(
                        "menu.national_spirit_builder.tip",
                        "Create ideas/spirits with a modifier editor and live HOI4 preview.",
                    ),
                ),
                (
                    tr("menu.dynamic_modifier", "Dynamic Modifier"),
                    self._dyn_mod_wizard,
                    "",
                    tr(
                        "menu.dynamic_modifier.tip",
                        "Build add_dynamic_modifier effects with variable-driven scaling.",
                    ),
                ),
                (
                    tr("menu.decision_maker", "Decision Maker"),
                    self._decision_wizard,
                    "",
                    tr(
                        "menu.decision_maker.tip",
                        "Build decisions and decision categories with GFX placement editor.",
                    ),
                ),
                (
                    tr("menu.event_maker", "Event Maker"),
                    self._event_wizard,
                    "",
                    tr(
                        "menu.event_maker.tip",
                        "Build country_event / news_event blocks with options and live preview.",
                    ),
                ),
                None,
                (
                    tr("menu.validate_tree", "Validate Tree"),
                    self._validate_tree,
                    "",
                    tr(
                        "menu.validate_tree.tip",
                        "Check for broken prerequisites, missing effects, and bad GFX references.",
                    ),
                ),
                (
                    tr("menu.load_mod", "Load Mod"),
                    self._load_mod,
                    "",
                    tr(
                        "menu.load_mod.tip",
                        "Point to your mod root folder to browse GFX and enable direct export.",
                    ),
                ),
                (
                    tr("menu.set_edit_targets", "Set Edit Targets"),
                    self._show_post_load_prompt,
                    "",
                    tr(
                        "menu.set_edit_targets.tip",
                        "Choose which existing ideas/events files new content should be appended to.",
                    ),
                ),
                (
                    tr("menu.settings", "Settings"),
                    self._open_settings,
                    "",
                    tr(
                        "menu.settings.tip",
                        "Configure mod path, GFX directories, MD detection, and UI options.",
                    ),
                ),
            ],
        )

        # Right side of menu bar
        self._errlog_btn = tk.Button(
            menubar,
            text=tr("menu.error_log", "Log"),
            command=self._show_error_log,
            bg="#080b10",
            fg="#6e7681",
            font=("Helvetica", 8, "bold"),
            relief="flat",
            padx=8,
            pady=0,
            cursor="hand2",
            bd=0,
            activebackground=BG_CARD,
            activeforeground=TEXT,
        )
        self._errlog_btn.pack(side="right", padx=4)
        Tooltip(
            self._errlog_btn,
            tr(
                "menu.error_log.tip",
                "View in-app error log.\nTurns red if any errors are caught during the session.",
            ),
        )
        tk.Frame(menubar, bg=BORDER_G, width=1, height=16).pack(side="right", padx=2)
        self._mod_lbl = tk.Label(
            menubar,
            text=tr("status.no_mod_loaded", "No mod loaded"),
            bg="#080b10",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
            padx=8,
        )
        self._mod_lbl.pack(side="right")
        # close menu when clicking on canvas
        self.bind(
            "<Button-1>",
            lambda e: _close_menu()
            if self._open_menu_win[0]
            and not str(e.widget).startswith(str(self._open_menu_win[0]))
            else None,
            add="+",
        )

        # hint label (used by _hint() method)
        self._hint_lbl = tk.Label(
            toolbar,
            text=tr(
                "hint.canvas_controls",
                "Right-click canvas to place a focus  -  Ctrl+drag to pan  -  Scroll to zoom",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
            anchor="w",
            padx=10,
        )
        self._hint_lbl.pack(fill="x", pady=1)

    def _build_toolbar_row2(self, toolbar):
        """Build toolbar row 2: canvas action buttons and coord display."""
        # ROW 2 — canvas tools (clean grouped toolbar)
        row2 = tk.Frame(toolbar, bg="#090d14", height=36)
        row2.pack(fill="x")
        row2.pack_propagate(False)
        self._conn_btn = None
        self._mutex_btn = None

        def _tb_sep():
            tk.Frame(row2, bg=BORDER_G, width=1, height=20).pack(side="left", padx=5)

        def _tb_lbl(t):
            tk.Label(
                row2,
                text=t,
                bg="#090d14",
                fg=TEXT_DIM,
                font=("Helvetica", 8, "bold"),
                padx=4,
            ).pack(side="left")

        def _tb_btn(lbl, cmd, fg, bg, tip, padx=2):
            b = tk.Button(
                row2,
                text=lbl,
                command=cmd,
                bg=bg,
                fg=fg,
                activebackground=BORDER_G,
                activeforeground=TEXT,
                font=("Helvetica", 9, "bold"),
                relief="flat",
                padx=9,
                pady=2,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            b.pack(side="left", padx=padx, pady=3)
            Tooltip(b, tip)
            return b

        _tb_lbl(tr("toolbar.section.canvas", "Canvas"))
        _tb_btn(
            tr("toolbar.add_focus", "+ Focus"),
            self._add_focus,
            TEXT,
            "#1e3a6e",
            tr(
                "toolbar.add_focus.tip",
                "Add a new focus.\nAlso: right-click the canvas.",
            ),
        )
        self._conn_btn = _tb_btn(
            tr("toolbar.prereq", "Prereq"),
            self._toggle_connect,
            TEXT,
            BG_CARD,
            tr(
                "toolbar.prereq.tip",
                "Open the prerequisite picker for the selected focus.",
            ),
        )
        self._mutex_btn = _tb_btn(
            tr("toolbar.mutex", "Mutex"),
            self._toggle_mutex,
            ORANGE,
            BG_CARD,
            tr("toolbar.mutex.tip", "Draw a mutually exclusive link."),
        )
        _tb_sep()
        _tb_lbl(tr("toolbar.section.tools", "Tools"))
        _tb_btn(
            tr("toolbar.ideas", "Ideas"),
            self._national_spirit_wizard,
            TEXT,
            "#1a2040",
            tr("toolbar.ideas.tip", "Build National Spirits / Ideas."),
        )
        _tb_btn(
            tr("toolbar.dyn_mod", "Dyn Mod"),
            self._dyn_mod_wizard,
            TEXT,
            BG_CARD,
            tr("toolbar.dyn_mod.tip", "Dynamic Modifier wizard."),
        )
        _tb_btn(
            tr("toolbar.decisions", "Decisions"),
            self._decision_wizard,
            TEXT,
            BG_CARD,
            tr("toolbar.decisions.tip", "Decision / Decision Category maker."),
        )
        _tb_btn(
            tr("toolbar.events", "Events"),
            self._event_wizard,
            TEXT,
            BG_CARD,
            tr("toolbar.events.tip", "Event Maker wizard."),
        )
        _tb_btn(
            tr("toolbar.add_income", "Add Income"),
            self._additional_income_wizard,
            "#4ade80",
            "#0d2b1a",
            tr(
                "toolbar.add_income.tip",
                "MD Additional Income Wizard - creates/links a spirit and wires up all money system files automatically.",
            ),
        )
        _tb_sep()
        _tb_lbl(tr("toolbar.section.select", "Select"))
        self._msel_btn = _tb_btn(
            tr("toolbar.multi", "Multi"),
            self._toggle_multisel,
            TEXT,
            "#1a1a2e",
            tr(
                "toolbar.multi.tip",
                "Toggle multi-select mode.\nCtrl+click focuses, then Delete.",
            ),
        )
        _tb_btn(
            tr("toolbar.delete_selected", "Del Selected"),
            self._delete_selected,
            TEXT,
            "#4a1010",
            tr("toolbar.delete_selected.tip", "Delete all selected focuses."),
        )
        _tb_sep()
        _tb_btn(
            tr("toolbar.clear_all", "Clear All"),
            self._clear_all,
            TEXT,
            "#7f1d1d",
            tr(
                "toolbar.clear_all.tip",
                "Delete ALL focuses from the canvas.\nSave first!",
            ),
        )
        _tb_sep()
        _tb_lbl(tr("toolbar.section.multi_tree", "Multi-Tree"))
        _tb_btn(
            tr("toolbar.shared", "+ Shared"),
            lambda: self._load_extra_tree("shared"),
            TEXT,
            "#2d1c08",
            tr(
                "toolbar.shared.tip",
                "Load a shared_focus tree alongside the main tree.\nIts focuses appear on canvas with amber [S] badges.",
            ),
        )
        _tb_btn(
            tr("toolbar.joint", "+ Joint"),
            lambda: self._load_extra_tree("joint"),
            TEXT,
            "#1a0d40",
            tr(
                "toolbar.joint.tip",
                "Load a joint_focus tree alongside the main tree.\nIts focuses appear on canvas with purple [J] badges.",
            ),
        )
        _tb_btn(
            tr("toolbar.load_all", "Load All"),
            self._load_all_trees,
            TEXT,
            "#0d1a2e",
            tr(
                "toolbar.load_all.tip",
                "Scan the mod's national_focus folder and load selected trees from a checklist.",
            ),
        )
        _tb_btn(
            tr("toolbar.save_all", "Save All"),
            self._save_all_trees,
            "#4ade80",
            "#0d1a0a",
            tr(
                "toolbar.save_all.tip",
                "Export all loaded trees (main + shared + joint) at once.",
            ),
        )

        # Coord display right side
        self._coord_lbl = tk.Label(
            row2,
            text="  x=0  y=0  ",
            bg="#090d14",
            fg=TEXT_DIM,
            font=("Courier", 9),
            padx=4,
        )
        self._coord_lbl.pack(side="right", padx=4)
        tk.Label(
            row2,
            text=tr("toolbar.cursor", "Cursor:"),
            bg="#090d14",
            fg=TEXT_DIM,
            font=("Helvetica", 8),
        ).pack(side="right")

        # Continuous Focus Position inputs (tree-level setting)
        tk.Frame(row2, bg=BORDER_G, width=1, height=20).pack(side="right", padx=5)

        def _cfp_commit(*_):
            try:
                self._cfp_x = int(self._cfp_x_var.get())
            except Exception:
                pass
            try:
                self._cfp_y = int(self._cfp_y_var.get())
            except Exception:
                pass

        _cfp_y_ent = tk.Entry(
            row2,
            textvariable=self._cfp_y_var,
            width=6,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        _cfp_y_ent.pack(side="right", ipady=1, padx=(0, 2))
        _cfp_y_ent.bind("<FocusOut>", _cfp_commit)
        _cfp_y_ent.bind("<Return>", _cfp_commit)
        tk.Label(row2, text="y:", bg="#090d14", fg=TEXT_DIM, font=("Courier", 9)).pack(
            side="right"
        )
        _cfp_x_ent = tk.Entry(
            row2,
            textvariable=self._cfp_x_var,
            width=6,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        _cfp_x_ent.pack(side="right", ipady=1, padx=(0, 2))
        _cfp_x_ent.bind("<FocusOut>", _cfp_commit)
        _cfp_x_ent.bind("<Return>", _cfp_commit)
        tk.Label(row2, text="x:", bg="#090d14", fg=TEXT_DIM, font=("Courier", 9)).pack(
            side="right"
        )
        tk.Label(
            row2,
            text=tr("toolbar.continuous_focus_pos", "Continuous Focus Pos:"),
            bg="#090d14",
            fg=TEXT_DIM,
            font=("Helvetica", 8),
        ).pack(side="right")

    def _build_keybinds(self):
        """Bind all global keyboard shortcuts."""

        # Guard: single-key hotkeys must not fire when a text/entry widget has focus
        # (prevents '0' resetting zoom when user types into a code box, etc.)
        def _guard(fn):
            def _inner(e):
                if isinstance(e.widget, (tk.Text, tk.Entry)):
                    return
                fn()

            return _inner

        self.bind("<Control-z>", lambda e: self._undo())
        self.bind("<Control-Z>", lambda e: self._undo())
        self.bind("<Control-n>", lambda e: self._new_tree_dialog())
        self.bind("<Control-s>", lambda e: self._save())
        self.bind("<Control-o>", lambda e: self._load())
        self.bind("<Control-e>", lambda e: self._export())
        self.bind("<Control-d>", lambda e: self._duplicate_focus())
        self.bind("<Control-a>", lambda e: self._select_all_focuses())
        self.bind("<Delete>", lambda e: self._key_delete())
        self.bind("<KeyPress-g>", _guard(self._toggle_grid))
        self.bind("<KeyPress-m>", _guard(self._toggle_minimap))
        self.bind("<KeyPress-f>", _guard(self._toggle_focus_list))
        self.bind("<KeyPress-0>", _guard(self._fit_all))

    def _build_layout(self):
        """Build body: status bar, left panel, canvas, sash, sidebar."""
        # ── Status bar (packed BEFORE body so it stays at bottom) ──
        self._statusbar = tk.Frame(self, bg="#060810", height=24)
        self._statusbar.pack(side="bottom", fill="x")
        self._statusbar.pack_propagate(False)
        tk.Frame(self._statusbar, bg=BORDER_G, height=1).place(
            relx=0, rely=0, relwidth=1
        )

        def _sb_item(text, fg=TEXT_DIM, var=None):
            f = tk.Frame(self._statusbar, bg="#060810")
            f.pack(side="left", fill="y")
            lbl = tk.Label(
                f, text=text, bg="#060810", fg=fg, font=("Courier", 9), padx=10, pady=3
            )
            lbl.pack(side="left")
            tk.Frame(f, bg=BORDER_G, width=1).pack(side="right", fill="y")
            if var:
                lbl.config(textvariable=var)
            return lbl

        self._sb_tree_lbl = _sb_item(tr("status.tree", "Tree: "), TEXT_DIM)
        self._sb_tree_val = tk.Label(
            self._statusbar,
            text=tr("status.no_tree", "no tree"),
            bg="#060810",
            fg=YELLOW,
            font=("Courier", 9),
            padx=0,
        )
        self._sb_tree_val.pack(side="left")
        tk.Frame(self._statusbar, bg=BORDER_G, width=1).pack(
            side="left", fill="y", padx=(6, 0)
        )
        self._sb_focus_lbl = _sb_item(tr("status.focuses", "Focuses: {count}", count=0))
        self._sb_sel_lbl = _sb_item(
            tr("status.selected", "Selected: {focus}", focus="—")
        )
        self._sb_zoom_lbl = _sb_item(tr("status.zoom", "Zoom: {zoom}%", zoom=100))
        self._sb_mod_lbl2 = _sb_item(tr("status.mod_none", "Mod: none"))
        tk.Label(
            self._statusbar,
            text="HOI4 Content Maker  [Wiki Accurate v2]",
            bg="#060810",
            fg="#2a3548",
            font=("Courier", 8),
            padx=10,
        ).pack(side="right")

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True)

        # ── Left focus list panel ──────────────────────────────────
        self._left_panel_visible = True
        self._left_panel = tk.Frame(body, bg=BG_PANEL, width=188)
        self._left_panel.pack(side="left", fill="y")
        self._left_panel.pack_propagate(False)
        tk.Frame(self._left_panel, bg="#060810", height=28).pack(fill="x")
        # header
        lp_hdr = tk.Frame(self._left_panel, bg="#060810")
        lp_hdr.place(x=0, y=0, relwidth=1, height=28)
        tk.Label(
            lp_hdr,
            text=tr("focus_list.header", "FOCUSES"),
            bg="#060810",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            padx=8,
        ).pack(side="left")
        self._lp_collapse_btn = tk.Button(
            lp_hdr,
            text="◀",
            command=self._toggle_focus_list,
            bg="#060810",
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            relief="flat",
            padx=6,
            cursor="hand2",
            bd=0,
        )
        self._lp_collapse_btn.pack(side="right")
        tk.Frame(self._left_panel, bg=BORDER_G, height=1).pack(fill="x")
        # search
        lp_search = tk.Frame(self._left_panel, bg=BG_PANEL)
        lp_search.pack(fill="x", padx=6, pady=4)
        self._lp_search_var = tk.StringVar()
        lp_ent = tk.Entry(
            lp_search,
            textvariable=self._lp_search_var,
            bg=BG_CARD,
            fg=TEXT_DIM,
            insertbackground=BLUE,
            font=("Helvetica", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        lp_ent.pack(fill="x", ipady=3)
        lp_ent.insert(0, tr("common.search_placeholder", "Search..."))
        lp_ent.bind(
            "<FocusIn>",
            lambda e: (lp_ent.delete(0, "end"), lp_ent.config(fg=TEXT))
            if lp_ent.get() == tr("common.search_placeholder", "Search...")
            else None,
        )
        lp_ent.bind(
            "<FocusOut>",
            lambda e: (
                lp_ent.insert(0, tr("common.search_placeholder", "Search...")),
                lp_ent.config(fg=TEXT_DIM),
            )
            if not lp_ent.get()
            else None,
        )
        self._lp_search_var.trace_add(
            "write", lambda *_: self._refresh_focus_list_debounced()
        )
        # list
        lp_list_frame = tk.Frame(self._left_panel, bg=BG_PANEL)
        lp_list_frame.pack(fill="both", expand=True)
        lp_sb = tk.Scrollbar(lp_list_frame, orient="vertical")
        lp_sb.pack(side="right", fill="y")
        self._lp_canvas = tk.Canvas(
            lp_list_frame, bg=BG_PANEL, highlightthickness=0, yscrollcommand=lp_sb.set
        )
        lp_sb.config(command=self._lp_canvas.yview)
        self._lp_canvas.pack(fill="both", expand=True)
        self._lp_inner = tk.Frame(self._lp_canvas, bg=BG_PANEL)
        self._lp_win = self._lp_canvas.create_window(
            (0, 0), window=self._lp_inner, anchor="nw"
        )
        self._lp_inner.bind(
            "<Configure>",
            lambda e: self._lp_canvas.configure(
                scrollregion=self._lp_canvas.bbox("all")
            ),
        )
        self._lp_canvas.bind(
            "<Configure>",
            lambda e: self._lp_canvas.itemconfig(self._lp_win, width=e.width),
        )
        self._lp_canvas.bind(
            "<MouseWheel>",
            lambda e: self._lp_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )
        tk.Frame(self._left_panel, bg=BORDER_G, width=1).place(
            relx=1, rely=0, relheight=1, x=-1
        )

        self.cv = tk.Canvas(body, bg=CANVAS_BG, highlightthickness=0, cursor="fleur")
        self.cv.pack(side="left", fill="both", expand=True)
        self._bind_canvas()
        # ── Draggable resize handle ──────────────────────────────
        self._sb_width = 360
        self._sash = tk.Frame(body, bg=BG_CARD, width=5, cursor="sb_h_double_arrow")
        self._sash.pack(side="left", fill="y")
        # Visible drag handle with arrows
        sash_lbl = tk.Label(
            self._sash,
            text="⋮",
            bg=BG_CARD,
            fg=TEXT_DIM,
            font=("Helvetica", 10),
            cursor="sb_h_double_arrow",
        )
        sash_lbl.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self._sash, sash_lbl):
            w.bind("<ButtonPress-1>", self._sash_pr)
            w.bind("<B1-Motion>", self._sash_mv)
            w.bind("<ButtonRelease-1>", self._sash_rl)
            w.bind("<Enter>", lambda e: self._sash.config(bg=BORDER_G))
            w.bind("<Leave>", lambda e: self._sash.config(bg=BG_CARD))
        self._sb_frame = tk.Frame(body, bg=BG_PANEL, width=self._sb_width)
        self._sb_frame.pack(side="right", fill="y")
        self._sb_frame.pack_propagate(False)
        self._build_sidebar(self._sb_frame)

    def _init_error_log(self):
        """Set up in-app error log — captures all Python exceptions.

        The error buffer and excepthook live in hoi4cm.core.log; this just
        aliases the shared buffer and registers the badge-flash callback.
        """
        self._error_entries = get_error_entries()
        set_error_callback(self._on_error_logged)
        install_excepthook()

    def _log_error(self, msg):
        """Record an error (core appends + fires the badge callback)."""
        add_error(msg)

    def _on_error_logged(self, count):
        """Flash the error log button when a new error is recorded."""
        if hasattr(self, "_errlog_btn"):
            self._errlog_btn.config(
                text=tr("error_log.badge_errors", "! Errors ({count})", count=count),
                fg="#f87171",
                bg="#450a0a",
            )
            self.after(
                3000,
                lambda: self._errlog_btn.config(
                    text=tr(
                        "error_log.badge_log_count", "! Log ({count})", count=count
                    ),
                    fg="#f87171",
                    bg="#450a0a",
                )
                if count > 0
                else None,
            )

    def _show_error_log(self):
        """Open the in-app error log window."""
        win = tk.Toplevel(self)
        win.title(tr("error_log.title", "Error Log"))
        win.configure(bg="#0d1117")
        win.geometry("760x480")
        win.resizable(True, True)

        # Header
        hdr = tk.Frame(win, bg="#080c12", pady=8)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=tr("error_log.header", "  !  Error Log"),
            bg="#080c12",
            fg="#f87171",
            font=("Courier", 12, "bold"),
        ).pack(side="left", padx=8)
        tk.Button(
            hdr,
            text=tr("common.clear", "Clear"),
            command=lambda: _clear(),
            bg="#450a0a",
            fg="#f87171",
            font=("Helvetica", 9),
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side="right", padx=8)
        tk.Button(
            hdr,
            text="✕",
            command=win.destroy,
            bg="#080c12",
            fg="#6e7681",
            font=("Helvetica", 10),
            relief="flat",
            cursor="hand2",
            padx=8,
        ).pack(side="right")
        tk.Frame(win, bg="#21262d", height=1).pack(fill="x")

        # No errors label
        no_err = tk.Label(
            win,
            text=tr(
                "error_log.empty",
                "\n\n  ok  No errors recorded.\n\n  The program is running cleanly.",
            ),
            bg="#0d1117",
            fg="#22c55e",
            font=("Courier", 11),
            justify="left",
            anchor="nw",
        )

        # Scrollable log area
        frm = tk.Frame(win, bg="#0d1117")
        frm.pack(fill="both", expand=True)
        sb = tk.Scrollbar(frm, orient="vertical")
        sb.pack(side="right", fill="y")
        txt = tk.Text(
            frm,
            bg="#0a0f18",
            fg="#c9d1d9",
            font=("Courier", 9),
            relief="flat",
            yscrollcommand=sb.set,
            wrap="none",
            state="disabled",
            selectbackground="#1e3a6e",
        )
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)

        txt.tag_configure("ts", foreground="#374151")
        txt.tag_configure("sep", foreground="#21262d")
        txt.tag_configure("err", foreground="#f87171")
        txt.tag_configure("tb", foreground="#c9d1d9")

        def _refresh():
            txt.config(state="normal")
            txt.delete("1.0", "end")
            if not self._error_entries:
                no_err.pack(fill="both", expand=True)
                frm.pack_forget()
            else:
                no_err.pack_forget()
                frm.pack(fill="both", expand=True)
                for ts, msg in self._error_entries:
                    txt.insert("end", f"[{ts}]  ", "ts")
                    lines = msg.splitlines()
                    txt.insert("end", lines[0] + "\n", "err")
                    for line in lines[1:]:
                        txt.insert("end", line + "\n", "tb")
                    txt.insert("end", "─" * 80 + "\n", "sep")
            txt.config(state="disabled")
            txt.see("end")

        def _clear():
            self._error_entries.clear()
            if hasattr(self, "_errlog_btn"):
                self._errlog_btn.config(
                    text=tr("error_log.badge_log", "! Log"), fg="#6e7681", bg="#161b22"
                )
            _refresh()

        _refresh()

    # ── UNDO ────────────────────────────────────────────────────
    def _snapshot(self):
        """Return a deep snapshot of all focuses (for undo)."""
        return copy.deepcopy({fid: f.to_dict() for fid, f in self.focuses.items()})

    def _push_undo(self, label="action"):
        """Call BEFORE making a change to save current state."""
        snap = self._snapshot()
        # deque(maxlen) evicts the oldest entry on overflow in O(1).
        self._undo_stack.append((label, snap))

    def _undo(self):
        """Restore the previous state."""
        if not self._undo_stack:
            self._hint("Nothing to undo.")
            return
        label, snap = self._undo_stack.pop()
        # Rebuild focuses from snapshot
        self.cv.delete("all")
        self.focuses.clear()
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self.selected = None
        for fd in snap.values():
            f = Focus.from_dict(fd)
            f._draw_key = None
            self.focuses[f.id] = f
        self._hide_form()
        self._redraw()
        self._hint(f"↩ Undid: {label}")

    def _hint(self, t):
        self._hint_lbl.config(text=t)

    def _refresh_tree_meta_panel(self):
        """Refresh the shared_focus / joint_focus read-only display in the sidebar."""
        if not hasattr(self, "_tree_meta_sf_box"):
            return
        for w in self._tree_meta_sf_box.winfo_children():
            w.destroy()
        for w in self._tree_meta_jf_box.winfo_children():
            w.destroy()
        sflist = getattr(self, "_shared_focuses", [])
        jflist = getattr(self, "_joint_focuses", [])
        if sflist:
            for sf in sflist:
                tk.Label(
                    self._tree_meta_sf_box,
                    text=f"  {sf}",
                    bg=BG_CARD,
                    fg="#86efac",
                    font=("Courier", 8),
                    anchor="w",
                ).pack(fill="x", padx=2, pady=1)
        else:
            tk.Label(
                self._tree_meta_sf_box,
                text=tr("common.none_parenthesized", "  (none)"),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(anchor="w", padx=2)
        if jflist:
            for jf in jflist:
                tk.Label(
                    self._tree_meta_jf_box,
                    text=f"  {jf}",
                    bg=BG_CARD,
                    fg="#fbbf24",
                    font=("Courier", 8),
                    anchor="w",
                ).pack(fill="x", padx=2, pady=1)
        else:
            tk.Label(
                self._tree_meta_jf_box,
                text=tr("common.none_parenthesized", "  (none)"),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(anchor="w", padx=2)

    # ── SIDEBAR ──────────────────────────────────────────────────
    def _build_sidebar(self, sb):
        # ── Loaded Trees Panel ────────────────────────────────────────
        _lt_outer = tk.Frame(sb, bg=BG_PANEL)
        _lt_outer.pack(fill="x")
        tk.Frame(_lt_outer, bg=BORDER_G, height=1).pack(fill="x")
        tk.Label(
            _lt_outer,
            text=tr("sidebar.loaded_trees", "  LOADED TREES"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7, "bold"),
            anchor="w",
        ).pack(fill="x", padx=4, pady=(3, 0))
        self._loaded_trees_inner = tk.Frame(sb, bg=BG_PANEL)
        self._loaded_trees_inner.pack(fill="x")
        tk.Frame(sb, bg=BORDER_G, height=1).pack(fill="x")
        self._refresh_loaded_trees_panel()

        # ── Tree Meta Panel (shared/joint focuses) ────────────────────
        meta = tk.Frame(sb, bg=BG_PANEL)
        meta.pack(fill="x")
        tk.Frame(meta, bg=BORDER_G, height=1).pack(fill="x")
        tk.Label(
            meta,
            text=tr("sidebar.tree_references", "  TREE REFERENCES"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7, "bold"),
            anchor="w",
        ).pack(fill="x", padx=4, pady=(3, 0))
        # Shared focuses row
        sf_row = tk.Frame(meta, bg=BG_PANEL)
        sf_row.pack(fill="x", padx=4, pady=(1, 0))
        tk.Label(
            sf_row,
            text="shared_focus:",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7),
            anchor="w",
            width=14,
        ).pack(side="left")
        self._tree_meta_sf_box = tk.Frame(
            sf_row, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_G
        )
        self._tree_meta_sf_box.pack(side="left", fill="x", expand=True)
        # Joint focuses row
        jf_row = tk.Frame(meta, bg=BG_PANEL)
        jf_row.pack(fill="x", padx=4, pady=(1, 4))
        tk.Label(
            jf_row,
            text="joint_focus:",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7),
            anchor="w",
            width=14,
        ).pack(side="left")
        self._tree_meta_jf_box = tk.Frame(
            jf_row, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_G
        )
        self._tree_meta_jf_box.pack(side="left", fill="x", expand=True)
        tk.Frame(meta, bg=BORDER_G, height=1).pack(fill="x")
        self._refresh_tree_meta_panel()

        # ── Header ───────────────────────────────────────────────────
        hdr = tk.Frame(sb, bg=BG_DARK)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=tr("sidebar.focus_properties", "  FOCUS PROPERTIES"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 10, "bold"),
            anchor="w",
            pady=8,
        ).pack(side="left")
        self._tree_src_lbl = tk.Label(
            hdr,
            text="",
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
            anchor="e",
            padx=6,
        )
        self._tree_src_lbl.pack(side="right")
        tk.Frame(sb, bg=BORDER_G, height=1).pack(fill="x")

        # ── "No selection" placeholder ────────────────────────────────
        wrap = tk.Frame(sb, bg=BG_PANEL)
        wrap.pack(fill="both", expand=True)
        self._sb_none = tk.Label(
            wrap,
            text=tr(
                "sidebar.no_selection",
                "\n\n  Click a focus to\n  edit its properties.\n\n  Right-click the canvas\n  to create a new focus.",
            ),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 10, "italic"),
            justify="left",
            anchor="nw",
        )
        self._sb_none.pack(fill="both", expand=True)

        # ── Tab container ─────────────────────────────────────────────
        self._tab_outer = tk.Frame(wrap, bg=BG_PANEL)
        # Alias used by _show_form/_hide_form. Set it now (not after the
        # sub-builders below) so the attribute survives a sub-builder failure.
        self._tab_host = self._tab_outer

        # Tab bar
        tab_bar = tk.Frame(self._tab_outer, bg=BG_DARK)
        tab_bar.pack(fill="x")
        self._tab_btns = {}
        self._active_tab = tk.StringVar(value="Properties")

        def _switch_tab(name):
            self._active_tab.set(name)
            for n, (btn, panel) in self._tab_btns.items():
                if n == name:
                    btn.config(
                        bg=BG_PANEL,
                        fg=BLUE,
                        relief="flat",
                        highlightbackground=BORDER_G,
                    )
                    panel.pack(fill="both", expand=True)
                    # Active tab underline
                    btn._line.config(bg=BLUE)
                else:
                    btn.config(
                        bg=BG_DARK,
                        fg=TEXT_DIM,
                        relief="flat",
                        highlightbackground=BG_DARK,
                    )
                    panel.pack_forget()
                    btn._line.config(bg=BG_DARK)

        tab_names = [
            ("Properties", tr("tab.properties", "Properties")),
            ("Effects", tr("tab.effects", "Effects")),
            ("Conditions", tr("tab.conditions", "Conditions")),
            ("Code", tr("tab.code", "Code")),
        ]

        for tname, tlabel in tab_names:
            col = tk.Frame(tab_bar, bg=BG_DARK)
            col.pack(side="left", expand=True, fill="x")
            btn = tk.Button(
                col,
                text=tlabel,
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "bold"),
                relief="flat",
                activebackground=BG_PANEL,
                activeforeground=BLUE,
                cursor="hand2",
                pady=6,
                bd=0,
                highlightthickness=0,
                command=lambda n=tname: _switch_tab(n),
            )
            btn.pack(fill="x")
            line = tk.Frame(col, bg=BG_DARK, height=2)
            line.pack(fill="x")
            btn._line = line
            # Scrollable panel per tab
            panel_outer = tk.Frame(self._tab_outer, bg=BG_PANEL)
            self._tab_btns[tname] = (btn, panel_outer)

        tk.Frame(self._tab_outer, bg=BORDER_G, height=1).pack(fill="x")

        # Per-tab scroll frames set up below
        self._sb_frm_props = None
        self._sb_frm_eff = None
        self._sb_frm_cond = None

        def _make_scroll_panel(parent):
            cv = tk.Canvas(parent, bg=BG_PANEL, highlightthickness=0)
            scr = tk.Scrollbar(parent, orient="vertical", command=cv.yview)
            frm = tk.Frame(cv, bg=BG_PANEL)
            win = cv.create_window((0, 0), window=frm, anchor="nw")
            cv.configure(yscrollcommand=scr.set)
            frm.bind(
                "<Configure>", lambda e, c=cv: c.configure(scrollregion=c.bbox("all"))
            )
            cv.bind(
                "<Configure>", lambda e, c=cv, w=win: c.itemconfig(w, width=e.width)
            )
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                cv.bind(ev, self._sb_scroll)
            scr.pack(side="right", fill="y")
            cv.pack(side="left", fill="both", expand=True)
            return frm

        # ── Tabs 1-4: built by dedicated sub-methods ──────────────────
        self._build_sidebar_props(self._tab_btns["Properties"][1], _make_scroll_panel)
        self._build_sidebar_effects(self._tab_btns["Effects"][1], _make_scroll_panel)
        self._build_sidebar_conditions(
            self._tab_btns["Conditions"][1], _make_scroll_panel
        )
        self._build_sidebar_code(self._tab_btns["Code"][1])
        # ── Show tab container (hidden until focus selected) ───────────
        # _show_form / _hide_form manage this; _tab_host alias set above.

        # Activate Properties tab by default
        _switch_tab("Properties")
        self._switch_tab_fn = _switch_tab

    def _build_sidebar_props(self, p, _make_scroll_panel):
        # ── TAB 1: Properties ─────────────────────────────────────────
        self._sb_frm = _make_scroll_panel(p)
        self._sb_frm_props = self._sb_frm

        self._fv_name = self._sb_entry(
            tr("focus.field.id", "Focus ID (tag):"), "TAG_focus_1"
        )
        self._fv_icon = self._sb_optmenu(
            tr("focus.field.icon_display", "Icon (display only):"), ICONS
        )
        self._fv_icon.trace_add("write", self._on_icon_change)
        self._fv_gfx = self._sb_gfx_picker()

        xyrow = tk.Frame(self._sb_frm, bg=BG_PANEL)
        xyrow.pack(fill="x", padx=8, pady=2)
        tk.Label(
            xyrow, text="X:", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 10), width=2
        ).pack(side="left")
        self._fv_x = tk.StringVar(value="0")
        tk.Entry(
            xyrow,
            textvariable=self._fv_x,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            width=5,
        ).pack(side="left", ipady=4, padx=(0, 6))
        tk.Label(
            xyrow, text="Y:", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 10), width=2
        ).pack(side="left")
        self._fv_y = tk.StringVar(value="0")
        tk.Entry(
            xyrow,
            textvariable=self._fv_y,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            width=5,
        ).pack(side="left", ipady=4)
        tk.Label(
            xyrow,
            text=tr("focus.field.grid_hint", "(grid)"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
        ).pack(side="left", padx=4)

        # ── OFFSETS section ───────────────────────────────────────────────
        tk.Frame(self._sb_frm, bg=BORDER_G, height=1).pack(
            fill="x", padx=6, pady=(6, 2)
        )
        off_hdr = tk.Frame(self._sb_frm, bg=BG_PANEL)
        off_hdr.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(
            off_hdr,
            text=tr("focus.offsets.title", "OFFSETS"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            anchor="w",
        ).pack(side="left")
        tk.Label(
            off_hdr,
            text=tr("focus.offsets.hint", "(conditional position shifts)"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 7, "italic"),
            anchor="w",
        ).pack(side="left", padx=4)
        self._offset_entries = []  # list of (x_var, y_var, trig_text) per offset block
        self._offset_box = tk.Frame(self._sb_frm, bg=BG_PANEL)
        self._offset_box.pack(fill="x", padx=8)
        self._add_offset_btn = tk.Button(
            self._sb_frm,
            text=tr("focus.offsets.add", "+ Add Offset"),
            command=self._add_offset,
            bg=BG_CARD,
            fg="#06b6d4",
            font=("Helvetica", 9),
            relief="flat",
            padx=6,
            pady=3,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground="#06b6d4",
        )
        self._add_offset_btn.pack(fill="x", padx=8, pady=(2, 4))
        tk.Frame(self._sb_frm, bg=BORDER_G, height=1).pack(
            fill="x", padx=6, pady=(2, 4)
        )

        self._fv_cost = self._sb_entry(
            tr("focus.field.cost", "Cost (1 = 7 days):"), "10"
        )

        # AI will_do raw block
        f_ai = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f_ai.pack(fill="x", padx=8, pady=2)
        hdr_ai = tk.Frame(f_ai, bg=BG_PANEL)
        hdr_ai.pack(fill="x")
        tk.Label(
            hdr_ai,
            text="ai_will_do = {",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            hdr_ai, text="}", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9)
        ).pack(side="right")
        self._fv_ai_raw = tk.Text(
            f_ai,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 9),
            relief="flat",
            height=5,
            highlightthickness=1,
            highlightbackground=BORDER_G,
            wrap="none",
            undo=True,
        )
        self._fv_ai_raw.pack(fill="x")
        # MD convention: use `base` at top level of ai_will_do
        self._fv_ai_raw.insert("1.0", "    base = 1")
        self._fv_ai = None

        self._fv_desc = self._sb_text(
            tr("focus.field.description", "Description (localisation):")
        )

        tk.Frame(self._sb_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=6)

        # PREREQS & MUTEX inside Properties tab
        self._sb_lbl(tr("focus.prerequisites.title", "PREREQUISITES"))
        self._prereq_box = tk.Frame(self._sb_frm, bg=BG_PANEL)
        self._prereq_box.pack(fill="x", padx=8)
        self._conn_btn = tk.Button(
            self._sb_frm,
            text=tr("focus.prerequisites.add", "+ Add Prerequisite"),
            command=self._pick_prereq,
            bg=BG_CARD,
            fg=BLUE,
            font=("Helvetica", 9),
            relief="flat",
            padx=6,
            pady=4,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BLUE,
        )
        self._conn_btn.pack(fill="x", padx=8, pady=3)

        tk.Frame(self._sb_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=6)
        self._sb_lbl(tr("focus.mutex.title", "MUTUALLY EXCLUSIVE"))
        self._mutex_box = tk.Frame(self._sb_frm, bg=BG_PANEL)
        self._mutex_box.pack(fill="x", padx=8)
        tk.Button(
            self._sb_frm,
            text=tr("focus.mutex.mode", "Mutex Mode - draw exclusion line"),
            command=self._toggle_mutex,
            bg=BG_CARD,
            fg=ORANGE,
            font=("Helvetica", 9),
            relief="flat",
            padx=6,
            pady=4,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=ORANGE,
        ).pack(fill="x", padx=8, pady=3)

        tk.Frame(self._sb_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=6)

        # Save / Delete / View Code
        tk.Button(
            self._sb_frm,
            text=tr("common.save_changes", "Save Changes"),
            command=self._apply,
            bg="#14532d",
            fg="#0a0a0a",
            font=("Helvetica", 10, "bold"),
            relief="flat",
            pady=6,
            cursor="hand2",
            highlightthickness=0,
        ).pack(fill="x", padx=8, pady=2)
        tk.Button(
            self._sb_frm,
            text=tr("focus.delete", "Delete Focus"),
            command=self._delete_focus,
            bg="#7f1d1d",
            fg="#0a0a0a",
            font=("Helvetica", 10),
            relief="flat",
            pady=5,
            cursor="hand2",
            highlightthickness=0,
        ).pack(fill="x", padx=8, pady=2)
        tk.Button(
            self._sb_frm,
            text=tr("focus.view_code", "View Focus Code  { }"),
            command=self._view_code,
            bg=BG_CARD,
            fg=TEXT,
            font=("Helvetica", 10),
            relief="flat",
            pady=5,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(fill="x", padx=8, pady=(2, 10))

    def _refresh_offsets(self, f=None):
        """Rebuild the OFFSETS UI rows from f.offsets. Clears and repopulates _offset_box."""
        if f is None:
            f = self.selected
        for w in self._offset_box.winfo_children():
            w.destroy()
        self._offset_entries = []
        if not f:
            return
        offsets = getattr(f, "offsets", [])
        if not offsets:
            tk.Label(
                self._offset_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w")
            return
        for i, off in enumerate(offsets):
            row = tk.Frame(
                self._offset_box,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_G,
                pady=2,
            )
            row.pack(fill="x", pady=2)
            # X / Y row + delete button
            xy_row = tk.Frame(row, bg=BG_CARD)
            xy_row.pack(fill="x", padx=4)
            tk.Label(
                xy_row,
                text="x:",
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=2,
            ).pack(side="left")
            x_var = tk.StringVar(value=str(off.get("x", 0)))
            tk.Entry(
                xy_row,
                textvariable=x_var,
                bg=BG_PANEL,
                fg=TEXT,
                font=("Helvetica", 9),
                relief="flat",
                width=5,
                highlightthickness=1,
                highlightbackground=BORDER_G,
            ).pack(side="left", ipady=2, padx=(0, 6))
            tk.Label(
                xy_row,
                text="y:",
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=2,
            ).pack(side="left")
            y_var = tk.StringVar(value=str(off.get("y", 0)))
            tk.Entry(
                xy_row,
                textvariable=y_var,
                bg=BG_PANEL,
                fg=TEXT,
                font=("Helvetica", 9),
                relief="flat",
                width=5,
                highlightthickness=1,
                highlightbackground=BORDER_G,
            ).pack(side="left", ipady=2)
            del_btn = tk.Button(
                xy_row,
                text="✕",
                bg=BG_CARD,
                fg=RED,
                relief="flat",
                font=("Georgia", 8),
                cursor="hand2",
                padx=3,
            )
            del_btn.config(command=lambda idx=i: self._del_offset(idx))
            del_btn.pack(side="right")
            # trigger raw block
            tk.Label(
                row,
                text="trigger = {",
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Courier", 8),
                anchor="w",
            ).pack(fill="x", padx=4)
            trig_text = tk.Text(
                row,
                bg=BG_PANEL,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Courier", 8),
                height=3,
                relief="flat",
                wrap="none",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            trig_text.pack(fill="x", padx=4, pady=(0, 2))
            trig_text.insert("1.0", off.get("trigger", ""))
            tk.Label(
                row, text="}", bg=BG_CARD, fg=TEXT_DIM, font=("Courier", 8), anchor="w"
            ).pack(fill="x", padx=4)
            self._offset_entries.append((x_var, y_var, trig_text))

    def _add_offset(self):
        """Add a blank offset entry to the selected focus and refresh UI."""
        if not self.selected:
            return
        self._save_offsets_to_focus()
        self.selected.offsets.append({"x": 0, "y": 0, "trigger": ""})
        self._refresh_offsets(self.selected)

    def _del_offset(self, idx):
        """Remove offset at idx from the selected focus and refresh UI."""
        if not self.selected:
            return
        self._save_offsets_to_focus()
        offs = getattr(self.selected, "offsets", [])
        if 0 <= idx < len(offs):
            offs.pop(idx)
        self._refresh_offsets(self.selected)

    def _save_offsets_to_focus(self):
        """Read current offset UI widgets and save to self.selected.offsets."""
        if not self.selected:
            return
        offs = []
        for x_var, y_var, trig_text in self._offset_entries:
            try:
                ox = int(x_var.get())
            except Exception:
                ox = 0
            try:
                oy = int(y_var.get())
            except Exception:
                oy = 0
            otrig = trig_text.get("1.0", "end").strip()
            offs.append({"x": ox, "y": oy, "trigger": otrig})
        self.selected.offsets = offs

    def _focus_flag_label(self, label):
        return {
            "cancel_if_invalid": tr(
                "focus.flag.cancel_if_invalid", "Cancel if invalid"
            ),
            "continue_if_invalid": tr(
                "focus.flag.continue_if_invalid", "Continue if invalid"
            ),
            "available_if_capitulated": tr(
                "focus.flag.available_if_capitulated", "Available if capitulated"
            ),
        }.get(label, label)


    def _build_sidebar_conditions(self, p, _make_scroll_panel):
        # ── TAB 3: Conditions ──────────────────────────────────────────
        cond_frm = _make_scroll_panel(p)
        self._sb_frm_cond = cond_frm

        # Temporarily point _sb_frm at cond frame for helpers
        _saved = self._sb_frm
        self._sb_frm = cond_frm

        self._sb_lbl(tr("focus.conditions.search_filters", "SEARCH FILTERS"))
        self._fv_search = self._sb_entry(
            tr("focus.conditions.search_filters_label", "search_filters:"),
            "FOCUS_FILTER_POLITICAL",
        )
        tk.Frame(cond_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=4)
        self._sb_lbl(tr("focus.conditions.availability", "AVAILABILITY"))
        self._fv_avail = self._sb_rawblock("available = {")
        tk.Frame(cond_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=4)
        self._sb_lbl(tr("focus.conditions.bypass", "BYPASS"))
        self._fv_bypass = self._sb_rawblock("bypass = {")
        tk.Frame(cond_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=4)
        self._sb_lbl(tr("focus.conditions.cancel", "CANCEL"))
        self._fv_cancel2 = self._sb_rawblock("cancel = {")
        tk.Frame(cond_frm, bg=BORDER_G, height=1).pack(fill="x", padx=6, pady=4)
        self._sb_lbl(tr("focus.conditions.flags", "FLAGS"))
        fr = tk.Frame(cond_frm, bg=BG_PANEL)
        fr.pack(fill="x", padx=8, pady=2)
        self._fv_cancel = self._sb_check(fr, "cancel_if_invalid", True)
        self._fv_continue = self._sb_check(fr, "continue_if_invalid", False)
        self._fv_cap = self._sb_check(fr, "available_if_capitulated", False)

        self._sb_frm = _saved  # restore to Properties frame

    def _build_sidebar_code(self, p):
        # ── TAB 4: Code ────────────────────────────────────────────────
        code_outer = tk.Frame(p, bg=BG_DARK)
        code_outer.pack(fill="both", expand=True)
        # toolbar row
        code_hdr = tk.Frame(code_outer, bg=BG_DARK)
        code_hdr.pack(fill="x", padx=8, pady=(6, 2))
        self._code_edit_mode = [False]
        self._code_edit_btn = tk.Button(
            code_hdr,
            text=tr("common.edit", "Edit"),
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        self._code_edit_btn.pack(side="right", padx=2)
        self._code_mode_lbl = tk.Label(
            code_hdr,
            text=tr("common.live", "live"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 7, "italic"),
        )
        self._code_mode_lbl.pack(side="right")

        def _copy_code():
            txt = self._code_txt.get("1.0", "end").strip()
            self.clipboard_clear()
            self.clipboard_append(txt)

        tk.Button(
            code_hdr,
            text=tr("common.copy", "Copy"),
            command=_copy_code,
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(side="right", padx=2)

        def _toggle_code_edit():
            self._code_edit_mode[0] = not self._code_edit_mode[0]
            if self._code_edit_mode[0]:
                # Enter edit mode — make text editable
                self._code_txt.config(
                    state="normal", bg="#0d1a0d", highlightbackground="#4ade80"
                )
                self._code_edit_btn.config(
                    text=tr("common.lock", "Lock"), fg="#4ade80", bg="#1a2c1a"
                )
                self._code_mode_lbl.config(
                    text=tr("common.editing", "editing"), fg="#4ade80"
                )
            else:
                # Lock: parse edits into the focus BEFORE overwriting the text
                if self.selected:
                    new_code = self._code_txt.get("1.0", "end").strip()
                    ok = self._apply_focus_code(self.selected, new_code)
                    if not ok:
                        # Parse failed — stay in edit mode so user can fix it
                        self._code_edit_mode[0] = True
                        return
                self._code_txt.config(
                    state="normal", bg="#050810", highlightbackground=BORDER_G
                )
                if self.selected:
                    self._refresh_code_tab(self.selected)
                self._code_txt.config(state="disabled")
                self._code_edit_btn.config(
                    text=tr("common.edit", "Edit"), fg=TEXT_DIM, bg=BG_CARD
                )
                self._code_mode_lbl.config(text=tr("common.live", "live"), fg=TEXT_DIM)

        self._code_edit_btn.config(command=_toggle_code_edit)
        # code text widget
        code_sb = tk.Scrollbar(code_outer, orient="vertical")
        code_sb.pack(side="right", fill="y", padx=(0, 4))
        self._code_txt = tk.Text(
            code_outer,
            bg="#050810",
            fg="#8aad8a",
            font=("Courier", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            wrap="none",
            state="disabled",
            yscrollcommand=code_sb.set,
        )
        code_sb.config(command=self._code_txt.yview)
        self._code_txt.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))

    def _sb_scroll(self, e):
        # Scroll whichever canvas is currently visible
        delta = -1 if (e.num == 4 or e.delta > 0) else 1
        w = e.widget
        # Walk up to find the canvas
        while w and not isinstance(w, tk.Canvas):
            try:
                w = w.master
            except Exception:
                break
        if w and isinstance(w, tk.Canvas):
            w.yview_scroll(delta, "units")

    def _sb_lbl(self, t):
        tk.Label(
            self._sb_frm,
            text=f"  {t}",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(4, 1))

    def _sb_entry(self, label, default):
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        tk.Label(
            f, text=label, bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9), anchor="w"
        ).pack(fill="x")
        var = tk.StringVar(value=default)
        tk.Entry(
            f,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        ).pack(fill="x", ipady=3)
        return var

    def _sb_optmenu(self, label, options):
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        tk.Label(
            f, text=label, bg=BG_PANEL, fg=TEXT_DIM, font=("Georgia", 8), anchor="w"
        ).pack(fill="x")
        var = tk.StringVar(value=options[0])
        om = tk.OptionMenu(f, var, *options)
        om.config(
            bg=BG_CARD,
            fg=TEXT,
            activebackground=BORDER_G,
            font=("Helvetica", 13),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            anchor="w",
        )
        om["menu"].config(bg=BG_CARD, fg=TEXT, activebackground=BORDER_G)
        om.pack(fill="x")
        return var

    def _sb_text(self, label):
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        tk.Label(
            f, text=label, bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9), anchor="w"
        ).pack(fill="x")
        t = tk.Text(
            f,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            height=3,
            wrap="word",
        )
        t.pack(fill="x")
        return t

    def _sb_rawblock(self, label):
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        hdr = tk.Frame(f, bg=BG_PANEL)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text=label, bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9), anchor="w"
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            hdr, text="}", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9), anchor="e"
        ).pack(side="right")
        t = tk.Text(
            f,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Courier", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            height=3,
            wrap="none",
            undo=True,
        )
        t.pack(fill="x")
        return t

    def _sb_check(self, parent, label, default):
        var = tk.BooleanVar(value=default)
        tk.Checkbutton(
            parent,
            text=self._focus_flag_label(label),
            variable=var,
            bg=BG_PANEL,
            fg=TEXT,
            selectcolor=BG_CARD,
            activebackground=BG_PANEL,
            font=("Helvetica", 10),
            anchor="w",
            cursor="hand2",
        ).pack(fill="x")
        return var

    def _show_form(self):
        self._sb_none.pack_forget()
        self._tab_host.pack(fill="both", expand=True)
        # Also expose legacy _sb_cv / _sb_scr references (no-ops now)
        self._sb_cv = None
        self._sb_scr = None

    def _hide_form(self):
        self._tab_host.pack_forget()
        self._sb_none.pack(fill="both", expand=True)






    def _flash_added(self, label):
        """Confirm an add in the browser status line and the main hint bar."""
        msg = tr("focus.effects.added_one", "Added: {name}", name=label)
        st = getattr(self, "_eb_status", None)
        try:
            if st is not None and st.winfo_exists():
                st.config(text=msg)
        except tk.TclError:
            pass
        self._hint(msg)



















    # ── MOUSE EVENTS ────────────────────────────────────────────







    # ── SIDEBAR RESIZE SASH ─────────────────────────────────────

    # ════════════════════════════════════════════════════════════════
    # MOD LOADING
    # ════════════════════════════════════════════════════════════════





    # ── GFX Picker sidebar widget ────────────────────────────────────
    def _sb_gfx_picker(self):
        """Icon GFX name entry — plain text, no sidebar preview (shown on canvas only)."""
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        tk.Label(
            f,
            text=tr("focus.field.icon_gfx_export", "Icon GFX name (export):"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            anchor="w",
        ).pack(fill="x")
        row = tk.Frame(f, bg=BG_PANEL)
        row.pack(fill="x")
        var = tk.StringVar(value="GFX_goal_generic_political_pressure")
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
        ent.pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(
            row,
            text=tr("common.browse_symbol", "⊞"),
            command=self._open_gfx_browser,
            bg=BG_CARD,
            fg=TEXT_DIM,
            relief="flat",
            font=("Helvetica", 11),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            padx=4,
        ).pack(side="right", padx=(2, 0))
        self._gfx_dd = None
        self._gfx_preview = None  # no sidebar preview
        return var

    def _set_gfx(self, name):
        self._fv_gfx.set(name)
        if self.selected:
            self.selected.gfx = name
            self.selected._draw_key = None
            self._redraw_now()

    def _update_gfx_preview(self, gfx_name):
        """No sidebar preview — just invalidate canvas so icon redraws."""
        if self.selected and getattr(self.selected, "gfx", "") != gfx_name:
            self.selected.gfx = gfx_name
            self.selected._draw_key = None
            self._redraw_now()

    def _open_gfx_browser(self):
        """
        Instant open: folder list shows immediately (no scanning).
        Click folder -> file list built in background thread.
        Scroll -> images loaded on demand per visible tile only.
        """
        if not MOD.loaded:
            folder = filedialog.askdirectory(
                title=tr(
                    "filedialog.select_icon_folder", "Select folder with icon files"
                )
            )
            if folder:
                self._gfx_browse_files(folder)
            return

        goals_root = os.path.join(MOD.root, "gfx", "interface", "goals")
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
        # Loose files in goals/ root
        loose = [
            f
            for f in os.listdir(goals_root)
            if f.lower().endswith((".dds", ".png", ".tga"))
        ]
        if loose:
            folders.append(("[goals root]", goals_root))
        # Subfolders
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

        # ── Window ────────────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title(tr("gfx.browser.title", "GFX Browser"))
        win.configure(bg=BG_DARK)
        win.geometry("900x580")
        win.resizable(True, True)

        panes = tk.Frame(win, bg=BG_DARK)
        panes.pack(fill="both", expand=True, padx=8, pady=8)

        # Left: folder list (text only, instant)
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

        # Right panel
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

        # Bottom bar
        bot = tk.Frame(win, bg=BG_DARK)
        bot.pack(fill="x", padx=10, pady=6)
        selected_var = tk.StringVar(value="")
        _initial_gfx = self._fv_gfx.get()
        tk.Label(
            bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
        ).pack(side="left", padx=4)
        tk.Button(
            bot,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right", padx=4)

        def _apply():
            self._set_gfx(selected_var.get())
            win.destroy()

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
                _sel_btn.config(
                    bg="#14532d", fg="#0a0a0a", cursor="hand2", state="normal"
                )
            elif v:
                _sel_btn.config(
                    bg="#1e6b3a", fg="#c8f0d8", cursor="hand2", state="normal"
                )
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
            "img_cache": {},  # path -> PhotoImage | None
            "drawn": set(),  # indices already rendered
            "canvas_ids": {},  # idx -> (rect_id, img_id or txt_id, lbl_id)
            "sel_idx": None,
            "scan_job": None,  # pending after() job
            "load_gen": None,  # background thread
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
                tags=("tile", "t%d" % idx),
            )
            # Placeholder spinner text while image loads
            iid = cv.create_text(
                x + TILE_W // 2,
                y + 44,
                text="...",
                fill=TEXT_DIM,
                font=("Helvetica", 14),
                tags=("tile", "t%d" % idx),
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
                tags=("tile", "t%d" % idx),
            )
            _st["canvas_ids"][idx] = (rid, iid, lid)
            for item in (rid, iid, lid):
                cv.tag_bind(item, "<Button-1>", lambda e, i=idx: _select_tile(i))
                cv.tag_bind(
                    item,
                    "<Double-Button-1>",
                    lambda e, i=idx: [_select_tile(i), _apply()],
                )
            # If image already cached, fill it in right now
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
            if img:
                new_iid = cv.create_image(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 44,
                    anchor="center",
                    image=img,
                    tags=("tile", "t%d" % idx),
                )
            else:
                new_iid = cv.create_text(
                    _tile_xy(idx)[0] + TILE_W // 2,
                    _tile_xy(idx)[1] + 30,
                    text="?",
                    fill=TEXT_DIM,
                    font=("Helvetica", 20),
                    tags=("tile", "t%d" % idx),
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
                if path in _st["img_cache"]:
                    continue
                img = None
                try:
                    if _PIL_OK and os.path.exists(path):
                        pil = _PILImage.open(path).convert("RGBA")
                        rs = getattr(
                            _PILImage, "LANCZOS", getattr(_PILImage, "ANTIALIAS", 1)
                        )
                        pil = pil.resize((72, 72), rs)
                        img = _PILImageTk.PhotoImage(pil)
                except Exception:
                    pass
                _st["img_cache"][path] = img
                # Tell main thread to update this tile
                _safe_after(win, 0, lambda i=idx: _fill_image(i))

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
            # Background load for visible + next ~40 tiles
            last = max(visible) if visible else 0
            ahead = list(range(last + 1, min(last + 41, len(_st["pairs"]))))
            to_load = [
                i
                for i in (visible + ahead)
                if _st["pairs"][i][1] not in _st["img_cache"]
            ]
            if to_load:
                snapshot = list(_st["pairs"])
                t = threading.Thread(
                    target=_bg_load_images, args=(snapshot, to_load), daemon=True
                )
                t.start()

        def _rebuild(pairs):
            cv.delete("all")
            _st["pairs"] = pairs
            _st["drawn"].clear()
            _st["canvas_ids"].clear()
            _st["sel_idx"] = None
            # Keep img_cache across folders — avoids reloading same files
            if not pairs:
                status_lbl.config(text=tr("gfx.icons_count", "{count} icons", count=0))
                return
            status_lbl.config(text="%d icons" % len(pairs))
            rows = (len(pairs) + COLS - 1) // COLS
            total_h = PAD + rows * (TILE_H + PAD)
            total_w = PAD + COLS * (TILE_W + PAD)
            cv.configure(scrollregion=(0, 0, total_w, total_h))
            cv.yview_moveto(0)
            _safe_after_idle(win, _lazy_fill)

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
            win.update_idletasks()
            # Collect file list (fast — just filenames, no image loading)
            pairs = _collect_files(folder_path)
            _rebuild(pairs)

        def _on_folder_select(evt):
            sel = folder_lb.curselection()
            if not sel:
                return
            _load_folder(folders[sel[0]][1])

        cv.bind("<Configure>", lambda e: _safe_after_idle(win, _lazy_fill))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                ev,
                lambda e: [
                    cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                    _safe_after_idle(win, _lazy_fill),
                ],
            )
        folder_lb.bind("<<ListboxSelect>>", _on_folder_select)
        search_var.trace_add(
            "write",
            lambda *_: _safe_after(
                win,
                300,
                lambda: _on_folder_select(None) if folder_lb.curselection() else None,
            ),
        )

        # Auto-select first folder
        if folders:
            folder_lb.selection_set(0)
            _load_folder(folders[0][1])

    def _gfx_browse_files(self, folder):
        """Fallback lazy browser — no mod loaded."""
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
        win = tk.Toplevel(self)
        win.title(tr("gfx.browser.title", "GFX Browser"))
        win.configure(bg=BG_DARK)
        win.geometry("700x480")
        cvf = tk.Frame(win, bg=BG_PANEL)
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
        selected_var = tk.StringVar(value=self._fv_gfx.get())
        bot = tk.Frame(win, bg=BG_DARK)
        bot.pack(fill="x", padx=8, pady=6)
        tk.Label(
            bot, textvariable=selected_var, bg=BG_DARK, fg=BLUE, font=("Helvetica", 9)
        ).pack(side="left")
        tk.Button(
            bot,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right", padx=4)

        def _apply():
            self._set_gfx(selected_var.get())
            win.destroy()

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
        _cache = {}
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
                cv.tag_bind(
                    item, "<Button-1>", lambda e, k=gfx_key: selected_var.set(k)
                )
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
                cv.tag_bind(
                    item, "<Button-1>", lambda e, k=gfx_key: selected_var.set(k)
                )
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
                if path in _cache:
                    continue
                img = None
                try:
                    if _PIL_OK and os.path.exists(path):
                        pil = _PILImage.open(path).convert("RGBA")
                        rs = getattr(
                            _PILImage, "LANCZOS", getattr(_PILImage, "ANTIALIAS", 1)
                        )
                        pil = pil.resize((72, 72), rs)
                        img = _PILImageTk.PhotoImage(pil)
                except Exception:
                    pass
                _cache[path] = img
                _safe_after(win, 0, lambda x=i: _fill(x))

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
                t = threading.Thread(
                    target=_bg, args=(list(pairs), to_load), daemon=True
                )
                t.start()

        cv.bind("<Configure>", lambda e: _safe_after_idle(win, _lazy))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind(
                ev,
                lambda e: [
                    cv.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units"),
                    _safe_after_idle(win, _lazy),
                ],
            )
        _safe_after_idle(win, _lazy)

    def _attach_autocomplete(self, entry_widget, var, get_choices_fn):
        """Attach a live autocomplete popup to any Entry widget."""
        _popup = [None]

        def _show(*_):
            if _popup[0] and _popup[0].winfo_exists():
                _popup[0].destroy()
            q = var.get().lower()
            choices = [c for c in get_choices_fn() if q in c.lower()][:50]
            if not choices:
                return
            pw = tk.Toplevel(self)
            pw.wm_overrideredirect(True)
            pw.configure(bg=BORDER_G)
            entry_widget.update_idletasks()
            x = entry_widget.winfo_rootx()
            y = entry_widget.winfo_rooty() + entry_widget.winfo_height() + 1
            w = max(entry_widget.winfo_width(), 260)
            h = min(len(choices) * 22 + 4, 220)
            pw.geometry(f"{w}x{h}+{x}+{y}")
            pw.lift()
            lb = tk.Listbox(
                pw,
                bg=BG_CARD,
                fg=TEXT,
                selectbackground=BLUE,
                font=("Courier", 9),
                relief="flat",
                bd=1,
                activestyle="none",
                cursor="hand2",
                selectforeground=TEXT,
            )
            sb = tk.Scrollbar(pw, orient="vertical", command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            lb.pack(fill="both", expand=True)
            for c in choices:
                lb.insert("end", c)

            def _pick(e=None):
                sel = lb.curselection()
                if sel:
                    var.set(lb.get(sel[0]))
                _hide()

            def _hide(*_):
                if _popup[0] and _popup[0].winfo_exists():
                    _popup[0].destroy()
                _popup[0] = None

            lb.bind("<ButtonRelease-1>", _pick)
            lb.bind("<Return>", _pick)
            pw.bind("<Escape>", _hide)
            _popup[0] = pw

        def _hide(*_):
            _safe_after(
                self,
                150,
                lambda: _popup[0].destroy()
                if _popup[0] and _popup[0].winfo_exists()
                else None,
            )
            _popup[0] = None

        entry_widget.bind("<KeyRelease>", _show)
        entry_widget.bind("<FocusOut>", _hide)

    def _get_mod_suggestions(self, etype, fname):
        """Return a list of mod-aware suggestions for a given effect+field."""
        if not MOD.loaded:
            return []
        # Events
        if etype in ("country_event", "news_event") and fname == "id":
            ids = []
            for lst in MOD.event_ids.values():
                ids.extend(lst)
            return sorted(set(ids))
        # Ideas
        if etype in ("add_ideas", "remove_ideas") and fname == "idea_name":
            return sorted(MOD.idea_ids)
        if etype == "swap_ideas" and fname in ("remove_idea", "add_idea"):
            return sorted(MOD.idea_ids)
        if etype == "add_timed_idea" and fname == "idea":
            return sorted(MOD.idea_ids)
        # Dynamic modifiers
        if (
            etype in ("add_dynamic_modifier", "remove_dynamic_modifier")
            and fname == "modifier"
        ):
            return sorted(MOD.dyn_mod_ids)
        if etype == "custom_effect_tooltip_block" and fname == "MODIFIER":
            return sorted(MOD.dyn_mod_ids)
        # Decisions
        if "decision_category" in fname or (
            etype == "unlock_decision_category_tooltip" and fname == "category"
        ):
            return sorted(MOD.decision_cats)
        if "decision" in fname or (
            etype == "unlock_decision_tooltip" and fname == "decision"
        ):
            return sorted(MOD.decision_ids)
        # add_to_variable / set_variable — variable names
        if etype in ("add_to_variable", "set_variable") and fname in (
            "variable",
            "var_name",
        ):
            return sorted(MOD.variables)
        # Country tags
        if fname in ("target", "country", "tag", "producer") and etype not in (
            "add_tech_bonus",
        ):
            return sorted(MOD.country_tags)
        # Focus IDs
        if fname == "focus_id" or (
            etype == "complete_national_focus" and fname == "focus_id"
        ):
            return sorted(MOD.focus_ids)
        return []

    def _sash_pr(self, e):
        self._sash_x = e.x_root

    def _sash_mv(self, e):
        dx = self._sash_x - e.x_root  # dragging left = wider sidebar
        self._sash_x = e.x_root
        new_w = max(260, min(700, self._sb_width + dx))
        if new_w != self._sb_width:
            self._sb_width = new_w
            self._sb_frame.config(width=new_w)

    def _sash_rl(self, e):
        pass








    # ── SELECTION ───────────────────────────────────────────────
    def _on_icon_change(self, *_):
        if not self.selected:
            return
        self.selected.icon = self._fv_icon.get()
        self.selected._draw_key = None
        self._redraw_now()

    def _autosave(self):
        if not self.selected:
            return
        f = self.selected
        raw = self._fv_name.get().strip()
        if not raw:
            return
        try:
            f.name = re.sub(r"[^A-Za-z0-9_]", "_", raw)
            f.icon = self._fv_icon.get()
            f.gfx = self._fv_gfx.get().strip() or "GFX_goal_generic_political_pressure"
            f.cost = int(self._fv_cost.get())
            raw_ai = self._fv_ai_raw.get("1.0", "end").strip()
            f.ai_will_do_raw = raw_ai
            # Extract top-level numeric value — accept either `base` or `factor`
            # (MD uses `base` at the ai_will_do top level, `factor` in modifier sub-blocks).

            m = re.search(r"^\s*base\s*=\s*([\d.]+)", raw_ai, re.MULTILINE)
            if not m:
                m = re.search(r"^\s*factor\s*=\s*([\d.]+)", raw_ai, re.MULTILINE)
            f.ai_will_do = int(float(m.group(1))) if m else 1
            nx = int(self._fv_x.get())
            ny = int(self._fv_y.get())
            if not any(
                o.x == nx and o.y == ny and o.id != f.id for o in self.focuses.values()
            ):
                f.x = nx
                f.y = ny
            f.desc = self._fv_desc.get("1.0", "end").strip()
            f.search_filters = self._fv_search.get().strip() or "FOCUS_FILTER_POLITICAL"
            f.available_cond = self._fv_avail.get("1.0", "end").strip()
            f.bypass_cond = self._fv_bypass.get("1.0", "end").strip()
            f.cancel_cond = self._fv_cancel2.get("1.0", "end").strip()
            f.cancel_if_invalid = self._fv_cancel.get()
            f.continue_if_invalid = self._fv_continue.get()
            f.available_if_capitulated = self._fv_cap.get()
            self._save_offsets_to_focus()
            f._draw_key = None
        except (ValueError, Exception):
            pass

    def _select(self, f):
        if self.selected and self.selected.id != f.id:
            self._autosave()
        self.selected = f
        self._redraw()
        self._show_form()
        self._populate(f)
        self._update_focus_list_selection()
        self._update_statusbar()

    def _deselect(self):
        self.selected = None
        self._hide_form()
        self._redraw()

    def _populate(self, f):
        # Update tree source label in header
        t_idx = getattr(f, "tree_idx", 0)
        if t_idx > 0 and t_idx <= len(self._extra_trees):
            et = self._extra_trees[t_idx - 1]
            badge_txt, badge_col = self._get_tree_badge(t_idx)
            if hasattr(self, "_tree_src_lbl"):
                self._tree_src_lbl.config(
                    text=f"[{badge_txt}] {et['type']}  {os.path.basename(et['file_path'])}",
                    fg=badge_col,
                )
        else:
            if hasattr(self, "_tree_src_lbl"):
                self._tree_src_lbl.config(text="[M] main", fg=TEXT_DIM)
        self._fv_name.set(f.name)
        self._fv_icon.set(f.icon)
        gfx = getattr(f, "gfx", "GFX_goal_generic_political_pressure")
        self._fv_gfx.set(gfx)
        self._fv_x.set(str(f.x))
        self._fv_y.set(str(f.y))
        self._fv_cost.set(str(f.cost))
        self._fv_ai_raw.delete("1.0", "end")
        raw = getattr(f, "ai_will_do_raw", "").strip()
        if raw:
            self._fv_ai_raw.insert("1.0", raw)
        else:
            # MD convention: ai_will_do uses `base = X` at top level
            self._fv_ai_raw.insert("1.0", "    base = %s" % f.ai_will_do)
        self._fv_desc.delete("1.0", "end")
        self._fv_desc.insert("1.0", f.desc)
        self._fv_search.set(getattr(f, "search_filters", "FOCUS_FILTER_POLITICAL"))
        for tv, attr in [
            (self._fv_avail, "available_cond"),
            (self._fv_bypass, "bypass_cond"),
            (self._fv_cancel2, "cancel_cond"),
        ]:
            tv.delete("1.0", "end")
            tv.insert("1.0", getattr(f, attr, ""))
        self._fv_cancel.set(f.cancel_if_invalid)
        self._fv_continue.set(f.continue_if_invalid)
        self._fv_cap.set(f.available_if_capitulated)
        self._refresh_offsets(f)
        self._refresh_prereqs()
        self._refresh_mutex()
        self._refresh_effects()
        self._refresh_code_tab(f)

    def _refresh_code_tab(self, f):
        """Update the Code tab live preview for focus f."""
        if not hasattr(self, "_code_txt"):
            return
        if self._code_edit_mode[0]:
            return
        out = self._build_focus_code(f)
        self._code_txt.config(state="normal")
        self._code_txt.delete("1.0", "end")
        self._code_txt.insert("1.0", out)
        self._code_txt.config(state="disabled")

    def _apply_focus_code(self, f, new_code):
        """Parse an edited focus block back into the focus object. Returns True on success."""

        try:

            def _extract_block(text, start):
                depth = 0
                i = start
                while i < len(text):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            return text[start + 1 : i].strip(), i
                    i += 1
                return text[start + 1 :].strip(), len(text) - 1

            def _extract_raw_block(text, key):
                m = re.search(rf"\b{re.escape(key)}\s*=\s*\{{", text)
                if not m:
                    return ""
                inner, _ = _extract_block(text, m.end() - 1)
                return inner.strip()

            # ── Simple scalar fields ───────────────────────────────────
            m = re.search(r"\bid\s*=\s*(\S+)", new_code)
            if m:
                f.name = m.group(1)

            m = re.search(r"\bicon\s*=\s*(\S+)", new_code)
            if m:
                f.gfx = m.group(1)

            m = re.search(r"(?<![a-z_])x\s*=\s*(-?\d+)", new_code)
            if m:
                f.x = int(m.group(1))

            m = re.search(r"(?<![a-z_])y\s*=\s*(-?\d+)", new_code)
            if m:
                f.y = int(m.group(1))

            m = re.search(r"\bcost\s*=\s*([\d.]+)", new_code)
            if m:
                try:
                    f.cost = int(float(m.group(1)))
                except Exception:
                    pass

            m = re.search(r"\brelative_position_id\s*=\s*(\S+)", new_code)
            if m:
                f.relative_position_id = m.group(1)

            for flag, attr in [
                ("cancel_if_invalid", "cancel_if_invalid"),
                ("continue_if_invalid", "continue_if_invalid"),
                ("available_if_capitulated", "available_if_capitulated"),
            ]:
                m = re.search(rf"\b{flag}\s*=\s*(yes|no)", new_code)
                if m:
                    setattr(f, attr, m.group(1) == "yes")

            m = re.search(r"\bsearch_filters\s*=\s*\{([^}]*)\}", new_code)
            if m:
                f.search_filters = m.group(1).strip()

            # ── Block fields ───────────────────────────────────────────
            for key, attr in [
                ("available", "available_cond"),
                ("bypass", "bypass_cond"),
                ("cancel", "cancel_cond"),
                ("will_lead_to_war_with", "will_lead_to_war_with"),
                ("complete_tooltip", "complete_tooltip"),
                ("select_effect", "select_effect"),
                ("bypass_effect", "bypass_effect"),
            ]:
                raw = _extract_raw_block(new_code, key)
                if raw is not None and raw != "":
                    setattr(f, attr, raw)

            raw_ai = _extract_raw_block(new_code, "ai_will_do")
            if raw_ai:
                f.ai_will_do_raw = raw_ai

            raw_reward = _extract_raw_block(new_code, "completion_reward")
            if raw_reward:
                f.effects = [{"type": "_raw_block", "fields": {"raw": raw_reward}}]

            # ── Parse offset blocks ────────────────────────────────────
            _parsed_offsets = []
            for _om in re.finditer(r"\boffset\s*=\s*\{", new_code):
                _os = _om.end() - 1
                _od = 0
                _oi = _os
                while _oi < len(new_code):
                    if new_code[_oi] == "{":
                        _od += 1
                    elif new_code[_oi] == "}":
                        _od -= 1
                        if _od == 0:
                            break
                    _oi += 1
                _oinner = new_code[_os + 1 : _oi]
                _oxm = re.search(r"\bx\s*=\s*(-?\d+)", _oinner)
                _oym = re.search(r"\by\s*=\s*(-?\d+)", _oinner)
                _ox = int(_oxm.group(1)) if _oxm else 0
                _oy = int(_oym.group(1)) if _oym else 0
                _otrig = _extract_raw_block(_oinner, "trigger")
                _parsed_offsets.append({"x": _ox, "y": _oy, "trigger": _otrig})
            f.offsets = _parsed_offsets

            # ── Sync sidebar fields & canvas ───────────────────────────
            if self.selected and self.selected.id == f.id:
                self._populate(f)
                for tv, attr in [
                    (self._fv_avail, "available_cond"),
                    (self._fv_bypass, "bypass_cond"),
                    (self._fv_cancel2, "cancel_cond"),
                ]:
                    try:
                        tv.config(state="normal")
                        tv.delete("1.0", "end")
                        tv.insert("1.0", getattr(f, attr, ""))
                    except Exception:
                        pass
            # Preserve viewport exactly — code edits must never move the camera
            _saved_zoom = self.zoom
            _saved_offset = self.offset[:]
            # Invalidate draw cache for this focus so the canvas updates its label
            f._draw_key = None
            self._redraw()

            # Schedule viewport restore AFTER the throttled redraw fires (16ms + margin)
            def _restore_vp():
                self.zoom = _saved_zoom
                self.offset[0] = _saved_offset[0]
                self.offset[1] = _saved_offset[1]
                self._draw_lines()
                for foc in self.focuses.values():
                    self._draw_focus(foc)

            self.cv.after(30, _restore_vp)
            return True
        except Exception as ex:
            self._log_error(str(ex))
            messagebox.showerror(
                tr("dialog.parse_error.title", "Parse Error"),
                tr(
                    "dialog.parse_error.body",
                    "Could not parse your edits:\n{error}\n\nCheck Error Log for details.",
                    error=ex,
                ),
            )
            return False

    def _build_focus_code(self, f):
        """Render a single focus block as HOI4 script (used by Code tab)."""
        I = "\t\t"
        out = [
            "focus = {",
            f"{I}id = {f.name}",
            f"{I}icon = {getattr(f,'gfx','GFX_goal_generic_political_pressure')}",
            "",
        ]
        rel_id = getattr(f, "relative_position_id", None)
        parent = (
            next((foc for foc in self.focuses.values() if foc.name == rel_id), None)
            if rel_id
            else None
        )
        if parent:
            out += [
                f"{I}x = {f.x - parent.x}",
                f"{I}y = {f.y - parent.y}",
                f"{I}relative_position_id = {rel_id}",
            ]
        else:
            out += [f"{I}x = {f.x}", f"{I}y = {f.y}"]
        for _off in getattr(f, "offsets", []):
            out.append(f"{I}offset = {{")
            out.append(f"{I}\tx = {_off['x']}")
            out.append(f"{I}\ty = {_off['y']}")
            if _off.get("trigger", "").strip():
                out.append(f"{I}\ttrigger = {{")
                for _ln in _off["trigger"].strip().splitlines():
                    out.append(f"{I}\t\t{_ln.strip()}")
                out.append(f"{I}\t}}")
            out.append(f"{I}}}")
        out += ["", f"{I}cost = {f.cost}", ""]
        for grp in f.prereqs:
            valid = [p for p in grp if p in self.focuses]
            if valid:
                inner = " ".join(f"focus = {self.focuses[p].name}" for p in valid)
                out.append(f"\t\tprerequisite = {{ {inner} }}")
        for mid in f.mutex:
            if mid in self.focuses:
                out.append(
                    f"\t\tmutually_exclusive = {{ focus = {self.focuses[mid].name} }}"
                )
        sf = getattr(f, "search_filters", "").strip()
        if sf:
            out.append(f"{I}search_filters = {{ {sf} }}")
        avail = getattr(f, "available_cond", "").strip()
        if avail:
            out.append(f"{I}available = {{")
            for ln in avail.splitlines():
                out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        bypass = getattr(f, "bypass_cond", "").strip()
        if bypass:
            out.append(f"{I}bypass = {{")
            for ln in bypass.splitlines():
                out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        cancelc = getattr(f, "cancel_cond", "").strip()
        if cancelc:
            out.append(f"{I}cancel = {{")
            for ln in cancelc.splitlines():
                out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        wltww = getattr(f, "will_lead_to_war_with", "").strip()
        if wltww:
            out.append(f"{I}will_lead_to_war_with = {{")
            for ln in wltww.splitlines():
                if ln.strip():
                    out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        ctip = getattr(f, "complete_tooltip", "").strip()
        if ctip:
            out.append(f"{I}complete_tooltip = {{")
            for ln in ctip.splitlines():
                if ln.strip():
                    out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        sel_eff = getattr(f, "select_effect", "").strip()
        if sel_eff:
            out.append(f"{I}select_effect = {{")
            for ln in sel_eff.splitlines():
                if ln.strip():
                    out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        if not f.cancel_if_invalid:
            out.append(f"{I}cancel_if_invalid = no")
        if f.continue_if_invalid:
            out.append(f"{I}continue_if_invalid = yes")
        if f.available_if_capitulated:
            out.append(f"{I}available_if_capitulated = yes")
        out += ["", f"{I}completion_reward = {{"]
        if f.effects:
            for eff in f.effects:
                out.append(self._render_effect(eff))
        else:
            out.append(f"{I}\t# add effects here")
        out.append(f"{I}}}")
        bp_eff = getattr(f, "bypass_effect", "").strip()
        if bp_eff:
            out.append(f"{I}bypass_effect = {{")
            for ln in bp_eff.splitlines():
                if ln.strip():
                    out.append(f"{I}\t{ln.strip()}")
            out.append(f"{I}}}")
        raw_ai = getattr(f, "ai_will_do_raw", "").strip()
        # MD convention: ai_will_do uses `base` at top level, `factor` only in modifier sub-blocks
        out += [
            "",
            f"{I}ai_will_do = {{",
            f"{I}\t{raw_ai}" if raw_ai else f"{I}\tbase = {f.ai_will_do}",
            f"{I}}}",
            "}",
        ]
        return "\n".join(out)

    def _refresh_prereqs(self):
        for w in self._prereq_box.winfo_children():
            w.destroy()
        if not self.selected or not self.selected.prereqs:
            tk.Label(
                self._prereq_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w")
            return
        for gi, grp in enumerate(self.selected.prereqs):
            names = [
                self.focuses[p].name if p in self.focuses else f"?{p}" for p in grp
            ]
            row = tk.Frame(
                self._prereq_box,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text="AND: " + " OR ".join(names),
                bg=BG_CARD,
                fg=TEXT,
                font=("Helvetica", 9),
                anchor="w",
                padx=4,
            ).pack(side="left", fill="x", expand=True)
            tk.Button(
                row,
                text="✕",
                command=lambda g=gi: self._rm_prereq(g),
                bg=BG_CARD,
                fg=RED,
                relief="flat",
                font=("Georgia", 8),
                cursor="hand2",
                padx=3,
            ).pack(side="right")

    def _refresh_mutex(self):
        for w in self._mutex_box.winfo_children():
            w.destroy()
        if not self.selected or not self.selected.mutex:
            tk.Label(
                self._mutex_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Georgia", 9, "italic"),
            ).pack(anchor="w")
            return
        for i, mid in enumerate(self.selected.mutex):
            name = self.focuses[mid].name if mid in self.focuses else f"?{mid}"
            row = tk.Frame(
                self._mutex_box,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground="#5a2020",
            )
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=f"✖ {name}",
                bg=BG_CARD,
                fg=ORANGE,
                font=("Georgia", 8),
                anchor="w",
                padx=4,
            ).pack(side="left", fill="x", expand=True)
            tk.Button(
                row,
                text="✕",
                command=lambda idx=i: self._rm_mutex(idx),
                bg=BG_CARD,
                fg=RED,
                relief="flat",
                font=("Georgia", 8),
                cursor="hand2",
                padx=3,
            ).pack(side="right")



    def _view_code(self):
        """Pop up a window to view AND edit the HOI4 script for the selected focus."""
        f = self.selected
        if not f:
            messagebox.showinfo(
                tr("focus_code.title", "View Code"),
                tr(
                    "focus_code.no_focus_selected",
                    "No focus selected.\nClick a focus on the canvas first.",
                ),
            )
            return

        # Use the canonical full builder so condition blocks and the new
        # preserved fields (will_lead_to_war_with, complete_tooltip, etc.)
        # all show up in the popup.
        code = self._build_focus_code(f)

        # ── Popup window ────────────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title(tr("focus_code.window_title", "Focus Code - {focus}", focus=f.name))
        win.configure(bg="#0d1117")
        win.geometry("680x580")
        win.resizable(True, True)

        # Header
        hdr = tk.Frame(win, bg="#161b22", pady=6)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=f"  📄  {f.name}",
            bg="#161b22",
            fg=TEXT,
            font=("Courier", 11, "bold"),
        ).pack(side="left", padx=6)
        tk.Button(
            hdr,
            text="✕",
            command=win.destroy,
            bg="#161b22",
            fg=TEXT_DIM,
            font=("Helvetica", 10),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER_G,
        ).pack(side="right", padx=8)

        # Copy button row
        btn_row = tk.Frame(win, bg=BG_PANEL, pady=4)
        btn_row.pack(fill="x", padx=8)

        def copy_code():
            content = txt.get("1.0", "end")
            win.clipboard_clear()
            win.clipboard_append(content)
            copy_btn.config(text=tr("common.copied", "Copied!"))
            _safe_after(
                win, 1600, lambda: copy_btn.config(text=tr("common.copy", "Copy"))
            )

        copy_btn = tk.Button(
            btn_row,
            text=tr("common.copy", "Copy"),
            command=copy_code,
            bg="#161b22",
            fg=BLUE,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        copy_btn.pack(side="left", padx=(0, 4))

        # Edit / Apply / Discard buttons
        def toggle_edit():
            if not _edit_mode[0]:
                # Enter edit mode
                _edit_mode[0] = True
                txt.config(
                    state="normal",
                    bg="#0d1117",
                    highlightthickness=1,
                    highlightbackground=BLUE,
                )
                edit_btn.config(
                    text=tr("focus_code.apply_changes", "Apply Changes"),
                    bg="#14532d",
                    fg="#4ade80",
                )
                discard_btn.pack(side="left", padx=4)
                mode_lbl.config(
                    text=tr(
                        "focus_code.edit_mode",
                        "Edit mode - changes apply to this focus",
                    )
                )
            else:
                # Apply: parse the edited code back into the focus
                new_code = txt.get("1.0", "end").strip()
                ok = self._apply_focus_code(f, new_code)
                if not ok:
                    return  # stay in edit mode so user can fix parse error
                _edit_mode[0] = False
                txt.config(state="normal")
                txt.delete("1.0", "end")
                txt.insert("1.0", self._build_focus_code(f))
                txt.config(state="disabled", bg="#0a0f18", highlightthickness=0)
                edit_btn.config(
                    text=tr("focus_code.edit_code", "Edit Code"), bg="#161b22", fg=TEXT
                )
                discard_btn.pack_forget()
                mode_lbl.config(
                    text=tr("focus_code.read_only", "Read-only - press Edit to modify")
                )

        def discard_edit():
            _edit_mode[0] = False
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", code)
            txt.config(state="disabled", bg="#0a0f18", highlightthickness=0)
            edit_btn.config(
                text=tr("focus_code.edit_code", "Edit Code"), bg="#161b22", fg=TEXT
            )
            discard_btn.pack_forget()
            mode_lbl.config(
                text=tr("focus_code.read_only", "Read-only - press Edit to modify")
            )

        edit_btn = tk.Button(
            btn_row,
            text=tr("focus_code.edit_code", "Edit Code"),
            command=toggle_edit,
            bg="#161b22",
            fg=TEXT,
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        edit_btn.pack(side="left", padx=(0, 4))
        discard_btn = tk.Button(
            btn_row,
            text=tr("focus_code.discard", "Discard"),
            command=discard_edit,
            bg="#450a0a",
            fg="#f87171",
            font=("Helvetica", 9),
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
        )
        # discard_btn starts hidden — shown in edit mode
        mode_lbl = tk.Label(
            btn_row,
            text=tr("focus_code.read_only", "Read-only - press Edit to modify"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
        )
        mode_lbl.pack(side="right", padx=4)

        # Scrollable code area
        frm = tk.Frame(win, bg=BG_PANEL)
        frm.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        sb_y = tk.Scrollbar(frm, orient="vertical")
        sb_y.pack(side="right", fill="y")
        sb_x = tk.Scrollbar(frm, orient="horizontal")
        sb_x.pack(side="bottom", fill="x")
        # Edit mode toggle
        _edit_mode = [False]
        txt = tk.Text(
            frm,
            bg="#0a0f18",
            fg="#c9d1d9",
            font=("Courier", 10),
            relief="flat",
            yscrollcommand=sb_y.set,
            xscrollcommand=sb_x.set,
            wrap="none",
            state="normal",
            insertbackground="#58a6ff",
            selectbackground="#1e3a6e",
        )
        txt.pack(fill="both", expand=True)
        sb_y.config(command=txt.yview)
        sb_x.config(command=txt.xview)

        txt.insert("1.0", code)

        # Syntax highlighting tags
        txt.tag_configure("kw", foreground="#58a6ff", font=("Courier", 10, "bold"))
        txt.tag_configure("val", foreground="#fbbf24")
        txt.tag_configure("brace", foreground="#6e7681")
        txt.tag_configure(
            "comment", foreground="#22c55e", font=("Courier", 10, "italic")
        )
        txt.tag_configure("str_val", foreground="#f97316")


        # Precompute line-start offsets once so each match's line/col is an
        # O(log n) bisect instead of four O(n) string scans.
        line_starts = [0]
        for _idx, _ch in enumerate(code):
            if _ch == "\n":
                line_starts.append(_idx + 1)

        def _pos(off):
            ln = bisect.bisect_right(line_starts, off) - 1
            return ln + 1, off - line_starts[ln]

        for tag, pat in [
            ("comment", r"(?m)#.*$"),
            ("kw", r"(?m)^\s{0,8}[a-z_]+ (?==)"),
            ("brace", r"[{}]"),
            ("str_val", r"=\s*[A-Z_][A-Z0-9_]+"),
            ("val", r"=\s*\d[\d.]*"),
        ]:
            for m in re.finditer(pat, code):
                n0, c0 = _pos(m.start())
                n1, c1 = _pos(m.end())
                txt.tag_add(tag, f"{n0}.{c0}", f"{n1}.{c1}")

        txt.config(state="disabled")  # starts read-only; Edit button unlocks

    # ── FOCUS CRUD ──────────────────────────────────────────────
    def _update_title(self):
        """Reflect current tree ID in the window title bar."""
        tid = self._tree_id.get() or "untitled"
        self.title(
            tr(
                "app.title.tree",
                "HOI4 Content Maker  -  {tree}  [Wiki Accurate v2]",
                tree=tid,
            )
        )
        self._update_statusbar()

    def _new_tree_dialog(self):
        """Dialog to set up a brand-new focus tree with country tag and naming."""
        win = tk.Toplevel(self)
        win.title(tr("focus.new_tree.title", "New Focus Tree"))
        win.configure(bg=BG_DARK)
        win.geometry("480x420")
        win.resizable(False, True)
        win.grab_set()

        def _row(label):
            f = tk.Frame(win, bg=BG_DARK)
            f.pack(fill="x", padx=24, pady=6)
            tk.Label(
                f,
                text=label,
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=22,
                anchor="w",
            ).pack(side="left")
            var = tk.StringVar()
            e = tk.Entry(
                f,
                textvariable=var,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Helvetica", 11),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            e.pack(side="left", fill="x", expand=True, ipady=4)
            return var, e

        tk.Label(
            win,
            text=tr("focus.new_tree.header", "NEW FOCUS TREE"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 12, "bold"),
            pady=14,
        ).pack()
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x", padx=16)

        var_tag, ent_tag = _row(
            tr("focus.new_tree.country_tag", "Country Tag  (e.g. JAP):")
        )
        var_name, ent_name = _row(
            tr("focus.new_tree.country_name", "Country Name (e.g. Japan):")
        )
        var_tree, ent_tree = _row(
            tr("focus.new_tree.tree_id", "Tree ID  (auto-filled):")
        )
        var_foc, ent_foc = _row(
            tr("focus.new_tree.focus_prefix", "Focus prefix  (auto-filled):")
        )

        preview_frame = tk.Frame(
            win,
            bg="#0d1525",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        preview_frame.pack(fill="x", padx=24, pady=8)
        preview_lbl = tk.Label(
            preview_frame,
            text="",
            bg="#0d1525",
            fg="#6ee7b7",
            font=("Courier", 9),
            justify="left",
            anchor="w",
            padx=10,
            pady=8,
        )
        preview_lbl.pack(fill="x")

        def _update(*_):
            tag = var_tag.get().strip().upper()
            name = var_name.get().strip().lower().replace(" ", "_")
            if tag:
                tree_id = ("%s_focus" % name) if name else ("%s_focus" % tag.lower())
                foc_pfx = tag + "_"
                var_tree.set(tree_id)
                var_foc.set(foc_pfx)
                preview_lbl.config(
                    text=(
                        "focus_tree = {\n"
                        "    id = %s\n"
                        "    country = {\n"
                        "        factor = 0\n"
                        "        modifier = { add = 20  original_tag = %s }\n"
                        "    }\n}" % (tree_id, tag)
                    )
                )
            else:
                preview_lbl.config(text="")

        var_tag.trace_add("write", _update)
        var_name.trace_add("write", _update)

        def _create():
            tag = var_tag.get().strip().upper()
            if not tag or len(tag) < 2:
                messagebox.showwarning(
                    tr("dialog.missing_tag.title", "Missing Tag"),
                    tr(
                        "dialog.missing_tag.body",
                        "Please enter a valid 2-3 letter country tag.",
                    ),
                    parent=win,
                )
                return
            name = var_name.get().strip().lower().replace(" ", "_")
            tree_id = var_tree.get().strip() or ("%s_focus" % tag.lower())
            foc_pfx = var_foc.get().strip() or (tag + "_")

            # Ask to save before clearing
            if self.focuses:
                ans = messagebox.askyesnocancel(
                    tr("dialog.save_current_tree.title", "Save Current Tree?"),
                    tr(
                        "dialog.save_current_tree.body",
                        "You have unsaved work on '{tree}'\n\nSave it before starting a new tree?",
                        tree=self._tree_id.get(),
                    ),
                    parent=win,
                )
                if ans is None:  # Cancel
                    return
                if ans:  # Yes — save first
                    self._save()
                # Clear canvas (Yes or No both clear)
                self.cv.delete("all")
                self.focuses.clear()
                self.selected = None
                self._lines.clear()
                self._grid_item = None
                self._grid_key = None
                self._grid_img = None
                self._hide_form()
                self._redraw_now()

            # Set tree ID
            self._tree_id.set(tree_id)
            self._update_title()

            # Store setup on app for export
            self._tree_country_tag = tag
            self._tree_country_name = name
            self._tree_focus_prefix = foc_pfx

            # Update Tree ID field hint
            self._hint(
                tr(
                    "hint.new_tree_ready",
                    "New tree ready - right-click canvas to add your first focus - prefix: {prefix}",
                    prefix=foc_pfx,
                )
            )

            # Prefill new focus default name with prefix
            self._default_focus_prefix = foc_pfx

            win.destroy()
            messagebox.showinfo(
                tr("dialog.tree_created.title", "Tree Created"),
                tr(
                    "dialog.tree_created.body",
                    "Tree ID: {tree}\nCountry: {tag}\nFocus prefix: {prefix}\n\nRight-click the canvas to place your first focus!",
                    tree=tree_id,
                    tag=tag,
                    prefix=foc_pfx,
                ),
            )

        btn_row = tk.Frame(win, bg=BG_DARK)
        btn_row.pack(pady=14)
        tk.Button(
            btn_row,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 10),
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=8)
        tk.Button(
            btn_row,
            text=tr("focus.new_tree.create", "Create Tree"),
            command=_create,
            bg="#fbbf24",
            fg="#0a0a0a",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=8)
        ent_tag.focus_set()
        win.bind("<Return>", lambda e: _create())

    def _add_focus(self):
        occ = {(f.x, f.y) for f in self.focuses.values()}
        gx, gy = 0, 0
        while (gx, gy) in occ:
            gx += 2  # HOI4 standard: focuses placed at even columns
            if gx > 14:
                gx = 0
                gy += 1
        self._new_focus_at(gx, gy)

    def _new_focus_at(self, wx, wy):
        self._push_undo("add focus")
        f = Focus(wx, wy)
        pfx = self._default_focus_prefix
        if pfx:
            f.name = pfx + "focus_%d" % f.id
        self.focuses[f.id] = f
        self._redraw()
        self._select(f)

    def _apply(self):
        if not self.selected:
            return
        self._push_undo("edit focus")
        f = self.selected
        raw = self._fv_name.get().strip()
        if not raw:
            messagebox.showerror(
                tr("dialog.error.title", "Error"),
                tr("dialog.focus_id_empty", "Focus ID cannot be empty."),
            )
            return
        f.name = re.sub(r"[^A-Za-z0-9_]", "_", raw)
        f.icon = self._fv_icon.get()
        f.gfx = self._fv_gfx.get().strip() or "GFX_goal_generic_political_pressure"
        try:
            f.cost = int(self._fv_cost.get())
            raw_ai = self._fv_ai_raw.get("1.0", "end").strip()
            f.ai_will_do_raw = raw_ai

            # Accept either `base` or `factor` at top level (MD convention uses `base`).
            m = re.search(r"^\s*base\s*=\s*([\d.]+)", raw_ai, re.MULTILINE)
            if not m:
                m = re.search(r"^\s*factor\s*=\s*([\d.]+)", raw_ai, re.MULTILINE)
            f.ai_will_do = int(float(m.group(1))) if m else 1
            nx = int(self._fv_x.get())
            ny = int(self._fv_y.get())
            # move on canvas if x/y changed
            if not any(
                o.x == nx and o.y == ny and o.id != f.id for o in self.focuses.values()
            ):
                f.x = nx
                f.y = ny
            else:
                messagebox.showwarning(
                    tr("dialog.position.title", "Position"),
                    tr(
                        "dialog.position_occupied",
                        "Another focus already occupies that grid position.",
                    ),
                )
        except ValueError:
            messagebox.showerror(
                tr("dialog.error.title", "Error"),
                tr(
                    "dialog.focus_numeric_fields",
                    "Cost, AI Will Do, X and Y must be integers.",
                ),
            )
            return
        f.desc = self._fv_desc.get("1.0", "end").strip()
        f.search_filters = self._fv_search.get().strip() or "FOCUS_FILTER_POLITICAL"
        f.available_cond = self._fv_avail.get("1.0", "end").strip()
        f.bypass_cond = self._fv_bypass.get("1.0", "end").strip()
        f.cancel_cond = self._fv_cancel2.get("1.0", "end").strip()
        f.cancel_if_invalid = self._fv_cancel.get()
        f.continue_if_invalid = self._fv_continue.get()
        f.available_if_capitulated = self._fv_cap.get()
        f._draw_key = None
        self._redraw()
        self._populate(f)
        self._refresh_focus_list()

    def _toggle_multisel(self):
        self._multisel_mode = not self._multisel_mode
        if self._multisel_mode:
            self._msel_btn.config(
                bg="#1a2e4a",
                fg="#00e5ff",
                text=tr("toolbar.multi_on", "Multi-Select ON"),
            )
            self._hint(
                tr(
                    "hint.multi_select_on",
                    "Multi-select ON - Ctrl+click focuses to select - Del to delete selected",
                )
            )
        else:
            self._multi_sel.clear()
            self._msel_btn.config(
                bg="#1a1a2e", fg=TEXT, text=tr("toolbar.multi_select", "Multi-Select")
            )
            self._hint(
                tr(
                    "hint.canvas_controls",
                    "Right-click canvas to place a focus  -  Ctrl+drag to pan  -  Scroll to zoom",
                )
            )
        self._redraw()

    def _delete_selected(self):
        """Delete all multi-selected focuses with confirmation."""
        if not self._multi_sel:
            messagebox.showinfo(
                tr("dialog.no_selection.title", "No Selection"),
                tr(
                    "dialog.no_focuses_selected",
                    "No focuses selected.\nCtrl+click focuses (or enable Multi-Select mode) to select them.",
                ),
                parent=self,
            )
            return
        n = len(self._multi_sel)
        names = ", ".join(
            self.focuses[fid].name for fid in self._multi_sel if fid in self.focuses
        )
        if not messagebox.askyesno(
            tr("dialog.delete_selected.title", "Delete Selected"),
            tr(
                "dialog.delete_selected.body",
                "Delete {count} selected focus(es)?\n\n{names}\n\nThis will also remove all prerequisite links to/from these focuses.",
                count=n,
                names=names,
            ),
            parent=self,
        ):
            return
        self._push_undo("delete selected")
        for fid in list(self._multi_sel):
            if fid not in self.focuses:
                continue
            # Remove refs from other focuses
            for o in self.focuses.values():
                o.prereqs = [[p for p in g if p != fid] for g in o.prereqs]
                o.prereqs = [g for g in o.prereqs if g]
                o.mutex = [m for m in o.mutex if m != fid]
            # Delete canvas items
            for item in self.focuses[fid]._items:
                self.cv.delete(item)
            del self.focuses[fid]
        self._multi_sel.clear()
        if self.selected and self.selected.id not in self.focuses:
            self.selected = None
            self._hide_form()
        self._redraw()
        self._hint(tr("hint.deleted_focuses", "Deleted {count} focus(es).", count=n))

    def _key_delete(self):
        """Handle Delete key — delete multi-selection or single selected focus."""
        # Don't fire when the user is typing in an Entry or Text widget
        w = self.focus_get()
        if isinstance(w, (tk.Entry, tk.Text)):
            return
        if self._multi_sel:
            self._delete_selected()
        elif self.selected:
            self._delete_focus()

    def _delete_focus(self):
        if not self.selected:
            return
        self._push_undo("delete focus")
        fid = self.selected.id
        for o in self.focuses.values():
            o.prereqs = [[p for p in g if p != fid] for g in o.prereqs]
            o.prereqs = [g for g in o.prereqs if g]
            o.mutex = [m for m in o.mutex if m != fid]
        for i in self.selected._items:
            self.cv.delete(i)
        del self.focuses[fid]
        self.selected = None
        self._hide_form()
        self._redraw()

    def _clear_all(self):
        if not messagebox.askyesno(
            tr("dialog.clear_all.title", "Clear All"),
            tr("dialog.clear_all.body", "Delete ALL focuses?"),
        ):
            return
        self.cv.delete("all")
        self.focuses.clear()
        self._reset_canvas_bounds()
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._extra_trees.clear()
        self._shared_focuses.clear()
        self._joint_focuses.clear()
        self._refresh_loaded_trees_panel()
        self._refresh_tree_meta_panel()
        self._hide_form()
        self._draw_grid()

    # ── CONNECT / MUTEX ─────────────────────────────────────────
    def _pick_prereq(self):
        """Open a selection popup to add a prerequisite to the selected focus."""
        if not self.selected:
            messagebox.showinfo(
                tr("dialog.add_prereq.title", "Add Prerequisite"),
                tr("dialog.select_focus_first", "Select a focus first."),
            )
            return
        child = self.selected
        # Collect all other focuses, excluding self and already-linked ones
        already = {fid for grp in child.prereqs for fid in grp}
        candidates = [
            f for f in self.focuses.values() if f.id != child.id and f.id not in already
        ]
        if not candidates:
            messagebox.showinfo(
                tr("dialog.add_prereq.title", "Add Prerequisite"),
                tr(
                    "dialog.no_prereq_candidates",
                    "No other focuses available to link as prerequisites.",
                ),
            )
            return

        win = tk.Toplevel(self)
        win.title(
            tr(
                "focus.prereq.window_title",
                "Add Prerequisite -> {focus}",
                focus=child.name,
            )
        )
        win.configure(bg=BG_DARK)
        win.geometry("580x520")
        win.resizable(True, True)
        win.grab_set()
        win.transient(self)

        tk.Label(
            win,
            text=tr("focus.prereq.select_for", "Select prerequisite(s) for:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            win, text=child.name, bg=BG_DARK, fg=GOLD_LT, font=("Helvetica", 10, "bold")
        ).pack(anchor="w", padx=12, pady=(0, 6))
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x", padx=10)

        # Search filter — auto-focused, no placeholder delay
        sv = tk.StringVar()
        se = tk.Entry(
            win,
            textvariable=sv,
            bg=BG_PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            font=("Helvetica", 9),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        se.pack(fill="x", padx=10, pady=(6, 2))
        se.insert(0, tr("focus.prereq.filter_placeholder", "Filter focuses..."))
        se.bind(
            "<FocusIn>",
            lambda e: se.delete(0, "end")
            if se.get() == tr("focus.prereq.filter_placeholder", "Filter focuses...")
            else None,
        )
        se.bind(
            "<FocusOut>",
            lambda e: (
                se.insert(0, tr("focus.prereq.filter_placeholder", "Filter focuses..."))
                if not se.get().strip()
                else None
            ),
        )

        # Live selection counter
        _counter_var = tk.StringVar(
            value=tr("common.selected_count", "{count} selected", count=0)
        )
        counter_lbl = tk.Label(
            win,
            textvariable=_counter_var,
            bg=BG_DARK,
            fg=BLUE,
            font=("Helvetica", 9, "bold"),
        )
        counter_lbl.pack(anchor="e", padx=14)

        frm = tk.Frame(win, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(frm, orient="vertical")
        lb = tk.Listbox(
            frm,
            bg=BG_PANEL,
            fg=TEXT,
            selectbackground=BLUE,
            selectforeground=BG_DARK,
            font=("Courier", 9),
            relief="flat",
            highlightthickness=0,
            selectmode=tk.EXTENDED,
            yscrollcommand=sb.set,
            activestyle="dotbox",
        )
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        # Populate sorted by name
        sorted_cands = sorted(candidates, key=lambda f: f.name.lower())
        _id_map = {}  # listbox index → focus id

        def _populate(filter_text=""):
            lb.delete(0, "end")
            _id_map.clear()
            ft = filter_text.lower().strip()
            for f in sorted_cands:
                if ft and ft not in f.name.lower():
                    continue
                t_idx = getattr(f, "tree_idx", 0)
                tree_badge = ""
                if t_idx > 0:
                    _bt, _ = self._get_tree_badge(t_idx)
                    tree_badge = f" [{_bt}]"
                lb.insert("end", f"  {f.name}{tree_badge}")
                _id_map[lb.size() - 1] = f.id

        _populate()

        def _on_filter(*_):
            q = sv.get()
            if q == tr("focus.prereq.filter_placeholder", "Filter focuses..."):
                q = ""
            _populate(q)
            _counter_var.set(tr("common.selected_count", "{count} selected", count=0))

        sv.trace_add("write", _on_filter)

        def _update_counter(*_):
            n = len(lb.curselection())
            _counter_var.set(tr("common.selected_count", "{count} selected", count=n))

        lb.bind("<ButtonRelease-1>", _update_counter)
        lb.bind("<KeyRelease>", _update_counter)

        # Tooltip on hover showing full ID
        _tip_win = [None]

        def _show_tip(e):
            idx = lb.nearest(e.y)
            if idx < 0 or idx not in _id_map:
                return
            f = next((f for f in self.focuses.values() if f.id == _id_map[idx]), None)
            if not f:
                return
            if _tip_win[0]:
                try:
                    _tip_win[0].destroy()
                except Exception:
                    pass
            t = tk.Toplevel(win)
            t.wm_overrideredirect(True)
            t.geometry(f"+{e.x_root+12}+{e.y_root-8}")
            tk.Label(
                t,
                text=f.name,
                bg="#1e3a5f",
                fg=TEXT,
                font=("Courier", 9),
                padx=6,
                pady=3,
                relief="flat",
                bd=1,
                highlightbackground=BLUE,
                highlightthickness=1,
            ).pack()
            _tip_win[0] = t

        def _hide_tip(e):
            if _tip_win[0]:
                try:
                    _tip_win[0].destroy()
                except Exception:
                    pass
                _tip_win[0] = None

        lb.bind("<Motion>", _show_tip)
        lb.bind("<Leave>", _hide_tip)

        # AND/OR explanation
        expl = tk.Frame(
            win,
            bg="#0d1525",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        expl.pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(
            expl,
            text=tr(
                "focus.prereq.and_or_explanation",
                "  OR group: ANY ONE of the selected focuses must be completed\n"
                "  AND group: ALL selected focuses must each be completed (added as separate blocks)",
            ),
            bg="#0d1525",
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            justify="left",
            anchor="w",
            padx=4,
            pady=4,
        ).pack(fill="x")

        btn_row = tk.Frame(win, bg=BG_DARK)
        btn_row.pack(fill="x", padx=10, pady=8)

        def _confirm_or():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning(
                    tr("dialog.no_selection.title", "No Selection"),
                    tr(
                        "dialog.select_at_least_one_focus", "Select at least one focus."
                    ),
                    parent=win,
                )
                return
            group = [_id_map[i] for i in sel if i in _id_map]
            if not group:
                return
            self._push_undo("add prerequisite OR group")
            child.prereqs.append(group)
            self._refresh_prereqs()
            self._draw_lines()
            win.destroy()

        def _confirm_and():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning(
                    tr("dialog.no_selection.title", "No Selection"),
                    tr(
                        "dialog.select_at_least_one_focus", "Select at least one focus."
                    ),
                    parent=win,
                )
                return
            fids = [_id_map[i] for i in sel if i in _id_map]
            if not fids:
                return
            self._push_undo("add prerequisite AND group")
            for fid in fids:
                child.prereqs.append([fid])
            self._refresh_prereqs()
            self._draw_lines()
            win.destroy()

        def _ctrl_a(e):
            lb.select_set(0, "end")
            _update_counter()
            return "break"

        lb.bind("<Control-a>", _ctrl_a)
        lb.bind("<Control-A>", _ctrl_a)
        lb.bind("<Double-Button-1>", lambda e: _confirm_or())
        lb.bind("<Return>", lambda e: _confirm_or())
        win.bind("<Escape>", lambda e: win.destroy())

        tk.Button(
            btn_row,
            text=tr("focus.prereq.add_or", "Add as OR Group"),
            command=_confirm_or,
            bg="#14532d",
            fg="#4ade80",
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        tk.Button(
            btn_row,
            text=tr("focus.prereq.add_and", "Add as AND Group"),
            command=_confirm_and,
            bg="#1e3a6e",
            fg="#93c5fd",
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        tk.Button(
            btn_row,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg="#450a0a",
            fg="#f87171",
            font=("Helvetica", 9),
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x")

        win.after(50, se.focus_set)

    def _toggle_connect(self):
        """Legacy stub — no longer used for drag-line connect. Kept for safety."""
        self._pick_prereq()

    def _make_prereq(self, child, parent):
        for g in child.prereqs:
            if parent.id in g:
                return
        child.prereqs.append([parent.id])
        self._redraw()
        if self.selected:
            self._refresh_prereqs()

    def _rm_prereq(self, gi):
        if not self.selected:
            return
        self.selected.prereqs.pop(gi)
        self._refresh_prereqs()
        self._draw_lines()

    def _toggle_mutex(self):
        # undo pushed inside when mutex is actually set
        if self.mutex_mode:
            self._end_mutex()
            return
        if not self.selected:
            messagebox.showinfo(
                tr("dialog.mutex.title", "Mutex"),
                tr("dialog.select_focus_first", "Select a focus first."),
            )
            return
        self.mutex_mode = True
        self.mutex_src = self.selected
        self._mutex_btn.config(fg=RED, text=tr("focus.mutex.cancel", "Cancel Mutex"))
        self._hint(
            tr(
                "hint.mutex_pick",
                "Click a focus to make it MUTUALLY EXCLUSIVE with [{focus}]",
                focus=self.mutex_src.name,
            )
        )
        cx, cy = self.w2c(self.mutex_src.x, self.mutex_src.y)
        self._temp_line = self.cv.create_line(
            cx, cy, cx, cy, fill=ORANGE, width=2, dash=(4, 4), tags="templine"
        )

    def _end_mutex(self):
        self.mutex_mode = False
        self.mutex_src = None
        if self._temp_line:
            self.cv.delete(self._temp_line)
            self._temp_line = None
        self._mutex_btn.config(fg=ORANGE, text=tr("toolbar.mutex", "Mutex"))
        self._hint(
            tr(
                "hint.canvas_controls",
                "Right-click canvas to place a focus  -  Ctrl+drag to pan  -  Scroll to zoom",
            )
        )
        self._redraw()

    def _make_mutex(self, a, b):
        if b.id not in a.mutex:
            a.mutex.append(b.id)
        if a.id not in b.mutex:
            b.mutex.append(a.id)
        self._redraw()
        if self.selected:
            self._refresh_mutex()

    def _rm_mutex(self, idx):
        if not self.selected:
            return
        mid = self.selected.mutex.pop(idx)
        if mid in self.focuses:
            other = self.focuses[mid]
            if self.selected.id in other.mutex:
                other.mutex.remove(self.selected.id)
        self._refresh_mutex()
        self._draw_lines()

    # ── EFFECT LIVE UPDATES ─────────────────────────────────────
    def _add_effect(self):
        # Legacy entry point — effects are now added via the browser popup.
        self._open_effect_browser()




    # ── IMPORT .TXT ─────────────────────────────────────────────

    def _import_drawio(self):
        """Import a Draw.io .xml/.drawio file as a HOI4 focus tree skeleton.

        Flow:
          1. Pick file
          2. Parse shapes (focuses) + arrows (prerequisites)
          3. Show tree-setup dialog (tag, name, tree ID)  ← NEW
          4. Apply tag prefix to every focus name
          5. Preview dialog
          6. Commit to canvas with proper HOI4 structure
        """
        import base64
        import urllib.parse
        import xml.etree.ElementTree as ET
        import zlib

        # ── Step 1: File picker ───────────────────────────────────────
        path = filedialog.askopenfilename(
            filetypes=[
                ("Draw.io / XML", "*.xml *.drawio"),
                ("All files", "*.*"),
            ],
            title=tr("filedialog.import_drawio", "Import Draw.io Diagram"),
        )
        if not path:
            return

        try:
            with open(path, encoding="utf-8", errors="replace") as fp:
                raw_file = fp.read()
        except Exception as e:
            messagebox.showerror(
                tr("dialog.drawio_import.title", "Draw.io Import"),
                tr(
                    "dialog.drawio_read_error", "Could not read file:\n{error}", error=e
                ),
            )
            return

        # ── Step 2: Parse XML ─────────────────────────────────────────
        def decompress_drawio(b64str):
            data = base64.b64decode(b64str)
            return urllib.parse.unquote(zlib.decompress(data, -15).decode("utf-8"))

        def get_graph_root(xml_str):
            root = ET.fromstring(xml_str)
            if root.tag == "mxGraphModel":
                return root
            for diag in root.iter("diagram"):
                text = (diag.text or "").strip()
                if not text:
                    return diag
                try:
                    return ET.fromstring(decompress_drawio(text))
                except Exception:
                    pass
                try:
                    return ET.fromstring(text)
                except Exception:
                    pass
            return root

        try:
            graph_root = get_graph_root(raw_file)
        except ET.ParseError as e:
            messagebox.showerror(
                tr("dialog.drawio_import.title", "Draw.io Import"),
                tr(
                    "dialog.drawio_parse_error",
                    "Could not parse XML:\n{error}\n\nExport as Editable Vector XML from Draw.io.",
                    error=e,
                ),
            )
            return

        cells = graph_root.findall(".//mxCell")

        def clean_label(raw):
            s = re.sub(r"<[^>]+>", "", raw or "")
            for ent, ch in [
                ("&amp;", "&"),
                ("&lt;", "<"),
                ("&gt;", ">"),
                ("&nbsp;", " "),
                ("&#xa;", ""),
            ]:
                s = s.replace(ent, ch)
            s = s.strip()
            s = re.sub(r"[\s\-]+", "_", s)
            s = re.sub(r"[^A-Za-z0-9_]", "", s)
            return s

        vertices = {}
        for c in cells:
            cid = c.get("id", "")
            if c.get("vertex") != "1" or cid in ("0", "1", ""):
                continue
            geo = c.find("mxGeometry")
            if geo is None:
                continue
            label = clean_label(c.get("value", ""))
            if not label:
                label = f"focus_{cid}"
            try:
                x = float(geo.get("x", 0) or 0)
                y = float(geo.get("y", 0) or 0)
                w = float(geo.get("width", 120) or 120)
                h = float(geo.get("height", 60) or 60)
            except Exception:
                x = y = 0
                w = 120
                h = 60
            vertices[cid] = {"label": label, "x": x, "y": y, "w": w, "h": h}

        # UserObject / object wrappers
        for obj in graph_root.findall(".//UserObject") + graph_root.findall(
            ".//object"
        ):
            inner = obj.find("mxCell")
            if inner is None or inner.get("vertex") != "1":
                continue
            cid = obj.get("id") or inner.get("id", "")
            if not cid or cid in ("0", "1"):
                continue
            geo = inner.find("mxGeometry")
            if geo is None:
                continue
            label = clean_label(
                obj.get("label") or obj.get("value") or obj.get("name") or ""
            )
            if not label:
                label = f"focus_{cid}"
            try:
                x = float(geo.get("x", 0) or 0)
                y = float(geo.get("y", 0) or 0)
                w = float(geo.get("width", 120) or 120)
                h = float(geo.get("height", 60) or 60)
            except Exception:
                x = y = 0
                w = 120
                h = 60
            vertices[cid] = {"label": label, "x": x, "y": y, "w": w, "h": h}

        if not vertices:
            messagebox.showwarning(
                tr("dialog.drawio_import.title", "Draw.io Import"),
                tr(
                    "dialog.drawio_no_shapes",
                    "No shapes found in the diagram.\n\nMake sure your shapes have labels and are saved as XML.",
                ),
            )
            return

        edges = []
        for c in cells:
            if c.get("edge") != "1":
                continue
            src = c.get("source", "")
            tgt = c.get("target", "")
            if src in vertices and tgt in vertices:
                edges.append((src, tgt))

        # ── Step 3: Tree-setup dialog (tag, name, tree ID) ───────────
        result = {}  # filled by dialog

        setup = tk.Toplevel(self)
        setup.title(tr("drawio.setup.title", "Draw.io Import - Tree Setup"))
        setup.configure(bg=BG_DARK)
        setup.geometry("480x420")
        setup.resizable(False, False)
        setup.grab_set()

        # Header
        hdr = tk.Frame(setup, bg="#1a0f2e", pady=10)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=tr("drawio.setup.header", "  Draw.io Import - Focus Tree Setup"),
            bg="#1a0f2e",
            fg="#a78bfa",
            font=("Helvetica", 12, "bold"),
        ).pack(side="left", padx=10)
        tk.Frame(setup, bg=BORDER_G, height=1).pack(fill="x")

        tk.Label(
            setup,
            text=tr(
                "drawio.setup.found",
                "  Found {focuses} focuses  -  {arrows} prerequisite arrows",
                focuses=len(vertices),
                arrows=len(edges),
            ),
            bg=BG_DARK,
            fg="#58a6ff",
            font=("Helvetica", 10, "bold"),
            pady=8,
            anchor="w",
        ).pack(fill="x", padx=16)
        tk.Frame(setup, bg=BORDER_G, height=1).pack(fill="x", padx=16)

        def _field(parent, label, placeholder=""):
            row = tk.Frame(parent, bg=BG_DARK)
            row.pack(fill="x", padx=20, pady=7)
            tk.Label(
                row,
                text=label,
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=26,
                anchor="w",
            ).pack(side="left")
            var = tk.StringVar(value=placeholder)
            e = tk.Entry(
                row,
                textvariable=var,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Helvetica", 11),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            e.pack(side="left", fill="x", expand=True, ipady=5)
            return var, e

        tk.Label(setup, text="", bg=BG_DARK).pack(pady=2)

        var_tag, ent_tag = _field(
            setup, tr("focus.new_tree.country_tag", "Country Tag  (e.g. JAP):")
        )
        var_name, ent_name = _field(
            setup, tr("focus.new_tree.country_name", "Country Name (e.g. Japan):")
        )
        var_tree, ent_tree = _field(
            setup, tr("focus.new_tree.tree_id", "Tree ID  (auto-filled):")
        )
        var_pfx, ent_pfx = _field(
            setup, tr("focus.new_tree.focus_prefix", "Focus prefix  (auto-filled):")
        )

        # Preview code box
        prev_frame = tk.Frame(setup, bg=BG_DARK)
        prev_frame.pack(fill="x", padx=20, pady=4)
        prev_txt = tk.Text(
            prev_frame,
            bg="#060a10",
            fg="#6ee7b7",
            font=("Courier", 8),
            height=5,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            state="disabled",
        )
        prev_txt.pack(fill="x")

        def _update(*_):
            tag = var_tag.get().strip().upper()
            name = var_name.get().strip().lower().replace(" ", "_")
            if tag:
                tid = f"{name}_focus" if name else f"{tag.lower()}_focus"
                pfx = tag + "_"
                var_tree.set(tid)
                var_pfx.set(pfx)
                code = (
                    f"focus_tree = {{\n"
                    f"\tid = {tid}\n\n"
                    f"\tcountry = {{\n"
                    f"\t\tfactor = 0\n"
                    f"\t\tmodifier = {{\n"
                    f"\t\t\tadd = 20\n"
                    f"\t\t\toriginal_tag = {tag}\n"
                    f"\t\t}}\n"
                    f"\t}}\n"
                    f"\n\t# {len(vertices)} focuses imported from Draw.io\n}}"
                )
                prev_txt.config(state="normal")
                prev_txt.delete("1.0", "end")
                prev_txt.insert("1.0", code)
                prev_txt.config(state="disabled")
            else:
                prev_txt.config(state="normal")
                prev_txt.delete("1.0", "end")
                prev_txt.config(state="disabled")

        var_tag.trace_add("write", _update)
        var_name.trace_add("write", _update)

        confirmed = [False]

        def _confirm():
            tag = var_tag.get().strip().upper()
            if not tag or len(tag) < 2:
                messagebox.showwarning(
                    tr("dialog.missing_tag.title", "Missing Tag"),
                    tr(
                        "dialog.missing_tag.body",
                        "Please enter a valid 2-3 letter country tag.",
                    ),
                    parent=setup,
                )
                return
            result["tag"] = tag
            result["name"] = var_name.get().strip().lower().replace(" ", "_")
            result["tree_id"] = var_tree.get().strip() or f"{tag.lower()}_focus"
            result["prefix"] = var_pfx.get().strip() or f"{tag}_"
            confirmed[0] = True
            setup.destroy()

        btn_row = tk.Frame(setup, bg=BG_DARK)
        btn_row.pack(pady=12)
        tk.Button(
            btn_row,
            text=tr("common.cancel", "Cancel"),
            command=setup.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 10),
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row,
            text=tr("common.next", "Next"),
            command=_confirm,
            bg="#a78bfa",
            fg="#0a0614",
            relief="flat",
            font=("Helvetica", 10, "bold"),
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=6)

        ent_tag.focus_set()
        setup.bind("<Return>", lambda e: _confirm())
        setup.wait_window()
        if not confirmed[0]:
            return

        tag = result["tag"]
        prefix = result["prefix"]  # e.g. "JAP_"
        tree_id = result["tree_id"]

        # ── Step 4: Apply tag prefix to all focus labels ──────────────
        # If label already starts with the prefix, don't double-add it
        for v in vertices.values():
            lbl = v["label"]
            if not lbl.upper().startswith(prefix.upper()):
                v["label"] = prefix + lbl

        # ── Step 5: Map pixel coords → HOI4 grid (compact clustering) ──
        #
        # Strategy: cluster focuses into rows by proximity, then within each
        # row assign columns by X order. This keeps the tree tight like the
        # HOI4 in-game view instead of stretching the raw pixel distances.

        def cluster_axis(values, tolerance_ratio=0.55):
            """Group pixel coords into discrete slots using centroid clustering.
            tolerance_ratio: fraction of median gap to use as merge threshold."""
            vals = sorted(set(round(v) for v in values))
            if not vals:
                return {}
            # Find median gap between distinct positions
            gaps = [b - a for a, b in zip(vals, vals[1:]) if b - a > 2]
            median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 80
            tol = max(10, median_gap * tolerance_ratio)
            # Merge close values into clusters
            clusters = []
            for v in vals:
                if clusters and v - clusters[-1][-1] <= tol:
                    clusters[-1].append(v)
                else:
                    clusters.append([v])
            # Map each raw value → cluster index
            mapping = {}
            for idx, cluster in enumerate(clusters):
                for v in cluster:
                    mapping[v] = idx
            return mapping

        all_px = [v["x"] for v in vertices.values()]
        all_py = [v["y"] for v in vertices.values()]

        x_cluster = cluster_axis(all_px, tolerance_ratio=0.60)
        y_cluster = cluster_axis(all_py, tolerance_ratio=0.60)

        def snap(val, mapping):
            """Find nearest key in mapping dict."""
            rounded = round(val)
            if rounded in mapping:
                return mapping[rounded]
            # nearest
            return mapping[min(mapping.keys(), key=lambda k: abs(k - val))]

        # Assign raw cluster indices
        raw_grid = {}
        for cid, v in vertices.items():
            col = snap(v["x"], x_cluster)
            row = snap(v["y"], y_cluster)
            raw_grid[cid] = (col, row)

        # HOI4 uses even columns (0,2,4,...) and integer rows (0,1,2,...)
        # Remap col index → HOI4 x, row index → HOI4 y
        # Option A collision resolution: nudge right first, then wrap to next row
        used = {}  # (gx, gy) -> cid
        grid_positions = {}
        auto_shifted = []  # track which focuses were moved for the hint

        # Find max column in use per row (to know how far right things go)
        def _find_free(gx_start, gy, max_right_search=30):
            """Try nudging right up to max_right_search slots, then drop to next row."""
            gx = gx_start
            for _ in range(max_right_search):
                if (gx, gy) not in used:
                    return gx, gy
                gx += 2
            # Column search exhausted — try next row at original column
            gy_try = gy + 1
            gx_try = gx_start
            while (gx_try, gy_try) in used:
                gx_try += 2
            return gx_try, gy_try

        for cid in sorted(
            raw_grid.keys(), key=lambda c: (raw_grid[c][1], raw_grid[c][0])
        ):
            col_idx, row_idx = raw_grid[cid]
            gx_orig = col_idx * 2  # even columns
            gy_orig = row_idx

            if (gx_orig, gy_orig) not in used:
                # No collision — place directly
                gx, gy = gx_orig, gy_orig
            else:
                # Collision detected — find nearest free slot
                gx, gy = _find_free(gx_orig, gy_orig)
                auto_shifted.append((vertices[cid]["label"], gx_orig, gy_orig, gx, gy))

            used[(gx, gy)] = cid
            grid_positions[cid] = (gx, gy)

        # Log shifts to hint bar after import completes
        _auto_shift_log = auto_shifted

        # ── Step 6: Preview dialog ────────────────────────────────────
        prev_win = tk.Toplevel(self)
        prev_win.title(tr("drawio.preview.title", "Draw.io Import - Preview"))
        prev_win.configure(bg="#0d1117")
        prev_win.geometry("680x560")
        prev_win.grab_set()
        prev_win.resizable(True, True)

        phdr = tk.Frame(prev_win, bg="#161b22", pady=8)
        phdr.pack(fill="x")
        tk.Label(
            phdr,
            text=tr(
                "drawio.preview.header",
                "  Preview - {tag} Focus Tree  ({count} focuses)",
                tag=tag,
                count=len(vertices),
            ),
            bg="#161b22",
            fg="#a78bfa",
            font=("Helvetica", 12, "bold"),
        ).pack(side="left", padx=10)
        tk.Frame(prev_win, bg="#30363d", height=1).pack(fill="x")

        # Tab strip: Focuses | Code Preview
        tab_bar = tk.Frame(prev_win, bg="#0d1117")
        tab_bar.pack(fill="x")
        pane_focuses = tk.Frame(prev_win, bg="#0d1117")
        pane_code = tk.Frame(prev_win, bg="#0d1117")

        def _show_pane(which):
            for p in (pane_focuses, pane_code):
                p.pack_forget()
            which.pack(fill="both", expand=True)

        for label, pane in [
            (tr("drawio.preview.tab_focuses", "Focuses & Links"), pane_focuses),
            (tr("drawio.preview.tab_code", "Code Preview"), pane_code),
        ]:
            tk.Button(
                tab_bar,
                text=label,
                command=lambda p=pane: _show_pane(p),
                bg="#0d1117",
                fg=TEXT_DIM,
                relief="flat",
                font=("Helvetica", 9, "bold"),
                padx=14,
                pady=6,
                cursor="hand2",
                activebackground=BG_PANEL,
                activeforeground=BLUE,
            ).pack(side="left")

        # ── Focuses pane ──
        lf = tk.Frame(pane_focuses, bg="#0d1117")
        lf.pack(fill="both", expand=True, padx=10, pady=6)
        lsb = tk.Scrollbar(lf)
        lsb.pack(side="right", fill="y")
        lst = tk.Text(
            lf,
            bg="#0a0f18",
            fg="#c9d1d9",
            font=("Courier", 9),
            relief="flat",
            yscrollcommand=lsb.set,
            wrap="none",
            state="normal",
            selectbackground="#1e3a6e",
        )
        lst.pack(fill="both", expand=True)
        lsb.config(command=lst.yview)
        lst.tag_configure("hdr", foreground="#a78bfa", font=("Courier", 9, "bold"))
        lst.tag_configure("focus", foreground="#58a6ff")
        lst.tag_configure("arrow", foreground="#22c55e")
        lst.tag_configure("dim", foreground="#374151")

        lst.insert("end", f"FOCUSES  ({len(vertices)})\n", "hdr")
        lst.insert("end", "─" * 64 + "\n", "dim")
        for cid in sorted(
            vertices.keys(), key=lambda c: (grid_positions[c][1], grid_positions[c][0])
        ):
            v = vertices[cid]
            gx, gy = grid_positions[cid]
            lst.insert("end", f"  {v['label']:<36}", "focus")
            lst.insert("end", f"  x={gx:2d}  y={gy:2d}\n", "dim")

        if edges:
            lst.insert("end", f"\nPREREQUISITES  ({len(edges)})\n", "hdr")
            lst.insert("end", "─" * 64 + "\n", "dim")
            for src, tgt in edges:
                lst.insert("end", f"  {vertices[src]['label']}", "focus")
                lst.insert("end", "  ──►  ", "dim")
                lst.insert("end", f"{vertices[tgt]['label']}\n", "arrow")
        lst.config(state="disabled")

        # ── Code preview pane ──
        cf = tk.Frame(pane_code, bg="#0d1117")
        cf.pack(fill="both", expand=True, padx=10, pady=6)
        csb = tk.Scrollbar(cf)
        csb.pack(side="right", fill="y")
        cxsb = tk.Scrollbar(cf, orient="horizontal")
        cxsb.pack(side="bottom", fill="x")
        ctxt = tk.Text(
            cf,
            bg="#0a0f18",
            fg="#c9d1d9",
            font=("Courier", 9),
            relief="flat",
            yscrollcommand=csb.set,
            xscrollcommand=cxsb.set,
            wrap="none",
            state="normal",
            selectbackground="#1e3a6e",
        )
        ctxt.pack(fill="both", expand=True)
        csb.config(command=ctxt.yview)
        cxsb.config(command=ctxt.xview)
        ctxt.tag_configure("kw", foreground="#58a6ff", font=("Courier", 9, "bold"))
        ctxt.tag_configure("val", foreground="#fbbf24")
        ctxt.tag_configure("cmt", foreground="#22c55e")
        ctxt.tag_configure("brc", foreground="#6e7681")

        # Build code preview
        code_lines = []
        code_lines.append("focus_tree = {")
        code_lines.append(f"\tid = {tree_id}")
        code_lines.append("")
        code_lines.append("\tcountry = {")
        code_lines.append("\t\tfactor = 0")
        code_lines.append("\t\tmodifier = {")
        code_lines.append("\t\t\tadd = 20")
        code_lines.append(f"\t\t\toriginal_tag = {tag}")
        code_lines.append("\t\t}")
        code_lines.append("\t}")
        code_lines.append("")
        code_lines.append("\tcontinuous_focus_position = { x = 0 y = 1700 }")
        code_lines.append("")

        # Sort focuses top-to-bottom, left-to-right (visual reading order)
        sorted_cids = sorted(
            vertices.keys(), key=lambda c: (grid_positions[c][1], grid_positions[c][0])
        )

        # Build prereq map: tgt_cid -> [src_cid, ...]
        prereq_map = {}
        for src_cid, tgt_cid in edges:
            prereq_map.setdefault(tgt_cid, []).append(src_cid)

        for cid in sorted_cids:
            v = vertices[cid]
            gx, gy = grid_positions[cid]
            fid = v["label"]
            prereqs = prereq_map.get(cid, [])
            is_root = not prereqs  # root focus = no prerequisites

            # ── Property order per skill rules ───────────────────────
            # id, icon, x/y, cost, prerequisite, mutually_exclusive,
            # search_filters, available, bypass, cancel,
            # completion_reward (with log line), ai_will_do
            code_lines.append("\tfocus = {")
            code_lines.append(f"\t\tid = {fid}")
            code_lines.append(
                "\t\ticon = GFX_goal_generic_political_pressure  # TODO: replace with real icon"
            )
            code_lines.append("")
            code_lines.append(f"\t\tx = {gx}")
            code_lines.append(f"\t\ty = {gy}")
            code_lines.append("")
            code_lines.append("\t\tcost = 10")
            code_lines.append("")
            if prereqs:
                for src_cid in prereqs:
                    code_lines.append(
                        f"\t\tprerequisite = {{ focus = {vertices[src_cid]['label']} }}"
                    )
                code_lines.append("")
            # commented optional blocks — uncomment as needed
            code_lines.append("\t\t# available = { }")
            code_lines.append("\t\t# bypass = { }")
            code_lines.append("\t\t# cancel = { }")
            code_lines.append("")
            code_lines.append("\t\tcompletion_reward = {")
            code_lines.append(
                f'\t\t\tlog = "[GetDateText]: [This.GetName]: focus {fid} executed"'
            )
            code_lines.append("\t\t\t# TODO: add effects")
            code_lines.append("\t\t}")
            code_lines.append("")
            code_lines.append("\t\tai_will_do = {")
            code_lines.append("\t\t\tfactor = 1")
            code_lines.append("\t\t}")
            code_lines.append("\t}")
            code_lines.append("")

        code_lines.append("}")
        code_str = "\n".join(code_lines)

        for line in code_lines:
            stripped = line.lstrip("\t")
            indent = "\t" * (len(line) - len(stripped))
            if stripped.startswith("#"):
                ctxt.insert("end", indent)
                ctxt.insert("end", stripped + "\n", "cmt")
            elif (
                "=" in stripped
                and not stripped.startswith("{")
                and not stripped.startswith("}")
            ):
                k, _, rest = stripped.partition("=")
                ctxt.insert("end", indent)
                ctxt.insert("end", k + "=", "kw")
                if "{" in rest:
                    ctxt.insert("end", rest + "\n", "brc")
                else:
                    ctxt.insert("end", rest + "\n", "val")
            elif stripped in ("{", "}") or stripped.endswith("{") or stripped == "}":
                ctxt.insert("end", indent)
                ctxt.insert("end", stripped + "\n", "brc")
            else:
                ctxt.insert("end", line + "\n")
        ctxt.config(state="disabled")

        _show_pane(pane_focuses)

        # Bottom bar
        note = tk.Label(
            prev_win,
            text=tr(
                "drawio.preview.note",
                "  Shapes become focuses with generic icons. Click each focus in the sidebar to add effects and icons.",
            ),
            bg="#0d1117",
            fg="#6e7681",
            font=("Helvetica", 8, "italic"),
            anchor="w",
            pady=4,
        )
        note.pack(fill="x", padx=10)

        pbtn = tk.Frame(prev_win, bg="#0d1117", pady=8)
        pbtn.pack(fill="x", padx=10)
        do_it = [False]

        def _go():
            do_it[0] = True
            prev_win.destroy()

        tk.Button(
            pbtn,
            text=tr("drawio.preview.import_skeleton", "Import as Skeleton"),
            command=_go,
            bg="#1a3a1a",
            fg="#4ade80",
            font=("Helvetica", 10, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            pbtn,
            text=tr("common.back", "Back"),
            command=prev_win.destroy,
            bg="#161b22",
            fg=TEXT_DIM,
            font=("Helvetica", 10),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            pbtn,
            text=tr("common.cancel", "Cancel"),
            command=prev_win.destroy,
            bg="#2d1515",
            fg="#f87171",
            font=("Helvetica", 10),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left")

        prev_win.wait_window()
        if not do_it[0]:
            return

        # ── Step 7: Commit to canvas ──────────────────────────────────
        self._push_undo("draw.io import")
        self.cv.delete("all")
        self.focuses.clear()
        self._reset_canvas_bounds()
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._hide_form()

        # Apply tree metadata from dialog
        self._tree_id.set(tree_id)
        self._update_title()
        self._tree_country_tag = tag
        self._tree_country_name = result.get("name", "")
        self._tree_focus_prefix = prefix
        self._default_focus_prefix = prefix

        # Create Focus objects sorted by visual order
        cid_to_fid = {}
        for cid in sorted_cids:
            v = vertices[cid]
            gx, gy = grid_positions[cid]
            f = Focus(gx, gy)
            f.name = v["label"]
            f.gfx = "GFX_goal_generic_political_pressure"
            f.cost = 10
            f.cancel_if_invalid = True
            f.continue_if_invalid = False
            f.available_if_capitulated = False
            f.search_filters = "FOCUS_FILTER_POLITICAL"
            self.focuses[f.id] = f
            cid_to_fid[cid] = f.id

        # Wire prerequisites
        for src_cid, tgt_cid in edges:
            if src_cid in cid_to_fid and tgt_cid in cid_to_fid:
                self.focuses[cid_to_fid[tgt_cid]].prereqs.append([cid_to_fid[src_cid]])

        self._redraw()
        shift_note = (
            tr(
                "drawio.imported.auto_shift_note",
                "  -  {count} auto-shifted to avoid overlap",
                count=len(_auto_shift_log),
            )
            if _auto_shift_log
            else ""
        )
        self._hint(
            tr(
                "drawio.imported.hint",
                "Imported {count} focuses from Draw.io  -  Tag: {tag}  -  Prefix: {prefix}{shift_note}  -  Click any focus to add effects and icons",
                count=len(self.focuses),
                tag=tag,
                prefix=prefix,
                shift_note=shift_note,
            )
        )
        if _auto_shift_log:
            detail = "\n".join(
                f"  • {lbl}  ({ox},{oy}) → ({nx},{ny})"
                for lbl, ox, oy, nx, ny in _auto_shift_log[:12]
            )
            if len(_auto_shift_log) > 12:
                detail += "\n" + tr(
                    "drawio.auto_shift.more",
                    "  ... and {count} more",
                    count=len(_auto_shift_log) - 12,
                )
            messagebox.showinfo(
                tr("drawio.auto_shift.title", "Auto-Shift Notice"),
                tr(
                    "drawio.auto_shift.body",
                    "{count} focus(es) were automatically moved to\navoid overlapping another focus:\n\n{detail}\n\nYou can drag them to better positions on the canvas.",
                    count=len(_auto_shift_log),
                    detail=detail,
                ),
                parent=self,
            )

    def _import_txt(self):
        # If mod is loaded, open directly in common/national_focus
        init_dir = None
        if MOD.loaded and MOD.root:
            nf_dir = os.path.join(MOD.root, "common", "national_focus")
            if os.path.isdir(nf_dir):
                init_dir = nf_dir
        path = filedialog.askopenfilename(
            initialdir=init_dir,
            filetypes=[
                (tr("filetype.hoi4_focus_tree", "HOI4 Focus Tree"), "*.txt"),
                (tr("filetype.all", "All"), "*.*"),
            ],
            title=tr(
                "filedialog.import_hoi4_focus_tree", "Import HOI4 Focus Tree .txt"
            ),
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as fp:
                raw = fp.read()
        except Exception as e:
            messagebox.showerror(
                tr("dialog.import_error.title", "Import Error"),
                tr("dialog.read_file_error", "Could not read file:\n{error}", error=e),
            )
            return

        # Auto-set the edit target so Export writes back to this file in place
        MOD.edit_focus_file = path
        # If mod is loaded, also try to auto-detect the matching localisation file
        if MOD.loaded and MOD.root:
            try:

                _tag_m = re.search(r"\b([A-Z]{2,4})_[A-Za-z]", raw)
                if _tag_m:
                    _ctag = _tag_m.group(1)
                    _loc_candidates = [
                        f"MD_focus_{_ctag}_l_english.yml",
                        f"{_ctag}_focus_l_english.yml",
                        f"{_ctag}_focuses_l_english.yml",
                    ]
                    _loc_dir = os.path.join(MOD.root, "localisation", "english")
                    if os.path.isdir(_loc_dir):
                        for _cand in _loc_candidates:
                            _cand_path = os.path.join(_loc_dir, _cand)
                            if os.path.isfile(_cand_path):
                                MOD.edit_loc_file = _cand_path
                                break
            except Exception:
                pass

        # strip BOM defensively (in case encoding didn't catch it)
        if raw.startswith("\ufeff"):
            raw = raw[1:]

        # strip comments
        def strip_comments(s):
            out = []
            for line in s.splitlines():
                idx = line.find("#")
                if idx >= 0:
                    line = line[:idx]
                out.append(line)
            return "\n".join(out)

        txt = strip_comments(raw)

        # Reset per-import metadata so values don't carry over from a prior load
        self._tree_country_raw = ""

        # ── Extract shared_focus and joint_focus lines BEFORE tokenising ──────

        self._shared_focuses = re.findall(r"\bshared_focus\s*=\s*(\S+)", txt)
        self._joint_focuses = re.findall(r"\bjoint_focus\s*=\s*(\S+)", txt)

        # ── Raw block extractor (preserves exact HOI4 syntax) ─────────────────
        def extract_raw_block_from_text(source, key):
            """Extract the contents of 'key = { ... }' as a raw indented string.
            Handles nested braces. Returns the inner text (without outer braces)."""
            pat = key + r"\s*=\s*\{"

            m = re.search(pat, source)
            if not m:
                return ""
            start = m.end() - 1  # points at the opening {
            depth = 0
            i = start
            while i < len(source):
                if source[i] == "{":
                    depth += 1
                elif source[i] == "}":
                    depth -= 1
                    if depth == 0:
                        inner = source[start + 1 : i]
                        # Normalise indentation: strip leading/trailing blank lines
                        lines = inner.split("\n")
                        # Find min non-empty indent
                        non_empty = [l for l in lines if l.strip()]
                        if non_empty:
                            min_indent = min(
                                len(l) - len(l.lstrip("\t")) for l in non_empty
                            )
                            lines = [
                                l[min_indent:] if len(l) >= min_indent else l
                                for l in lines
                            ]
                        return "\n".join(lines).strip("\n")
                i += 1
            return ""

        # Build per-focus raw completion_reward map keyed by focus id

        _raw_rewards = {}  # focus_id_str -> raw inner text
        for _fm in re.finditer(r"\b(?:shared_focus|focus)\s*=\s*\{", txt):
            # find matching close of this focus block
            _fs = _fm.end() - 1
            _d = 0
            _fi = _fs
            while _fi < len(txt):
                if txt[_fi] == "{":
                    _d += 1
                elif txt[_fi] == "}":
                    _d -= 1
                    if _d == 0:
                        break
                _fi += 1
            _fblock = txt[_fs + 1 : _fi]
            # get id
            _id_m = re.search(r"\bid\s*=\s*(\S+)", _fblock)
            if not _id_m:
                continue
            _fid = _id_m.group(1)
            # get raw completion_reward inner text from this focus block
            _rr = extract_raw_block_from_text(_fblock, "completion_reward")
            if _rr:
                _raw_rewards[_fid] = _rr
            # also capture raw available/bypass/cancel and the new preserved fields
            for _condkey in (
                "available",
                "bypass",
                "cancel",
                "will_lead_to_war_with",
                "complete_tooltip",
                "select_effect",
                "bypass_effect",
                "allow_branch",
            ):
                _cv = extract_raw_block_from_text(_fblock, _condkey)
                if _cv:
                    _raw_rewards[(_fid, _condkey)] = _cv
            # Extract all offset = { x = N y = M trigger = { ... } } blocks as structured data
            _offsets = []
            for _om in re.finditer(r"\boffset\s*=\s*\{", _fblock):
                _os = _om.end() - 1
                _od = 0
                _oi = _os
                while _oi < len(_fblock):
                    if _fblock[_oi] == "{":
                        _od += 1
                    elif _fblock[_oi] == "}":
                        _od -= 1
                        if _od == 0:
                            break
                    _oi += 1
                _oinner = _fblock[_os + 1 : _oi]
                _oxm = re.search(r"\bx\s*=\s*(-?\d+)", _oinner)
                _oym = re.search(r"\by\s*=\s*(-?\d+)", _oinner)
                _ox = int(_oxm.group(1)) if _oxm else 0
                _oy = int(_oym.group(1)) if _oym else 0
                _otrig = extract_raw_block_from_text(_oinner, "trigger")
                _offsets.append({"x": _ox, "y": _oy, "trigger": _otrig})
            if _offsets:
                _raw_rewards[(_fid, "_offsets")] = _offsets

        # simple recursive brace tokenizer
        def tokenize(s):
            tokens = []
            i = 0
            while i < len(s):
                c = s[i]
                if c in " \t\n\r":
                    i += 1
                    continue
                if c == "{":
                    tokens.append("{")
                    i += 1
                    continue
                if c == "}":
                    tokens.append("}")
                    i += 1
                    continue
                if c == "=":
                    tokens.append("=")
                    i += 1
                    continue
                # quoted string
                if c == '"':
                    j = i + 1
                    while j < len(s) and s[j] != '"':
                        j += 1
                    tokens.append(s[i + 1 : j])
                    i = j + 1
                    continue
                # bare word/number
                j = i
                while j < len(s) and s[j] not in ' \t\n\r{}="':
                    j += 1
                if j > i:
                    tokens.append(s[i:j])
                i = j
            return tokens

        def parse_block(tokens, pos):
            """Parse a { ... } block into a dict/list structure."""
            result = {}
            pos += 1  # skip {
            while pos < len(tokens) and tokens[pos] != "}":
                key = tokens[pos]
                pos += 1
                if pos >= len(tokens):
                    break
                if tokens[pos] == "=":
                    pos += 1
                    if pos >= len(tokens):
                        break
                    if tokens[pos] == "{":
                        val, pos = parse_block(tokens, pos)
                    else:
                        val = tokens[pos]
                        pos += 1
                        # Recover from malformed `key = value = { ... }` syntax
                        # that HOI4 tolerates. Skip the orphan block so its
                        # closing brace doesn't get attributed to the parent.
                        if (
                            pos + 1 < len(tokens)
                            and tokens[pos] == "="
                            and tokens[pos + 1] == "{"
                        ):
                            pos += 1
                            _, pos = parse_block(tokens, pos)
                    # allow repeated keys as list
                    if key in result:
                        existing = result[key]
                        if not isinstance(existing, list):
                            result[key] = [existing]
                        result[key].append(val)
                    else:
                        result[key] = val
                else:
                    # bare value (e.g. inside prerequisite)
                    if key not in ("", "=", "{", "}"):
                        result.setdefault("_values", []).append(key)
            return result, pos + 1  # skip }

        tokens = tokenize(txt)

        # find top-level focus_tree block
        focuses_data = []
        tree_name = "imported_focus_tree"
        i = 0
        while i < len(tokens):
            if (
                tokens[i] == "focus_tree"
                and i + 1 < len(tokens)
                and tokens[i + 1] == "="
            ):
                block, i = parse_block(tokens, i + 2)
                tree_name = block.get("id", "imported_focus_tree")
                # Read continuous_focus_position directly — never recalculate from focus coords
                _cfp_blk = block.get("continuous_focus_position", {})
                if isinstance(_cfp_blk, dict):
                    try:
                        self._cfp_x = int(_cfp_blk.get("x", ""))
                    except Exception:
                        self._cfp_x = None
                    try:
                        self._cfp_y = int(_cfp_blk.get("y", ""))
                    except Exception:
                        self._cfp_y = None
                else:
                    self._cfp_x = self._cfp_y = None
                # Update toolbar display
                self._cfp_x_var.set("" if self._cfp_x is None else str(self._cfp_x))
                self._cfp_y_var.set("" if self._cfp_y is None else str(self._cfp_y))
                # Extract country tag from country > modifier > original_tag (or tag for compat)
                _country_blk = block.get("country", {})
                if isinstance(_country_blk, dict):
                    _mod_blk = _country_blk.get("modifier", {})
                    if isinstance(_mod_blk, dict):
                        _imported_tag = (
                            (_mod_blk.get("original_tag") or _mod_blk.get("tag") or "")
                            .upper()
                            .strip()
                        )
                        if _imported_tag and len(_imported_tag) >= 2:
                            self._tree_country_tag = _imported_tag
                # Preserve the full country block verbatim so we can write it back unchanged
                self._tree_country_raw = extract_raw_block_from_text(txt, "country")
                # collect focuses
                raw_focuses = block.get("focus", [])
                if isinstance(raw_focuses, dict):
                    raw_focuses = [raw_focuses]
                for rf in raw_focuses:
                    if isinstance(rf, dict):
                        focuses_data.append(rf)
            else:
                i += 1

        # Fallback: handle files without a focus_tree = { } wrapper.
        # Some shared/joint files contain bare top-level focus = { } or
        # shared_focus = { } blocks (no enclosing focus_tree block).
        if not focuses_data:
            i = 0
            while i < len(tokens):
                if (
                    tokens[i] in ("focus", "shared_focus")
                    and i + 1 < len(tokens)
                    and tokens[i + 1] == "="
                    and i + 2 < len(tokens)
                    and tokens[i + 2] == "{"
                ):
                    blk, i = parse_block(tokens, i + 2)
                    if isinstance(blk, dict) and "id" in blk:
                        focuses_data.append(blk)
                else:
                    i += 1
            if focuses_data and not tree_name or tree_name == "imported_focus_tree":
                # Try to infer tree name from file name
                tree_name = os.path.splitext(os.path.basename(path))[0]
                self._tree_id.set(tree_name)

        # ── Robust per-focus fallback ─────────────────────────────────────────
        # HOI4's own parser tolerates structural quirks (an unbalanced brace,
        # malformed `key=val={...}` patterns, etc.) that our structured parser
        # can choke on. Walk the raw text, brace-match each `focus = { ... }`
        # block, and parse each one independently. If this finds more focuses
        # than the structured pass, prefer it.
        #
        # The fallback can find at most one focus per `focus = {` block, so when
        # the structured pass already produced that many it can never win — skip
        # the brace-walk entirely on well-formed files (the common case).
        _block_count = len(re.findall(r"\b(?:focus|shared_focus)\s*=\s*\{", txt))
        if len(focuses_data) < _block_count:
            _per_block_focuses = []
            for _bm in re.finditer(r"\b(?:focus|shared_focus)\s*=\s*\{", txt):
                _bs = _bm.end() - 1  # position of '{'
                _bd = 0
                _bi = _bs
                while _bi < len(txt):
                    if txt[_bi] == "{":
                        _bd += 1
                    elif txt[_bi] == "}":
                        _bd -= 1
                        if _bd == 0:
                            break
                    _bi += 1
                if _bi >= len(txt):
                    continue
                _btxt = txt[_bs : _bi + 1]
                _btoks = tokenize(_btxt)
                if not _btoks or _btoks[0] != "{":
                    continue
                _bdict, _ = parse_block(_btoks, 0)
                if isinstance(_bdict, dict) and "id" in _bdict:
                    _per_block_focuses.append(_bdict)
            if len(_per_block_focuses) > len(focuses_data):
                focuses_data = _per_block_focuses
                if tree_name == "imported_focus_tree":
                    tree_name = os.path.splitext(os.path.basename(path))[0]
                self._tree_id.set(tree_name)

        if not focuses_data:
            # Build a specific error message describing what the file actually contains
            _found_blocks = []

            for _kw in ("focus_tree", "focus", "shared_focus", "joint_focus"):
                if re.search(rf"\b{_kw}\s*=\s*\{{", txt):
                    _found_blocks.append(_kw)
            if _found_blocks:
                _detail = tr(
                    "import.blocks_not_parsed",
                    "File contains blocks: {blocks}\nbut none could be parsed as valid focus blocks.",
                    blocks=", ".join(_found_blocks),
                )
            else:
                _detail = tr(
                    "import.no_recognized_blocks",
                    "No recognized HOI4 block types (focus, focus_tree, shared_focus) were found.",
                )
            messagebox.showwarning(
                tr("dialog.import.title", "Import"),
                tr(
                    "dialog.no_focus_data_found",
                    "No focus data found in:\n{file}\n\n{detail}",
                    file=os.path.basename(path),
                    detail=_detail,
                ),
            )
            return

        # clear existing
        # Clear canvas; _items refs are gone since we cv.delete('all')
        self.cv.delete("all")
        self.focuses.clear()
        self._reset_canvas_bounds()
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._extra_trees.clear()
        self._refresh_loaded_trees_panel()
        self._hide_form()
        self._tree_id.set(tree_name)
        self._update_title()
        # tag detection happens AFTER all focuses are loaded (see end of method)

        # ── Pass 1: create Focus objects, store relative_position_id ──────────────
        name_to_id = {}
        raw_pos = {}  # fid_str -> (raw_x, raw_y, rel_id or None)
        for rf in focuses_data:
            fid_str = rf.get("id", "")
            if not fid_str:
                continue
            try:
                gx = int(rf.get("x", 0))
                gy = int(rf.get("y", 0))
            except Exception:
                gx = 0
                gy = 0
            rel_id = rf.get("relative_position_id", None)
            raw_pos[fid_str] = (gx, gy, rel_id)
            f = Focus(gx, gy)  # coords resolved below
            f.name = fid_str
            # Store original relative anchor + raw deltas for lossless export
            if rel_id:
                f.relative_position_id = rel_id
                f._rel_dx = gx
                f._rel_dy = gy
            f.gfx = rf.get("icon", "GFX_goal_generic_political_pressure")
            try:
                _c = float(rf.get("cost", "10"))
                f.cost = _c if _c != int(_c) else int(_c)
            except Exception:
                f.cost = 10
            aiblock = rf.get("ai_will_do", {})
            if isinstance(aiblock, dict):
                try:
                    f.ai_will_do = int(
                        float(aiblock.get("factor", aiblock.get("base", 1)))
                    )
                except Exception:
                    f.ai_will_do = 1
                f.ai_will_do_raw = dict_to_raw(aiblock)  # preserve full block
            else:
                try:
                    f.ai_will_do = int(float(aiblock))
                except Exception:
                    f.ai_will_do = 1
                f.ai_will_do_raw = ""
            f.cancel_if_invalid = rf.get("cancel_if_invalid", "yes") == "yes"
            f.continue_if_invalid = rf.get("continue_if_invalid", "no") == "yes"
            f.available_if_capitulated = (
                rf.get("available_if_capitulated", "no") == "yes"
            )
            # search_filters — can be a dict with _values (bare words in { })
            sf = rf.get("search_filters", "")
            if isinstance(sf, dict):
                sf = " ".join(
                    str(v) for v in sf.get("_values", []) if not str(v).startswith("_")
                )
            elif isinstance(sf, list):
                sf = " ".join(str(v) for v in sf)
            f.search_filters = (
                str(sf).strip("{}").strip() if sf else "FOCUS_FILTER_POLITICAL"
            )

            # condition blocks — store raw dict as indented lines
            def _block_to_str(block, depth=1):
                """Recursively convert a parsed HOI4 block dict to script text.
                Handles nested dicts, repeated keys (lists), and bools → yes/no."""
                if not block:
                    return ""
                if isinstance(block, bool):
                    return "yes" if block else "no"
                if isinstance(block, str):
                    return block.strip()
                if not isinstance(block, dict):
                    return str(block)
                T = "\t" * depth
                lines = []
                for k, v in block.items():
                    if str(k).startswith("_"):
                        continue
                    if isinstance(v, bool):
                        lines.append(f"{T}{k} = {'yes' if v else 'no'}")
                    elif isinstance(v, list):
                        # list means the key appears multiple times, e.g. has_idea repeated
                        for item in v:
                            if isinstance(item, dict):
                                inner = _block_to_str(item, depth + 1)
                                lines.append(f"{T}{k} = {{\n{inner}\n{T}}}")
                            elif isinstance(item, bool):
                                lines.append(f"{T}{k} = {'yes' if item else 'no'}")
                            else:
                                lines.append(f"{T}{k} = {item}")
                    elif isinstance(v, dict):
                        inner = _block_to_str(v, depth + 1)
                        lines.append(f"{T}{k} = {{\n{inner}\n{T}}}")
                    else:
                        lines.append(f"{T}{k} = {v}")
                return "\n".join(lines)

            # ── condition blocks: use raw text captured before tokenising ──
            f.available_cond = _raw_rewards.get(
                (fid_str, "available"), _block_to_str(rf.get("available", {}))
            )
            f.bypass_cond = _raw_rewards.get(
                (fid_str, "bypass"), _block_to_str(rf.get("bypass", {}))
            )
            f.cancel_cond = _raw_rewards.get(
                (fid_str, "cancel"), _block_to_str(rf.get("cancel", {}))
            )
            # preserve extra fields introduced later (war with, tooltips, select/bypass effects)
            f.will_lead_to_war_with = _raw_rewards.get(
                (fid_str, "will_lead_to_war_with"),
                _block_to_str(rf.get("will_lead_to_war_with", {})),
            )
            f.complete_tooltip = _raw_rewards.get(
                (fid_str, "complete_tooltip"),
                _block_to_str(rf.get("complete_tooltip", {})),
            )
            f.select_effect = _raw_rewards.get(
                (fid_str, "select_effect"), _block_to_str(rf.get("select_effect", {}))
            )
            f.bypass_effect = _raw_rewards.get(
                (fid_str, "bypass_effect"), _block_to_str(rf.get("bypass_effect", {}))
            )
            f.allow_branch = _raw_rewards.get(
                (fid_str, "allow_branch"), _block_to_str(rf.get("allow_branch", {}))
            )
            _text_val = rf.get("text", "")
            f.text = (
                str(_text_val).strip()
                if _text_val and not isinstance(_text_val, dict)
                else ""
            )
            f.offsets = _raw_rewards.get((fid_str, "_offsets"), [])
            # ── completion_reward: always preserve as single raw block ──────
            raw_rw = _raw_rewards.get(fid_str, "")
            if raw_rw:
                f.effects = [{"type": "_raw_block", "fields": {"raw": raw_rw}}]
            else:
                f.effects = []
            self.focuses[f.id] = f
            name_to_id[fid_str] = f.id

        # ── Resolve relative_position_id chains → absolute grid coords ───────────
        # HOI4: focus with relative_position_id="X", x=dx, y=dy means:
        #   absolute = (resolve(X).x + dx,  resolve(X).y + dy)
        # Chains can nest multiple levels deep: A → B → C (absolute)
        def resolve_abs(name, visited=None):
            if visited is None:
                visited = set()
            if name not in raw_pos:
                return (0, 0)
            if name in visited:
                return raw_pos[name][:2]  # circular ref guard
            visited.add(name)
            rx, ry, rel = raw_pos[name]
            if rel is None or rel not in raw_pos:
                return (rx, ry)
            bx, by = resolve_abs(rel, visited)
            return (bx + rx, by + ry)

        for fid_str, fid in name_to_id.items():
            ax, ay = resolve_abs(fid_str)
            self.focuses[fid].x = ax
            self.focuses[fid].y = ay

        # second pass: link prerequisites and mutex
        for rf in focuses_data:
            fid_str = rf.get("id", "")
            if fid_str not in name_to_id:
                continue
            fid = name_to_id[fid_str]
            f = self.focuses[fid]
            # prerequisites
            prereqs = rf.get("prerequisite", [])
            if isinstance(prereqs, dict):
                prereqs = [prereqs]
            for pblock in prereqs:
                if not isinstance(pblock, dict):
                    continue
                group_fids = []
                pf = pblock.get("focus", [])
                if isinstance(pf, str):
                    pf = [pf]
                for pname in pf:
                    if pname in name_to_id:
                        group_fids.append(name_to_id[pname])
                if group_fids:
                    f.prereqs.append(group_fids)
            # mutually exclusive
            mutex = rf.get("mutually_exclusive", [])
            if isinstance(mutex, dict):
                mutex = [mutex]
            for mblock in mutex:
                if not isinstance(mblock, dict):
                    continue
                mf = mblock.get("focus", "")
                if isinstance(mf, str) and mf in name_to_id:
                    mid = name_to_id[mf]
                    if mid not in f.mutex:
                        f.mutex.append(mid)

        self._detect_and_apply_tag()  # scan focus IDs now that all focuses are loaded
        # If explicit tag was read from original_tag, ensure prefix is set correctly
        if not self._default_focus_prefix and getattr(self, "_tree_country_tag", ""):
            self._default_focus_prefix = self._tree_country_tag + "_"
        self._refresh_tree_meta_panel()
        self._redraw()
        self._fit_all()
        _sf_info = (
            f"\nshared_focus: {len(self._shared_focuses)} ref(s)"
            if self._shared_focuses
            else ""
        )
        _jf_info = (
            f"\njoint_focus:  {len(self._joint_focuses)} ref(s)"
            if self._joint_focuses
            else ""
        )
        messagebox.showinfo(
            tr("dialog.import_complete.title", "Import Complete"),
            tr(
                "dialog.import_complete.body",
                "Imported {count} focuses from:\n{file}\n\nTree ID: {tree}{shared}{joint}\n\nNote: available/bypass conditions and complex effects\nmay need manual review.",
                count=len(self.focuses),
                file=os.path.basename(path),
                tree=tree_name,
                shared=_sf_info,
                joint=_jf_info,
            ),
        )

    # ── MULTI-TREE HELPERS ───────────────────────────────────────

    def _get_tree_badge(self, tree_idx):
        """Return (badge_text, color) for a given tree_idx. Returns ('', FC_BORDER) for main tree."""
        _SHARED_COLS = ["#f59e0b", "#fb923c", "#fcd34d", "#f97316"]
        _JOINT_COLS = ["#a855f7", "#818cf8", "#c084fc", "#60a5fa"]
        if tree_idx <= 0 or tree_idx > len(getattr(self, "_extra_trees", [])):
            return "", FC_BORDER
        info = self._extra_trees[tree_idx - 1]
        tt = info["type"]
        if tt == "shared":
            n = sum(
                1 for t in self._extra_trees[: tree_idx - 1] if t["type"] == "shared"
            )
            return ("S" if n == 0 else f"S{n + 1}"), _SHARED_COLS[n % len(_SHARED_COLS)]
        else:
            n = sum(
                1 for t in self._extra_trees[: tree_idx - 1] if t["type"] == "joint"
            )
            return ("J" if n == 0 else f"J{n + 1}"), _JOINT_COLS[n % len(_JOINT_COLS)]



    def _install_extra_tree(self, raw, path, tree_type):
        """Parse raw focus-tree text, register the tree, and build its focuses.

        Shared core behind both the shared/joint loaders. Returns
        (focus_count, tree_id). Raises EmptyFocusTreeError when the file holds
        no focus data."""
        parsed = parse_focus_tree(raw, path)
        tree_idx = len(self._extra_trees) + 1
        tree_info = {
            "type": tree_type,
            "file_path": path,
            "tree_id": parsed.tree_id,
            "cfp_x": parsed.cfp_x,
            "cfp_y": parsed.cfp_y,
            "shared_focuses": parsed.shared_refs,
            "joint_focuses": parsed.joint_refs,
            "country_tag": parsed.country_tag,
            "had_wrapper": parsed.had_wrapper,
            "focus_ids": set(),
        }
        self._extra_trees.append(tree_info)
        if tree_type == "shared" and parsed.tree_id not in self._shared_focuses:
            self._shared_focuses.append(parsed.tree_id)
        elif tree_type == "joint" and parsed.tree_id not in self._joint_focuses:
            self._joint_focuses.append(parsed.tree_id)
        self._refresh_tree_meta_panel()
        # Snapshot existing focuses BEFORE inserting the new ones so cross-tree
        # position/prereq resolution sees only already-loaded trees.
        new_focuses = build_focuses(
            parsed,
            tree_idx,
            country_tag=getattr(self, "_tree_country_tag", ""),
            existing_focuses=list(self.focuses.values()),
        )
        for f in new_focuses:
            self.focuses[f.id] = f
            tree_info["focus_ids"].add(f.id)
        self._refresh_loaded_trees_panel()
        self._redraw()
        self._fit_all()
        return len(new_focuses), parsed.tree_id

    def _load_extra_tree(self, tree_type):
        """Load a shared or joint focus tree file onto the canvas alongside the main tree."""
        init_dir = None
        if MOD.loaded and MOD.root:
            nf_dir = os.path.join(MOD.root, "common", "national_focus")
            if os.path.isdir(nf_dir):
                init_dir = nf_dir
        path = filedialog.askopenfilename(
            initialdir=init_dir,
            filetypes=[
                (tr("filetype.hoi4_focus_tree", "HOI4 Focus Tree"), "*.txt"),
                (tr("filetype.all", "All"), "*.*"),
            ],
            title=tr(
                "filedialog.load_extra_focus_tree",
                "Load {type} Focus Tree .txt",
                type=tree_type.capitalize(),
            ),
        )
        if not path:
            return
        # Duplicate check
        for et in self._extra_trees:
            if os.path.normpath(et["file_path"]) == os.path.normpath(path):
                messagebox.showwarning(
                    tr("dialog.already_loaded.title", "Already Loaded"),
                    tr(
                        "dialog.already_loaded.body",
                        "This file is already loaded:\n{file}",
                        file=os.path.basename(path),
                    ),
                )
                return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as fp:
                raw = fp.read()
        except Exception as e:
            messagebox.showerror(
                tr("dialog.load_error.title", "Load Error"),
                tr("dialog.read_file_error", "Could not read file:\n{error}", error=e),
            )
            return
        try:
            count, tree_id = self._install_extra_tree(raw, path, tree_type)
        except EmptyFocusTreeError as e:
            messagebox.showwarning(tr("dialog.load_tree.title", "Load Tree"), str(e))
            return
        self._refresh_loaded_trees_panel()
        self._redraw()
        self._fit_all()
        messagebox.showinfo(
            tr("dialog.loaded.title", "Loaded"),
            tr(
                "dialog.extra_tree_loaded.body",
                "Loaded {count} focuses from {type} tree:\n{file}\n\nTree ID: {tree}",
                count=count,
                type=tree_type,
                file=os.path.basename(path),
                tree=tree_id,
            ),
        )

    def _unload_extra_tree(self, tree_idx):
        """Remove all focuses belonging to an extra tree from the canvas."""
        if tree_idx <= 0 or tree_idx > len(self._extra_trees):
            return
        info = self._extra_trees[tree_idx - 1]
        tid = info["tree_id"]
        if info["type"] == "shared" and tid in self._shared_focuses:
            self._shared_focuses.remove(tid)
        elif info["type"] == "joint" and tid in self._joint_focuses:
            self._joint_focuses.remove(tid)
        # Delete canvas items and focus objects
        for fid in list(info["focus_ids"]):
            if fid in self.focuses:
                f = self.focuses[fid]
                for item in f._items:
                    try:
                        self.cv.delete(item)
                    except Exception:
                        pass
                del self.focuses[fid]
        self._lines.clear()
        if self.selected and self.selected.id not in self.focuses:
            self.selected = None
            self._hide_form()
        # Remove from list; re-index tree_idx on focuses belonging to later trees
        self._extra_trees.pop(tree_idx - 1)
        for new_idx, et in enumerate(self._extra_trees, start=1):
            if new_idx >= tree_idx:
                for fid in et["focus_ids"]:
                    if fid in self.focuses:
                        self.focuses[fid].tree_idx = new_idx
                        self.focuses[fid]._draw_key = None
        self._refresh_tree_meta_panel()
        self._refresh_loaded_trees_panel()
        self._redraw()

    def _refresh_loaded_trees_panel(self):
        """Rebuild the Loaded Trees panel list in the sidebar."""
        if not hasattr(self, "_loaded_trees_inner"):
            return
        for w in self._loaded_trees_inner.winfo_children():
            w.destroy()
        if not self._extra_trees:
            tk.Label(
                self._loaded_trees_inner,
                text=tr("sidebar.no_extra_trees", "  No extra trees loaded"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
                anchor="w",
            ).pack(fill="x", padx=4, pady=2)
            return
        for idx, et in enumerate(self._extra_trees, start=1):
            badge_txt, badge_col = self._get_tree_badge(idx)
            row = tk.Frame(
                self._loaded_trees_inner,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            row.pack(fill="x", padx=4, pady=2)
            tk.Label(
                row,
                text=f" [{badge_txt}]",
                bg=badge_col,
                fg="#000000",
                font=("Courier", 8, "bold"),
                padx=4,
                pady=2,
            ).pack(side="left")
            info_f = tk.Frame(row, bg=BG_CARD)
            info_f.pack(side="left", fill="x", expand=True)
            tk.Label(
                info_f,
                text=et["tree_id"],
                bg=BG_CARD,
                fg=TEXT,
                font=("Courier", 8, "bold"),
                anchor="w",
            ).pack(fill="x", padx=4, pady=(2, 0))
            tk.Label(
                info_f,
                text=tr(
                    "sidebar.loaded_tree_summary",
                    "  {file}  -  {count} focuses",
                    file=os.path.basename(et["file_path"]),
                    count=len(et["focus_ids"]),
                ),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 7),
                anchor="w",
            ).pack(fill="x", padx=4, pady=(0, 2))
            btn_f = tk.Frame(row, bg=BG_CARD)
            btn_f.pack(side="right", padx=2)
            tk.Button(
                btn_f,
                text=tr("common.save", "Save"),
                command=lambda i=idx: self._export_extra_tree(i),
                bg=BG_CARD,
                fg=BLUE,
                font=("Helvetica", 8),
                relief="flat",
                padx=4,
                pady=1,
                cursor="hand2",
            ).pack(pady=(4, 0))
            tk.Button(
                btn_f,
                text="✕",
                command=lambda i=idx: self._unload_extra_tree(i),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                relief="flat",
                padx=4,
                pady=1,
                cursor="hand2",
            ).pack(pady=(0, 4))

    def _export_extra_tree(self, tree_idx):
        """Export a single extra (shared/joint) tree to its source file."""
        if tree_idx <= 0 or tree_idx > len(self._extra_trees):
            return
        info = self._extra_trees[tree_idx - 1]
        focuses_in_tree = [
            f for f in self.focuses.values() if getattr(f, "tree_idx", 0) == tree_idx
        ]
        if not focuses_in_tree:
            messagebox.showwarning(
                tr("dialog.export.title", "Export"),
                tr("dialog.no_focuses_in_tree", "No focuses in this tree."),
            )
            return
        out_text = export_focus_tree(
            focuses_in_tree,
            info,
            focus_lookup=self.focuses,
            effect_renderer=self._render_effect,
        )
        # Save to source file or ask
        if os.path.isfile(info["file_path"]):
            path = info["file_path"]
        else:
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("HOI4 Focus Tree", "*.txt"), ("All", "*.*")],
                initialfile=os.path.basename(info["file_path"]),
                title=tr(
                    "filedialog.save_extra_tree",
                    "Save {type} Tree .txt",
                    type=info["type"].capitalize(),
                ),
            )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(out_text)
        info["file_path"] = path
        messagebox.showinfo(
            tr("dialog.saved.title", "Saved"),
            tr(
                "dialog.extra_tree_saved",
                "{type} tree saved:\n{file}",
                type=info["type"].capitalize(),
                file=os.path.basename(path),
            ),
        )

    def _load_all_trees(self):
        """Scan national_focus directory and show a checklist so the user can batch-load trees."""
        # Determine scan directory
        init_dir = None
        if MOD.loaded and MOD.root:
            nf_dir = os.path.join(MOD.root, "common", "national_focus")
            if os.path.isdir(nf_dir):
                init_dir = nf_dir
        if not init_dir:
            init_dir = filedialog.askdirectory(
                title=tr(
                    "filedialog.select_national_focus_dir",
                    "Select national_focus directory to scan",
                )
            )
            if not init_dir:
                return

        # Collect all .txt files recursively
        all_files = []
        for root_d, _dirs, files in os.walk(init_dir):
            for fn in sorted(files):
                if fn.lower().endswith(".txt"):
                    all_files.append(os.path.join(root_d, fn))

        if not all_files:
            messagebox.showinfo(
                tr("load_all.title", "Load All Trees"),
                tr(
                    "load_all.no_txt_files",
                    "No .txt files found in:\n{path}",
                    path=init_dir,
                ),
            )
            return

        # Already-loaded paths for duplicate detection
        loaded_paths = {
            os.path.normpath(et["file_path"])
            for et in getattr(self, "_extra_trees", [])
        }

        # ── Checklist dialog ────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title(tr("load_all.select_files.title", "Load All Trees - Select Files"))
        win.configure(bg=BG_DARK)
        win.geometry("740x560")
        win.resizable(True, True)
        win.grab_set()
        win.transient(self)

        tk.Label(
            win,
            text=tr(
                "load_all.found_files",
                "  Found {count} .txt files in national_focus",
                count=len(all_files),
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(
            win, text=f"  {init_dir}", bg=BG_DARK, fg=TEXT_DIM, font=("Courier", 8)
        ).pack(anchor="w", padx=12, pady=(0, 6))
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x", padx=10)

        # Header row
        hdr = tk.Frame(win, bg="#0d1525")
        hdr.pack(fill="x", padx=10, pady=(4, 0))
        tk.Label(
            hdr,
            text=tr("load_all.column.load", "Load"),
            bg="#0d1525",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            width=5,
        ).pack(side="left")
        tk.Label(
            hdr,
            text=tr("load_all.column.filename", "Filename"),
            bg="#0d1525",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
        ).pack(side="left", padx=(0, 20))
        tk.Label(
            hdr,
            text=tr("load_all.column.type", "Type"),
            bg="#0d1525",
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
        ).pack(side="right", padx=20)

        # Scrollable file list
        frm = tk.Frame(win, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(frm, orient="vertical")
        sb.pack(side="right", fill="y")
        list_canvas = tk.Canvas(
            frm, bg=BG_DARK, highlightthickness=0, yscrollcommand=sb.set
        )
        list_canvas.pack(side="left", fill="both", expand=True)
        sb.config(command=list_canvas.yview)
        inner = tk.Frame(list_canvas, bg=BG_DARK)
        inner_win = list_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: (
                list_canvas.configure(scrollregion=list_canvas.bbox("all")),
                list_canvas.itemconfig(inner_win, width=list_canvas.winfo_width()),
            ),
        )
        list_canvas.bind(
            "<Configure>", lambda e: list_canvas.itemconfig(inner_win, width=e.width)
        )
        list_canvas.bind(
            "<MouseWheel>",
            lambda e: list_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

        # Row data: list of (filepath, BooleanVar checked, StringVar type)
        rows = []
        for fp in all_files:
            fname = os.path.basename(fp)
            already = os.path.normpath(fp) in loaded_paths
            # Default type based on filename prefix convention
            def_type = "shared"
            m = __import__("re").match(r"^(\d+)_", fname)
            if m:
                n = int(m.group(1))
                if n >= 5:
                    def_type = "main"
                else:
                    def_type = "shared"
            chk_var = tk.BooleanVar(value=(not already and def_type != "main"))
            type_var = tk.StringVar(value=def_type)
            rows.append((fp, chk_var, type_var, already))

            row_f = tk.Frame(
                inner,
                bg=BG_CARD if not already else "#1a1f2e",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            )
            row_f.pack(fill="x", padx=2, pady=1)

            chk = tk.Checkbutton(
                row_f,
                variable=chk_var,
                bg=row_f.cget("bg"),
                fg=TEXT,
                selectcolor=BG_DARK,
                activebackground=row_f.cget("bg"),
                relief="flat",
            )
            chk.pack(side="left", padx=4)
            if already:
                chk.config(state="disabled")

            name_lbl = tk.Label(
                row_f,
                text=fname,
                bg=row_f.cget("bg"),
                fg=TEXT_DIM if already else TEXT,
                font=("Courier", 8),
                anchor="w",
            )
            name_lbl.pack(side="left", fill="x", expand=True, padx=2)
            if already:
                tk.Label(
                    row_f,
                    text=tr("load_all.loaded_marker", " (loaded)"),
                    bg=row_f.cget("bg"),
                    fg="#4ade80",
                    font=("Helvetica", 8, "italic"),
                ).pack(side="left")

            # Type selector
            type_f = tk.Frame(row_f, bg=row_f.cget("bg"))
            type_f.pack(side="right", padx=4)
            for lbl, val, col in [
                (tr("load_all.type.main", "Main"), "main", TEXT_DIM),
                (tr("load_all.type.shared", "Shared"), "shared", "#f59e0b"),
                (tr("load_all.type.joint", "Joint"), "joint", "#a855f7"),
            ]:
                tk.Radiobutton(
                    type_f,
                    text=lbl,
                    variable=type_var,
                    value=val,
                    bg=row_f.cget("bg"),
                    fg=col,
                    selectcolor=BG_DARK,
                    activebackground=row_f.cget("bg"),
                    font=("Helvetica", 8),
                    relief="flat",
                ).pack(side="left")
            if already:
                for w in type_f.winfo_children():
                    w.config(state="disabled")

        # Select/deselect all helpers
        def _sel_all():
            for fp, cv2, tv, already in rows:
                if not already and tv.get() != "main":
                    cv2.set(True)

        def _desel_all():
            for _, cv2, _, _ in rows:
                cv2.set(False)

        def _sel_shared():
            for _, cv2, tv, already in rows:
                if not already:
                    cv2.set(tv.get() == "shared")

        def _sel_joint():
            for _, cv2, tv, already in rows:
                if not already:
                    cv2.set(tv.get() == "joint")

        ctrl = tk.Frame(win, bg=BG_DARK)
        ctrl.pack(fill="x", padx=10, pady=(2, 0))
        for lbl, cmd in [
            (tr("load_all.select_all_extra", "All Shared+Joint"), _sel_all),
            (tr("common.none", "None"), _desel_all),
            (tr("load_all.shared_only", "Shared only"), _sel_shared),
            (tr("load_all.joint_only", "Joint only"), _sel_joint),
        ]:
            tk.Button(
                ctrl,
                text=lbl,
                command=cmd,
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8),
                relief="flat",
                padx=6,
                pady=2,
                cursor="hand2",
            ).pack(side="left", padx=2)

        # Load button
        btn_row = tk.Frame(win, bg=BG_DARK)
        btn_row.pack(fill="x", padx=10, pady=8)

        def _do_load():
            to_load = [
                (fp, tv.get())
                for fp, cv2, tv, already in rows
                if cv2.get() and not already and tv.get() != "main"
            ]
            if not to_load:
                messagebox.showwarning(
                    tr("load_all.title", "Load All Trees"),
                    tr("load_all.no_files_selected", "No files selected to load."),
                    parent=win,
                )
                return
            win.destroy()
            ok, fail = [], []
            for fp, ttype in to_load:
                # Reuse _load_extra_tree logic but skip the file dialog
                try:
                    self._load_extra_tree_from_path(fp, ttype)
                    ok.append(os.path.basename(fp))
                except Exception as e:
                    fail.append(f"{os.path.basename(fp)}: {e}")

            msg = (
                tr("load_all.loaded_count", "Loaded {count} file(s).", count=len(ok))
                + "\n"
            )
            if ok:
                msg += (
                    "\n"
                    + tr("load_all.loaded_header", "Loaded:")
                    + "\n"
                    + "\n".join(f"  ✓ {n}" for n in ok)
                )
            if fail:
                msg += (
                    "\n\n"
                    + tr("load_all.failed_header", "Failed:")
                    + "\n"
                    + "\n".join(f"  ✕ {e}" for e in fail)
                )
            messagebox.showinfo(tr("load_all.title", "Load All Trees"), msg)
            # Zoom to fit all focuses
            if ok:
                self._fit_all()

        tk.Button(
            btn_row,
            text=tr("load_all.load_selected", "Load Selected"),
            command=_do_load,
            bg="#1e3a6e",
            fg="#93c5fd",
            font=("Helvetica", 9, "bold"),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            btn_row,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg="#450a0a",
            fg="#f87171",
            font=("Helvetica", 9),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x")

    def _load_extra_tree_from_path(self, path, tree_type):
        """Internal: load a shared/joint tree from a known path (no file dialog)."""
        # Duplicate check
        for et in self._extra_trees:
            if os.path.normpath(et["file_path"]) == os.path.normpath(path):
                return  # silently skip already-loaded files
        with open(path, encoding="utf-8-sig", errors="replace") as fp:
            raw = fp.read()
        # EmptyFocusTreeError (rich diagnostic) propagates to the batch caller.
        self._install_extra_tree(raw, path, tree_type)

    def _save_all_trees(self):
        """Export all loaded trees (main + extra) with one click."""
        results = []
        errors = []
        try:
            self._export()
            results.append(f"Main: {self._tree_id.get()}")
        except Exception as e:
            errors.append(f"Main tree: {e}")
        for idx, et in enumerate(self._extra_trees, start=1):
            try:
                self._export_extra_tree(idx)
                results.append(f"{et['type'].capitalize()}: {et['tree_id']}")
            except Exception as e:
                errors.append(f"{et['tree_id']}: {e}")
        msg = tr("save_all.complete", "Save All Trees complete!") + "\n\n"
        if results:
            msg += (
                tr("save_all.saved_header", "Saved:")
                + "\n"
                + "\n".join(f"  • {r}" for r in results)
            )
        if errors:
            msg += (
                "\n\n"
                + tr("save_all.errors_header", "Errors:")
                + "\n"
                + "\n".join(f"  ✕ {e}" for e in errors)
            )
        messagebox.showinfo(tr("save_all.title", "Save All Trees"), msg)

    # ── SAVE / LOAD ─────────────────────────────────────────────
    def _save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                (tr("filetype.json_project", "JSON Project"), "*.json"),
                (tr("filetype.all", "All"), "*.*"),
            ],
            title=tr("filedialog.save_project", "Save Project"),
        )
        if not path:
            return
        data = {
            "tree_name": self._tree_id.get(),
            "focuses": [f.to_dict() for f in self.focuses.values()],
        }
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2)
        messagebox.showinfo(
            tr("dialog.saved.title", "Saved"),
            tr("dialog.project_saved", "Project saved:\n{path}", path=path),
        )

    def _detect_and_apply_tag(self):
        """Scan all loaded focus IDs, detect common country tag prefix, apply to new focuses."""
        if not self.focuses:
            return
        names = [f.name for f in self.focuses.values() if f.name and "_" in f.name]
        if not names:
            return
        from collections import Counter

        # Extract first segment before first underscore (e.g. "JAP" from "JAP_militarism")
        segs = [n.split("_")[0].upper() for n in names]
        # Filter: must be 2-5 chars (typical HOI4 tags are 3 chars like JAP, GER, USA)
        segs = [s for s in segs if 2 <= len(s) <= 5 and s.isalpha()]
        if not segs:
            return
        most_common, count = Counter(segs).most_common(1)[0]
        # Apply if appears in at least 2 focuses OR >30% of all (handles small trees too)
        threshold = count >= 2 and (count / len(names) >= 0.30)
        if threshold and len(most_common) >= 2:
            self._default_focus_prefix = most_common + "_"
            self._hint(
                f"🏷 Tag detected: {most_common}  —  new focuses will auto-prefix '{most_common}_'"
            )
        else:
            self._default_focus_prefix = ""

    def _load(self):
        path = filedialog.askopenfilename(
            filetypes=[
                (tr("filetype.json_project", "JSON Project"), "*.json"),
                (tr("filetype.all", "All"), "*.*"),
            ],
            title=tr("filedialog.load_project", "Load Project"),
        )
        if not path:
            return
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        self.cv.delete("all")
        self.focuses.clear()
        self._reset_canvas_bounds()
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._tree_id.set(data.get("tree_name", "TAG_focus_tree"))
        self._update_title()
        for fd in data.get("focuses", []):
            f = Focus.from_dict(fd)
            f._draw_key = None
            self.focuses[f.id] = f
        self._detect_and_apply_tag()
        self._hide_form()
        self._redraw()

    # ── EXPORT ──────────────────────────────────────────────────


    def _apply_md_visibility(self):
        """Show/hide MD effect categories based on whether MD is detected."""
        md_cats = {
            "MD Economy",
            "MD Buildings",
            "MD Politics",
            "MD Factions",
            "MD Influence",
            "MD Modifiers",
        }
        base_cats = [c for c in EFFECT_CATS if c not in md_cats]
        # Mutate the shared list IN PLACE (not rebind) so every module that
        # imported EFFECT_CATS — including the extracted effects panel — sees
        # the update. Rebinding would only change this module's name.
        if MOD.is_md:
            EFFECT_CATS[:] = base_cats + sorted(md_cats)
        else:
            EFFECT_CATS[:] = base_cats


    def _open_settings(self):
        """Settings panel — GFX paths, MD detection, extra dirs."""
        win = tk.Toplevel(self)
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
            lambda e: sc.itemconfig(sc.find_withtag("all")[0], width=e.width)
            if sc.find_withtag("all")
            else None,
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
                if MOD.root and d.startswith(MOD.root):
                    d = os.path.relpath(d, MOD.root)
                v.set(d)

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
            self._apply_md_visibility()
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

        _default_hoi4 = _default_hoi4_mod_dir()
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
                initialdir=mp_var.get()
                if os.path.isdir(mp_var.get())
                else os.path.expanduser("~"),
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
        _lbl(
            tr("settings.reload_hint", "  Changes take effect when you reload the mod.")
        )

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

        presets = [
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
        for pname, pg, pi in presets:

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
        _path_row(
            tr("settings.event_pictures", "Event pictures:"), "path_event_pictures"
        )
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
                messagebox.showerror(
                    "Error", "Profile name cannot be empty.", parent=win
                )
                return
            try:
                cw, ch = int(np_cw.get()), int(np_ch.get())
                nw, nh = int(np_nw.get()), int(np_nh.get())
            except ValueError:
                messagebox.showerror(
                    "Error", "Dimensions must be integers.", parent=win
                )
                return
            MOD.event_dim_profiles[name] = {"country": (cw, ch), "news": (nw, nh)}
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
                title=tr(
                    "filedialog.select_extra_gfx_folder", "Select extra GFX folder"
                )
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
            entries = self._error_entries
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
            command=self._show_error_log,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            font=("Helvetica", 9),
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side="left", padx=(0, 4))

        def _clear_log():
            self._error_entries.clear()
            if hasattr(self, "_errlog_btn"):
                self._errlog_btn.config(
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

        # Built-in vanilla HOI4 tag names as quick-fill
        _VANILLA_TAGS = {
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
            for t, n in _VANILLA_TAGS.items():
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
                tr(
                    "settings.loc_token_style.colon", "Colon-style   [TAG:NameWithFlag]"
                ),
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
            style = _tok_var.get()
            ex = {
                "colon": "🏳 Soviet Union  ←  [SOV:NameWithFlag] resolved via tag name map",
                "dot": "🏳 SOV  ←  [SOV.GetName] (dot-style)",
                "both": "🏳 Soviet Union  ←  tries [TAG:X] first, then [TAG.X]",
            }
            tok_prev_lbl.config(text="  " + ex.get(style, ""))

        _tok_var.trace_add("write", _update_tok_preview)
        _update_tok_preview()

        # ── BOTTOM BAR ────────────────────────────────────────────────
        tk.Frame(frm, bg=BORDER_G, height=1).pack(fill="x", padx=8, pady=(12, 2))
        tk.Label(
            frm,
            text=tr(
                "settings.saved_to", "  Settings saved to:  {path}", path=CONFIG_PATH
            ),
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

    def _additional_income_wizard(self):
        """Open the MD Additional Income wizard."""
        open_additional_income_wizard(self)

    def _national_spirit_wizard(self):
        """Open the National Spirit/Ideas builder wizard."""
        open_national_spirit_wizard(self)

    def _dyn_mod_wizard(self):
        """Open the Dynamic Modifier wizard."""
        open_dyn_mod_wizard(self)

    def _decision_wizard(self):
        """Open the Decision Maker wizard."""
        open_decision_wizard(self)

    def _event_wizard(self):
        """Open the Event Maker wizard."""
        open_event_wizard(self)

    def _update_statusbar(self):
        """Refresh all status bar labels."""
        if not hasattr(self, "_sb_focus_lbl"):
            return
        tid = self._tree_id.get() or tr("status.no_tree", "no tree")
        fc = len(self.focuses)
        sel = getattr(self.selected, "name", "—") if self.selected else "—"
        zoom = int(getattr(self, "zoom", 1.0) * 100)
        # mod name from _mod_lbl text (set by _on_mod_loaded)
        try:
            mod_txt = (
                self._sb_mod_lbl2.cget("text")
                if hasattr(self, "_sb_mod_lbl2")
                else tr("status.mod_none", "Mod: none")
            )
            # keep whatever was already set unless we can get it from mod_lbl
            if hasattr(self, "_mod_lbl"):
                raw = self._mod_lbl.cget("text")
                mod_txt = (
                    tr("status.mod", "Mod: {mod}", mod=raw)
                    if raw and raw != tr("status.no_mod_loaded", "No mod loaded")
                    else tr("status.mod_none", "Mod: none")
                )
        except Exception:
            mod_txt = tr("status.mod_none", "Mod: none")
        self._sb_tree_val.config(text=tid)
        self._sb_focus_lbl.config(
            text=tr("status.focuses", "Focuses: {count}", count=fc)
        )
        self._sb_sel_lbl.config(
            text=tr("status.selected", "Selected: {focus}", focus=sel)
        )
        self._sb_zoom_lbl.config(text=tr("status.zoom", "Zoom: {zoom}%", zoom=zoom))
        self._sb_mod_lbl2.config(text=mod_txt)

    # ─────────────────── FOCUS LIST PANEL ────────────────────────
    def _refresh_focus_list_debounced(self):
        """Coalesce rapid search-box keystrokes into a single list rebuild.

        _refresh_focus_list() tears down and recreates every row, so firing it
        on each keystroke is wasteful on large trees. Schedule one rebuild
        ~120ms after typing stops instead.
        """
        if getattr(self, "_lp_search_job", None):
            try:
                self.after_cancel(self._lp_search_job)
            except Exception:
                pass
        self._lp_search_job = self.after(120, self._refresh_focus_list)

    def _refresh_focus_list(self):
        """Rebuild the left-panel focus list widgets.
        Called on: add/delete focus, rename, search change, mod load.
        For selection-only changes, _update_focus_list_selection() is cheaper.
        """
        self._lp_search_job = None
        if not hasattr(self, "_lp_inner"):
            return
        for w in self._lp_inner.winfo_children():
            w.destroy()
        self._lp_row_widgets = {}  # fid -> (row, bar, dot, lbl)
        query = ""
        if hasattr(self, "_lp_search_var"):
            q = self._lp_search_var.get().strip()
            if q and q != "Search\u2026":
                query = q.lower()
        for f in self.focuses.values():
            if query and query not in f.name.lower():
                continue
            has_fx = bool(f.effects)
            broken = any(pid not in self.focuses for grp in f.prereqs for pid in grp)
            dot_col = "#ef4444" if broken else ("#22c55e" if has_fx else "#fbbf24")
            is_sel = bool(self.selected and self.selected.id == f.id)
            row_bg = "#1e2d4a" if is_sel else BG_PANEL
            row_fg = "#93c5fd" if is_sel else TEXT_DIM
            row = tk.Frame(self._lp_inner, bg=row_bg, cursor="hand2")
            row.pack(fill="x")
            bar = tk.Frame(row, bg=BLUE if is_sel else row_bg, width=3)
            bar.pack(side="left", fill="y")
            dot = tk.Label(
                row, text="\u25cf", bg=row_bg, fg=dot_col, font=("Helvetica", 7), padx=2
            )
            dot.pack(side="left")
            lbl = tk.Label(
                row,
                text=f.name,
                bg=row_bg,
                fg=row_fg,
                font=("Courier", 9),
                anchor="w",
                padx=2,
                pady=4,
            )
            lbl.pack(side="left", fill="x", expand=True)
            self._lp_row_widgets[f.id] = (row, bar, dot, lbl)

            def _click(e, fid=f.id):
                if fid in self.focuses:
                    self._select(self.focuses[fid])
                    self._redraw()

            for w in (row, dot, lbl, bar):
                w.bind("<Button-1>", _click)
                w.bind(
                    "<Enter>",
                    lambda e, r=row, s=is_sel: r.config(
                        bg="#253550" if not s else "#1e2d4a"
                    ),
                )
                w.bind("<Leave>", lambda e, r=row, s=is_sel, c=row_bg: r.config(bg=c))

    def _update_focus_list_selection(self):
        """Fast highlight update — only recolours rows, no widget rebuild."""
        if not hasattr(self, "_lp_row_widgets"):
            self._refresh_focus_list()
            return
        sel_id = self.selected.id if self.selected else None
        for fid, (row, bar, dot, lbl) in self._lp_row_widgets.items():
            try:
                is_sel = fid == sel_id
                bg = "#1e2d4a" if is_sel else BG_PANEL
                fg = "#93c5fd" if is_sel else TEXT_DIM
                bar_bg = BLUE if is_sel else bg
                row.config(bg=bg)
                bar.config(bg=bar_bg)
                dot.config(bg=bg)
                lbl.config(bg=bg, fg=fg)
            except tk.TclError:
                pass  # widget destroyed mid-update

    def _toggle_focus_list(self):
        """Show/hide the left focus list panel."""
        if not hasattr(self, "_left_panel"):
            return
        if self._left_panel_visible:
            self._left_panel.pack_forget()
            self._left_panel_visible = False
            if hasattr(self, "_lp_collapse_btn"):
                self._lp_collapse_btn.config(text="▶")
        else:
            self._left_panel.pack(side="left", fill="y", before=self.cv)
            self._left_panel_visible = True
            if hasattr(self, "_lp_collapse_btn"):
                self._lp_collapse_btn.config(text="◀")






    # ─────────────────── DUPLICATE FOCUS ─────────────────────────
    def _duplicate_focus(self):
        """Duplicate the currently selected focus."""
        if not self.selected:
            messagebox.showinfo(
                tr("dialog.duplicate.title", "Duplicate"),
                tr("dialog.select_focus_first", "Select a focus first."),
            )
            return

        f = self.selected
        nf = copy.deepcopy(f)
        nf.id = id(nf)
        # Generate new unique name
        base = re.sub(r"_copy\d*$", "", f.name) + "_copy"
        n = 1
        candidate = base
        while candidate in {foc.name for foc in self.focuses.values()}:
            candidate = f"{base}{n}"
            n += 1
        nf.name = candidate
        nf.x = f.x + 1
        nf.y = f.y
        # Clear prereqs/mutex since IDs won't match
        nf.prereqs = []
        nf.mutex = []
        # Clear draw cache so new focus renders immediately
        nf._draw_key = None
        nf._items = []
        self.focuses[nf.id] = nf
        self._push_undo("duplicate")
        self._redraw_now()  # force immediate, bypass throttle
        self._select(nf)
        self._refresh_focus_list()

    # ─────────────────── BULK RENAME ─────────────────────────────
    def _bulk_rename_dialog(self):
        """Dialog to bulk rename all focus IDs by replacing a prefix."""
        if not self.focuses:
            messagebox.showinfo(
                tr("bulk_rename.title", "Bulk Rename"),
                tr("bulk_rename.no_focuses", "No focuses to rename."),
            )
            return

        win = tk.Toplevel(self)
        win.title(tr("bulk_rename.window_title", "Bulk Rename Prefix"))
        win.configure(bg=BG_DARK)
        win.geometry("480x380")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(
            win,
            text=tr("bulk_rename.header", "BULK RENAME PREFIX"),
            bg=BG_DARK,
            fg=TEXT,
            font=("Helvetica", 11, "bold"),
            pady=12,
        ).pack(fill="x", padx=16)
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

        tk.Label(
            win,
            text=tr(
                "bulk_rename.description",
                "Replaces prefix across all {count} focus IDs,\nprerequisite references, and mutex links.",
                count=len(self.focuses),
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
            justify="left",
            anchor="w",
            pady=6,
        ).pack(fill="x", padx=16)

        def _row(label, default):
            f = tk.Frame(win, bg=BG_DARK)
            f.pack(fill="x", padx=16, pady=3)
            tk.Label(
                f,
                text=label,
                bg=BG_DARK,
                fg=TEXT_DIM,
                font=("Helvetica", 9),
                width=8,
                anchor="w",
            ).pack(side="left")
            v = tk.StringVar(value=default)
            tk.Entry(
                f,
                textvariable=v,
                bg=BG_CARD,
                fg=TEXT,
                insertbackground=BLUE,
                font=("Courier", 10),
                relief="flat",
                highlightthickness=1,
                highlightbackground=BORDER_G,
            ).pack(side="left", fill="x", expand=True, ipady=4)
            return v

        # Auto-detect current prefix (longest common prefix up to first _)
        names = [f.name for f in self.focuses.values()]
        auto_from = ""
        if names:
            parts = names[0].split("_")
            if parts:
                auto_from = parts[0] + "_"

        v_from = _row(tr("bulk_rename.from", "From:"), auto_from)
        v_to = _row(tr("bulk_rename.to", "To:"), "")

        # Preview
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x", padx=16, pady=6)
        tk.Label(
            win,
            text=tr("bulk_rename.preview", "Preview (first 5):"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16)
        prev_txt = tk.Text(
            win,
            bg="#050810",
            fg="#4ade80",
            font=("Courier", 9),
            relief="flat",
            height=5,
            highlightthickness=1,
            highlightbackground=BORDER_G,
            state="disabled",
        )
        prev_txt.pack(fill="x", padx=16, pady=4)

        def _update_preview(*_):
            fr = v_from.get()
            to = v_to.get()
            lines = []
            for f in list(self.focuses.values())[:5]:
                new = (
                    f.name.replace(fr, to, 1)
                    if fr and f.name.startswith(fr)
                    else f.name
                )
                lines.append(f"  {f.name}  →  {new}")
            prev_txt.config(state="normal")
            prev_txt.delete("1.0", "end")
            prev_txt.insert("1.0", "\n".join(lines))
            prev_txt.config(state="disabled")

        v_from.trace_add("write", _update_preview)
        v_to.trace_add("write", _update_preview)
        _update_preview()

        def _apply():
            fr = v_from.get()
            to = v_to.get()
            if not fr:
                messagebox.showwarning(
                    tr("bulk_rename.rename_title", "Rename"),
                    tr("bulk_rename.from_empty", "From prefix cannot be empty."),
                )
                return
            self._push_undo("bulk_rename")
            # Build mapping old_name → new_name
            mapping = {}
            for f in self.focuses.values():
                if f.name.startswith(fr):
                    mapping[f.name] = to + f.name[len(fr) :]
            # Apply to names
            for f in self.focuses.values():
                if f.name in mapping:
                    f.name = mapping[f.name]
            # prereqs and mutex store integer fids — no remapping needed
            # (names changed above; fid links are stable)
            n = len(mapping)
            win.destroy()
            self._redraw()
            self._refresh_focus_list()
            messagebox.showinfo(
                tr("bulk_rename.renamed_title", "Renamed"),
                tr("bulk_rename.renamed_body", "Renamed {count} focus IDs.", count=n),
            )

        bf = tk.Frame(win, bg=BG_DARK)
        bf.pack(fill="x", padx=16, pady=8)
        tk.Button(
            bf,
            text=tr("common.cancel", "Cancel"),
            command=win.destroy,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            font=("Helvetica", 9, "bold"),
        ).pack(side="right", padx=4)
        tk.Button(
            bf,
            text=tr(
                "bulk_rename.apply_all", "Apply to All {count}", count=len(self.focuses)
            ),
            command=_apply,
            bg="#14532d",
            fg="#4ade80",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            font=("Helvetica", 10, "bold"),
        ).pack(side="right")

    # ─────────────────── SELECT ALL ──────────────────────────────
    def _select_all_focuses(self):
        """Select all focuses — enables multi-select with everything selected."""
        if not self.focuses:
            messagebox.showinfo(
                tr("menu.select_all", "Select All"),
                tr("select_all.no_focuses", "No focuses to select."),
            )
            return
        if not self._multisel_mode:
            self._toggle_multisel()
        self._multi_sel = set(self.focuses.keys())
        self._redraw()

    # ─────────────────── VALIDATE TREE ───────────────────────────
    def _validate_tree(self):
        """Check tree for common errors and report them."""
        issues = []
        for f in self.focuses.values():
            # Broken prereqs (prereqs store Focus IDs = ints)
            for grp in f.prereqs:
                for pid in grp:
                    if pid not in self.focuses:
                        issues.append(f"[{f.name}]  broken prereq → id:{pid}")
            # Broken mutex (mutex stores Focus IDs = ints)
            for mid in f.mutex:
                if mid not in self.focuses:
                    issues.append(f"[{f.name}]  broken mutex → id:{mid}")
            # No effects
            if not f.effects:
                issues.append(f"[{f.name}]  no effects in completion_reward")
            # Missing GFX
            gfx = getattr(f, "gfx", "")
            if not gfx or gfx == "GFX_goal_generic_political_pressure":
                issues.append(f"[{f.name}]  using default/missing icon GFX")

        win = tk.Toplevel(self)
        win.title(tr("validation.title", "Tree Validation"))
        win.configure(bg=BG_DARK)
        win.geometry("640x440")
        win.resizable(True, True)

        hdr = tk.Frame(win, bg="#080c12")
        hdr.pack(fill="x")
        if issues:
            tk.Label(
                hdr,
                text=tr(
                    "validation.issues_found",
                    "  {count} issues found",
                    count=len(issues),
                ),
                bg="#080c12",
                fg="#fbbf24",
                font=("Helvetica", 11, "bold"),
                pady=8,
            ).pack(side="left", padx=8)
        else:
            tk.Label(
                hdr,
                text=tr("validation.clean", "  Tree looks clean!"),
                bg="#080c12",
                fg="#22c55e",
                font=("Helvetica", 11, "bold"),
                pady=8,
            ).pack(side="left", padx=8)
        tk.Button(
            hdr,
            text="✕",
            command=win.destroy,
            bg="#080c12",
            fg=TEXT_DIM,
            relief="flat",
            cursor="hand2",
            padx=10,
        ).pack(side="right")
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")

        frm = tk.Frame(win, bg=BG_DARK)
        frm.pack(fill="both", expand=True)
        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")
        txt = tk.Text(
            frm,
            bg="#050810",
            fg=TEXT,
            font=("Courier", 10),
            relief="flat",
            yscrollcommand=sb.set,
            wrap="word",
            highlightthickness=0,
        )
        sb.config(command=txt.yview)
        txt.pack(fill="both", expand=True, padx=8, pady=8)
        if issues:
            for issue in issues:
                if "broken" in issue:
                    txt.insert("end", "  🔴  " + issue + "\n")
                elif "no effects" in issue:
                    txt.insert("end", "  🟡  " + issue + "\n")
                else:
                    txt.insert("end", "  🔵  " + issue + "\n")
        else:
            txt.insert(
                "end",
                "\n"
                + tr(
                    "validation.all_prereqs_valid",
                    "  All prerequisite chains are valid.",
                )
                + "\n"
                + tr("validation.all_mutex_valid", "  All mutex references resolve.")
                + "\n"
                + tr(
                    "validation.all_effects_present",
                    "  All focuses have completion_reward effects.",
                )
                + "\n",
            )
        txt.config(state="disabled")

    def _export(self):
        # Flush any unsaved edits from the form back to the current focus before export
        try:
            if self.selected:
                self._autosave()
        except Exception:
            pass
        # Only export main-tree focuses (tree_idx == 0)
        main_focuses = {
            fid: f for fid, f in self.focuses.items() if getattr(f, "tree_idx", 0) == 0
        }
        if not main_focuses:
            messagebox.showwarning(
                tr("dialog.export.title", "Export"),
                tr(
                    "dialog.no_main_focuses_export",
                    "No main-tree focuses to export.\nUse 'Save All' or the Loaded Trees panel to export shared/joint trees.",
                ),
            )
            return
        tid = (
            re.sub(r"[^A-Za-z0-9_]", "_", self._tree_id.get().strip())
            or "TAG_focus_tree"
        )

        # ── Detect country TAG from tree id or focus prefix ──────────
        # Tree id pattern: TAG_focus_tree → TAG
        tag_match = re.match(r"^([A-Z]{2,5})_", tid)
        country_tag = (
            tag_match.group(1)
            if tag_match
            else getattr(self, "_tree_country_tag", "TAG")
        )
        country_tag = country_tag.upper()

        out = []
        out.append("focus_tree = {")
        out.append(f"\tid = {tid}")
        out.append("")
        # Prefer the verbatim country block captured from import; fall back to a
        # default that follows MD convention (base/add/original_tag) if none was
        # imported (e.g., tree created from scratch).
        _country_raw = getattr(self, "_tree_country_raw", "").strip()
        if _country_raw:
            out.append("\tcountry = {")
            for ln in _country_raw.splitlines():
                if ln.strip():
                    out.append(f"\t\t{ln}")
            out.append("\t}")
        else:
            out.append("\tcountry = {")
            out.append("\t\tbase = 0")
            out.append("\t\tmodifier = {")
            out.append("\t\t\tadd = 100")
            out.append(f"\t\t\toriginal_tag = {country_tag}")
            out.append("\t\t}")
            out.append("\t}")
        out.append("")

        # Write shared_focus and joint_focus lines (preserved from import, never stripped)
        for sf in getattr(self, "_shared_focuses", []):
            out.append(f"\tshared_focus = {sf}")
        for jf in getattr(self, "_joint_focuses", []):
            out.append(f"\tjoint_focus = {jf}")
        if getattr(self, "_shared_focuses", []) or getattr(self, "_joint_focuses", []):
            out.append("")

        # continuous_focus_position: use stored value from import, never recalculate
        cfp_x = getattr(self, "_cfp_x", None)
        cfp_y = getattr(self, "_cfp_y", None)
        # Also check if user edited the toolbar fields
        try:
            _tx = int(self._cfp_x_var.get())
            cfp_x = _tx
        except Exception:
            pass
        try:
            _ty = int(self._cfp_y_var.get())
            cfp_y = _ty
        except Exception:
            pass
        if cfp_x is None or cfp_y is None:
            # Fallback for trees created from scratch (no imported value)
            if main_focuses:
                cfp_x = min(f.x for f in main_focuses.values()) * 100
                cfp_y = max(f.y for f in main_focuses.values()) * 100
            else:
                cfp_x, cfp_y = 0, 0
        out.append(f"\tcontinuous_focus_position = {{ x = {cfp_x} y = {cfp_y} }}")
        out.append("")

        for f in main_focuses.values():
            gx = f.x
            gy = f.y
            out.append("\tfocus = {")

            # ── Property order per skill rules ───────────────────────
            # id, icon, x/y, relative_position_id, cost,
            # prerequisite, mutually_exclusive, search_filters,
            # available, bypass, cancel,
            # will_lead_to_war_with, complete_tooltip,
            # select_effect, completion_reward, bypass_effect, ai_will_do

            out.append(f"\t\tid = {f.name}")
            _focus_gfx = getattr(f, "gfx", "generic_political_pressure")
            if _focus_gfx.startswith("GFX_goal_"):
                _focus_gfx = _focus_gfx[len("GFX_goal_") :]
            out.append(f"\t\ticon = {_focus_gfx}")
            # Custom localisation key override (preserved from import)
            _ftext = getattr(f, "text", "").strip()
            if _ftext:
                out.append(f"\t\ttext = {_ftext}")

            rel_id = getattr(f, "relative_position_id", None)
            parent = (
                next(
                    (foc for foc in self.focuses.values() if foc.name == rel_id),
                    None,
                )
                if rel_id
                else None
            )
            if parent:
                # Use stored raw delta if available (imported files), else compute
                dx = getattr(f, "_rel_dx", None)
                dy = getattr(f, "_rel_dy", None)
                if dx is None or dy is None:
                    dx = gx - parent.x
                    dy = gy - parent.y
                out.append(f"\t\tx = {dx}")
                out.append(f"\t\ty = {dy}")
                out.append(f"\t\trelative_position_id = {rel_id}")
            else:
                out.append(f"\t\tx = {gx}")
                out.append(f"\t\ty = {gy}")
            for _off in getattr(f, "offsets", []):
                out.append("\t\toffset = {")
                out.append(f"\t\t\tx = {_off['x']}")
                out.append(f"\t\t\ty = {_off['y']}")
                if _off.get("trigger", "").strip():
                    out.append("\t\t\ttrigger = {")
                    for _ln in _off["trigger"].strip().splitlines():
                        out.append(f"\t\t\t\t{_ln.strip()}")
                    out.append("\t\t\t}")
                out.append("\t\t}")

            out.append(f"\t\tcost = {f.cost}")

            # prerequisites
            if f.prereqs:
                for grp in f.prereqs:
                    valid = [p for p in grp if p in self.focuses]
                    if not valid:
                        continue
                    inner = " ".join(f"focus = {self.focuses[p].name}" for p in valid)
                    out.append(f"\t\tprerequisite = {{ {inner} }}")

            # mutually exclusive
            if f.mutex:
                for mid in f.mutex:
                    if mid in self.focuses:
                        out.append(
                            f"\t\tmutually_exclusive = {{ focus = {self.focuses[mid].name} }}"
                        )

            sf = getattr(f, "search_filters", "").strip()
            if sf:
                out.append(f"\t\tsearch_filters = {{ {sf} }}")

            # allow_branch (gates focus visibility — preserved from import)
            allow_br = getattr(f, "allow_branch", "").strip()
            if allow_br:
                out.append("\t\tallow_branch = {")
                lines = allow_br.splitlines()
                non_empty = [l for l in lines if l.strip()]
                min_ind = (
                    min((len(l) - len(l.lstrip("\t"))) for l in non_empty)
                    if non_empty
                    else 0
                )
                for ln in lines:
                    stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
                    out.append(f"\t\t\t{stripped}")
                out.append("\t\t}")

            # available
            avail = getattr(f, "available_cond", "").strip()
            if avail:
                out.append("\t\tavailable = {")
                # Preserve relative indentation from raw block
                lines = avail.splitlines()
                non_empty = [l for l in lines if l.strip()]
                min_ind = (
                    min((len(l) - len(l.lstrip("\t"))) for l in non_empty)
                    if non_empty
                    else 0
                )
                for ln in lines:
                    stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
                    out.append(f"\t\t\t{stripped}")
                out.append("\t\t}")

            # bypass
            bypass = getattr(f, "bypass_cond", "").strip()
            if bypass:
                out.append("\t\tbypass = {")
                lines = bypass.splitlines()
                non_empty = [l for l in lines if l.strip()]
                min_ind = (
                    min((len(l) - len(l.lstrip("\t"))) for l in non_empty)
                    if non_empty
                    else 0
                )
                for ln in lines:
                    stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
                    out.append(f"\t\t\t{stripped}")
                out.append("\t\t}")

            # cancel
            cancelc = getattr(f, "cancel_cond", "").strip()
            if cancelc:
                out.append("\t\tcancel = {")
                lines = cancelc.splitlines()
                non_empty = [l for l in lines if l.strip()]
                min_ind = (
                    min((len(l) - len(l.lstrip("\t"))) for l in non_empty)
                    if non_empty
                    else 0
                )
                for ln in lines:
                    stripped = ln[min_ind:] if len(ln) >= min_ind else ln.lstrip("\t")
                    out.append(f"\t\t\t{stripped}")
                out.append("\t\t}")

            # will_lead_to_war_with (raw block — can contain multiple tags)
            wltww = getattr(f, "will_lead_to_war_with", "").strip()
            if wltww:
                if wltww.startswith("{") and wltww.endswith("}"):
                    inner = wltww[1:-1].strip()
                else:
                    inner = wltww
                out.append("\t\twill_lead_to_war_with = {")
                for ln in inner.splitlines():
                    if ln.strip():
                        out.append(f"\t\t\t{ln.strip()}")
                out.append("\t\t}")

            # complete_tooltip (raw block of effects)
            ctip = getattr(f, "complete_tooltip", "").strip()
            if ctip:
                out.append("\t\tcomplete_tooltip = {")
                for ln in ctip.splitlines():
                    if ln.strip():
                        out.append(f"\t\t\t{ln.strip()}")
                out.append("\t\t}")

            # select_effect (raw block — runs when focus is selected)
            sel_eff = getattr(f, "select_effect", "").strip()
            if sel_eff:
                out.append("\t\tselect_effect = {")
                for ln in sel_eff.splitlines():
                    if ln.strip():
                        out.append(f"\t\t\t{ln.strip()}")
                out.append("\t\t}")

            # boolean flags — only emit when they differ from defaults
            if not f.cancel_if_invalid:
                out.append("\t\tcancel_if_invalid = no")
            if f.continue_if_invalid:
                out.append("\t\tcontinue_if_invalid = yes")
            if f.available_if_capitulated:
                out.append("\t\tavailable_if_capitulated = yes")

            # completion_reward — preserve imported raw block verbatim;
            # only inject the hardcoded log line for newly created focuses
            # (whose raw block is empty) to avoid duplicating it on every save.
            _has_raw_reward = bool(
                f.effects and any(e.get("type") == "_raw_block" for e in f.effects)
            )
            out.append("")
            out.append("\t\tcompletion_reward = {")
            if not _has_raw_reward:
                out.append(
                    f'\t\t\tlog = "[GetDateText]: [Root.GetName]: Focus {f.name}"'
                )
            if f.effects:
                for eff in f.effects:
                    out.append(self._render_effect(eff))
            else:
                out.append("\t\t\t# TODO: add effects")
            out.append("\t\t}")

            # bypass_effect (raw block — runs when focus is bypassed)
            bp_eff = getattr(f, "bypass_effect", "").strip()
            if bp_eff:
                out.append("\t\tbypass_effect = {")
                for ln in bp_eff.splitlines():
                    if ln.strip():
                        out.append(f"\t\t\t{ln.strip()}")
                out.append("\t\t}")

            out.append("")
            out.append("\t\tai_will_do = {")
            raw_ai = getattr(f, "ai_will_do_raw", "").strip()
            if raw_ai:
                for ln in raw_ai.splitlines():
                    out.append(f"\t\t\t{ln.strip()}")
            else:
                # MD convention: ai_will_do uses `base = X` at top level, `factor = X` only in modifier sub-blocks
                out.append(f"\t\t\tbase = {f.ai_will_do}")
            out.append("\t\t}")
            out.append("\t}")
            out.append("")

        out.append("}")

        # ── File naming: 05_TAG.txt per skill rules ───────────────────
        default_filename = f"05_{country_tag}.txt"

        # If an edit target is set, overwrite it directly; otherwise prompt
        if MOD.edit_focus_file and os.path.isfile(MOD.edit_focus_file):
            path = MOD.edit_focus_file
        else:
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[
                    (tr("filetype.hoi4_focus_tree", "HOI4 Focus Tree"), "*.txt"),
                    (tr("filetype.all", "All"), "*.*"),
                ],
                initialfile=default_filename,
                title=tr("filedialog.export_hoi4_txt", "Export HOI4 .txt"),
            )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(out))

        if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file):
            loc_path = MOD.edit_loc_file
        else:
            loc_filename = f"MD_focus_{country_tag}_l_english.yml"
            _saved_dir = os.path.dirname(os.path.abspath(path))
            _mod_root = MOD.root if MOD.root and os.path.isdir(MOD.root) else None
            if _mod_root is None:
                _candidate = _saved_dir
                for _ in range(5):
                    _candidate = os.path.dirname(_candidate)
                    if os.path.isdir(
                        os.path.join(_candidate, "common")
                    ) and os.path.isdir(os.path.join(_candidate, "localisation")):
                        _mod_root = _candidate
                        break
            if _mod_root:
                loc_path = os.path.join(
                    _mod_root, "localisation", "english", loc_filename
                )
            else:
                # Last resort: ask the user where to save the loc file
                loc_path = filedialog.asksaveasfilename(
                    defaultextension=".yml",
                    filetypes=[
                        (tr("filetype.yml_localisation", "YML localisation"), "*.yml"),
                        (tr("filetype.all", "All"), "*.*"),
                    ],
                    initialfile=loc_filename,
                    title=tr(
                        "filedialog.save_localisation_yml",
                        "Save Localisation .yml  (should go in localisation/english/)",
                    ),
                )
                if not loc_path:
                    loc_path = os.path.join(
                        _saved_dir, loc_filename
                    )  # absolute fallback

        # Build map of keys this (main) tree needs — skip extra tree focuses
        new_loc = {}
        for f in main_focuses.values():
            title = f.name.replace("_", " ").title()
            desc = f.desc if f.desc else f"Complete the {title} national focus."
            new_loc[f.name] = title
            new_loc[f"{f.name}_desc"] = desc

        # Read existing keys from file (handles both  key: "val"  and  key:0 "val")
        existing_keys = set()
        if os.path.isfile(loc_path):

            with open(loc_path, encoding="utf-8-sig", errors="replace") as fp:
                for line in fp:
                    m = re.match(r'\s+(\S+?)(?::\d+)?\s*[=:]?\s*"', line)
                    if m:
                        existing_keys.add(m.group(1))

        to_add = {k: v for k, v in new_loc.items() if k not in existing_keys}
        loc_saved = ""
        if to_add:
            os.makedirs(os.path.dirname(loc_path) or ".", exist_ok=True)
            if not os.path.isfile(loc_path):
                with open(loc_path, "w", encoding="utf-8-sig") as fp:
                    fp.write("l_english:\n")
            # Only write a section header if one doesn't already exist
            needs_header = True
            try:
                with open(loc_path, encoding="utf-8-sig", errors="replace") as _fp:
                    _existing = _fp.read()
                if f"##########Focuses - {country_tag}##########" in _existing:
                    needs_header = False
            except Exception:
                pass
            with open(loc_path, "a", encoding="utf-8-sig") as fp:
                if needs_header:
                    fp.write(f"\n ##########Focuses - {country_tag}##########\n")
                for k, v in to_add.items():
                    fp.write(f' {k}: "{v}"\n')
            loc_saved = "\n" + tr(
                "export.localisation_added",
                "Localisation: {file}  (+{count} new keys)",
                file=os.path.basename(loc_path),
                count=len(to_add),
            )
        else:
            loc_saved = "\n" + tr(
                "export.localisation_skipped",
                "Localisation: all keys already present in {file} - skipped",
                file=os.path.basename(loc_path),
            )

        messagebox.showinfo(
            tr("dialog.exported.title", "Exported"),
            tr(
                "dialog.exported.body",
                "Export complete!\n\nFocus tree: {focus_file}{loc_saved}\n\nInstall paths:\n  .txt  ->  common/national_focus/{default_filename}\n\nReminders:\n  - Replace placeholder icons with real GFX keys\n  - Add shared_focus lines if using shared trees",
                focus_file=os.path.basename(path),
                loc_saved=loc_saved,
                default_filename=default_filename,
            ),
        )


# ─────────────────────────── ENTRY POINT ────────────────────────
if __name__ == "__main__":

    def _launch():
        log.info("_launch: creating App...")
        app = App()
        log.info("_launch: App created, updating idle tasks...")
        app.update_idletasks()
        W, H = 1440, 880
        sw = app.winfo_screenwidth()
        sh = app.winfo_screenheight()
        app.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        log.info(f"_launch: geometry set to {W}x{H}, entering mainloop...")
        app.mainloop()
        log.info("_launch: mainloop exited")

    log.info("Entry point: calling show_splash...")
    show_splash(_launch, apply_dpi_scaling=_apply_tk_dpi_scaling)
