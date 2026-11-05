"""Content navigation and inexpensive editor save/validation status."""

from __future__ import annotations

import copy
import re
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from hoi4cm.core.i18n import tr
from hoi4cm.core.logger import add_error, get_logger
from hoi4cm.models.sidebar_form import (
    FocusSidebarValues,
    parse_ai_will_do,
    parse_focus_cost,
    sidebar_values_match_focus,
)
from hoi4cm.ui.theme import BG_CARD, BLUE, TEXT, TEXT_DIM

log = get_logger("editor_chrome")


@dataclass
class EditorStatus:
    """Revision tokens are supplied by edit/save/validation boundaries."""

    saved: object = None
    validated: object = None
    change_revision: int = 0

    def labels(self, signature, pending=False):
        if pending or signature != self.saved:
            saved = tr("editor.unsaved", "Unsaved")
        else:
            saved = tr("editor.saved", "Saved")
        if self.validated is None:
            validation = tr("editor.validation.not_run", "Validation: not run")
        elif not pending and signature == self.validated:
            validation = tr("editor.validation.current", "Validation: current")
        else:
            validation = tr("editor.validation.outdated", "Validation: outdated")
        return saved, validation


def _state(app) -> EditorStatus:
    state = getattr(app, "_editor_status", None)
    if state is None:
        state = app._editor_status = EditorStatus()
    return state


def validation_signature(app):
    """Snapshot revisions plus metadata, without serializing focus documents."""
    observe_selected_content(app)
    metadata = tuple(
        getattr(app, name, None)
        for name in (
            "_tree_country_tag",
            "_tree_country_name",
            "_tree_country_raw",
            "_tree_focus_prefix",
            "_tree_extras",
            "_tree_had_wrapper",
            "_shared_focuses",
            "_joint_focuses",
            "_canvas_min",
            "_canvas_max",
            "_default_focus_prefix",
        )
    )
    extras = tuple(
        {
            key: value
            for key, value in tree.items()
            if key not in ("focus_ids", "focuses")
        }
        for tree in getattr(app, "_extra_trees", ())
    )
    return (
        id(app.focuses),
        app.focuses.revision,
        _state(app).change_revision,
        app._tree_id.get(),
        app._cfp_x_var.get(),
        app._cfp_y_var.get(),
        copy.deepcopy((metadata, extras)),
    )


def mark_editor_changed(app):
    """Signal a committed edit that does not change document geometry."""
    _state(app).change_revision += 1


def observe_selected_content(app):
    """Notice in-place committed edits while inspecting only one focus."""
    selected = getattr(app, "selected", None)
    if selected is None:
        app._editor_observed_focus = None
        app._editor_observed_content = None
        return
    content = selected.to_dict()
    previous = getattr(app, "_editor_observed_focus", None)
    if previous is selected and content != app._editor_observed_content:
        mark_editor_changed(app)
        # The older recovery writer keys on geometry revisions. A committed
        # form/effect edit must invalidate that cached token as well.
        app._autosave_writer = None
    app._editor_observed_focus = selected
    app._editor_observed_content = copy.deepcopy(content)


def mark_editor_saved(app):
    """Record a successful save/load boundary after pending edits are flushed."""
    _state(app).saved = validation_signature(app)
    update_editor_status(app)


def editor_is_dirty(app):
    return validation_signature(app) != _state(app).saved or pending_editor_changes(app)


def validation_completed(app, signature=None):
    """Keep the dispatch token so late results cannot validate newer edits."""
    _state(app).validated = (
        validation_signature(app) if signature is None else signature
    )
    update_editor_status(app)


def pending_editor_changes(app):
    """Inspect only the selected focus and its form/code editor."""
    focus = getattr(app, "selected", None)
    if focus is None or not hasattr(app, "_fv_name"):
        return False
    try:
        raw_ai = app._fv_ai_raw.get("1.0", "end").strip()
        values = FocusSidebarValues(
            name=re.sub(r"[^A-Za-z0-9_]", "_", app._fv_name.get().strip()),
            icon=app._fv_icon.get(),
            gfx=app._fv_gfx.get().strip() or "GFX_goal_generic_political_pressure",
            cost=parse_focus_cost(app._fv_cost.get()),
            ai_will_do=parse_ai_will_do(raw_ai),
            ai_will_do_raw=raw_ai,
            x=int(app._fv_x.get()),
            y=int(app._fv_y.get()),
            loc_name=app._fv_loc_name.get().strip(),
            desc=app._fv_desc.get("1.0", "end").strip(),
            search_filters=app._fv_search.get().strip() or "FOCUS_FILTER_POLITICAL",
            available_cond=app._fv_avail.get("1.0", "end").strip(),
            bypass_cond=app._fv_bypass.get("1.0", "end").strip(),
            cancel_cond=app._fv_cancel2.get("1.0", "end").strip(),
            cancel_if_invalid=app._fv_cancel.get(),
            continue_if_invalid=app._fv_continue.get(),
            available_if_capitulated=app._fv_cap.get(),
            offsets=tuple(app._read_offsets_from_form()),
        )
    except ValueError, OverflowError, tk.TclError:
        return True
    if not sidebar_values_match_focus(focus, values):
        return True
    if getattr(app, "_code_edit_mode", [False])[0]:
        return (
            app._code_txt.get("1.0", "end").strip()
            != app._build_focus_code(focus).strip()
        )
    return False


def update_editor_status(app):
    """Refresh chrome independently of canvas rendering and selection."""
    chrome = getattr(app, "_editor_chrome", None)
    if chrome is not None:
        chrome.refresh()


