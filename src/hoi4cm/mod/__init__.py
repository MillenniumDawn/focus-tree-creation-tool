"""Mod discovery: a pure asset index plus GFX helpers.

The loaded index, user settings, and PhotoImage cache are owned by the App.
This package does not construct a process-wide mix of those lifetimes.
"""

from hoi4cm.mod.context import detect_loc_file, find_loc_files
from hoi4cm.mod.gfx_writer import (
    DEFAULT_FOCUS_ICON,
    SpriteTypeEntry,
    append_sprite_types,
    build_focus_sprite_entries,
    build_sprite_type,
    resolve_focus_image_paths,
    resolve_mod_texture_path,
)
from hoi4cm.mod.graphics_catalog import (
    AssetRef,
    GraphicsCatalog,
    GraphicsScanConfig,
)
from hoi4cm.mod.index import ModIndex, ScanSettings
from hoi4cm.mod.workspace_files import (
    WorkspaceFiles,
    WriteEntry,
    notifying_workspace_files,
)

__all__ = [
    "AssetRef",
    "DEFAULT_FOCUS_ICON",
    "GraphicsCatalog",
    "GraphicsScanConfig",
    "ModIndex",
    "ScanSettings",
    "SpriteTypeEntry",
    "WorkspaceFiles",
    "WriteEntry",
    "append_sprite_types",
    "build_focus_sprite_entries",
    "build_sprite_type",
    "detect_loc_file",
    "find_loc_files",
    "notifying_workspace_files",
    "resolve_focus_image_paths",
    "resolve_mod_texture_path",
]
