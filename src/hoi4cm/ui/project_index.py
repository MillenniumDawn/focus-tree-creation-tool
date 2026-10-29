"""Read-only project navigation snapshots, independent of Tk and exporters."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from hoi4cm.core.i18n import tr
from hoi4cm.core.paths import read_file_with_encoding

_TREE_DECLARATION = re.compile(
    r'"[^"\n]*"?|#[^\n]*|(?P<tree>\b(?:focus_tree|shared_focus|joint_focus|focus)\s*=\s*\{)'
)


@dataclass(frozen=True)
class ExplorerItem:
    key: str
    parent: str
    label: str
    kind: str
    path: str = ""
    focus_id: int | None = None
    detail: str = ""
    icon: str = ""
    search_text: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self, "search_text", f"{self.label} {self.path} {self.detail}".casefold()
        )


def project_items(app, mod) -> tuple[ExplorerItem, ...]:
    """Use document ownership, never infer countries from filenames."""
    project = getattr(app, "_last_project_path", None) or ""
    started = getattr(
        app,
        "_navigation_started",
        bool(
            project
            or app.workspace.main_tree.file_path
            or app.focuses
            or app._extra_trees
        ),
    )
    source = getattr(app, "_navigation_source", app.workspace.main_tree.file_path) or ""
    root_path = mod.root or project or source
    if not (root_path or started or app.focuses or app._extra_trees):
        return ()
    name = (
        (mod.mod_name or Path(mod.root).name)
        if mod.root
        else Path(project or source).stem
    )
    items = [
        ExplorerItem(
            "project",
            "",
            name or tr("explorer.untitled_project", "Untitled project"),
            "project",
            root_path,
        ),
        ExplorerItem(
            "focus-trees",
            "project",
            tr("nav.focus_trees", "Focus Trees"),
            "tree_catalog",
            str(Path(mod.root) / "common" / "national_focus") if mod.root else "",
        ),
    ]
    trees = [(0, app._tree_id.get(), source, "main")] if started else []
    trees.extend(
        (
            index,
            tree.get("tree_id", ""),
            tree.get("file_path", ""),
            tree.get("type", ""),
        )
        for index, tree in enumerate(app._extra_trees, 1)
    )
    known = {tree[0] for tree in trees}
    trees.extend(
        (
            index,
            tr("explorer.unregistered_tree", "Unregistered tree {index}", index=index),
            "",
            tr("explorer.ownership_unavailable", "ownership unavailable"),
        )
        for index in app.focuses.tree_membership
        if index not in known
    )
    grouped = {}
    for index, tree_id, path, kind in trees:
        key = f"tree:{index}"
        grouped[index] = (key, path)
        items.append(
            ExplorerItem(
                key,
                "focus-trees",
                tree_id or tr("explorer.untitled_tree", "Untitled tree"),
                "tree",
                path,
                detail=kind,
            )
        )
    for focus in app.focuses.values():
        parent, path = grouped[focus.tree_idx]
        items.append(
            ExplorerItem(
                f"focus:{focus.id}",
                parent,
                focus.loc_name or focus.name,
                "focus",
                path,
                focus.id,
                focus.name,
            )
        )
    for index, (parent, _path) in grouped.items():
        if not app.focuses.tree_membership.get(index):
            items.append(
                ExplorerItem(
                    f"empty-tree:{index}",
                    parent,
                    tr(
                        "explorer.no_focuses",
                        "No focuses yet — use {button}",
                        button=tr("toolbar.add_focus", "+ Focus"),
                    ),
                    "state",
                )
            )
    for label, relative, icon in (
        (
            tr("explorer.resource.localization", "Localization"),
            "localisation",
            "file_localization",
        ),
        (tr("explorer.resource.graphics", "Graphics"), "gfx", "file_graphics"),
        (
            tr("explorer.resource.scripted_effects", "Scripted Effects"),
            "common/scripted_effects",
            "file_scripted_effects",
        ),
    ):
        path = str(Path(mod.root) / relative) if mod.root else ""
        items.append(
            ExplorerItem(
                f"resource:{relative}", "project", label, "resource", path, icon=icon
            )
        )
    return tuple(items)


def focus_file_items(items, paths=None, errors=()) -> tuple[ExplorerItem, ...]:
    """List unopened source files once, alongside the existing loaded trees."""
    category = next((item for item in items if item.kind == "tree_catalog"), None)
    if category is None:
        return ()
    if not category.path:
        return (
            ExplorerItem(
                "trees:unloaded",
                category.key,
                tr("explorer.tree_files.unloaded", "Load a mod to browse other trees"),
                "state",
            ),
        )
    if paths is None:
        return (
            ExplorerItem(
                "trees:loading",
                category.key,
                tr("explorer.tree_files.loading", "Discovering focus-tree files…"),
                "state",
            ),
        )
    loaded = {
        os.path.normcase(os.path.abspath(item.path))
        for item in items
        if item.kind == "tree" and item.path
    }
    entries = [
        ExplorerItem(
            f"tree-file:{path}",
            category.key,
            str(Path(path).relative_to(category.path)),
            "tree_file",
            path,
            detail=tr(
                "explorer.tree_files.unopened",
                "Unopened focus-tree file — Enter or double-click to open",
            ),
        )
        for path in paths
        if Path(path).suffix.casefold() == ".txt"
        and os.path.normcase(os.path.abspath(path)) not in loaded
    ]
    entries.extend(
        ExplorerItem(
            f"trees:error:{index}",
            category.key,
            tr("explorer.read_failure", "Read failure — see error log"),
            "state",
            detail=error,
        )
        for index, error in enumerate(errors)
    )
    if not entries and not any(item.kind == "tree" for item in items):
        entries.append(
            ExplorerItem(
                "trees:empty",
                category.key,
                tr(
                    "explorer.tree_files.none",
                    "No focus-tree files found — create a new tree",
                ),
                "state",
            )
        )
    return tuple(entries)


def filter_project(
    items: tuple[ExplorerItem, ...], query: str
) -> tuple[ExplorerItem, ...]:
    """Match cached text and retain ancestors; matching groups retain children."""
    query = query.strip().casefold()
    if not query:
        return items
    by_key = {item.key: item for item in items}
    matches = {item.key for item in items if query in item.search_text}
    visible = set(matches)
    for item in items:
        if item.parent in matches:
            matches.add(item.key)
            visible.add(item.key)
    for key in tuple(visible):
        parent = by_key[key].parent
        while parent and parent not in visible:
            visible.add(parent)
            parent = by_key[parent].parent
    return tuple(item for item in items if item.key in visible)


def discover_resources(path: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """List source files without reading/writing them; preserve scan failures."""
    files: list[str] = []
    errors: list[str] = []
    try:
        with os.scandir(path):
            pass
    except FileNotFoundError:
        return (), ()
    except OSError as exc:
        return (), (str(exc),)
    for directory, dirs, names in os.walk(
        path, onerror=lambda exc: errors.append(str(exc))
    ):
        dirs.sort(key=str.casefold)
        files.extend(
            str(Path(directory) / name) for name in sorted(names, key=str.casefold)
        )
    return tuple(files), tuple(errors)


def discover_focus_files(path: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Exclude utility tables without parsing/building every focus in the mod."""
    paths, scan_errors = discover_resources(path)
    files, errors = [], list(scan_errors)
    for source in paths:
        if Path(source).suffix.casefold() != ".txt":
            continue
        text, encoding = read_file_with_encoding(source)
        if text is None or encoding is None:
            errors.append(f"Cannot read focus-tree source: {source}")
        elif any(match.group("tree") for match in _TREE_DECLARATION.finditer(text)):
            files.append(source)
    return tuple(files), tuple(errors)


__all__ = [
    "ExplorerItem",
    "discover_resources",
    "discover_focus_files",
    "filter_project",
    "focus_file_items",
    "project_items",
]
