"""Shared Tk-shell doubles for headless UI mixin tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hoi4cm.ui.mod_loading import ModLoadingMixin


class _FakeTcl:
    def call(self, *_args: object) -> object:
        return ()


class ModLoadingAppFake(ModLoadingMixin):
    """Small host shared by mod-loading tests that exercise the same mixin."""

    _lifecycle: Any
    _mod_lbl: Any
    cv: Any
    _focus_bundles: dict[int, Any]
    after_calls: list[tuple[int, Callable[[], None]]]
    visibility_updates: int
    dropdown_refreshes: int
    status_updates: int
    invalidations: int
    redraws: int
    _apply_md_visibility: Any
    _refresh_mod_dropdowns: Any
    _update_statusbar: Any
    _invalidate_canvas_images: Any
    _redraw_now: Any

    def __init__(self) -> None:
        self._lifecycle = None
        self._config_write_warned = False
        self._mod_image_resource_registered = False
        self._focus_bundles: dict[int, object] = {}
        self.callbacks: list[Callable[[], None]] = []
        self.loaded_roots: list[str] = []
        self.after_calls = []
        self._mod_lbl = None
        self.cv = None
        self.visibility_updates = 0
        self.dropdown_refreshes = 0
        self.status_updates = 0
        self.invalidations = 0
        self.redraws = 0
        self.tk = _FakeTcl()

    def after(self, _milliseconds: int, callback: Callable[[], None]) -> object:
        self.callbacks.append(callback)
        return callback

    def after_cancel(self, identifier: object) -> None:
        self.callbacks = [cb for cb in self.callbacks if cb is not identifier]

    def winfo_exists(self) -> int:
        return 1

    def _on_mod_loaded(self, root: str) -> None:
        self.loaded_roots.append(root)

    def flush(self) -> None:
        while self.callbacks:
            self.callbacks.pop(0)()