def configure_validation_style(app):
    """Keep the validation table dark without changing other widgets' theme."""
    style = ttk.Style(app)
    style.layout("Val.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    border = "Validation.Treeheading.border"
    if border not in style.element_names():
        style.element_create(border, "from", "clam", "Treeheading.border")
    style.layout(
        "Val.Treeview.Heading",
        [
            (
                border,
                {
                    "sticky": "nswe",
                    "children": [
                        (
                            "Treeheading.padding",
                            {
                                "sticky": "nswe",
                                "children": [
                                    (
                                        "Treeheading.image",
                                        {"side": "right", "sticky": ""},
                                    ),
                                    ("Treeheading.text", {"sticky": "we"}),
                                ],
                            },
                        ),
                    ],
                },
            ),
        ],
    )
    style.configure(
        "Val.Treeview",
        background="#050810",
        foreground=TEXT,
        fieldbackground="#050810",
        borderwidth=0,
        rowheight=22,
    )
    style.configure(
        "Val.Treeview.Heading", background="#1e293b", foreground=TEXT, relief="flat"
    )
    style.map("Val.Treeview", background=[("selected", "#1e2d4a")])


class EditorChrome:
    """The active content surface and selected-focus navigation commands."""

    def __init__(self, app):
        self.app = app
        self.active_content = "Focus Trees"
        self.navigation_buttons: dict[str, tk.Button] = {}
        # Display names for the content ids; ``active_content`` stays an id.
        self.titles: dict[str, str] = {}
        self.windows: dict[str, tk.Toplevel] = {}
        self._status_job = None
        self._closed = False
        self._failing = False

    def start(self):
        """Poll the selected form only; dispose through the app lifecycle."""
        if self._closed:
            return
        try:
            self.refresh()
            self._failing = False
        except Exception as exc:  # polling must survive one bad refresh
            if not self._failing:
                self._failing = True
                log.exception("editor status refresh failed")
                add_error(f"Editor status refresh failed: {exc}")
        finally:
            self._status_job = self.app.after(300, self.start)

    def close(self):
        self._closed = True
        if self._status_job is not None:
            self.app.after_cancel(self._status_job)
            self._status_job = None

    def navigate(self, label, command=None):
        app = self.app
        editor = getattr(app, "_focus_editor", None)
        if editor is not None and not editor.close():
            return
        if label == "Focus Trees":
            for window in tuple(self.windows.values()):
                window.grab_release()
                window.lower(app)
            app.lift()
            app.cv.focus_set()
            self.active_content = label
            self.refresh()
            return
        window = self.windows.get(label)
        if window is not None and window.winfo_exists():
            window.lift()
            window.grab_set()
            window.focus_set()
            self.active_content = label
            self.refresh()
            return
        before = set(app.winfo_children())
        self.active_content = label
        self.refresh()
        try:
            assert command is not None
            command()
        finally:
            opened = [
                child
                for child in app.winfo_children()
                if child not in before and isinstance(child, tk.Toplevel)
            ]
            if opened:
                window = opened[-1]
                self.windows[label] = window

                def closed(event):
                    if event.widget is window:
                        self.windows.pop(label, None)
                        if self.active_content == label:
                            self.active_content = "Focus Trees"
                        self.refresh()

                window.bind("<Destroy>", closed, add="+")
            else:
                self.active_content = "Focus Trees"
            self.refresh()

    def search(self):
        app = self.app
        self.navigate("Focus Trees")
        if not app._left_panel_visible:
            app._toggle_focus_list()
        entry = app._focus_search_entry
        entry.focus_set()
        entry.selection_range(0, "end")

    def reveal(self):
        if self.app.selected is not None:
            self.app._center_on_focus(self.app.selected.id)

    def actions(self):
        if self.app.selected is not None:
            self.app._focus_actions.show(self.app.selected.id)

    def zoom(self, factor):
        app = self.app
        previous = app.zoom
        app.zoom = max(0.15, min(3.0, previous * factor))
        for axis, center in enumerate(
            (app.cv.winfo_width() / 2, app.cv.winfo_height() / 2)
        ):
            app.offset[axis] = center - (center - app.offset[axis]) * (
                app.zoom / previous
            )
        app._redraw()
        self.refresh()

    def refresh(self):
        app = self.app
        tree_id = app._tree_id.get() or tr("status.no_tree", "no tree")
        selected = getattr(app, "selected", None)
        index = selected.tree_idx if selected is not None else 0
        if 0 < index <= len(app._extra_trees):
            tree_id = app._extra_trees[index - 1].get("tree_id", tree_id)
        title = self.titles.get(self.active_content, self.active_content)
        app._editor_context_lbl.config(text=f"{title}  /  {tree_id}")
        app._editor_zoom_lbl.config(text=f"{int(app.zoom * 100)}%")
        for label, button in self.navigation_buttons.items():
            active = label == self.active_content
            button.config(bg=BLUE if active else BG_CARD, fg=TEXT)
        sidebar = getattr(app, "_project_sidebar", None)
        if sidebar is not None:
            sidebar.refresh()
        if not hasattr(app, "_fv_name"):
            return
        saved, validation = _state(app).labels(
            validation_signature(app), pending_editor_changes(app)
        )
        app._editor_save_lbl.config(text=saved, fg=TEXT_DIM)
        app._editor_validation_lbl.config(text=validation)


__all__ = [
    "configure_validation_style",
    "editor_is_dirty",
    "EditorChrome",
    "EditorStatus",
    "mark_editor_changed",
    "mark_editor_saved",
    "observe_selected_content",
    "pending_editor_changes",
    "update_editor_status",
    "validation_completed",
    "validation_signature",
]
