from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path


def _open_temporary_file(target: Path) -> tuple[Path, int]:
    for _ in range(100):
        path = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
        try:
            return path, os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            continue
    raise FileExistsError(f"could not create a temporary file for {target}")


class WorkspaceFiles:
    def __init__(self, *, on_written: Callable[[str], None] | None = None) -> None:
        self._on_written = on_written

    def write_text(self, path: str | Path, text: str, *, encoding: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_mode = stat.S_IMODE(target.stat().st_mode)
        except FileNotFoundError:
            target_mode = None
        temporary_path: Path | None = None
        descriptor: int | None = None
        try:
            temporary_path, descriptor = _open_temporary_file(target)
            if target_mode is not None:
                os.chmod(temporary_path, target_mode)
            with os.fdopen(descriptor, "w", encoding=encoding) as temporary:
                descriptor = None
                temporary.write(text)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
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
