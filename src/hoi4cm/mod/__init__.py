"""Mod context — the discovered-mod assets singleton the whole app reads.

The :class:`~hoi4cm.mod.context.ModContext` instance lives at module level as
``MOD`` for back-compat with the rest of the codebase. Wizard code reads
``MOD.sprites``, ``MOD.idea_ids``, etc. just like it did in the monolith.
"""

from hoi4cm.mod.context import ModContext, detect_loc_file, find_loc_files
from hoi4cm.mod.graphics_catalog import (
    AssetRef,
    GraphicsCatalog,
    GraphicsScanConfig,
)
from hoi4cm.mod.workspace_files import (
    WorkspaceFiles,
    WriteEntry,
    notifying_workspace_files,
)

# Module-level singleton. Lazily constructed on first import so any code that
# does ``from hoi4cm.mod import MOD`` gets the same instance.
MOD = ModContext()


__all__ = [
    "AssetRef",
    "GraphicsCatalog",
    "GraphicsScanConfig",
    "ModContext",
    "MOD",
    "WorkspaceFiles",
    "WriteEntry",
    "detect_loc_file",
    "find_loc_files",
    "notifying_workspace_files",
]
