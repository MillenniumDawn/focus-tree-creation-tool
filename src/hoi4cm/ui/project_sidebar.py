"""Content navigation and a searchable, read-only project explorer."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from hoi4cm.core.logger import add_error
from hoi4cm.mod import MOD
from hoi4cm.ui.project_index import (
    ExplorerItem,
    discover_focus_files,
    discover_resources,
    filter_project,
    focus_file_items,
    project_items,
)
from hoi4cm.ui.tasks import run_bg
from hoi4cm.ui.theme import BLUE, TEXT
from hoi4cm.ui.widgets import Tooltip

NAVY = "#102130"
MUTED = "#99b9d8"
ACTIVE = "#084d87"
DIVIDER = "#294257"


def sidebar_icon(master, name, size, scale):
    """Load supplied transparent symbols using Tk alone, including frozen builds."""
    source = tk.PhotoImage(
        master=master,
        data=(
            Path(__file__).with_name("assets") / "sidebar" / f"{name}.png"
        ).read_bytes(),
    )
    return source.subsample(max(1, round(source.width() / (size * scale))))


def reveal_source(path):
    """Reveal an existing resource's containing folder using the platform shell."""
    parent = str(Path(path).parent)
    if sys.platform == "win32":
        os.startfile(parent)
    else:
        # The folder viewer owns its lifetime; never wait on the Tk thread.
        subprocess.Popen(  # pylint: disable=consider-using-with
            ["open" if sys.platform == "darwin" else "xdg-open", parent]
        )


