"""Bounded background recovery saves; all live state stays on Tk."""

from __future__ import annotations

from copy import deepcopy
from functools import partial
from pathlib import Path

from hoi4cm.core.logger import get_logger
from hoi4cm.editor.recovery import (
    RecoveryCommitGate,
    RecoveryResult,
    capture_recovery_snapshot,
    write_recovery,
)
from hoi4cm.editor.workspace_autosave import (
    sibling_autosave_path,
    workspace_autosave_path,
)
from hoi4cm.ui.tasks import run_bg

_log = get_logger("recovery")


class RecoveryController:
    def __init__(self, owner) -> None:
        self._owner = owner
        self._gate = RecoveryCommitGate()
        self._document: object = None
        self._token: object = None
        self._busy = False
        self._pending = False
        self._closed = False
        owner._lifecycle.add_resource(self.close)

    @property
    def busy(self) -> bool:
        return self._busy

    def invalidate(self) -> None:
        self._gate.invalidate()
        self._document = self._token = None
        self._pending = False

    def close(self) -> None:
        self._closed = True
        self.invalidate()

    def tick(self) -> None:
        if self._closed:
            return
        owner = self._owner
        owner._autosave_job = None
        try:
            if not owner._is_dirty():
                owner._autosave_failing = False
                owner._sibling_autosave_failing = None
                return
            if self._busy:
                self._pending = True
                return
            owner._capture_workspace()
            workspace = owner.workspace
            document = workspace.focuses
            primary = workspace_autosave_path()
            sibling = (
                sibling_autosave_path(owner._last_project_path)
                if owner._last_project_path
                else None
            )
            paths = (primary, sibling) if sibling else (primary,)
            metadata = {
                key: value for key, value in vars(workspace).items() if key != "focuses"
            }
            token = (document.content_revision, metadata, paths)
            if (
                self._document is document
                and self._token == token
                and all(Path(path).is_file() for path in paths)
            ):
                owner._autosave_failing = False
                owner._sibling_autosave_failing = None
                return
            self._token = None
            snapshot = capture_recovery_snapshot(
                workspace, paths, self._gate.generation
            )
            token = deepcopy(token)
            self._busy = True

            def done(result):
                self._busy = False
                if not self._closed and snapshot.generation == self._gate.generation:
                    if not result.cancelled:
                        self._report(result, sibling)
                        if (
                            result.primary_error is None
                            and result.sibling_error is None
                        ):
                            self._document = document
                            self._token = token
                if self._pending and not self._closed:
                    self._pending = False
                    owner._cancel_autosave()
                    self.tick()

            run_bg(
                owner,
                partial(write_recovery, snapshot, self._gate),
                done,
                on_error=lambda error: done(RecoveryResult(primary_error=error)),
            )
        except Exception as error:
            self._busy = False
            self._report(RecoveryResult(primary_error=error), None)
        finally:
            owner._schedule_autosave()

    def _report(self, result: RecoveryResult, sibling: str | None) -> None:
        owner = self._owner
        if result.primary_error is not None:
            error = result.primary_error
            _log.error("workspace autosave failed: %s", error)
            if not getattr(owner, "_autosave_failing", False):
                owner._autosave_failing = True
                owner._log_error(f"Workspace autosave failed: {error}")
            return
        owner._autosave_failing = False
        if result.sibling_error is not None:
            error = result.sibling_error
            _log.error("sibling autosave failed for %s: %s", sibling, error)
            if getattr(owner, "_sibling_autosave_failing", None) != sibling:
                owner._sibling_autosave_failing = sibling
                owner._log_error(f"Sibling autosave failed for {sibling}: {error}")
        else:
            owner._sibling_autosave_failing = None


def invalidate_recovery(owner) -> None:
    controller = vars(owner).get("_recovery")
    if controller is not None:
        controller.invalidate()


__all__ = ["RecoveryController", "invalidate_recovery"]
