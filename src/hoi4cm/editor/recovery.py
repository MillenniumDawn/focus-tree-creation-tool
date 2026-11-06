"""Owned recovery data and generation-checked atomic replacements."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from hoi4cm.editor.project_codec import encode_project
from hoi4cm.editor.recovery_eligibility import (
    RECOVERY_KEY,
    RecoveryEligibilityError,
    activate_recovery,
    complete_recovery,
    new_recovery_token,
    recovery_is_eligible,
    revoke_recovery,
)
from hoi4cm.mod.workspace_files import WorkspaceFiles
from hoi4cm.models import EditorWorkspace


@dataclass(frozen=True)
class RecoverySnapshot:
    content: bytes
    paths: tuple[str, ...]
    generation: int
    eligibility: str | None = None


@dataclass(frozen=True)
class RecoveryResult:
    cancelled: bool = False
    primary_error: Exception | None = None
    sibling_error: Exception | None = None


class RecoveryCommitGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._eligibility: str | None = None
        self._registered = False

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            token = self._eligibility
        if token is not None:
            revoke_recovery(token)
            self._eligibility = None
            self._registered = False

    def eligibility(self) -> str:
        """Called on Tk only; retain the successful lease until invalidation."""
        if self._registered and not self.is_eligible():
            self._eligibility = None
            self._registered = False
        if self._eligibility is None:
            self._eligibility = new_recovery_token()
        return self._eligibility

    def activate(self, paths: tuple[str, ...]) -> None:
        if not self._registered:
            activate_recovery(self.eligibility(), paths)
            self._registered = True

    def is_eligible(self) -> bool:
        return self._eligibility is not None and recovery_is_eligible(self._eligibility)

    def commit(self, generation: int, replace: Callable[[], None]) -> bool:
        with self._lock:
            if generation != self._generation:
                return False
        replace()
        with self._lock:
            return generation == self._generation


def capture_recovery_snapshot(
    workspace: EditorWorkspace,
    paths: tuple[str, ...],
    generation: int,
    *,
    eligibility: str | None = None,
) -> RecoverySnapshot:
    data = encode_project(workspace)
    if eligibility is not None:
        data = {
            RECOVERY_KEY: eligibility,
            **{key: value for key, value in data.items() if key != RECOVERY_KEY},
        }
    text = json.dumps(data, separators=(",", ":"))
    return RecoverySnapshot(text.encode("utf-8"), paths, generation, eligibility)


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
    token = snapshot.eligibility
    if token is None or not snapshot.content.startswith(
        ('{"' + RECOVERY_KEY + '":"' + token + '"').encode("utf-8")
    ):
        return RecoveryResult(
            primary_error=RecoveryEligibilityError(
                "Asynchronous recovery requires an eligible recovery snapshot"
            )
        )
    for index, path in enumerate(snapshot.paths):
        if snapshot.generation != gate.generation or (
            snapshot.eligibility is not None
            and not recovery_is_eligible(snapshot.eligibility)
        ):
            return RecoveryResult(cancelled=True)
        try:
            write_recovery_bytes(
                path, snapshot.content, gate=gate, generation=snapshot.generation
            )
            if snapshot.eligibility is not None and not recovery_is_eligible(
                snapshot.eligibility
            ):
                return RecoveryResult(cancelled=True)
            if snapshot.eligibility is not None:
                complete_recovery(snapshot.eligibility)
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