class ProjectSidebar:
    """One sidebar controller; navigation never changes document ownership."""

    def __init__(self, app, body):
        self.app = app
        self.items = ()
        self.by_key = {}
        self._signature = None
        self._resource_root = None
        self.resources = ()
        self.catalog = ()
        self._focus_files = None
        self._focus_errors = ()
        self._discovery_generation = 0
        self._job = None
        self._searching = False
        self._expanded = {"project", "focus-trees"}
        self._known_keys = set()
        self._width = 280
        self._hover = ""
        self._selected_id = None
        scale = app.winfo_fpixels("1i") / 96
        self.scale = scale
        self.panes = tk.PanedWindow(
            body,
            orient="horizontal",
            bg=DIVIDER,
            sashwidth=5,
            bd=0,
            opaqueresize=True,
            showhandle=False,
        )
        self.panes.pack(fill="both", expand=True)
        app._left_panel_visible = True
        app._left_panel = self.panel = tk.Frame(
            self.panes, bg=NAVY, width=int(280 * scale)
        )
        self.panel.pack_propagate(False)
        self.panes.add(self.panel, minsize=int(230 * scale), width=int(280 * scale))
        self.canvas_host = tk.Frame(self.panes, bg=NAVY)
        self.panes.add(self.canvas_host, minsize=int(250 * scale), stretch="always")
        header = tk.Frame(self.panel, bg=NAVY)
        header.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(
            header, text="CONTENT", bg=NAVY, fg=MUTED, font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        self.collapse_icon = sidebar_icon(app, "sidebar_collapse", 28, scale)
        self.expand_icon = sidebar_icon(app, "sidebar_expand", 28, scale)
        tk.Button(
            header,
            image=self.collapse_icon,
            command=self.toggle,
            bg=NAVY,
            fg=MUTED,
            relief="flat",
            takefocus=True,
            highlightcolor=BLUE,
        ).pack(side="right")
        chrome = app._editor_chrome
        self.accents = {}
        self.icons = []
        for index, (label, command) in enumerate(
            (
                ("Focus Trees", None),
                ("Decisions", app._decision_wizard),
                ("Events", app._event_wizard),
                ("Ideas", app._national_spirit_wizard),
                ("Dynamic Modifiers", app._dyn_mod_wizard),
            )
        ):
            row = tk.Frame(self.panel, bg=NAVY)
            row.pack(fill="x", pady=2)
            accent = tk.Frame(row, bg=NAVY, width=3)
            accent.pack(side="left", fill="y")
            icon_name = (
                "nav_focus_trees",
                "nav_decisions",
                "nav_events",
                "nav_ideas",
                "nav_dynamic_modifiers",
            )[index]
            icon = sidebar_icon(app, icon_name, 36, scale)
            self.icons.append(icon)
            button = tk.Button(
                row,
                text=f"   {label}",
                image=icon,
                compound="left",
                anchor="w",
                command=lambda label=label, command=command: chrome.navigate(
                    label, command
                ),
                bg=NAVY,
                fg=TEXT,
                activebackground=ACTIVE,
                activeforeground=TEXT,
                font=("Segoe UI", 11),
                relief="flat",
                bd=0,
                padx=16,
                pady=5,
                takefocus=True,
                highlightthickness=1,
                highlightbackground=NAVY,
                highlightcolor=BLUE,
                cursor="hand2",
            )
            button.pack(fill="x", padx=(0, 8))
            Tooltip(button, label)
            chrome.navigation_buttons[label] = button
            self.accents[label] = accent
        tk.Frame(self.panel, bg=DIVIDER, height=1).pack(
            fill="x", padx=14, pady=(16, 12)
        )
        project_header = tk.Frame(self.panel, bg=NAVY)
        project_header.pack(fill="x", padx=16)
        tk.Label(
            project_header,
            text="PROJECT",
            bg=NAVY,
            fg=MUTED,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        refresh = tk.Button(
            project_header,
            text="↻",
            command=self.reload_resources,
            bg=NAVY,
            fg=MUTED,
            relief="flat",
            takefocus=True,
            highlightcolor=BLUE,
            bd=0,
        )
        refresh.pack(side="right")
        Tooltip(refresh, "Refresh project source files")
        search = tk.Frame(self.panel, bg=NAVY)
        search.pack(fill="x", padx=12, pady=(8, 10))
        self.utility_icons = {
            name: sidebar_icon(app, name, 28, scale)
            for name in ("search", "close", "open_project", "new_focus")
        }
        app._lp_search_var = tk.StringVar(master=app)
        app._focus_search_entry = tk.Entry(
            search,
            textvariable=app._lp_search_var,
            bg=NAVY,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=DIVIDER,
            highlightcolor=BLUE,
        )
        clear_search = tk.Button(
            search,
            image=self.utility_icons["close"],
            command=lambda: app._lp_search_var.set(""),
            bg=NAVY,
            relief="flat",
            takefocus=True,
            highlightcolor=BLUE,
        )
        clear_search.pack(side="right", padx=(4, 0))
        Tooltip(clear_search, "Clear project search")
        app._focus_search_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.search_hint_icon = sidebar_icon(app, "search", 20, scale)
        self.search_hint = tk.Label(
            search,
            text="Search project…",
            image=self.search_hint_icon,
            compound="left",
            bg=NAVY,
            fg=MUTED,
            font=("Segoe UI", 10),
            cursor="xterm",
        )
        self.search_hint.place(x=8, rely=0.5, anchor="w")
        self.search_hint.bind(
            "<Button-1>", lambda _event: app._focus_search_entry.focus_set()
        )
        app._focus_search_entry.bind(
            "<FocusIn>", lambda _event: self.search_hint.place_forget()
        )
        app._focus_search_entry.bind(
            "<FocusOut>", lambda _event: self._update_search_hint()
        )
        Tooltip(app._focus_search_entry, "Search project by name, ID or source path")
        app._focus_search_entry.bind("<Return>", self.first_result)
        app._lp_search_var.trace_add("write", lambda *_: self.schedule_filter())
        self.new_tree_button = tk.Button(
            self.panel,
            text="  New Focus Tree",
            image=self.utility_icons["new_focus"],
            compound="left",
            command=self.create_tree,
            bg=ACTIVE,
            fg=TEXT,
            relief="flat",
            anchor="w",
            padx=10,
            pady=3,
            takefocus=True,
            highlightcolor=BLUE,
        )
        self.new_tree_button.pack(fill="x", padx=12, pady=(0, 10))
        Tooltip(
            self.new_tree_button,
            "Create a new focus tree using the existing setup wizard",
        )
        self.empty = tk.Frame(self.panel, bg=NAVY)
        tk.Label(
            self.empty,
            text="Open a project or use\nNew Focus Tree to get started.",
            bg=NAVY,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(pady=12)
        for label, command, icon_name in (
            ("Open Project…", app._load, "open_project"),
        ):
            tk.Button(
                self.empty,
                text=label,
                image=self.utility_icons[icon_name],
                compound="left",
                command=command,
                bg=ACTIVE,
                fg=TEXT,
                relief="flat",
                takefocus=True,
            ).pack(fill="x", padx=16, pady=4)
        self.tree_frame = tk.Frame(self.panel, bg=NAVY)
        style = ttk.Style(app)
        self.item_icons = {
            name: sidebar_icon(app, name, 30, scale)
            for name in (
                "project_folder_closed",
                "project_folder_open",
                "file_focus_tree",
                "nav_focus_trees",
                "item_focus",
                "file_localization",
                "file_graphics",
                "file_scripted_effects",
                "file_generic",
            )
        }
        if "Project.indicator" not in style.element_names():
            # Tk 9 keeps open/leaf flags internal; the theme element follows both
            # Tk 8 and Tk 9 correctly, unlike an image map keyed by user1/user2.
            style.element_create(
                "Project.indicator", "from", "clam", "Treeitem.indicator"
            )
        style.layout(
            "Project.Treeview.Item",
            [
                (
                    "Treeitem.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Project.indicator", {"side": "left", "sticky": ""}),
                            ("Treeitem.image", {"side": "left", "sticky": ""}),
                            (
                                "Treeitem.focus",
                                {
                                    "side": "left",
                                    "sticky": "nswe",
                                    "children": [
                                        (
                                            "Treeitem.text",
                                            {"side": "left", "sticky": ""},
                                        )
                                    ],
                                },
                            ),
                        ],
                    },
                )
            ],
        )
        style.layout("Project.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Project.Treeview",
            background=NAVY,
            fieldbackground=NAVY,
            foreground=TEXT,
            rowheight=int(34 * scale),
            font=("Segoe UI", 10),
            borderwidth=0,
            indent=int(18 * scale),
            indicatorsize=int(12 * scale),
        )
        style.map(
            "Project.Treeview",
            background=[("selected", ACTIVE)],
            foreground=[("selected", "white")],
        )
        self.tree = ttk.Treeview(
            self.tree_frame,
            show="tree",
            selectmode="browse",
            style="Project.Treeview",
            takefocus=True,
        )
        self.tree.column("#0", width=250, minwidth=40, stretch=True)
        for part in ("trough", "thumb", "uparrow", "downarrow"):
            element = f"Project.Vertical.Scrollbar.{part}"
            if element not in style.element_names():
                style.element_create(
                    element, "from", "clam", f"Vertical.Scrollbar.{part}"
                )
        style.layout(
            "Project.Vertical.TScrollbar",
            [
                (
                    "Project.Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            (
                                "Project.Vertical.Scrollbar.uparrow",
                                {"side": "top", "sticky": ""},
                            ),
                            (
                                "Project.Vertical.Scrollbar.downarrow",
                                {"side": "bottom", "sticky": ""},
                            ),
                            (
                                "Project.Vertical.Scrollbar.thumb",
                                {"sticky": "nswe", "expand": True},
                            ),
                        ],
                    },
                )
            ],
        )
        style.configure(
            "Project.Vertical.TScrollbar",
            background=DIVIDER,
            troughcolor=NAVY,
            arrowcolor=MUTED,
            bordercolor=NAVY,
            lightcolor=DIVIDER,
            darkcolor=DIVIDER,
        )
        scroll = ttk.Scrollbar(
            self.tree_frame,
            orient="vertical",
            command=self.tree.yview,
            style="Project.Vertical.TScrollbar",
        )
        scroll.pack(side="right", fill="y")

        def scroll_state(first, last):
            scroll.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scroll.pack_forget()
            elif not scroll.winfo_manager():
                scroll.pack(side="right", fill="y", before=self.tree)

        self.tree.configure(yscrollcommand=scroll_state)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("state", foreground=MUTED)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<<TreeviewOpen>>", lambda _event: self.folder_icon(True))
        self.tree.bind("<<TreeviewClose>>", lambda _event: self.folder_icon(False))
        self.tree.bind("<Return>", self.activate)
        self.tree.bind("<Double-1>", self.activate)
        self.tree.bind("<Shift-F10>", self.spotlight)
        # Keep normal class keyboard navigation, but stop canvas/global bindings.
        self.tree.bindtags(
            (str(self.tree), "Treeview", "ProjectExplorer", str(app), "all")
        )
        for key in (
            "<Left>",
            "<Right>",
            "<Up>",
            "<Down>",
            "<Delete>",
            "<Control-a>",
            "<Control-d>",
        ):
            self.tree.bind_class("ProjectExplorer", key, lambda _event: "break")
        self.tip = Tooltip(self.tree, "")
        self.tree.bind("<Motion>", self.hover, add="+")
        self.message = tk.Label(
            self.panel,
            bg=NAVY,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=int(240 * scale),
        )
        self.message.pack(side="bottom", fill="x", padx=16, pady=10)
        self.panel.bind(
            "<Configure>",
            lambda event: self.message.configure(
                wraplength=max(40, event.width - int(32 * scale))
            ),
        )
        Tooltip(
            self.message,
            "Enter or double-click a focus to open Spotlight.\n"
            "Arrow keys select; Left/Right collapse/expand.\n"
            "Enter on a source file reveals its folder.",
        )
        self.refresh()

    def refresh(self):
        app = self.app
        signature = (
            id(app.focuses),
            app.focuses.revision,
            app._tree_id.get(),
            app._last_project_path,
            getattr(app, "_navigation_started", False),
            getattr(app, "_navigation_source", ""),
            app.workspace.main_tree.file_path,
            MOD.root,
            MOD.edit_focus_file,
            tuple(
                (t.get("tree_id"), t.get("file_path"), t.get("type"))
                for t in app._extra_trees
            ),
        )
        if signature != self._signature:
            self._signature = signature
            self.items = project_items(app, MOD)
            if not MOD.root:
                self.resources = tuple(
                    ExplorerItem(
                        f"unloaded:{item.key}",
                        item.key,
                        "Unavailable — load a mod to browse",
                        "state",
                    )
                    for item in self.items
                    if item.kind == "resource"
                )
            self._update_index()
        if self._resource_root != MOD.root:
            self._resource_root = root = MOD.root
            self.resources = ()
            self._focus_files = None
            self._focus_errors = ()
            self._discovery_generation += 1
            generation = self._discovery_generation
            if root:
                self.resources = tuple(
                    ExplorerItem(
                        f"loading:{item.key}",
                        item.key,
                        "Discovering source files…",
                        "state",
                    )
                    for item in self.items
                    if item.kind == "resource"
                )
                categories = tuple(
                    item
                    for item in self.items
                    if item.kind in ("resource", "tree_catalog")
                )

                def work():
                    return tuple(
                        (
                            item,
                            (
                                discover_focus_files(item.path)
                                if item.kind == "tree_catalog"
                                else discover_resources(item.path)
                            ),
                        )
                        for item in categories
                    )

                def done(results):
                    if MOD.root != root or generation != self._discovery_generation:
                        return
                    entries = []
                    for category, (paths, errors) in results:
                        if category.kind == "tree_catalog":
                            self._focus_files, self._focus_errors = paths, errors
                            for error in errors:
                                add_error(f"Focus-tree discovery: {error}")
                            continue
                        entries.extend(
                            ExplorerItem(
                                f"file:{path}",
                                category.key,
                                str(Path(path).relative_to(category.path)),
                                "file",
                                path,
                            )
                            for path in paths
                        )
                        for index, error in enumerate(errors):
                            add_error(f"Project explorer: {error}")
                            entries.append(
                                ExplorerItem(
                                    f"error:{category.key}:{index}",
                                    category.key,
                                    "Read failure — see error log",
                                    "state",
                                    detail=error,
                                )
                            )
                        if not paths and not errors:
                            entries.append(
                                ExplorerItem(
                                    f"empty:{category.key}",
                                    category.key,
                                    "No source files found",
                                    "state",
                                )
                            )
                    self.resources = tuple(entries)
                    self._update_index()

                run_bg(app, work, done)
            else:
                self.resources = tuple(
                    ExplorerItem(
                        f"unloaded:{item.key}",
                        item.key,
                        "Unavailable — load a mod to browse",
                        "state",
                    )
                    for item in self.items
                    if item.kind == "resource"
                )
            self._update_index()
        self.sync_selection()
        for label, accent in self.accents.items():
            active = label == app._editor_chrome.active_content
            accent.config(bg=BLUE if active else NAVY)
            app._editor_chrome.navigation_buttons[label].config(
                bg=ACTIVE if active else NAVY
            )

    def create_tree(self):
        if self.app._focus_editor.close():
            self.app._new_tree_dialog()

    def _update_index(self):
        self.catalog = focus_file_items(
            self.items, self._focus_files, self._focus_errors
        )
        self.by_key = {
            item.key: item for item in self.items + self.catalog + self.resources
        }
        self.render()

    def folder_icon(self, opened):
        key = self.tree.focus()
        if key == "project" and self.tree.exists(key):
            self.tree.item(
                key,
                image=self.item_icons[
                    "project_folder_open" if opened else "project_folder_closed"
                ],
            )

    def reload_resources(self):
        self._resource_root = object()
        self.refresh()

    def _update_search_hint(self):
        if (
            self.app._lp_search_var.get()
            or self.app.focus_get() is self.app._focus_search_entry
        ):
            self.search_hint.place_forget()
        else:
            self.search_hint.place(x=8, rely=0.5, anchor="w")

    def schedule_filter(self):
        self._update_search_hint()
        if self._job:
            self.app.after_cancel(self._job)
        self._job = self.app.after(120, self.render)

    def render(self):
        if self._job:
            self.app.after_cancel(self._job)
        self._job = None
        query = self.app._lp_search_var.get().strip()
        if not self._searching:
            self._expanded = (
                {
                    key
                    for key in self.by_key
                    if self.tree.exists(key) and self.tree.item(key, "open")
                }
                if self.tree.get_children()
                else self._expanded
            )
        new_keys = set(self.by_key) - self._known_keys
        self._expanded.update(key for key in new_keys if key.startswith("tree:"))
        self._known_keys = set(self.by_key)
        self._searching = bool(query)
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        if not self.items:
            self.tree_frame.pack_forget()
            self.empty.pack(fill="x")
            self.message.config(text="Everything for your mod, in one place.")
            return
        self.empty.pack_forget()
        self.tree_frame.pack(fill="both", expand=True)
        visible = filter_project(self.items + self.catalog + self.resources, query)
        # Parents precede children, including asynchronously discovered resources.
        for item in visible:
            icon_name = {
                "project": (
                    "project_folder_open"
                    if query or item.key in self._expanded
                    else "project_folder_closed"
                ),
                "tree": "file_focus_tree",
                "tree_file": "file_focus_tree",
                "tree_catalog": "nav_focus_trees",
                "focus": "item_focus",
                "file": "file_generic",
            }.get(item.kind)
            if item.kind == "resource":
                icon_name = {
                    "Localization": "file_localization",
                    "Graphics": "file_graphics",
                    "Scripted Effects": "file_scripted_effects",
                }[item.label]
            self.tree.insert(
                item.parent,
                "end",
                iid=item.key,
                text=" " + item.label,
                image=self.item_icons[icon_name] if icon_name else "",
                open=bool(query) or item.key in self._expanded,
                tags=("state",) if item.kind == "state" else (),
            )
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected)
        elif self.app.selected is not None:
            key = f"focus:{self.app.selected.id}"
            if self.tree.exists(key):
                self.tree.selection_set(key)
                self.tree.focus(key)
        self.message.config(
            text=(
                "No results. Try a name, ID or file path."
                if not visible
                else (
                    "Search project…"
                    if not query
                    else f"{len(visible)} items including groups"
                )
            )
        )
        self.sync_selection()

    def sync_selection(self, force=False):
        focus = self.app.selected
        focus_id = focus.id if focus else None
        if not force and focus_id == self._selected_id:
            return
        self._selected_id = focus_id
        if focus is None:
            return
        key = f"focus:{focus.id}"
        if self.tree.exists(key) and self.tree.selection() != (key,):
            self.tree.selection_set(key)
            self.tree.focus(key)
            self.tree.see(key)

    def select(self, _event=None):
        had_focus = self.app.focus_get() is self.tree
        keys = self.tree.selection()
        if not keys:
            return
        item = self.by_key.get(keys[0])
        if item is None:
            return
        if item.focus_id is not None and item.focus_id in self.app.focuses:
            focus = self.app.focuses[item.focus_id]
            if self.app.selected is not focus:
                if self.app._select(focus) is False:
                    self.sync_selection(force=True)
                    return
                self.app._center_on_focus(focus.id)
        elif item.kind == "tree":
            if not self.app._focus_editor.close():
                self.sync_selection(force=True)
                return
            child = next(
                (
                    entry
                    for entry in self.items
                    if entry.parent == item.key and entry.focus_id is not None
                ),
                None,
            )
            if child:
                focus = self.app.focuses.get(child.focus_id)
                if focus is not None:
                    self.app.offset[:] = [
                        self.app.cv.winfo_width() / 2 - focus.x * 96 * self.app.zoom,
                        self.app.cv.winfo_height() / 2 - focus.y * 130 * self.app.zoom,
                    ]
                    self.app._redraw()
        if had_focus:
            self.tree.focus_set()
        help_text = {
            "focus": "Enter: open Focus Spotlight",
            "file": "Enter: reveal source folder",
            "tree_file": "Enter or double-click: open focus tree",
            "tree_catalog": "All focus-tree files in this mod",
            "tree": "Left / Right: collapse or expand",
            "project": "Your loaded project and source resources",
            "resource": (
                "Browse existing source files"
                if item.path
                else "Load a mod to browse source files"
            ),
        }
        self.message.config(text=help_text.get(item.kind, item.label))

    def activate(self, event=None):
        if event is not None and event.type == tk.EventType.ButtonPress:
            if not self.tree.identify_row(event.y):
                return None
            region = self.tree.identify("element", event.x, event.y)
            if "indicator" in region:
                return None
        keys = self.tree.selection()
        item = self.by_key.get(keys[0]) if keys else None
        if item and item.kind == "focus":
            self.select()
            if self.app.selected and self.app.selected.id == item.focus_id:
                self.app._focus_actions.show(item.focus_id, keyboard=True)
        elif item and item.kind == "tree_file":
            self.app._import_txt(path=item.path)
        elif item and item.kind == "file":
            try:
                reveal_source(item.path)
            except OSError as exc:
                add_error(f"Cannot reveal {item.path}: {exc}")
                self.message.config(text=f"Cannot reveal source: {exc}")
        elif item and item.kind != "state":
            opened = not self.tree.item(item.key, "open")
            self.tree.item(item.key, open=opened)
            self.folder_icon(opened)
        return "break"

    def spotlight(self, _event=None):
        return self.activate()

    def first_result(self, _event=None):
        self.render()
        result = next(
            (
                item
                for item in filter_project(
                    self.items + self.catalog + self.resources,
                    self.app._lp_search_var.get(),
                )
                if item.kind in ("focus", "file", "tree_file")
            ),
            None,
        )
        if result:
            self.tree.selection_set(result.key)
            self.tree.focus(result.key)
            self.tree.see(result.key)
            self.tree.focus_set()
            self.select()
        return "break"

    def hover(self, event):
        key = self.tree.identify_row(event.y)
        if key != self._hover:
            self._hover = key
            self.tip._cancel()
            item = self.by_key.get(key)
            if item:
                self.tip.text = "\n".join(
                    part for part in (item.label, item.detail, item.path) if part
                )
                self.tip._schedule()

    def toggle(self):
        app = self.app
        if app._left_panel_visible:
            self._width = self.panel.winfo_width()
            self.panes.forget(self.panel)
        else:
            self.panes.add(
                self.panel,
                before=self.canvas_host,
                minsize=int(230 * self.scale),
                width=self._width,
                stretch="never",
            )
        app._left_panel_visible = not app._left_panel_visible
        app._sidebar_toggle_btn.config(
            image=self.collapse_icon if app._left_panel_visible else self.expand_icon
        )

    def close(self):
        if self._job:
            self.app.after_cancel(self._job)
            self._job = None
        self.tip._cancel()


__all__ = ["ProjectSidebar"]
