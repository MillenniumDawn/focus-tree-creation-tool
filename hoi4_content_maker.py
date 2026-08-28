# =================================================================
#  Content Maker for Hearts of Iron 4
#  HOI4 Content Maker
#  Version 2.0  |  Millennium Dawn Team
# =================================================================
#
#  COPYRIGHT NOTICE
#  Copyright (c) 2025 Millennium Dawn Team.
#
#  SPDX-License-Identifier: CC-BY-ND-4.0
#
#  Licensed under the Creative Commons Attribution-NoDerivatives
#  4.0 International License. See LICENSE in the repository root
#  for the complete terms.
#
#  CONTACT
#  For licensing enquiries, permissions, or general contact:
#    millenniumdawnteam@gmail.com
#
# =================================================================

"""
Content Maker for Hearts of Iron 4
HOI4 Content Maker  —  v2.0  |  Millennium Dawn Team

Copyright (c) 2025 Millennium Dawn Team.

Wiki    : https://hoi4.paradoxwikis.com/National_focus_modding
Requires: Python 3.14+  (tkinter built-in, no pip install needed)
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
    EFFECT_CATS,
    EmptyDrawioGraphError,
    EmptyFocusTreeError,
    Focus,
    UndoStack,
    add_error,
    apply_focus_code,
    batch_load_trees,
    build_drawio_focuses,
    build_focus_name_lookup,
    build_focuses,
    drawio_to_focus_data,
    execute_export_plans,
    get_error_entries,
    group_focuses_by_tree,
    install_excepthook,
    make_extra_export_plan,
    make_main_export_plan,
    parse_drawio_graph,
    parse_focus_tree,
    read_file,
    render_focus_block,
    sanitize_component,
    set_error_callback,
    show_splash,
    tr,
)
from hoi4cm.editor import (
    clear_workspace_autosave,
    read_project,
    sibling_autosave_path,
    workspace_autosave_path,
    write_project,
)
from hoi4cm.focus_tree.validate import (
    collect_loc_keys_from_text,
    validate_document,
    worst_severity_per_focus,
)
from hoi4cm.mod import MOD, detect_loc_file
from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.models import (
    EditorWorkspace,
    FocusSidebarValues,
    TreeDocument,
    TreeMetadata,
    apply_sidebar_values,
    parse_ai_will_do,
    parse_focus_cost,
    sidebar_values_match_focus,
)
from hoi4cm.ui import (
    BG_CARD,
    BG_DARK,
    BG_PANEL,
    BLUE,
    BORDER,
    BORDER_G,
    CANVAS_BG,
    FC_BORDER,
    GOLD_LT,
    ICONS,
    ORANGE,
    RED,
    TEXT,
    TEXT_DIM,
    YELLOW,
    ApplicationLifecycle,
    Tooltip,
    TutorialController,
    _safe_after,
    make_progress,
    progress_modal,
    report_error,
    report_write_failure,
    run_bg,
)
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.checklist import (
    ChecklistItem,
    VirtualChecklist,
    apply_select_mode,
    default_tree_type,
    is_loadable,
)
from hoi4cm.ui.effects_panel import EffectsMixin
from hoi4cm.ui.focus_list import FocusListCache, FocusListItem, VirtualFocusList
from hoi4cm.ui.gfx_browser import open_focus_icon_browser
from hoi4cm.ui.loaded_trees import LoadedTreeRowItem, VirtualLoadedTreesList
from hoi4cm.ui.menubar import build_menubar
from hoi4cm.ui.mod_loading import ModLoadingMixin
from hoi4cm.ui.settings_dialog import open_settings
from hoi4cm.ui.toolbar import build_toolbar_row2
from hoi4cm.ui.tree_badges import build_tree_badges

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
from tkinter import filedialog, messagebox

log.info("tkinter imported OK")
import bisect
import re
import time


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


class App(CanvasMixin, ModLoadingMixin, EffectsMixin, tk.Tk):  # type: ignore[misc]
    CANVAS_MIN_SIZE = 10
    CANVAS_EXPAND_STEP = 5
    TREE_META_REF_CAP = 50

    def __init__(self):
        log.info("App.__init__: calling tk.Tk.__init__...")
        super().__init__()
        self._lifecycle = ApplicationLifecycle(self)
        self._lifecycle.add_resource(self._close_app_caches)
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
        self.workspace = EditorWorkspace()
        self.focuses = self.workspace.focuses
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
        self._validation_issues = []
        self._validation_worst = {}
        self._validation_job = None
        self._validation_win = None
        self._saved_revision = self.focuses.revision
        self._saved_fingerprint = self._workspace_fingerprint()
        self._autosave_job = None
        self._autosave_interval_ms = 60000
        self._last_project_path = None
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self._build_ui()
        self._redraw()
        self._schedule_validation()
        self._update_title()
        self._schedule_autosave()
        self.after(800, self._run_startup_prompts)

    def _run_startup_prompts(self):
        """Sequence recovery before any optional first-launch teaching."""
        self._maybe_offer_autosave_restore()
        self._tutorial.start()

    def _on_app_close(self):
        if self._is_dirty():
            ans = messagebox.askyesnocancel(
                tr("dialog.unsaved_changes.title", "Unsaved Changes"),
                tr(
                    "dialog.unsaved_changes.close_body",
                    "You have unsaved changes.\n\nSave before closing?",
                ),
                parent=self,
            )
            if ans is None:
                return
            if ans and not self._save():
                return
        if not self._lifecycle.begin_close():
            return
        try:
            self._cancel_autosave()
            MOD.save_config()
        except Exception:
            pass
        finally:
            self._lifecycle.finish_close()
            self.destroy()

    def _workspace_fingerprint(self):
        try:
            cfp_x = int(self._cfp_x_var.get())
        except TypeError, ValueError, AttributeError:
            cfp_x = getattr(self, "_cfp_x", None)
        try:
            cfp_y = int(self._cfp_y_var.get())
        except TypeError, ValueError, AttributeError:
            cfp_y = getattr(self, "_cfp_y", None)
        extra_fp = []
        for tree in getattr(self, "_extra_trees", []):
            extra_fp.append(
                (
                    tree.get("type", ""),
                    tree.get("file_path", ""),
                    tree.get("tree_id", ""),
                    tree.get("cfp_x"),
                    tree.get("cfp_y"),
                    tree.get("country_tag", ""),
                    tree.get("had_wrapper", True),
                    tuple(sorted(tree.get("focus_ids", set()))),
                    tuple(tree.get("shared_focuses", [])),
                    tuple(tree.get("joint_focuses", [])),
                )
            )
        return (
            self._tree_id.get() if hasattr(self, "_tree_id") else "TAG_focus_tree",
            getattr(self, "_tree_country_tag", ""),
            getattr(self, "_tree_country_name", ""),
            getattr(self, "_tree_country_raw", ""),
            getattr(self, "_tree_focus_prefix", ""),
            getattr(self, "_tree_extras", {}),
            getattr(MOD, "edit_focus_file", "") or "",
            getattr(self, "_tree_had_wrapper", True),
            cfp_x,
            cfp_y,
            tuple(getattr(self, "_shared_focuses", [])),
            tuple(getattr(self, "_joint_focuses", [])),
            tuple(getattr(self, "_canvas_min", [0, 0])),
            tuple(getattr(self, "_canvas_max", [9, 9])),
            getattr(self, "_default_focus_prefix", ""),
            tuple(extra_fp),
        )

    def _is_dirty(self) -> bool:
        if getattr(self, "focuses", None) is None:
            return False
        if self.focuses.revision != getattr(self, "_saved_revision", 0):
            return True
        try:
            return self._workspace_fingerprint() != getattr(
                self, "_saved_fingerprint", None
            )
        except Exception:
            return False

    def _mark_clean(self) -> None:
        self._saved_revision = self.focuses.revision
        try:
            self._saved_fingerprint = self._workspace_fingerprint()
        except Exception:
            self._saved_fingerprint = None
        self._update_title()

    def _confirm_discard(self, action: str = "close") -> bool:
        if not self._is_dirty():
            return True
        ans = messagebox.askyesnocancel(
            tr("dialog.unsaved_changes.title", "Unsaved Changes"),
            tr(
                "dialog.unsaved_changes.body",
                "You have unsaved changes.\n\nSave before {action}?",
                action=action,
            ),
            parent=self,
        )
        if ans is None:
            return False
        if ans and not self._save():
            return False
        return True

    def _schedule_autosave(self) -> None:
        self._cancel_autosave()
        if not hasattr(self, "_autosave_interval_ms"):
            return
        try:
            self._autosave_job = self.after(
                self._autosave_interval_ms, self._autosave_tick
            )
        except Exception:
            self._autosave_job = None

    def _cancel_autosave(self) -> None:
        job = getattr(self, "_autosave_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._autosave_job = None

    def _autosave_tick(self) -> None:
        self._autosave_job = None
        try:
            if self._is_dirty():
                path = workspace_autosave_path()
                self._capture_workspace()
                write_project(path, self.workspace)
                sibling = getattr(self, "_last_project_path", None)
                if sibling:
                    try:
                        write_project(sibling_autosave_path(sibling), self.workspace)
                    except Exception:
                        log.exception("sibling autosave failed")
        except Exception:
            log.exception("workspace autosave failed")
        finally:
            self._schedule_autosave()

    def _maybe_offer_autosave_restore(self) -> None:
        path = workspace_autosave_path()
        if not os.path.isfile(path):
            return
        if self._is_dirty():
            return
        try:
            autosaved = read_project(path)
        except Exception:
            return
        if not autosaved.focuses and autosaved.main_tree.metadata.tree_id in (
            "",
            "TAG_focus_tree",
        ):
            return
        focus_count = len(autosaved.focuses)
        tree_id = autosaved.main_tree.metadata.tree_id or "untitled"
        ans = messagebox.askyesnocancel(
            tr("dialog.autosave_restore.title", "Restore Autosave?"),
            tr(
                "dialog.autosave_restore.body",
                "An autosaved workspace was found ({count} focuses, tree '{tree}').\n\nRestore it?",
                count=focus_count,
                tree=tree_id,
            ),
            parent=self,
        )
        if ans is None:
            return
        if ans:
            try:
                self.cv.delete("all")
                self.selected = None
                self._lines.clear()
                self._grid_item = None
                self._grid_key = None
                self._grid_img = None
                self._install_workspace(autosaved)
                self._update_title()
                self._detect_and_apply_tag()
                self._refresh_tree_meta_panel()
                self._refresh_loaded_trees_panel()
                self._hide_form()
                self._redraw()
                self._invalidate_focus_list_structure()
                self._hint(
                    tr(
                        "hint.autosave_restored",
                        "Autosaved workspace restored — save to keep it",
                    )
                )
            except Exception as ex:
                log.exception("autosave restore failed")
                report_error(
                    tr(
                        "dialog.autosave_restore_error.body",
                        "Could not restore autosave:\n{error}",
                        error=ex,
                    ),
                    ex,
                    parent=self,
                    title=tr("dialog.autosave_restore_error.title", "Restore Failed"),
                )
        else:
            clear_workspace_autosave(path)

    def _close_app_caches(self):
        from hoi4cm.wizards import _shared as _wiz_shared

        MOD.sprite_imgs.clear()
        for cache in _wiz_shared._app_img_caches:
            cache.clear()

    def _begin_document_generation(self):
        self._lifecycle.begin("document")
        self._invalidate_canvas_images()

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
        self._undo_stack = UndoStack(maxlen=60)
        self._tree_id = tk.StringVar(value="TAG_focus_tree")
        # Continuous focus position — stored as integers when read from file
        self._cfp_x = None  # None = no value read; use fallback on export
        self._cfp_y = None
        self._cfp_x_var = tk.StringVar(value="")
        self._cfp_y_var = tk.StringVar(value="")
        # shared_focus and joint_focus lines preserved from import
        self._shared_focuses = self.workspace.main_tree.metadata.shared_focuses
        self._joint_focuses = self.workspace.main_tree.metadata.joint_focuses
        # Extra loaded trees (shared/joint trees loaded alongside the main tree)
        self._extra_trees = (
            []
        )  # list of dicts: {type, file_path, tree_id, cfp_x, cfp_y, shared_focuses, joint_focuses, country_tag, country_raw, tree_extras, had_wrapper, focus_ids}
        self._tree_badge_table = None  # rebuilt by _get_tree_badge on change
        toolbar = tk.Frame(self, bg=BG_DARK)
        toolbar.pack(fill="x")
        self._menu_controller = build_menubar(
            self,
            toolbar,
            tutorial_command=lambda: self._tutorial.start(manual=True),
        )
        build_toolbar_row2(self, toolbar)
        self._build_keybinds()
        self._build_layout()
        self._tutorial = TutorialController(self, self._menu_controller)
        self._lifecycle.add_resource(self._tutorial.close)

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
        self.bind("<Control-y>", lambda e: self._redo())
        self.bind("<Control-Y>", lambda e: self._redo())
        self.bind("<Control-Shift-Z>", lambda e: self._redo())
        self.bind("<Control-Shift-z>", lambda e: self._redo())
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
            lambda e: (
                (lp_ent.delete(0, "end"), lp_ent.config(fg=TEXT))
                if lp_ent.get() == tr("common.search_placeholder", "Search...")
                else None
            ),
        )
        lp_ent.bind(
            "<FocusOut>",
            lambda e: (
                (
                    lp_ent.insert(0, tr("common.search_placeholder", "Search...")),
                    lp_ent.config(fg=TEXT_DIM),
                )
                if not lp_ent.get()
                else None
            ),
        )
        self._lp_search_var.trace_add(
            "write", lambda *_: self._refresh_focus_list_debounced()
        )
        # list
        lp_list_frame = tk.Frame(self._left_panel, bg=BG_PANEL)
        lp_list_frame.pack(fill="both", expand=True)
        self._focus_list = VirtualFocusList(
            lp_list_frame,
            on_select=self._select_focus_from_list,
            background=BG_PANEL,
        )
        self._focus_list_cache = FocusListCache()
        self._focus_list.pack(fill="both", expand=True)
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
                lambda: (
                    self._errlog_btn.config(
                        text=tr(
                            "error_log.badge_log_count", "! Log ({count})", count=count
                        ),
                        fg="#f87171",
                        bg="#450a0a",
                    )
                    if count > 0
                    else None
                ),
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
    def _push_undo(self, label="action", touched_ids=None):
        """Call BEFORE making a change to save enough state to undo it.

        `touched_ids` lists the focus ids the caller is about to mutate or
        delete; leave it as `()` for an action that only creates new
        focuses (undo deletes those via an id-set diff, no snapshot needed).
        Pass `None` (the default) when the touched set isn't known or is
        most of the tree anyway (bulk import/clear) — that takes a full
        compressed snapshot instead, same as the old behavior.
        """
        self._undo_stack.push(label, self.focuses, touched_ids)

    def _undo(self):
        """Restore the previous state, touching only what it changed."""
        result = self._undo_stack.undo(self.focuses, Focus.from_dict)
        if result is None:
            self._hint("Nothing to undo.")
            return
        label, changed_ids, removed_ids = result
        for fid in changed_ids | removed_ids:
            self.cv.delete("F" + str(fid))
        if self.selected and self.selected.id in removed_ids:
            self.selected = None
            self._hide_form()
        elif self.selected and self.selected.id in changed_ids:
            self.selected = self.focuses[self.selected.id]
            self._populate(self.selected)
            self._refresh_prereqs()
            self._refresh_mutex()
            self._refresh_effects()
        self._redraw()
        self._invalidate_focus_list_structure()
        self._hint(f"↩ Undid: {label}")

    def _redo(self):
        """Re-apply the most recently undone action."""
        result = self._undo_stack.redo(self.focuses, Focus.from_dict)
        if result is None:
            self._hint("Nothing to redo.")
            return
        label, changed_ids, removed_ids = result
        for fid in changed_ids | removed_ids:
            self.cv.delete("F" + str(fid))
        if self.selected and self.selected.id in removed_ids:
            self.selected = None
            self._hide_form()
        elif self.selected and self.selected.id in changed_ids:
            self.selected = self.focuses[self.selected.id]
            self._populate(self.selected)
            self._refresh_prereqs()
            self._refresh_mutex()
            self._refresh_effects()
        self._redraw()
        self._invalidate_focus_list_structure()
        self._hint(f"↪ Redid: {label}")

    def _hint(self, t):
        self._hint_lbl.config(text=t)

    # ── VALIDATION (background + dialog) ───────────────────────────
    def _validation_sprites(self):
        if MOD.loaded and getattr(MOD, "sprites", None):
            try:
                # return mapping view directly; validate_document only does `in` checks
                # caller must not mutate
                return MOD.sprites
            except Exception:
                return None
        return None

    def _validation_loc_keys(self):
        path = getattr(MOD, "edit_loc_file", "")
        if path and os.path.isfile(path):
            try:
                text = read_file(path)
                keys = collect_loc_keys_from_text(text)
                return keys
            except Exception:
                return None
        return None

    def _schedule_validation(self):
        if getattr(self, "_validation_job", None):
            return
        try:
            self._validation_job = self.after(150, self._run_validation)
        except Exception:
            self._run_validation()

    def _run_validation(self):
        """Validate the document on a worker thread; apply results in on_done.

        sprites/loc_keys gathering stays on the Tk thread (it only reads
        ``MOD`` and disk, not widgets, but is captured before dispatch same
        as ``self.focuses``) so the worker only ever sees plain snapshots.
        ``lifecycle.begin`` invalidates any older "validation"-scoped run
        still in flight, so a stale result never overwrites a newer one.
        """
        self._validation_job = None
        self._lifecycle.begin("validation")
        sprites = self._validation_sprites()
        loc_keys = self._validation_loc_keys()
        focuses = dict(self.focuses)

        def work():
            return validate_document(focuses, sprites=sprites, loc_keys=loc_keys)

        run_bg(self, work, self._apply_validation_result, scope="validation")

    def _apply_validation_result(self, issues):
        try:
            worst = worst_severity_per_focus(issues)
        except Exception:
            worst = {}
        prev_issues = self._validation_issues
        prev_worst = self._validation_worst
        changed = issues != prev_issues or worst != prev_worst
        self._validation_issues = issues
        self._validation_worst = worst
        if changed:
            # refresh UI surfaces that depend on validation
            try:
                self._redraw()
            except Exception:
                pass
            try:
                self._invalidate_focus_list_structure()
            except Exception:
                pass
        # if validation dialog is open, refresh its contents
        win = getattr(self, "_validation_win", None)
        if win is not None and win.winfo_exists():
            try:
                self._refresh_validation_dialog(win)
            except Exception:
                pass

    def _center_on_focus(self, fid):
        f = self.focuses.get(fid)
        if f is None:
            return
        try:
            cw = self.cv.winfo_width() or 800
            ch = self.cv.winfo_height() or 600
            self.offset[0] = cw / 2 - f.x * 96 * self.zoom
            self.offset[1] = ch / 2 - f.y * 130 * self.zoom
            self._redraw()
            self._select(f)
        except Exception:
            pass

    def _redraw(self, *args, **kwargs):
        # only validation-relevant redraws should re-queue validation
        channels = kwargs.get("channels", args[0] if args else None)
        should_schedule = True
        try:
            from hoi4cm.ui.canvas_scheduler import RedrawChannel

            if channels is not None:
                should_schedule = bool(channels & RedrawChannel.SCENE)
        except Exception:
            should_schedule = True
        super()._redraw(*args, **kwargs)  # type: ignore[misc]
        if should_schedule:
            try:
                self._schedule_validation()
            except Exception:
                pass

    def _redraw_now(self, *args, **kwargs):
        channels = kwargs.get("channels", args[0] if args else None)
        should_schedule = True
        try:
            from hoi4cm.ui.canvas_scheduler import RedrawChannel

            if channels is not None:
                should_schedule = bool(channels & RedrawChannel.SCENE)
        except Exception:
            should_schedule = True
        super()._redraw_now(*args, **kwargs)  # type: ignore[misc]
        if should_schedule:
            try:
                self._schedule_validation()
            except Exception:
                pass

    def _refresh_tree_meta_panel(self):
        """Refresh the shared_focus / joint_focus read-only display in the sidebar."""
        if not hasattr(self, "_tree_meta_sf_box"):
            return
        for w in self._tree_meta_sf_box.winfo_children():
            w.destroy()
        for w in self._tree_meta_jf_box.winfo_children():
            w.destroy()
        self._fill_tree_meta_box(
            self._tree_meta_sf_box, getattr(self, "_shared_focuses", []), "#86efac"
        )
        self._fill_tree_meta_box(
            self._tree_meta_jf_box, getattr(self, "_joint_focuses", []), "#fbbf24"
        )

    def _fill_tree_meta_box(self, box, refs, color):
        """Render up to TREE_META_REF_CAP ref labels into box, plus a "+N more"."""
        if not refs:
            tk.Label(
                box,
                text=tr("common.none_parenthesized", "  (none)"),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(anchor="w", padx=2)
            return
        shown = refs[: self.TREE_META_REF_CAP]
        for ref in shown:
            tk.Label(
                box,
                text=f"  {ref}",
                bg=BG_CARD,
                fg=color,
                font=("Courier", 8),
                anchor="w",
            ).pack(fill="x", padx=2, pady=1)
        hidden = len(refs) - len(shown)
        if hidden > 0:
            tk.Label(
                box,
                text=tr("sidebar.tree_refs_more", "  +{count} more", count=hidden),
                bg=BG_CARD,
                fg=TEXT_DIM,
                font=("Helvetica", 8, "italic"),
            ).pack(fill="x", padx=2, pady=1)

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
        self._loaded_trees_empty = tk.Label(
            _lt_outer,
            text=tr("sidebar.no_extra_trees", "  No extra trees loaded"),
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Helvetica", 8, "italic"),
            anchor="w",
        )
        # Fixed-height box (~3 rows before scrolling); wraps the pooled list
        # instead of sizing it directly since Frame.configure(height=...)
        # collides with _PooledList's own "_configure" Configure-event handler.
        self._loaded_trees_box = tk.Frame(sb, bg=BG_DARK, height=150)
        self._loaded_trees_box.pack_propagate(False)
        self._loaded_trees_inner = VirtualLoadedTreesList(
            self._loaded_trees_box,
            on_export=self._export_extra_tree,
            on_unload=self._unload_extra_tree,
        )
        self._loaded_trees_inner.pack(fill="both", expand=True)
        self._loaded_trees_border = tk.Frame(sb, bg=BORDER_G, height=1)
        self._loaded_trees_border.pack(fill="x")
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
        self._fv_x_entry = tk.Entry(
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
        )
        self._fv_x_entry.pack(side="left", ipady=4, padx=(0, 6))
        tk.Label(
            xyrow, text="Y:", bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 10), width=2
        ).pack(side="left")
        self._fv_y = tk.StringVar(value="0")
        self._fv_y_entry = tk.Entry(
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
        )
        self._fv_y_entry.pack(side="left", ipady=4)
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
            tr("focus.field.cost", "Cost (1 = 7 days):"),
            "10",
            store_as="_fv_cost_entry",
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
        offsets = getattr(f, "offsets", []) if f else []
        sig = (
            getattr(f, "id", None),
            tuple((o.get("x"), o.get("y"), o.get("trigger")) for o in offsets),
        )
        if MOD.sidebar_refresh_skip and getattr(self, "_offsets_sig", None) == sig:
            return
        self._offsets_sig = sig
        for w in self._offset_box.winfo_children():
            w.destroy()
        self._offset_entries = []
        if not f:
            return
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
        self._push_undo("add offset", touched_ids=(self.selected.id,))
        self._save_offsets_to_focus()
        self.selected.offsets.append({"x": 0, "y": 0, "trigger": ""})
        self._refresh_offsets(self.selected)

    def _del_offset(self, idx):
        """Remove offset at idx from the selected focus and refresh UI."""
        if not self.selected:
            return
        self._push_undo("remove offset", touched_ids=(self.selected.id,))
        self._save_offsets_to_focus()
        offs = getattr(self.selected, "offsets", [])
        if 0 <= idx < len(offs):
            offs.pop(idx)
        self._refresh_offsets(self.selected)

    def _read_offsets_from_form(self):
        """Read current offset UI widgets as a plain list of dicts."""
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
        return offs

    def _save_offsets_to_focus(self):
        """Read current offset UI widgets and save to self.selected.offsets."""
        if not self.selected:
            return
        self.selected.offsets = self._read_offsets_from_form()

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

    def _sb_entry(self, label, default, store_as=None):
        f = tk.Frame(self._sb_frm, bg=BG_PANEL)
        f.pack(fill="x", padx=8, pady=2)
        tk.Label(
            f, text=label, bg=BG_PANEL, fg=TEXT_DIM, font=("Helvetica", 9), anchor="w"
        ).pack(fill="x")
        var = tk.StringVar(value=default)
        entry = tk.Entry(
            f,
            textvariable=var,
            bg=BG_CARD,
            fg=TEXT,
            insertbackground=BLUE,
            font=("Helvetica", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
        )
        entry.pack(fill="x", ipady=3)
        if store_as:
            setattr(self, store_as, entry)
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
            command=lambda: open_focus_icon_browser(
                self, self._set_gfx, self._fv_gfx.get()
            ),
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
            self._redraw_now()

    def _update_gfx_preview(self, gfx_name):
        """No sidebar preview — just invalidate canvas so icon redraws."""
        if self.selected and getattr(self.selected, "gfx", "") != gfx_name:
            self.selected.gfx = gfx_name
            self._redraw_now()

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
                lambda: (
                    _popup[0].destroy()
                    if _popup[0] and _popup[0].winfo_exists()
                    else None
                ),
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
        self._redraw_now()

    def _read_sidebar_values(self):
        """Snapshot sidebar widgets into FocusSidebarValues.

        Returns None when the name field is empty so autosave cannot blank an
        existing focus id on a half-cleared form.

        Numeric fields (cost, x, y) are coerced individually with per-field
        fallbacks to the current focus value when parsing fails, so a single
        invalid entry does not silently drop the other edits.
        """
        raw = self._fv_name.get().strip()
        if not raw:
            return None
        raw_ai = self._fv_ai_raw.get("1.0", "end").strip()

        # Parse numeric fields individually; on failure, fall back to the
        # current focus value so other edits are not silently dropped.
        f = self.selected
        cost, cost_err = self._coerce_numeric(
            self._fv_cost, parse_focus_cost, f.cost if f else 0, "cost"
        )
        x, x_err = self._coerce_numeric(self._fv_x, int, f.x if f else 0, "x")
        y, y_err = self._coerce_numeric(self._fv_y, int, f.y if f else 0, "y")
        self._set_field_error("_fv_cost_entry", cost_err)
        self._set_field_error("_fv_x_entry", x_err)
        self._set_field_error("_fv_y_entry", y_err)

        return FocusSidebarValues(
            name=re.sub(r"[^A-Za-z0-9_]", "_", raw),
            icon=self._fv_icon.get(),
            gfx=self._fv_gfx.get().strip() or "GFX_goal_generic_political_pressure",
            cost=cost,
            ai_will_do=parse_ai_will_do(raw_ai),
            ai_will_do_raw=raw_ai,
            x=x,
            y=y,
            desc=self._fv_desc.get("1.0", "end").strip(),
            search_filters=self._fv_search.get().strip() or "FOCUS_FILTER_POLITICAL",
            available_cond=self._fv_avail.get("1.0", "end").strip(),
            bypass_cond=self._fv_bypass.get("1.0", "end").strip(),
            cancel_cond=self._fv_cancel2.get("1.0", "end").strip(),
            cancel_if_invalid=self._fv_cancel.get(),
            continue_if_invalid=self._fv_continue.get(),
            available_if_capitulated=self._fv_cap.get(),
            offsets=tuple(self._read_offsets_from_form()),
        )

    def _coerce_numeric(self, var, parser, fallback, field_name):
        """Parse a numeric sidebar field with per-field fallback.

        Returns (value, has_error). On parse failure, returns fallback
        and marks the field with an inline error indicator.
        """
        try:
            return parser(var.get()), False
        except ValueError, TypeError:
            self._log_error(
                f"Invalid {field_name} value {var.get()!r}; using fallback {fallback}"
            )
            return fallback, True

    def _set_field_error(self, entry_attr, has_error):
        """Toggle the highlight colour of a sidebar entry widget."""
        entry = getattr(self, entry_attr, None)
        if entry is None:
            return
        entry.config(highlightbackground=RED if has_error else BORDER_G)

    def _autosave(self):
        if not self.selected:
            return
        f = self.selected
        try:
            values = self._read_sidebar_values()
            if values is None:
                return
            # Refuse occupied cells the same way canvas drag does: keep the live
            # coordinates and still flush every other field the form changed.
            if (values.x, values.y) != (f.x, f.y) and not self.focuses.position_free(
                values.x, values.y, except_id=f.id
            ):
                log.warning(
                    "Autosave kept position for %s: (%s, %s) is occupied",
                    f.name,
                    values.x,
                    values.y,
                )
                values = FocusSidebarValues(**{**values.__dict__, "x": f.x, "y": f.y})
            # Pure select-away with an untouched form must not rebuild indexes.
            if sidebar_values_match_focus(f, values):
                return
            name_changed = apply_sidebar_values(f, values)
            self.focuses.move(f.id, values.x, values.y)
            # name is the only autosave field that still needs a full index rebuild;
            # x/y already go through move()'s incremental occupied_positions patch.
            if name_changed:
                self.focuses.touch()
        except Exception as ex:
            log.exception("Autosave failed")
            self._log_error(
                f"Autosave failed for focus {getattr(f, 'name', '?')}: {ex}"
            )

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
            apply_focus_code(
                f,
                new_code,
                focus_lookup=self.focuses,
            )
            self.focuses.touch()
            self._invalidate_focus_list_structure()
            if self.selected and self.selected.id == f.id:
                self._populate(f)

            _saved_zoom = self.zoom
            _saved_offset = self.offset[:]
            self._redraw()

            def _restore_vp():
                self.zoom = _saved_zoom
                self.offset[0] = _saved_offset[0]
                self.offset[1] = _saved_offset[1]
                self._redraw_now()

            self.cv.after(30, _restore_vp)
            return True
        except Exception as ex:
            report_error(
                tr(
                    "dialog.parse_error.body",
                    "Could not parse your edits:\n{error}\n\nCheck Error Log for details.",
                    error=ex,
                ),
                ex,
                title=tr("dialog.parse_error.title", "Parse Error"),
            )
            return False

    def _build_focus_code(self, f):
        """Render a single focus block as HOI4 script (used by Code tab)."""
        return render_focus_block(
            f,
            focus_lookup=self.focuses,
            focus_name_lookup=self.focuses.by_name,
        )

    def _ref_name(self, fid):
        """Display name for a referenced focus id, or ?id while unresolved."""
        return self.focuses[fid].name if fid in self.focuses else f"?{fid}"

    def _refresh_prereqs(self):
        groups = self.selected.prereqs if self.selected else []
        sig = (
            getattr(self.selected, "id", None),
            tuple(tuple(self._ref_name(p) for p in g) for g in groups),
        )
        if MOD.sidebar_refresh_skip and getattr(self, "_prereqs_sig", None) == sig:
            return
        self._prereqs_sig = sig
        for w in self._prereq_box.winfo_children():
            w.destroy()
        if not groups:
            tk.Label(
                self._prereq_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Helvetica", 9, "italic"),
            ).pack(anchor="w")
            return
        for gi, grp in enumerate(self.selected.prereqs):
            names = [self._ref_name(p) for p in grp]
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
        mutex = self.selected.mutex if self.selected else []
        sig = (
            getattr(self.selected, "id", None),
            tuple(self._ref_name(m) for m in mutex),
        )
        if MOD.sidebar_refresh_skip and getattr(self, "_mutex_sig", None) == sig:
            return
        self._mutex_sig = sig
        for w in self._mutex_box.winfo_children():
            w.destroy()
        if not mutex:
            tk.Label(
                self._mutex_box,
                text=tr("common.none", "None"),
                bg=BG_PANEL,
                fg=TEXT_DIM,
                font=("Georgia", 9, "italic"),
            ).pack(anchor="w")
            return
        for i, mid in enumerate(self.selected.mutex):
            name = self._ref_name(mid)
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
        dirty = (
            " *"
            if getattr(self, "_saved_fingerprint", None) is not None
            and self._is_dirty()
            else ""
        )
        self.title(
            tr(
                "app.title.tree",
                "HOI4 Content Maker  -  {tree}{dirty}  [Wiki Accurate v2]",
                tree=tid,
                dirty=dirty,
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

            if self._is_dirty() or self.focuses:
                if self._is_dirty():
                    ans = messagebox.askyesnocancel(
                        tr("dialog.unsaved_changes.title", "Unsaved Changes"),
                        tr(
                            "dialog.unsaved_changes.new_tree_body",
                            "You have unsaved changes.\n\nSave before starting a new tree?",
                        ),
                        parent=win,
                    )
                    if ans is None:
                        return
                    if ans and not self._save():
                        return
                self.cv.delete("all")
                self.focuses.clear()
                self.selected = None
                self._lines.clear()
                self._grid_item = None
                self._grid_key = None
                self._grid_img = None
                self._hide_form()
                self._redraw_now()
                self._invalidate_focus_list_structure()

            self._begin_document_generation()

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
        self.focuses.validate_indexes(rebuild=True)
        occ = self.focuses.occupied_positions
        gx, gy = 0, 0
        while (gx, gy) in occ:
            gx += 2  # HOI4 standard: focuses placed at even columns
            if gx > 14:
                gx = 0
                gy += 1
        self._new_focus_at(gx, gy)

    def _new_focus_at(self, wx, wy):
        self._push_undo("add focus", touched_ids=())
        f = Focus(wx, wy)
        pfx = self._default_focus_prefix
        if pfx:
            f.name = pfx + "focus_%d" % f.id
        self.focuses.add(f)
        self._redraw()
        self._select(f)
        self._invalidate_focus_list_structure()

    def _apply(self):
        if not self.selected:
            return
        f = self.selected
        values = self._read_sidebar_values()
        if values is None:
            messagebox.showerror(
                tr("dialog.error.title", "Error"),
                tr("dialog.focus_id_empty", "Focus ID cannot be empty."),
            )
            return
        if (values.x, values.y) != (f.x, f.y) and not self.focuses.position_free(
            values.x, values.y, except_id=f.id
        ):
            messagebox.showwarning(
                tr("dialog.position.title", "Position"),
                tr(
                    "dialog.position_occupied",
                    "Another focus already occupies that grid position.",
                ),
            )
            return
        if sidebar_values_match_focus(f, values):
            return
        self._push_undo("edit focus", touched_ids=(f.id,))
        name_changed = apply_sidebar_values(f, values)
        if not self.focuses.move(f.id, values.x, values.y):
            # Pre-checked; if indexes raced, restore name indexes at least.
            self.focuses.touch()
            messagebox.showwarning(
                tr("dialog.position.title", "Position"),
                tr(
                    "dialog.position_occupied",
                    "Another focus already occupies that grid position.",
                ),
            )
            self._redraw()
            self._populate(f)
            return
        if name_changed:
            self.focuses.touch()
        self._redraw()
        self._populate(f)
        self._invalidate_focus_list_structure()

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
        del_ids = {fid for fid in self._multi_sel if fid in self.focuses}
        touched_ids = (
            del_ids
            | set().union(
                *(self.focuses.reverse_prerequisites.get(fid, set()) for fid in del_ids)
            )
            | set().union(
                *(self.focuses.reverse_mutex.get(fid, set()) for fid in del_ids)
            )
        )
        self._push_undo("delete selected", touched_ids=touched_ids)
        for fid in del_ids:
            self.cv.delete("F" + str(fid))
        self.focuses.delete_many(del_ids)
        self._multi_sel.clear()
        if self.selected and self.selected.id not in self.focuses:
            self.selected = None
            self._hide_form()
        self._redraw()
        self._invalidate_focus_list_structure()
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
        fid = self.selected.id
        touched_ids = {fid}
        touched_ids.update(self.focuses.reverse_prerequisites.get(fid, ()))
        touched_ids.update(self.focuses.reverse_mutex.get(fid, ()))
        self._push_undo("delete focus", touched_ids=touched_ids)
        self.cv.delete("F" + str(fid))
        self.focuses.delete_many((fid,))
        self.selected = None
        self._hide_form()
        self._redraw()
        self._invalidate_focus_list_structure()

    def _clear_all(self):
        if not messagebox.askyesno(
            tr("dialog.clear_all.title", "Clear All"),
            tr("dialog.clear_all.body", "Delete ALL focuses?"),
        ):
            return
        self._push_undo("clear all")
        self._begin_document_generation()
        self.cv.delete("all")
        self._focus_bundles.clear()
        self.focuses.clear()
        self._reset_canvas_bounds()
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._extra_trees.clear()
        self._invalidate_tree_badges()
        self._shared_focuses.clear()
        self._joint_focuses.clear()
        self._refresh_loaded_trees_panel()
        self._refresh_tree_meta_panel()
        self._hide_form()
        self._draw_grid()
        self._invalidate_focus_list_structure()

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
            lambda e: (
                se.delete(0, "end")
                if se.get()
                == tr("focus.prereq.filter_placeholder", "Filter focuses...")
                else None
            ),
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

        sorted_cands = sorted(candidates, key=lambda f: f.name.lower())
        items = []
        for f in sorted_cands:
            t_idx = getattr(f, "tree_idx", 0)
            tree_badge = ""
            if t_idx > 0:
                _bt, _ = self._get_tree_badge(t_idx)
                tree_badge = f" [{_bt}]"
            items.append(FocusListItem(f.id, f"  {f.name}{tree_badge}"))

        placeholder = tr("focus.prereq.filter_placeholder", "Filter focuses...")

        def _update_counter(*_):
            n = len(focus_list.selected_keys)
            _counter_var.set(
                tr("common.selected_count", "{count} selected", count=n)
            )

        focus_list = VirtualFocusList(
            frm,
            on_select=lambda _key: _update_counter(),
            on_activate=lambda _key: _confirm_or(),
            multi_select=True,
            background=BG_PANEL,
        )
        focus_list.pack(fill="both", expand=True)
        focus_list.invalidate_structure(items, placeholder=placeholder)

        def _on_filter(*_):
            q = sv.get()
            if q == placeholder:
                q = ""
            focus_list.invalidate_structure(items, query=q, placeholder=placeholder)
            _update_counter()

        sv.trace_add("write", _on_filter)

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
            group = list(focus_list.selected_keys)
            if not group:
                messagebox.showwarning(
                    tr("dialog.no_selection.title", "No Selection"),
                    tr(
                        "dialog.select_at_least_one_focus", "Select at least one focus."
                    ),
                    parent=win,
                )
                return
            self._push_undo("add prerequisite OR group", touched_ids=(child.id,))
            self.focuses.link_prerequisite(child.id, group, mode="or")
            self._refresh_prereqs()
            self._draw_lines()
            win.destroy()

        def _confirm_and():
            fids = list(focus_list.selected_keys)
            if not fids:
                messagebox.showwarning(
                    tr("dialog.no_selection.title", "No Selection"),
                    tr(
                        "dialog.select_at_least_one_focus", "Select at least one focus."
                    ),
                    parent=win,
                )
                return
            self._push_undo("add prerequisite AND group", touched_ids=(child.id,))
            self.focuses.link_prerequisite(child.id, fids, mode="and")
            self._refresh_prereqs()
            self._draw_lines()
            win.destroy()

        def _ctrl_a(e):
            focus_list.select_all()
            _update_counter()
            return "break"

        win.bind("<Control-a>", _ctrl_a)
        win.bind("<Control-A>", _ctrl_a)
        focus_list.canvas.bind("<Control-a>", _ctrl_a)
        focus_list.canvas.bind("<Control-A>", _ctrl_a)
        win.bind("<Return>", lambda e: _confirm_or())
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
        self._push_undo("add prerequisite", touched_ids=(child.id,))
        self.focuses.link_prerequisite(child.id, (parent.id,))
        self._redraw()
        if self.selected:
            self._refresh_prereqs()

    def _rm_prereq(self, gi):
        if not self.selected:
            return
        child_id = self.selected.id
        self._push_undo("remove prerequisite group", touched_ids=(child_id,))
        self.focuses.unlink_prerequisite_group(self.selected.id, gi)
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
        self._push_undo("add mutex", touched_ids=(a.id, b.id))
        self.focuses.link_mutex(a.id, b.id)
        self._redraw()
        if self.selected:
            self._refresh_mutex()

    def _rm_mutex(self, idx):
        if not self.selected:
            return
        mid = self.selected.mutex[idx]
        self._push_undo("remove mutex", touched_ids=(self.selected.id, mid))
        self.focuses.unlink_mutex(self.selected.id, mid)
        self._refresh_mutex()
        self._draw_lines()

    # ── EFFECT LIVE UPDATES ─────────────────────────────────────
    def _add_effect(self):
        # Legacy entry point — effects are now added via the browser popup.
        self._open_effect_browser()

    # ── IMPORT .TXT ─────────────────────────────────────────────

    def _import_drawio(self):
        """Import a Draw.io file as a HOI4 focus tree skeleton."""
        import xml.etree.ElementTree as ET

        path = filedialog.askopenfilename(
            filetypes=[
                ("Draw.io / XML", "*.xml *.drawio"),
                ("All files", "*.*"),
            ],
            title=tr("filedialog.import_drawio", "Import Draw.io Diagram"),
        )
        if not path:
            return
        self._begin_document_generation()

        try:
            # Untrusted file: cap the raw read so a giant .drawio can't
            # exhaust memory before parsing.
            if os.path.getsize(path) > 64 * 1024 * 1024:
                raise ValueError("file exceeds 64 MB")
            with open(path, encoding="utf-8", errors="replace") as fp:
                raw_file = fp.read()
        except Exception as e:
            report_error(
                tr(
                    "dialog.drawio_read_error", "Could not read file:\n{error}", error=e
                ),
                e,
                title=tr("dialog.drawio_import.title", "Draw.io Import"),
            )
            return

        # parse_drawio_graph guards against decompression bombs and XML
        # entity-expansion (billion laughs) in shared .drawio files via
        # bounded_inflate/safe_fromstring, and raises EmptyDrawioGraphError
        # when the diagram has no usable shapes. It's the one potentially
        # slow step (decompress + XML walk + clustering), so it runs on a
        # worker thread; steps 3+ (all dialogs) continue in on_done.
        def work():
            return parse_drawio_graph(raw_file)

        def on_error(exc):
            if isinstance(exc, EmptyDrawioGraphError):
                messagebox.showwarning(
                    tr("dialog.drawio_import.title", "Draw.io Import"),
                    tr(
                        "dialog.drawio_no_shapes",
                        "No shapes found in the diagram.\n\nMake sure your shapes have labels and are saved as XML.",
                    ),
                )
            elif isinstance(exc, (ET.ParseError, ValueError)):
                messagebox.showerror(
                    tr("dialog.drawio_import.title", "Draw.io Import"),
                    tr(
                        "dialog.drawio_parse_error",
                        "Could not parse XML:\n{error}\n\nExport as Editable Vector XML from Draw.io.",
                        error=exc,
                    ),
                )
            # else: unexpected error, already recorded in the in-app error
            # log by run_bg.

        def on_done(graph):
            self._import_drawio_continue(graph, path)

        run_bg(self, work, on_done, on_error=on_error, scope="document")

    def _import_drawio_continue(self, graph, path):
        """Collect import settings, preview the tree, and add its focuses."""
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
                focuses=len(graph.vertices),
                arrows=len(graph.edges),
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
                    f"\n\t# {len(graph.vertices)} focuses imported from Draw.io\n}}"
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

        drawio_result = drawio_to_focus_data(graph, prefix)
        label_by_cid = {df.cid: df.label for df in drawio_result.focuses}

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
                count=len(drawio_result.focuses),
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

        lst.insert("end", f"FOCUSES  ({len(drawio_result.focuses)})\n", "hdr")
        lst.insert("end", "─" * 64 + "\n", "dim")
        for df in drawio_result.focuses:
            lst.insert("end", f"  {df.label:<36}", "focus")
            lst.insert("end", f"  x={df.x:2d}  y={df.y:2d}\n", "dim")

        if drawio_result.edges:
            lst.insert("end", f"\nPREREQUISITES  ({len(drawio_result.edges)})\n", "hdr")
            lst.insert("end", "─" * 64 + "\n", "dim")
            for src, tgt in drawio_result.edges:
                lst.insert("end", f"  {label_by_cid[src]}", "focus")
                lst.insert("end", "  ──►  ", "dim")
                lst.insert("end", f"{label_by_cid[tgt]}\n", "arrow")
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

        # drawio_result.focuses is already sorted top-to-bottom, left-to-right
        # (visual reading order) by drawio_to_focus_data.

        # Build prereq map: tgt_cid -> [src_cid, ...]
        prereq_map = {}
        for src_cid, tgt_cid in drawio_result.edges:
            prereq_map.setdefault(tgt_cid, []).append(src_cid)

        for df in drawio_result.focuses:
            gx, gy = df.x, df.y
            fid = df.label
            prereqs = prereq_map.get(df.cid, [])
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
                        f"\t\tprerequisite = {{ focus = {label_by_cid[src_cid]} }}"
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
            code_lines.append("\t\t\tbase = 1")
            code_lines.append("\t\t}")
            code_lines.append("\t}")
            code_lines.append("")

        code_lines.append("}")

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
        # Whole tree is replaced — full snapshot, not worth bounding the
        # touched set for a rare bulk import.
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

        # Build Focus objects (sorted by visual order) and wire prerequisites.
        new_focuses = build_drawio_focuses(drawio_result)
        self.focuses.load(new_focuses)

        self._redraw()
        self._invalidate_focus_list_structure()
        auto_shifted = drawio_result.auto_shifted
        shift_note = (
            tr(
                "drawio.imported.auto_shift_note",
                "  -  {count} auto-shifted to avoid overlap",
                count=len(auto_shifted),
            )
            if auto_shifted
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
        if auto_shifted:
            detail = "\n".join(
                f"  • {lbl}  ({ox},{oy}) → ({nx},{ny})"
                for lbl, ox, oy, nx, ny in auto_shifted[:12]
            )
            if len(auto_shifted) > 12:
                detail += "\n" + tr(
                    "drawio.auto_shift.more",
                    "  ... and {count} more",
                    count=len(auto_shifted) - 12,
                )
            messagebox.showinfo(
                tr("drawio.auto_shift.title", "Auto-Shift Notice"),
                tr(
                    "drawio.auto_shift.body",
                    "{count} focus(es) were automatically moved to\navoid overlapping another focus:\n\n{detail}\n\nYou can drag them to better positions on the canvas.",
                    count=len(auto_shifted),
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
            report_error(
                tr("dialog.read_file_error", "Could not read file:\n{error}", error=e),
                e,
                title=tr("dialog.import_error.title", "Import Error"),
            )
            return

        self._begin_document_generation()

        # Auto-set the edit target so Export writes back to this file in place
        MOD.edit_focus_file = path
        # If mod is loaded, also try to auto-detect the matching localisation file
        if MOD.loaded and MOD.root:
            _loc_path = detect_loc_file(
                MOD.root, raw, language=MOD.loc_language
            )
            if _loc_path:
                MOD.edit_loc_file = _loc_path

        import_generation = getattr(self, "_import_generation", 0) + 1
        self._import_generation = import_generation
        modal = progress_modal(
            self, tr("dialog.import.title", "Import"), determinate=False
        )

        # Parse + build are the expensive, pure-CPU steps (no Tk, no self) —
        # they run on a worker thread; everything that touches MOD/toolbar
        # vars/panels/canvas below stays in on_done, on the Tk thread.
        def work():
            t0 = time.perf_counter()
            parsed = parse_focus_tree(raw, path)
            t1 = time.perf_counter()
            # country_tag intentionally omitted: applying original_tag-matching
            # offsets would shift the main tree's x/y, but the monolith's own
            # _export writes f.x/f.y (not _raw_gx/_raw_gy) as the base position
            # and also re-emits the offset block, so the shift would double up
            # on export. Extra (shared/joint) trees go through
            # focus_tree/export.py, which does use _raw_gx/_raw_gy, so offsets
            # stay safe there.
            new_focuses = build_focuses(parsed, 0)
            t2 = time.perf_counter()
            log.debug(
                "import main tree %s: parse %.1fms build %.1fms (%d focuses)",
                path,
                (t1 - t0) * 1000,
                (t2 - t1) * 1000,
                len(new_focuses),
            )
            return parsed, new_focuses

        def on_done(result):
            modal.close()
            if import_generation != self._import_generation:
                return
            parsed, new_focuses = result

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
            self._invalidate_tree_badges()
            self._refresh_loaded_trees_panel()
            self._hide_form()
            self._tree_id.set(parsed.tree_id)
            self._update_title()
            # tag detection happens AFTER all focuses are loaded (see below)

            # Reset per-import metadata so values don't carry over from a
            # prior load
            self._cfp_x = parsed.cfp_x
            self._cfp_y = parsed.cfp_y
            self._cfp_x_var.set("" if self._cfp_x is None else str(self._cfp_x))
            self._cfp_y_var.set("" if self._cfp_y is None else str(self._cfp_y))
            self._tree_country_raw = parsed.country_raw
            self._tree_extras = parsed.tree_extras
            self._tree_had_wrapper = parsed.had_wrapper
            self._shared_focuses = parsed.shared_refs
            self._joint_focuses = parsed.joint_refs
            # Only overwrite the country tag when one was actually detected in
            # the country block, matching the old behaviour of leaving a
            # prior tag alone.
            if parsed.country_tag and parsed.country_tag != "TAG":
                self._tree_country_tag = parsed.country_tag

            self.focuses.load(new_focuses)

            self._detect_and_apply_tag()  # scan IDs now all focuses are loaded
            # If explicit tag was read from original_tag, ensure prefix is
            # set correctly
            if not self._default_focus_prefix and getattr(
                self, "_tree_country_tag", ""
            ):
                self._default_focus_prefix = self._tree_country_tag + "_"
            self._refresh_tree_meta_panel()
            self._redraw()
            self._invalidate_focus_list_structure()
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
                    tree=parsed.tree_id,
                    shared=_sf_info,
                    joint=_jf_info,
                ),
            )

        def on_error(exc):
            modal.close()
            if import_generation != self._import_generation:
                return
            if isinstance(exc, EmptyFocusTreeError):
                messagebox.showwarning(tr("dialog.import.title", "Import"), str(exc))
            # else: unexpected error, already recorded in the in-app error
            # log by run_bg.

        run_bg(self, work, on_done, on_error=on_error, scope="document")

    # ── MULTI-TREE HELPERS ───────────────────────────────────────

    def _invalidate_tree_badges(self):
        """Drop the cached badge table after _extra_trees changes shape."""
        self._tree_badge_table = None

    def _get_tree_badge(self, tree_idx):
        """Return (badge_text, color) for a given tree_idx. Returns ('', FC_BORDER) for main tree.

        The canvas asks once per visible focus per redraw (plus once per
        minimap dot and legend row), so the whole table is built once per
        change to _extra_trees instead of counting same-typed trees per call.
        The length check is a backstop for a mutation site that forgot to call
        _invalidate_tree_badges.
        """
        extra_trees = getattr(self, "_extra_trees", [])
        if tree_idx <= 0 or tree_idx > len(extra_trees):
            return "", FC_BORDER
        table = getattr(self, "_tree_badge_table", None)
        if table is None or len(table) != len(extra_trees):
            table = build_tree_badges(extra_trees)
            self._tree_badge_table = table
        return table[tree_idx - 1]

    def _install_extra_tree(self, parsed, new_focuses, path, tree_type):
        """Register a parsed extra tree and adopt its focuses. Tk-thread only."""
        tree_info = {
            "type": tree_type,
            "file_path": path,
            "tree_id": parsed.tree_id,
            "cfp_x": parsed.cfp_x,
            "cfp_y": parsed.cfp_y,
            "shared_focuses": parsed.shared_refs,
            "joint_focuses": parsed.joint_refs,
            "country_tag": parsed.country_tag,
            "country_raw": parsed.country_raw,
            "tree_extras": parsed.tree_extras,
            "had_wrapper": parsed.had_wrapper,
            "focus_ids": set(),
        }
        self._extra_trees.append(tree_info)
        self._invalidate_tree_badges()
        if tree_type == "shared" and parsed.tree_id not in self._shared_focuses:
            self._shared_focuses.append(parsed.tree_id)
        elif tree_type == "joint" and parsed.tree_id not in self._joint_focuses:
            self._joint_focuses.append(parsed.tree_id)
        self._refresh_tree_meta_panel()
        self.focuses.extend(new_focuses)
        for f in new_focuses:
            tree_info["focus_ids"].add(f.id)
        self._refresh_loaded_trees_panel()
        self._redraw()
        self._invalidate_focus_list_structure()
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
            report_error(
                tr("dialog.read_file_error", "Could not read file:\n{error}", error=e),
                e,
                title=tr("dialog.load_error.title", "Load Error"),
            )
            return
        tree_idx = len(self._extra_trees) + 1
        existing_focuses = list(self.focuses.values())
        country_tag = getattr(self, "_tree_country_tag", "")
        modal = progress_modal(
            self, tr("dialog.load_tree.title", "Load Tree"), determinate=False
        )

        def work():
            t0 = time.perf_counter()
            parsed = parse_focus_tree(raw, path)
            t1 = time.perf_counter()
            new_focuses = build_focuses(
                parsed,
                tree_idx,
                country_tag=country_tag,
                existing_focuses=existing_focuses,
            )
            t2 = time.perf_counter()
            log.debug(
                "install tree %s: parse %.1fms build %.1fms (%d focuses)",
                path,
                (t1 - t0) * 1000,
                (t2 - t1) * 1000,
                len(new_focuses),
            )
            return parsed, new_focuses

        def on_done(result):
            modal.close()
            parsed, new_focuses = result
            count, tree_id = self._install_extra_tree(
                parsed, new_focuses, path, tree_type
            )
            messagebox.showinfo(
                tr("dialog.loaded.title", "Loaded"),
                tr(
                    "dialog.extra_tree_loaded.body",
                    "Loaded {count} focuses from {type} tree:\n"
                    "{file}\n\nTree ID: {tree}",
                    count=count,
                    type=tree_type,
                    file=os.path.basename(path),
                    tree=tree_id,
                ),
            )

        def on_error(exc):
            modal.close()
            if isinstance(exc, EmptyFocusTreeError):
                messagebox.showwarning(
                    tr("dialog.load_tree.title", "Load Tree"), str(exc)
                )

        run_bg(self, work, on_done, on_error=on_error, scope="document")

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
                self.cv.delete("F" + str(fid))
        self.focuses.delete_many(info["focus_ids"], clean_references=False)
        self.cv.delete("line")
        self._lines.clear()
        self._lines_used = 0
        if self.selected and self.selected.id not in self.focuses:
            self.selected = None
            self._hide_form()
        # Remove from list; re-index tree_idx on focuses belonging to later trees
        self._extra_trees.pop(tree_idx - 1)
        self._invalidate_tree_badges()
        tree_updates = {}
        for new_idx, et in enumerate(self._extra_trees, start=1):
            if new_idx >= tree_idx:
                for fid in et["focus_ids"]:
                    if fid in self.focuses:
                        tree_updates[fid] = new_idx
        self.focuses.set_trees(tree_updates)
        self._refresh_tree_meta_panel()
        self._refresh_loaded_trees_panel()
        self._redraw()
        self._invalidate_focus_list_structure()

    def _refresh_loaded_trees_panel(self):
        """Rebuild the Loaded Trees panel list in the sidebar."""
        if not hasattr(self, "_loaded_trees_inner"):
            return
        if self._extra_trees:
            self._loaded_trees_empty.pack_forget()
            self._loaded_trees_box.pack(fill="x", before=self._loaded_trees_border)
        else:
            self._loaded_trees_box.pack_forget()
            self._loaded_trees_empty.pack(fill="x", padx=4, pady=2)
        items = []
        for idx, et in enumerate(self._extra_trees, start=1):
            badge_txt, badge_col = self._get_tree_badge(idx)
            items.append(
                LoadedTreeRowItem(
                    tree_idx=idx,
                    badge_text=badge_txt,
                    badge_color=badge_col,
                    tree_id=et["tree_id"],
                    summary=tr(
                        "sidebar.loaded_tree_summary",
                        "  {file}  -  {count} focuses",
                        file=os.path.basename(et["file_path"]),
                        count=len(et["focus_ids"]),
                    ),
                )
            )
        self._loaded_trees_inner.set_items(items)

    def _export_extra_tree(
        self,
        tree_idx,
        *,
        focuses_in_tree=None,
        focus_name_lookup=None,
        show_dialog=True,
    ):
        """Export a single extra (shared/joint) tree to its source file."""
        if focuses_in_tree is None:
            focuses_in_tree = [
                focus
                for focus in self.focuses.values()
                if getattr(focus, "tree_idx", 0) == tree_idx
            ]
        plan = self._make_extra_export_plan(
            tree_idx,
            focuses_in_tree,
            dict(self.focuses),
            focus_name_lookup or build_focus_name_lookup(self.focuses.values()),
            show_dialog=show_dialog,
        )
        if plan is None:
            return None

        def on_done(results):
            failures = self._apply_export_results(
                results,
                title=tr("dialog.export.title", "Export"),
            )
            if failures:
                return
            if show_dialog:
                info = self._extra_trees[tree_idx - 1]
                messagebox.showinfo(
                    tr("dialog.saved.title", "Saved"),
                    tr(
                        "dialog.extra_tree_saved",
                        "{type} tree saved:\n{file}",
                        type=info["type"].capitalize(),
                        file=os.path.basename(plan.focus_path),
                    ),
                )

        return self._run_export_plans(
            [plan],
            on_done,
            title=tr("dialog.export.title", "Export"),
        )

    def _batch_load_trees_worker(
        self,
        to_load,
        existing_seed,
        extra_trees_start_idx,
        country_tag,
        progress,
        cancelled=None,
    ):
        """Parse and build selected trees sequentially on a worker thread."""
        return batch_load_trees(
            to_load,
            existing_seed,
            extra_trees_start_idx,
            country_tag,
            progress,
            cancelled=cancelled,
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

        # Scrollable checklist. Rows are pooled and recycled (ui/checklist.py),
        # so ~790 candidate files cost ~2 dozen widget rows, not ~5,500.
        frm = tk.Frame(win, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=10, pady=4)

        rows = []
        for fp in all_files:
            fname = os.path.basename(fp)
            already = os.path.normpath(fp) in loaded_paths
            # Default type based on filename prefix convention
            def_type = default_tree_type(fname)
            rows.append(
                ChecklistItem(
                    key=fp,
                    name=fname,
                    already=already,
                    checked=tk.BooleanVar(value=(not already and def_type != "main")),
                    type_var=tk.StringVar(value=def_type),
                )
            )

        checklist = VirtualChecklist(
            frm,
            type_choices=[
                (tr("load_all.type.main", "Main"), "main", TEXT_DIM),
                (tr("load_all.type.shared", "Shared"), "shared", "#f59e0b"),
                (tr("load_all.type.joint", "Joint"), "joint", "#a855f7"),
            ],
            loaded_marker=tr("load_all.loaded_marker", " (loaded)"),
        )
        checklist.pack(fill="both", expand=True)
        checklist.set_items(rows)

        ctrl = tk.Frame(win, bg=BG_DARK)
        ctrl.pack(fill="x", padx=10, pady=(2, 0))
        for lbl, mode in [
            (tr("load_all.select_all_extra", "All Shared+Joint"), "all"),
            (tr("common.none", "None"), "none"),
            (tr("load_all.shared_only", "Shared only"), "shared"),
            (tr("load_all.joint_only", "Joint only"), "joint"),
        ]:
            tk.Button(
                ctrl,
                text=lbl,
                command=lambda m=mode: apply_select_mode(rows, m),
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
                (item.key, item.type_var.get()) for item in rows if is_loadable(item)
            ]
            if not to_load:
                messagebox.showwarning(
                    tr("load_all.title", "Load All Trees"),
                    tr("load_all.no_files_selected", "No files selected to load."),
                    parent=win,
                )
                return
            win.destroy()
            self._begin_document_generation()

            # Snapshot the Tk-thread state the worker needs to resolve
            # cross-tree relative positions/prereqs. The worker must not
            # touch self.focuses/self._extra_trees directly (ui/tasks.py).
            existing_seed = list(self.focuses.values())
            extra_trees_start_idx = len(self._extra_trees)
            country_tag = getattr(self, "_tree_country_tag", "")

            modal = progress_modal(
                self, tr("load_all.title", "Load All Trees"), cancellable=True
            )

            def _update_progress(i, total, label):
                modal.set_text(
                    tr(
                        "mod.loading.step",
                        "Step {step}/{total}: {label}",
                        step=i,
                        total=total,
                        label=label,
                    )
                )
                modal.set_fraction(i / total if total else 1.0)

            progress = make_progress(self, _update_progress, scope="document")

            def work():
                return self._batch_load_trees_worker(
                    to_load,
                    existing_seed,
                    extra_trees_start_idx,
                    country_tag,
                    progress,
                    cancelled=modal.cancelled,
                )

            def on_done(payload):
                modal.close()
                results, was_cancelled = payload
                ok, fail = [], []
                pending_focuses = []
                for r in results:
                    fname = os.path.basename(r["path"])
                    if not r["ok"]:
                        fail.append(f"{fname}: {r['error']}")
                        continue
                    ok.append(fname)
                    parsed = r["parsed"]
                    tree_info = {
                        "type": r["type"],
                        "file_path": r["path"],
                        "tree_id": parsed.tree_id,
                        "cfp_x": parsed.cfp_x,
                        "cfp_y": parsed.cfp_y,
                        "shared_focuses": parsed.shared_refs,
                        "joint_focuses": parsed.joint_refs,
                        "country_tag": parsed.country_tag,
                        "country_raw": parsed.country_raw,
                        "tree_extras": parsed.tree_extras,
                        "had_wrapper": parsed.had_wrapper,
                        "focus_ids": set(),
                    }
                    self._extra_trees.append(tree_info)
                    self._invalidate_tree_badges()
                    if (
                        r["type"] == "shared"
                        and parsed.tree_id not in self._shared_focuses
                    ):
                        self._shared_focuses.append(parsed.tree_id)
                    elif (
                        r["type"] == "joint"
                        and parsed.tree_id not in self._joint_focuses
                    ):
                        self._joint_focuses.append(parsed.tree_id)
                    for f in r["new_focuses"]:
                        pending_focuses.append(f)
                        tree_info["focus_ids"].add(f.id)

                self.focuses.extend(pending_focuses)

                if ok:
                    self._refresh_tree_meta_panel()
                    self._refresh_loaded_trees_panel()
                    self._redraw()
                    self._invalidate_focus_list_structure()

                msg = (
                    tr(
                        "load_all.loaded_count",
                        "Loaded {count} file(s).",
                        count=len(ok),
                    )
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
                if was_cancelled:
                    msg += "\n\n" + tr(
                        "load_all.cancelled",
                        "Cancelled. Loaded files were kept.",
                    )
                messagebox.showinfo(tr("load_all.title", "Load All Trees"), msg)
                # Zoom to fit all focuses
                if ok:
                    self._fit_all()

            def on_error(exc):
                # _batch_load_trees_worker catches per-file errors internally,
                # so reaching here means something outside that loop broke.
                modal.close()
                messagebox.showerror(
                    tr("load_all.title", "Load All Trees"),
                    tr(
                        "load_all.batch_error",
                        "Loading failed unexpectedly:\n{error}",
                        error=exc,
                    ),
                )

            run_bg(self, work, on_done, on_error=on_error, scope="document")

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

    def _run_export_plans(self, plans, on_done, *, title):
        """Run pre-resolved export plans off the Tk thread with progress UI."""
        self._begin_document_generation()
        modal = progress_modal(self, title)

        def update_progress(index, total, label):
            modal.set_text(
                tr(
                    "mod.loading.step",
                    "Step {step}/{total}: {label}",
                    step=index,
                    total=total,
                    label=label,
                )
            )
            modal.set_fraction(index / total if total else 1.0)

        progress = make_progress(self, update_progress, scope="document")

        def work():
            return execute_export_plans(
                plans,
                WorkspaceFiles().write_texts,
                progress=progress,
            )

        def finish(results):
            modal.close()
            on_done(results)

        def on_error(error):
            modal.close()
            messagebox.showerror(title, f"Export failed unexpectedly:\n{error}")

        return run_bg(self, work, finish, on_error=on_error, scope="document")

    def _apply_export_results(self, results, *, title=None, show_errors=True):
        """Apply Tk-thread-only export side effects and report write failures."""
        failures = []
        for result in results:
            if not result.ok:
                failures.append(result)
                if show_errors:
                    report_write_failure(
                        self,
                        result.plan.focus_path,
                        result.error,
                        title=title,
                    )
                else:
                    add_error(f"Write failed: {result.plan.focus_path}: {result.error}")
                continue
            if result.plan.extra_tree_idx is not None:
                self._extra_trees[result.plan.extra_tree_idx - 1][
                    "file_path"
                ] = result.plan.focus_path
            if MOD.loaded and MOD.root:
                for path in result.written_paths:
                    MOD.note_file_written(path)
        return failures

    def _save_all_trees(self):
        """Export all loaded trees (main + extra) with one click."""
        self._autosave()
        focuses_by_tree = group_focuses_by_tree(self.focuses.values())
        focus_lookup = dict(self.focuses)
        focus_name_lookup = build_focus_name_lookup(self.focuses.values())
        plans = []
        main_plan = self._make_main_export_plan(
            focuses_by_tree.get(0, []),
            focus_lookup,
            focus_name_lookup,
            show_dialog=False,
        )
        if main_plan is not None:
            plans.append(main_plan)
        for idx in range(1, len(self._extra_trees) + 1):
            plan = self._make_extra_export_plan(
                idx,
                focuses_by_tree.get(idx, []),
                focus_lookup,
                focus_name_lookup,
                show_dialog=False,
            )
            if plan is not None:
                plans.append(plan)

        def on_done(results):
            failures = self._apply_export_results(results, show_errors=False)
            saved = [result.plan.label for result in results if result.ok]
            msg = tr("save_all.complete", "Save All Trees complete!") + "\n\n"
            if saved:
                msg += (
                    tr("save_all.saved_header", "Saved:")
                    + "\n"
                    + "\n".join(f"  • {label}" for label in saved)
                )
            if failures:
                msg += (
                    "\n\n"
                    + tr("save_all.errors_header", "Errors:")
                    + "\n"
                    + "\n".join(
                        f"  ✕ {result.plan.label}: {result.error}"
                        for result in failures
                    )
                )
            messagebox.showinfo(tr("save_all.title", "Save All Trees"), msg)

        if plans:
            self._run_export_plans(
                plans,
                on_done,
                title=tr("save_all.title", "Save All Trees"),
            )
        else:
            on_done([])

    def _make_main_export_plan(
        self, main_focuses, focus_lookup, focus_name_lookup, *, show_dialog
    ):
        """Resolve main-tree destinations and snapshot a plan on the Tk thread."""
        if not main_focuses:
            if show_dialog:
                messagebox.showwarning(
                    tr("dialog.export.title", "Export"),
                    tr(
                        "dialog.no_main_focuses_export",
                        "No main-tree focuses to export.\nUse 'Save All' or the Loaded Trees panel to export shared/joint trees.",
                    ),
                )
            return None
        tree_id = self._tree_id.get()
        tid = re.sub(r"[^A-Za-z0-9_]", "_", tree_id.strip()) or "TAG_focus_tree"
        tag_match = re.match(r"^([A-Z]{2,5})_", tid)
        country_tag = (
            tag_match.group(1)
            if tag_match
            else getattr(self, "_tree_country_tag", "TAG")
        )
        country_tag = sanitize_component(country_tag.upper(), fallback="TAG")
        cfp_x = getattr(self, "_cfp_x", None)
        cfp_y = getattr(self, "_cfp_y", None)
        try:
            cfp_x = int(self._cfp_x_var.get())
        except Exception:
            pass
        try:
            cfp_y = int(self._cfp_y_var.get())
        except Exception:
            pass
        default_filename = f"05_{country_tag}.txt"
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
            return None
        if MOD.edit_loc_file and os.path.isfile(MOD.edit_loc_file):
            loc_path = MOD.edit_loc_file
        else:
            loc_target = MOD.loc_target
            loc_filename = loc_target.filename(f"MD_focus_{country_tag}")
            saved_dir = os.path.dirname(os.path.abspath(path))
            mod_root = MOD.root if MOD.root and os.path.isdir(MOD.root) else None
            if mod_root is None:
                candidate = saved_dir
                for _ in range(5):
                    candidate = os.path.dirname(candidate)
                    if os.path.isdir(
                        os.path.join(candidate, "common")
                    ) and os.path.isdir(os.path.join(candidate, "localisation")):
                        mod_root = candidate
                        break
            if mod_root:
                loc_path = os.path.join(
                    mod_root, "localisation", loc_target.dirname(), loc_filename
                )
            else:
                loc_path = filedialog.asksaveasfilename(
                    defaultextension=".yml",
                    filetypes=[
                        (tr("filetype.yml_localisation", "YML localisation"), "*.yml"),
                        (tr("filetype.all", "All"), "*.*"),
                    ],
                    initialfile=loc_filename,
                    title=tr(
                        "filedialog.save_localisation_yml",
                        "Save Localisation .yml  (should go in localisation/{language}/)",
                        language=loc_target.dirname(),
                    ),
                )
                if not loc_path:
                    loc_path = os.path.join(saved_dir, loc_filename)
        return make_main_export_plan(
            label=f"Main: {tree_id}",
            focus_path=path,
            loc_path=loc_path,
            focuses=main_focuses,
            tree_info={
                "tree_id": tree_id,
                "country_tag": country_tag,
                "cfp_x": cfp_x,
                "cfp_y": cfp_y,
                "country_raw": getattr(self, "_tree_country_raw", ""),
                "tree_extras": getattr(self, "_tree_extras", {}),
                "shared_focuses": list(getattr(self, "_shared_focuses", [])),
                "joint_focuses": list(getattr(self, "_joint_focuses", [])),
            },
            focus_lookup=focus_lookup,
            focus_name_lookup=focus_name_lookup,
            loc_language=MOD.loc_language,
        )

    def _make_extra_export_plan(
        self, tree_idx, focuses_in_tree, focus_lookup, focus_name_lookup, *, show_dialog
    ):
        """Resolve one extra tree destination and snapshot its export plan."""
        if tree_idx <= 0 or tree_idx > len(self._extra_trees):
            return None
        info = self._extra_trees[tree_idx - 1]
        if not focuses_in_tree:
            if show_dialog:
                messagebox.showwarning(
                    tr("dialog.export.title", "Export"),
                    tr("dialog.no_focuses_in_tree", "No focuses in this tree."),
                )
            return None
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
            return None
        return make_extra_export_plan(
            label=f"{info['type'].capitalize()}: {info['tree_id']}",
            focus_path=path,
            focuses=focuses_in_tree,
            tree_info=dict(info),
            focus_lookup=focus_lookup,
            focus_name_lookup=focus_name_lookup,
            extra_tree_idx=tree_idx,
        )

    # ── SAVE / LOAD ─────────────────────────────────────────────
    def _capture_workspace(self):
        main_extras = dict(self.workspace.main_tree.extras)
        tree_extras = getattr(self, "_tree_extras", None)
        if tree_extras:
            main_extras["tree_extras"] = tree_extras
        try:
            cfp_x = int(self._cfp_x_var.get())
        except TypeError, ValueError:
            cfp_x = getattr(self, "_cfp_x", None)
        try:
            cfp_y = int(self._cfp_y_var.get())
        except TypeError, ValueError:
            cfp_y = getattr(self, "_cfp_y", None)
        meta = TreeMetadata(
            tree_id=self._tree_id.get(),
            country_tag=getattr(self, "_tree_country_tag", ""),
            country_name=getattr(self, "_tree_country_name", ""),
            country_raw=getattr(self, "_tree_country_raw", ""),
            focus_prefix=getattr(self, "_tree_focus_prefix", ""),
            cfp_x=cfp_x,
            cfp_y=cfp_y,
            shared_focuses=list(self._shared_focuses),
            joint_focuses=list(self._joint_focuses),
        )
        self.workspace.main_tree = TreeDocument(
            metadata=meta,
            file_path=getattr(MOD, "edit_focus_file", "") or "",
            had_wrapper=getattr(self, "_tree_had_wrapper", True),
            focus_ids=set(self.focuses.tree_membership.get(0, ())),
            extras=main_extras,
        )
        self.workspace.extra_trees = []
        for tree in self._extra_trees:
            known_tree_keys = {
                "type",
                "file_path",
                "tree_id",
                "cfp_x",
                "cfp_y",
                "shared_focuses",
                "joint_focuses",
                "country_tag",
                "had_wrapper",
                "focus_ids",
            }
            tree_meta = TreeMetadata(
                tree_id=tree.get("tree_id", ""),
                country_tag=tree.get("country_tag", ""),
                cfp_x=tree.get("cfp_x"),
                cfp_y=tree.get("cfp_y"),
                shared_focuses=list(tree.get("shared_focuses", [])),
                joint_focuses=list(tree.get("joint_focuses", [])),
            )
            self.workspace.extra_trees.append(
                TreeDocument(
                    metadata=tree_meta,
                    tree_type=tree.get("type", "shared"),
                    file_path=tree.get("file_path", ""),
                    had_wrapper=tree.get("had_wrapper", True),
                    focus_ids=set(tree.get("focus_ids", ())),
                    extras={
                        key: value
                        for key, value in tree.items()
                        if key not in known_tree_keys
                    },
                )
            )
        self.workspace.canvas_min = tuple(self._canvas_min)
        self.workspace.canvas_max = tuple(self._canvas_max)
        self.workspace.default_focus_prefix = self._default_focus_prefix
        return self.workspace

    def _install_workspace(self, workspace):
        self._begin_document_generation()
        self.workspace = workspace
        self.focuses = workspace.focuses
        meta = workspace.main_tree.metadata
        self._tree_id.set(meta.tree_id)
        self._tree_country_tag = meta.country_tag
        self._tree_country_name = meta.country_name
        self._tree_country_raw = meta.country_raw
        self._tree_extras = workspace.main_tree.extras.get("tree_extras", {})
        self._tree_focus_prefix = meta.focus_prefix
        self._tree_had_wrapper = workspace.main_tree.had_wrapper
        # Legacy projects decode with an empty file_path; keep the user's
        # existing export target rather than wiping it.
        if workspace.main_tree.file_path:
            MOD.edit_focus_file = workspace.main_tree.file_path
        self._cfp_x = meta.cfp_x
        self._cfp_y = meta.cfp_y
        self._cfp_x_var.set("" if meta.cfp_x is None else str(meta.cfp_x))
        self._cfp_y_var.set("" if meta.cfp_y is None else str(meta.cfp_y))
        self._shared_focuses = meta.shared_focuses
        self._joint_focuses = meta.joint_focuses
        self._extra_trees = []
        for tree in workspace.extra_trees:
            tree_meta = tree.metadata
            self._extra_trees.append(
                {
                    **tree.extras,
                    "type": tree.tree_type,
                    "file_path": tree.file_path,
                    "tree_id": tree_meta.tree_id,
                    "cfp_x": tree_meta.cfp_x,
                    "cfp_y": tree_meta.cfp_y,
                    "shared_focuses": tree_meta.shared_focuses,
                    "joint_focuses": tree_meta.joint_focuses,
                    "country_tag": tree_meta.country_tag,
                    "had_wrapper": tree.had_wrapper,
                    "focus_ids": tree.focus_ids,
                }
            )
        self._invalidate_tree_badges()
        self._canvas_min = list(workspace.canvas_min)
        self._canvas_max = list(workspace.canvas_max)
        self._default_focus_prefix = workspace.default_focus_prefix

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
            return False
        try:
            write_project(path, self._capture_workspace())
        except Exception as e:
            log.error("project save failed: %s", e, exc_info=True)
            report_write_failure(self, path, e)
            return False
        try:
            self._last_project_path = path
        except Exception:
            pass
        try:
            self._mark_clean()
        except Exception:
            pass
        try:
            clear_workspace_autosave()
        except Exception:
            pass
        try:
            clear_workspace_autosave(sibling_autosave_path(path))
        except Exception:
            pass
        messagebox.showinfo(
            tr("dialog.saved.title", "Saved"),
            tr("dialog.project_saved", "Project saved:\n{path}", path=path),
        )
        return True

    def _detect_and_apply_tag(self):
        """Detect common tag prefix from loaded focuses."""
        if not self.focuses:
            return
        names = [f.name for f in self.focuses.values() if f.name and "_" in f.name]
        if not names:
            return
        from collections import Counter

        # First segment before "_" (e.g. "JAP" from "JAP_militarism")
        segs = [n.split("_")[0].upper() for n in names]
        # Filter: 2-5 chars (typical tag like JAP, GER, USA)
        segs = [s for s in segs if 2 <= len(s) <= 5 and s.isalpha()]
        if not segs:
            return
        most_common, count = Counter(segs).most_common(1)[0]
        # Apply if >=2 focuses and >=30% (handles small trees)
        threshold = count >= 2 and (count / len(names) >= 0.30)
        if threshold and len(most_common) >= 2:
            self._default_focus_prefix = most_common + "_"
            self._hint(
                f"🏷 Tag {most_common} — new focuses auto-prefix '{most_common}_'"
            )
        else:
            self._default_focus_prefix = ""

    def _load(self):
        try:
            if not self._confirm_discard(action="loading"):
                return
        except AttributeError:
            pass
        path = filedialog.askopenfilename(
            filetypes=[
                (tr("filetype.json_project", "JSON Project"), "*.json"),
                (tr("filetype.all", "All"), "*.*"),
            ],
            title=tr("filedialog.load_project", "Load Project"),
        )
        if not path:
            return
        try:
            workspace = read_project(path)
        except Exception as e:
            report_error(
                tr(
                    "dialog.load_project_error.body",
                    "Could not load project:\n{error}",
                    error=e,
                ),
                e,
                title=tr("dialog.load_project_error.title", "Load Project Error"),
            )
            return
        self.cv.delete("all")
        self.selected = None
        self._lines.clear()
        self._grid_item = None
        self._grid_key = None
        self._grid_img = None
        self._install_workspace(workspace)
        try:
            self._last_project_path = path
        except Exception:
            pass
        try:
            self._mark_clean()
        except Exception:
            pass
        try:
            clear_workspace_autosave()
        except Exception:
            pass
        self._detect_and_apply_tag()
        self._refresh_tree_meta_panel()
        self._refresh_loaded_trees_panel()
        self._hide_form()
        self._redraw()
        self._invalidate_focus_list_structure()

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
        open_settings(self)

    def _additional_income_wizard(self):
        """Open the MD Additional Income wizard."""
        from hoi4cm.wizards import open_additional_income_wizard

        open_additional_income_wizard(self)

    def _national_spirit_wizard(self):
        """Open the National Spirit/Ideas builder wizard."""
        from hoi4cm.wizards import open_national_spirit_wizard

        open_national_spirit_wizard(self)

    def _dyn_mod_wizard(self):
        """Open the Dynamic Modifier wizard."""
        from hoi4cm.wizards import open_dyn_mod_wizard

        open_dyn_mod_wizard(self)

    def _decision_wizard(self):
        """Open the Decision Maker wizard."""
        from hoi4cm.wizards import open_decision_wizard

        open_decision_wizard(self)

    def _event_wizard(self):
        """Open the Event Maker wizard."""
        from hoi4cm.wizards import open_event_wizard

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
        """Coalesce rapid search-box keystrokes into one structural refresh."""
        if getattr(self, "_lp_search_job", None):
            try:
                self.after_cancel(self._lp_search_job)
            except Exception:
                pass
        self._lp_search_job = self.after(120, self._invalidate_focus_list_structure)

    def _invalidate_focus_list_structure(self):
        """Refresh list data after add/delete/rename/import or search changes."""
        self._lp_search_job = None
        if not hasattr(self, "_focus_list"):
            return
        worst = getattr(self, "_validation_worst", {})

        def _build_items():
            return (
                FocusListItem(
                    f.id,
                    f.name,
                    has_effects=bool(f.effects),
                    has_broken_prerequisite=any(
                        pid not in self.focuses for group in f.prereqs for pid in group
                    ),
                    validation_severity=worst.get(f.id),
                )
                for f in self.focuses.values()
            )

        # Rebuild the item tuple only when the document structure changes;
        # search keystrokes just re-filter the cached tuple.
        self._focus_list_items = self._focus_list_cache.get(self.focuses, _build_items)
        # patch cached items if validation changed without document revision bump
        if self._focus_list_items:
            needs_patch = any(
                item.validation_severity != worst.get(item.key)
                for item in self._focus_list_items
            )
            if needs_patch:
                self._focus_list_cache.invalidate()
                self._focus_list_items = self._focus_list_cache.get(
                    self.focuses, _build_items
                )
        query = self._lp_search_var.get() if hasattr(self, "_lp_search_var") else ""
        placeholder = tr("common.search_placeholder", "Search...")
        selected_id = self.selected.id if self.selected else None
        self._focus_list.invalidate_structure(
            self._focus_list_items,
            query=query,
            placeholder=placeholder,
            selected_key=selected_id,
        )

    def _update_focus_list_selection(self):
        """Update at most the old and new materialized row highlights."""
        if not hasattr(self, "_focus_list"):
            return
        sel_id = self.selected.id if self.selected else None
        self._focus_list.update_selection(sel_id)

    def _select_focus_from_list(self, focus_id):
        if focus_id in self.focuses:
            self._select(self.focuses[focus_id])
            self._redraw()

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
        nf = f.duplicate()
        # Generate new unique name
        base = re.sub(r"_copy\d*$", "", f.name) + "_copy"
        existing_names = {foc.name for foc in self.focuses.values()}
        n = 1
        candidate = base
        while candidate in existing_names:
            candidate = f"{base}{n}"
            n += 1
        nf.name = candidate
        nf.x = f.x + 1
        nf.y = f.y
        # Clear prereqs/mutex since IDs won't match
        nf.prereqs = []
        nf.mutex = []
        self._push_undo("duplicate", touched_ids=())
        self.focuses.add(nf)
        self._redraw_now()  # force immediate, bypass throttle
        self._select(nf)
        self._invalidate_focus_list_structure()

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
                "Replaces prefix across all {count} focus IDs,\n"
                "prerequisite references, and mutex links.",
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
            renamed_ids = {f.id for f in self.focuses.values() if f.name.startswith(fr)}
            self._push_undo("bulk_rename", touched_ids=renamed_ids)
            n = len({f.name for f in self.focuses.values() if f.name.startswith(fr)})
            self.focuses.rename_prefix(fr, to)
            win.destroy()
            self._redraw()
            self._invalidate_focus_list_structure()
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
    def _refresh_validation_dialog(self, win):
        filt = getattr(win, "_val_filter_var", None)
        tree = getattr(win, "_val_tree", None)
        hdr_lbl = getattr(win, "_val_hdr_lbl", None)
        if filt is None or tree is None:
            return
        issues = getattr(self, "_validation_issues", [])
        mode = filt.get()
        if mode == "error":
            shown = [it for it in issues if it.severity == "error"]
        elif mode == "warning":
            shown = [it for it in issues if it.severity == "warning"]
        else:
            shown = list(issues)
        if hdr_lbl is not None:
            err = sum(1 for it in issues if it.severity == "error")
            warn = sum(1 for it in issues if it.severity == "warning")
            if not issues:
                hdr_lbl.config(
                    text=tr("validation.clean", "  Tree looks clean!"),
                    fg="#22c55e",
                )
            else:
                hdr_lbl.config(
                    text=tr(
                        "validation.issues_found",
                        "  {count} issues — {err} errors, {warn} warnings",
                        count=len(issues),
                        err=err,
                        warn=warn,
                    ),
                    fg="#fbbf24" if err else "#f59e0b",
                )
        for iid in tree.get_children():
            tree.delete(iid)
        for idx, it in enumerate(shown):
            sev_icon = (
                "🔴"
                if it.severity == "error"
                else "🟡"
                if it.severity == "warning"
                else "🔵"
            )
            focus_txt = it.focus_name or "—"
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(sev_icon, focus_txt, it.message, it.code),
                tags=(str(idx),),
            )
        # store mapping for click handler
        win._val_shown = shown  # type: ignore[attr-defined]

    def _validate_tree(self):
        """Validate tree via pure validator and show filterable dialog."""
        from tkinter import ttk

        try:
            sprites = self._validation_sprites()
            loc_keys = self._validation_loc_keys()
            issues = validate_document(self.focuses, sprites=sprites, loc_keys=loc_keys)
            self._validation_issues = issues
            self._validation_worst = worst_severity_per_focus(issues)
            self._redraw()
            self._invalidate_focus_list_structure()
        except Exception:
            issues = getattr(self, "_validation_issues", [])
        win = tk.Toplevel(self)
        win.title(tr("validation.title", "Tree Validation"))
        win.configure(bg=BG_DARK)
        win.geometry("820x460")
        win.resizable(True, True)
        self._validation_win = win

        def _on_close():
            self._validation_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", _on_close)
        hdr = tk.Frame(win, bg="#080c12")
        hdr.pack(fill="x")
        hdr_lbl = tk.Label(
            hdr,
            text="",
            bg="#080c12",
            fg="#fbbf24",
            font=("Helvetica", 11, "bold"),
            pady=8,
        )
        hdr_lbl.pack(side="left", padx=8)
        win._val_hdr_lbl = hdr_lbl  # type: ignore[attr-defined]
        tk.Button(
            hdr,
            text="✕",
            command=_on_close,
            bg="#080c12",
            fg=TEXT_DIM,
            relief="flat",
            cursor="hand2",
            padx=10,
        ).pack(side="right")
        tk.Frame(win, bg=BORDER_G, height=1).pack(fill="x")
        # filter row
        filt_var = tk.StringVar(value="all")
        win._val_filter_var = filt_var  # type: ignore[attr-defined]
        filt_row = tk.Frame(win, bg=BG_DARK)
        filt_row.pack(fill="x", padx=8, pady=6)
        tk.Label(
            filt_row,
            text=tr("validation.filter", "Filter:"),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 9),
        ).pack(side="left")
        for val, label in (
            ("all", tr("validation.filter_all", "All")),
            ("error", tr("validation.filter_errors", "Errors")),
            ("warning", tr("validation.filter_warnings", "Warnings")),
        ):
            tk.Radiobutton(
                filt_row,
                text=label,
                variable=filt_var,
                value=val,
                bg=BG_DARK,
                fg=TEXT,
                selectcolor="#1e293b",
                activebackground=BG_DARK,
                command=lambda: self._refresh_validation_dialog(win),
            ).pack(side="left", padx=6)

        def _copy_filtered():
            shown = getattr(win, "_val_shown", [])
            if not shown:
                return
            text = "\n".join(
                f"{it.severity.upper()}: {it.message} [{it.code}]" for it in shown
            )
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self._hint(
                    tr("validation.copied", "Copied {count} issues", count=len(shown))
                )
            except Exception:
                pass

        tk.Button(
            filt_row,
            text=tr("validation.copy", "Copy"),
            command=_copy_filtered,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            font=("Helvetica", 9),
        ).pack(side="right", padx=4)
        tk.Button(
            filt_row,
            text=tr("validation.revalidate", "Re-validate"),
            command=self._run_validation,
            bg=BG_CARD,
            fg=TEXT,
            relief="flat",
            padx=10,
            pady=2,
            cursor="hand2",
            font=("Helvetica", 9),
        ).pack(side="right")
        frm = tk.Frame(win, bg=BG_DARK)
        frm.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # Treeview with scrollbar
        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")
        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure(
                "Val.Treeview",
                background="#050810",
                foreground=TEXT,
                fieldbackground="#050810",
                borderwidth=0,
                highlightthickness=0,
                rowheight=22,
            )
            style.configure(
                "Val.Treeview.Heading",
                background="#1e293b",
                foreground=TEXT,
                relief="flat",
            )
            style.map("Val.Treeview", background=[("selected", "#1e2d4a")])
        except Exception:
            pass
        tree = ttk.Treeview(
            frm,
            columns=("sev", "focus", "message", "code"),
            show="headings",
            style="Val.Treeview",
            yscrollcommand=sb.set,
        )
        win._val_tree = tree  # type: ignore[attr-defined]
        tree.heading("sev", text="")
        tree.heading("focus", text=tr("validation.col_focus", "Focus"))
        tree.heading("message", text=tr("validation.col_message", "Message"))
        tree.heading("code", text=tr("validation.col_code", "Code"))
        tree.column("sev", width=40, minwidth=30, stretch=False, anchor="center")
        tree.column("focus", width=160, minwidth=100, anchor="w")
        tree.column("message", width=420, minwidth=200, anchor="w")
        tree.column("code", width=120, minwidth=80, anchor="w")
        sb.config(command=tree.yview)
        tree.pack(fill="both", expand=True)
        hint = tk.Label(
            win,
            text=tr(
                "validation.hint",
                "Click a row to select the focus on the canvas. Double-click to center.",
            ),
            bg=BG_DARK,
            fg=TEXT_DIM,
            font=("Helvetica", 8),
            anchor="w",
        )
        hint.pack(fill="x", padx=8, pady=(0, 6))

        def _select_focus(event=None):
            sel = tree.selection()
            if not sel:
                return
            try:
                idx = int(sel[0])
            except Exception:
                return
            shown = getattr(win, "_val_shown", [])
            if 0 <= idx < len(shown):
                it = shown[idx]
                if it.focus_id is not None and it.focus_id in self.focuses:
                    self._select(self.focuses[it.focus_id])
                    self._hint(f"Selected {it.focus_name}: {it.code}")

        def _center_focus(event=None):
            sel = tree.selection()
            if not sel:
                return
            try:
                idx = int(sel[0])
            except Exception:
                return
            shown = getattr(win, "_val_shown", [])
            if 0 <= idx < len(shown):
                it = shown[idx]
                if it.focus_id is not None and it.focus_id in self.focuses:
                    self._center_on_focus(it.focus_id)

        tree.bind("<<TreeviewSelect>>", _select_focus)
        tree.bind("<Double-Button-1>", _center_focus)
        self._refresh_validation_dialog(win)
        if not issues:
            tree.insert(
                "",
                "end",
                values=(
                    "",
                    "",
                    tr(
                        "validation.all_prereqs_valid",
                        "All prerequisite chains are valid.",
                    ),
                    "",
                ),
            )

    def _export(
        self, *, focuses_in_tree=None, focus_name_lookup=None, show_dialog=True
    ):
        """Export the main tree through the shared background export pipeline."""
        try:
            if self.selected:
                self._autosave()
        except Exception:
            pass
        main_focuses = focuses_in_tree
        if main_focuses is None:
            main_focuses = [
                focus
                for focus in self.focuses.values()
                if getattr(focus, "tree_idx", 0) == 0
            ]
        plan = self._make_main_export_plan(
            main_focuses,
            dict(self.focuses),
            focus_name_lookup or build_focus_name_lookup(self.focuses.values()),
            show_dialog=show_dialog,
        )
        if plan is None:
            return None

        def on_done(results):
            failures = self._apply_export_results(
                results,
                title=tr("dialog.export.title", "Export"),
            )
            if failures or not show_dialog:
                return
            result = results[0]
            if result.localisation_added:
                loc_saved = "\n" + tr(
                    "export.localisation_added",
                    "Localisation: {file}  (+{count} new keys)",
                    file=os.path.basename(plan.loc_path),
                    count=result.localisation_added,
                )
            else:
                loc_saved = "\n" + tr(
                    "export.localisation_skipped",
                    "Localisation: all keys already present in {file} - skipped",
                    file=os.path.basename(plan.loc_path),
                )
            messagebox.showinfo(
                tr("dialog.exported.title", "Exported"),
                tr(
                    "dialog.exported.body",
                    "Export complete!\n\nFocus tree: {focus_file}{loc_saved}\n\n"
                    "Install paths:\n"
                    "  .txt  ->  common/national_focus/{default_filename}\n\n"
                    "Reminders:\n  - Replace placeholder icons with real GFX keys\n"
                    "  - Add shared_focus lines if using shared trees",
                    focus_file=os.path.basename(plan.focus_path),
                    loc_saved=loc_saved,
                    default_filename=os.path.basename(plan.focus_path),
                ),
            )

        return self._run_export_plans(
            [plan],
            on_done,
            title=tr("dialog.export.title", "Export"),
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
        app.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        log.info(f"_launch: geometry set to {W}x{H}, entering mainloop...")
        app.mainloop()
        log.info("_launch: mainloop exited")

    log.info("Entry point: calling show_splash...")
    show_splash(_launch, apply_dpi_scaling=_apply_tk_dpi_scaling)
