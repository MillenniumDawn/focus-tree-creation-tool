from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable, Iterable
from pathlib import Path

from hoi4cm.core.logger import get_logger

_log = get_logger("workspace_files")

# (path, text, encoding) — one file in a grouped write.
WriteEntry = tuple[str | Path, str, str]


def _open_temporary_file(target: Path) -> tuple[Path, int]:
    for _ in range(100):
        path = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
        try:
            return path, os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            continue
    raise FileExistsError(f"could not create a temporary file for {target}")


def _unlink(path: Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _read_bytes(target: Path) -> bytes | None:
    """Snapshot ``target`` for rollback, or ``None`` if it does not exist yet."""
    try:
        return target.read_bytes()
    except FileNotFoundError:
        return None


def _stage(target: Path, text: str, encoding: str) -> Path:
    """Write ``text`` to a sibling temp file, fully flushed to disk.

    Everything that can reasonably fail — a missing parent, an unwritable
    directory, a bad encoding, a full disk — fails here, before the target
    itself is touched.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target_mode: int | None
    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        target_mode = None
    temporary_path, descriptor = _open_temporary_file(target)
    try:
        if target_mode is not None:
            os.chmod(temporary_path, target_mode)
        with os.fdopen(descriptor, "w", encoding=encoding) as temporary:
            descriptor = -1
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
    except BaseException:
        if descriptor != -1:
            os.close(descriptor)
        _unlink(temporary_path)
        raise
    return temporary_path


def _restore(committed: list[tuple[Path, bytes | None]]) -> None:
    """Best-effort undo of the swaps a failed group write already made."""
    for target, backup in reversed(committed):
        try:
            if backup is None:
                _unlink(target)
            else:
                target.write_bytes(backup)
        except OSError:
            _log.error("could not roll back %s after a failed group write", target)


class WorkspaceFiles:
    def __init__(self, *, on_written: Callable[[str], None] | None = None) -> None:
        self._on_written = on_written

    def write_text(self, path: str | Path, text: str, *, encoding: str) -> None:
        """Replace ``path`` with ``text`` atomically (temp file + ``os.replace``)."""
        self.write_texts([(path, text, encoding)])

    def write_texts(self, entries: Iterable[WriteEntry]) -> None:
        """Replace several files as one all-or-nothing group.

        Every temp file is written and fsynced before the first one is swapped
        in, so the usual failures abort while all targets still hold their old
        contents. If a swap fails part-way through anyway, the targets already
        swapped are restored from the snapshots taken just before the swap.
        """
        pending = [(Path(path), text, encoding) for path, text, encoding in entries]
        if not pending:
            return
        # A lone target has nothing to roll back to: os.replace either happened
        # or it did not. Skipping the snapshot keeps single writes as cheap as
        # they were before grouping existed.
        keep_backups = len(pending) > 1
        staged: list[tuple[Path, Path]] = []
        committed: list[tuple[Path, bytes | None]] = []
        try:
            for target, text, encoding in pending:
                staged.append((_stage(target, text, encoding), target))
            for temporary, target in staged:
                backup = _read_bytes(target) if keep_backups else None
                os.replace(temporary, target)
                committed.append((target, backup))
        except BaseException:
            if keep_backups:
                _restore(committed)
            raise
        finally:
            for temporary, _target in staged:
                _unlink(temporary)
        for _temporary, target in staged:
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


def notifying_workspace_files(mod, mod_root) -> WorkspaceFiles:
    """A ``WorkspaceFiles`` that tells the mod's catalog what it writes.

    The ``on_written`` callback fires only when the save target is inside the
    currently loaded mod, so writing into some other folder never pokes the
    live catalog. This is the seam that keeps newly written images / .gfx
    files visible without a full rescan.
    """
    on_written = None
    root = getattr(mod, "root", "") or ""
    if getattr(mod, "loaded", False) and root and mod_root:
        same_mod = os.path.normcase(os.path.abspath(root)) == os.path.normcase(
            os.path.abspath(mod_root)
        )
        if same_mod:
            on_written = mod.note_file_written
    return WorkspaceFiles(on_written=on_written)


__all__ = ["WorkspaceFiles", "WriteEntry", "notifying_workspace_files"]
