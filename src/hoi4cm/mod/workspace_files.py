from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def _relax_permissions(path: str) -> None:
    """Widen NamedTemporaryFile's 0600 to the process default (0666 & ~umask).

    Without this, every atomically-written mod file lands owner-only, unlike
    a plain ``open(...)`` write.
    """
    mask = os.umask(0)
    os.umask(mask)
    try:
        os.chmod(path, 0o666 & ~mask)
    except OSError:
        pass


class WorkspaceFiles:
    def __init__(self, *, on_written: Callable[[str], None] | None = None) -> None:
        self._on_written = on_written

    def write_text(self, path: str | Path, text: str, *, encoding: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding=encoding,
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(text)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = temporary.name
            _relax_permissions(temporary_path)
            os.replace(temporary_path, target)
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
        self._notify(target)

    def append_text(self, path: str | Path, text: str, *, encoding: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding=encoding) as stream:
            stream.write(text)
        self._notify(target)

    def _notify(self, path: Path) -> None:
        if self._on_written is not None:
            self._on_written(str(path))


__all__ = ["WorkspaceFiles"]
