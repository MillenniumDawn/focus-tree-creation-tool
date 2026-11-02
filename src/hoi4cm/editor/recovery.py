"""Owned recovery data and generation-checked atomic replacements."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from hoi4cm.editor.project_codec import encode_project
from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.models import EditorWorkspace


@dataclass(frozen=True)
class RecoverySnapshot:
    content: bytes
    paths: tuple[str, ...]
    generation: int


@dataclass(frozen=True)
class RecoveryResult:
    cancelled: bool = False
    primary_error: Exception | None = None
    sibling_error: Exception | None = None


class RecoveryCommitGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1

    def commit(self, generation: int, replace: Callable[[], None]) -> bool:
        with self._lock:
            if generation != self._generation:
                return False
            replace()
            return True


def capture_recovery_snapshot(
    workspace: EditorWorkspace, paths: tuple[str, ...], generation: int
) -> RecoverySnapshot:
    text = json.dumps(encode_project(workspace), separators=(",", ":"))
    return RecoverySnapshot(text.encode("utf-8"), paths, generation)


class _RecoveryCancelled(Exception):
    pass


def write_recovery_bytes(
    path: str, content: bytes, *, gate: RecoveryCommitGate, generation: int
) -> None:
    with WorkspaceFiles().stage_bytes(path, content) as replace:
        if not gate.commit(generation, replace):
            raise _RecoveryCancelled


def write_recovery(
    snapshot: RecoverySnapshot, gate: RecoveryCommitGate
) -> RecoveryResult:
    for index, path in enumerate(snapshot.paths):
        if snapshot.generation != gate.generation:
            return RecoveryResult(cancelled=True)
        try:
            write_recovery_bytes(
                path, snapshot.content, gate=gate, generation=snapshot.generation
            )
        except _RecoveryCancelled:
            return RecoveryResult(cancelled=True)
        except Exception as error:
            if index == 0:
                return RecoveryResult(primary_error=error)
            return RecoveryResult(sibling_error=error)
    return RecoveryResult()


__all__ = [
    "RecoveryCommitGate",
    "RecoveryResult",
    "RecoverySnapshot",
    "capture_recovery_snapshot",
    "write_recovery",
    "write_recovery_bytes",
]
