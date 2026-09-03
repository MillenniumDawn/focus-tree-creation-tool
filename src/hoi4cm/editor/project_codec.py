from __future__ import annotations

import json
import ntpath
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hoi4cm.core.safe_path import safe_join
from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.models import (
    EditorWorkspace,
    Focus,
    FocusDocument,
    TreeDocument,
    TreeMetadata,
)

PROJECT_FORMAT = "hoi4cm-project"
PROJECT_VERSION = 2
_KNOWN_ROOT_KEYS = {"format", "version", "workspace", "tree_name", "focuses"}
_SEMANTIC_FOCUS_ATTRS = (
    "_raw_gx",
    "_raw_gy",
    "_rel_dx",
    "_rel_dy",
    "_joint_extra",
    "_script_extras",
)


def encode_project(workspace: EditorWorkspace) -> dict[str, Any]:
    data = dict(workspace.extras)
    data.update(
        {
            "format": PROJECT_FORMAT,
            "version": PROJECT_VERSION,
            "workspace": {
                **workspace.workspace_extras,
                "main_tree": _encode_tree(workspace.main_tree),
                "extra_trees": [_encode_tree(tree) for tree in workspace.extra_trees],
                "focuses": [
                    _encode_focus(focus) for focus in workspace.focuses.values()
                ],
                "canvas": {
                    **workspace.canvas_extras,
                    "min": list(workspace.canvas_min),
                    "max": list(workspace.canvas_max),
                },
                "default_focus_prefix": workspace.default_focus_prefix,
            },
        }
    )
    return data


def decode_project(data: Mapping[str, Any]) -> EditorWorkspace:
    rejected_paths: list[str] = []
    format_name = data.get("format")
    if format_name is not None:
        if format_name != PROJECT_FORMAT:
            raise ValueError(f"unsupported project format: {format_name!r}")
        if data.get("version") != PROJECT_VERSION:
            raise ValueError(f"unsupported project version: {data.get('version')!r}")
        if not isinstance(data.get("workspace"), Mapping):
            raise ValueError("project workspace must be an object")
        workspace = _decode_v2(data, rejected_paths)
    elif data.get("version") == PROJECT_VERSION and isinstance(
        data.get("workspace"), Mapping
    ):
        workspace = _decode_v2(data, rejected_paths)
    else:
        workspace = _decode_legacy(data)
    workspace.__dict__["_rejected_file_paths"] = tuple(rejected_paths)
    return workspace


def write_project(path: str | Path, workspace: EditorWorkspace) -> None:
    """Save the project atomically — a failed write leaves the old file intact."""
    text = json.dumps(encode_project(workspace), indent=2)
    WorkspaceFiles().write_text(path, text, encoding="utf-8")


def read_project(path: str | Path) -> EditorWorkspace:
    with open(path, encoding="utf-8") as file:
        return decode_project(json.load(file))


def _encode_focus(focus: Focus) -> dict[str, Any]:
    data = focus.to_dict()
    for attr in _SEMANTIC_FOCUS_ATTRS:
        if hasattr(focus, attr):
            data[attr] = getattr(focus, attr)
    return data


def _encode_tree(tree: TreeDocument) -> dict[str, Any]:
    data = dict(tree.extras)
    data.update(
        {
            "metadata": {**tree.metadata_extras, **asdict(tree.metadata)},
            "tree_type": tree.tree_type,
            "file_path": tree.file_path,
            "had_wrapper": tree.had_wrapper,
            "focus_ids": sorted(tree.focus_ids),
        }
    )
    return data


def _decode_v2(data: Mapping[str, Any], rejected_paths: list[str]) -> EditorWorkspace:
    raw_workspace = data["workspace"]
    raw_canvas = raw_workspace.get("canvas", {})
    if not isinstance(raw_canvas, Mapping):
        raw_canvas = {}
    canvas_min = _pair(raw_canvas.get("min"), (0, 0))
    canvas_max = _pair(raw_canvas.get("max"), (9, 9))
    return EditorWorkspace(
        focuses=FocusDocument(
            Focus.from_dict(focus) for focus in raw_workspace.get("focuses", [])
        ),
        main_tree=_decode_tree(
            raw_workspace.get("main_tree", {}), "main", rejected_paths
        ),
        extra_trees=[
            _decode_tree(tree, tree.get("tree_type", "shared"), rejected_paths)
            for tree in raw_workspace.get("extra_trees", [])
        ],
        canvas_min=canvas_min,
        canvas_max=canvas_max,
        canvas_extras={
            key: value for key, value in raw_canvas.items() if key not in {"min", "max"}
        },
        default_focus_prefix=raw_workspace.get("default_focus_prefix", ""),
        workspace_extras={
            key: value
            for key, value in raw_workspace.items()
            if key
            not in {
                "main_tree",
                "extra_trees",
                "focuses",
                "canvas",
                "default_focus_prefix",
            }
        },
        extras={
            key: value for key, value in data.items() if key not in _KNOWN_ROOT_KEYS
        },
    )


def _decode_legacy(data: Mapping[str, Any]) -> EditorWorkspace:
    metadata = TreeMetadata(tree_id=data.get("tree_name", "TAG_focus_tree"))
    return EditorWorkspace(
        focuses=FocusDocument(
            Focus.from_dict(focus, legacy=True) for focus in data.get("focuses", [])
        ),
        main_tree=TreeDocument(metadata=metadata),
        extras={
            key: value
            for key, value in data.items()
            if key not in {"tree_name", "focuses"}
        },
    )


def _decode_tree(
    data: Mapping[str, Any], default_type: str, rejected_paths: list[str]
) -> TreeDocument:
    metadata_data = data.get("metadata", {})
    if not isinstance(metadata_data, Mapping):
        metadata_data = {}
    metadata_fields = TreeMetadata.__dataclass_fields__
    metadata = TreeMetadata(
        **{key: value for key, value in metadata_data.items() if key in metadata_fields}
    )
    known = {"metadata", "tree_type", "file_path", "had_wrapper", "focus_ids"}
    raw_file_path = data.get("file_path", "")
    file_path = validate_project_file_path(raw_file_path)
    if raw_file_path and not file_path:
        path_text = str(raw_file_path)
        if path_text not in rejected_paths:
            rejected_paths.append(path_text)
    return TreeDocument(
        metadata=metadata,
        tree_type=data.get("tree_type", default_type),
        file_path=file_path,
        had_wrapper=bool(data.get("had_wrapper", True)),
        focus_ids=set(data.get("focus_ids", [])),
        metadata_extras={
            key: value
            for key, value in metadata_data.items()
            if key not in metadata_fields
        },
        extras={key: value for key, value in data.items() if key not in known},
    )


def validate_project_file_path(
    path: object, base: str | os.PathLike[str] | None = None
) -> str:
    if isinstance(path, os.PathLike):
        path = os.fspath(path)
    if not isinstance(path, str) or not path:
        return ""
    normalized = path.replace("\\", "/")
    if ".." in normalized.split("/"):
        return ""
    if ntpath.splitdrive(path)[0] and not os.path.isabs(path):
        return ""
    if os.path.isabs(path) or ntpath.isabs(path) or normalized.startswith("/"):
        if base is None or not os.path.isabs(path):
            return ""
    if base is None:
        return path
    try:
        return safe_join(base, normalized)
    except OSError, TypeError, ValueError:
        return ""


def _pair(value: object, default: tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return int(value[0]), int(value[1])
    return default


__all__ = [
    "PROJECT_FORMAT",
    "PROJECT_VERSION",
    "decode_project",
    "validate_project_file_path",
    "encode_project",
    "read_project",
    "write_project",
]
