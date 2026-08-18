from __future__ import annotations

import os

from hoi4cm.core.paths import autosave_path

AUTOSAVE_NAME = "workspace.json"


def workspace_autosave_path(name: str = AUTOSAVE_NAME) -> str:
    return autosave_path(name)


def sibling_autosave_path(project_path: str) -> str:
    # ".autosave.json" sibling next to the chosen project file — C extension
    # keeps crash recovery beside the user's save while the global
    # ~/.hoi4cm/autosave/workspace.json remains the primary restore source.
    if project_path.endswith(".json"):
        return project_path[: -len(".json")] + ".autosave.json"
    return project_path + ".autosave.json"


def clear_workspace_autosave(path: str | None = None) -> None:
    p = path or workspace_autosave_path()
    try:
        os.unlink(p)
    except OSError:
        pass


__all__ = ["AUTOSAVE_NAME", "clear_workspace_autosave", "workspace_autosave_path"]
