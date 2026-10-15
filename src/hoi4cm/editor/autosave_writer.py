"""Synchronous recovery writes, deduplicated by document and metadata state."""

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from hoi4cm.models import EditorWorkspace

from .project_codec import serialize_project, write_project_text


class AutosaveWriter:
    """Keep only the last successful token, never another full focus snapshot."""

    def __init__(self) -> None:
        self._document: object = None
        self._token: object = None

    def save(
        self,
        workspace: EditorWorkspace,
        paths: tuple[str, ...],
        sibling_error: Callable[[], None],
    ) -> bool:
        metadata = {k: v for k, v in vars(workspace).items() if k != "focuses"}
        token = (workspace.focuses.revision, metadata, paths)
        if (
            self._document is workspace.focuses
            and self._token == token
            and all(Path(path).is_file() for path in paths)
        ):
            return False
        # Any partial attempt invalidates the previous pair, even if edits revert.
        self._token = None
        text = serialize_project(workspace)
        for index, path in enumerate(paths):
            try:
                write_project_text(path, text)
            except Exception:
                if index == 0:
                    raise
                sibling_error()
                return True  # Retry the complete recovery pair next tick.
        self._document = workspace.focuses
        self._token = deepcopy(token)
        return True
