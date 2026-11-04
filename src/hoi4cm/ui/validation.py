"""Deduplicate validation inputs and keep at most one detached worker snapshot."""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass

from hoi4cm.core.i18n import get_language
from hoi4cm.focus_tree.validate import (
    capture_validation_snapshot,
    collect_loc_keys_from_file,
    validate_document,
)
from hoi4cm.ui.tasks import run_bg


@dataclass(frozen=True, eq=False)
class _ValidationKey:
    document: object
    catalog: object
    signature: tuple[object, ...]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _ValidationKey):
            return NotImplemented
        return (
            self.document is other.document
            and self.catalog is other.catalog
            and self.signature == other.signature
        )


def _file_stamp(path: str):
    try:
        stat = os.stat(path) if path else None
    except OSError:
        return None
    if stat is None:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)


class ValidationController:
    def __init__(self, owner) -> None:
        self._owner = owner
        self._completed: _ValidationKey | None = None
        self._running: _ValidationKey | None = None
        self._force_pending = False
        self._job = None
        self._poll_job = None
        self._closed = False
        owner._lifecycle.add_resource(self.close)

    def _key(self) -> _ValidationKey:
        owner = self._owner
        catalog = owner.index.graphics_catalog
        return _ValidationKey(
            owner.focuses,
            catalog,
            (
                owner.focuses.content_revision,
                owner.index.loaded,
                catalog.generation,
                owner.edit_loc_file,
                _file_stamp(owner.edit_loc_file),
                owner.app_config.loc_language,
                get_language(),
            ),
        )

    def start(self) -> None:
        self.schedule()
        if self._poll_job is None:
            self._poll_job = self._owner.after(1000, self._poll)

    def _poll(self) -> None:
        self._poll_job = None
        if not self._closed:
            self.schedule()
            self._poll_job = self._owner.after(1000, self._poll)

    def close(self) -> None:
        self._closed = True
        for job in (self._job, self._poll_job):
            if job is not None:
                try:
                    self._owner.after_cancel(job)
                except tk.TclError, RuntimeError:
                    pass
        self._job = self._poll_job = None

    def schedule(self) -> None:
        if self._closed or self._job is not None or self._running is not None:
            return
        if self._key() != self._completed:
            self._job = self._owner.after(150, self.run)

    def run(self, *, force: bool = False) -> None:
        if self._closed:
            return
        if self._job is not None:
            self._owner.after_cancel(self._job)
            self._job = None
        if self._running is not None:
            self._force_pending |= force
            return
        key = self._key()
        if not force and key == self._completed:
            return
        owner = self._owner
        owner._lifecycle.begin("validation")
        sprites = owner._validation_sprites()
        loc_path = owner.edit_loc_file
        snapshot = capture_validation_snapshot(owner.focuses)
        self._running = key

        def work():
            return validate_document(
                snapshot, sprites=sprites, loc_keys=collect_loc_keys_from_file(loc_path)
            )

        def done(issues):
            self._running = None
            if not self._closed and key == self._key():
                self._completed = key
                owner._apply_validation_result(issues)
                if getattr(owner, "_editor_chrome", None) is not None:
                    from hoi4cm.ui.editor_chrome import validation_completed

                    validation_completed(owner)
            self._continue()

        def failed(_error):
            self._running = None
            if not self._closed and (self._force_pending or key != self._key()):
                self._continue()

        run_bg(owner, work, done, on_error=failed, scope="validation")

    def _continue(self) -> None:
        if self._force_pending:
            self._force_pending = False
            self.run(force=True)
        else:
            self.schedule()


__all__ = ["ValidationController"]
