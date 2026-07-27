from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from hoi4cm.ui.lifecycle import find_lifecycle


class TkOwner(Protocol):
    def after(self, milliseconds: int, callback: Callable[[], None]) -> object: ...

    def after_cancel(self, identifier: object) -> None: ...

    def winfo_exists(self) -> int: ...

    def bind(
        self,
        sequence: str,
        callback: Callable[[object], None],
        add: str | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class _ImageResult:
    generation: int
    decoded: object | None
    realizer: Callable[[object], object]
    apply: Callable[[object | None], None]


@dataclass(frozen=True)
class _BatchDone:
    generation: int


_QueueItem = _ImageResult | _BatchDone
_Item = TypeVar("_Item")


class TkImageLoader:
    def __init__(self, owner: TkOwner, *, poll_interval: int = 16) -> None:
        self._owner = owner
        self._poll_interval = poll_interval
        self._owner_thread = threading.get_ident()
        self._generation = 0
        self._pending_batches = 0
        self._poll_scheduled = False
        self._poll_job: object | None = None
        self._closed = False
        self._results: queue.SimpleQueue[_QueueItem] = queue.SimpleQueue()
        self._remove_resource: Callable[[], None] | None = None
        lifecycle = find_lifecycle(owner)
        if lifecycle is not None:
            self._remove_resource = lifecycle.add_resource(self.close)
        try:
            owner.bind("<Destroy>", self._on_destroy, add="+")
        except AttributeError, RuntimeError, tk.TclError:
            pass

    def submit_many(
        self,
        items: Iterable[_Item],
        decoder: Callable[[_Item], object | None],
        *,
        realizer: Callable[[object], object],
        apply: Callable[[_Item, object | None], None],
    ) -> None:
        self._require_owner_thread()
        batch = tuple(items)
        if not batch or self._closed:
            return

        generation = self._generation
        self._pending_batches += 1
        self._schedule_poll()

        def load() -> None:
            for item in batch:
                if self._closed:
                    return
                if generation != self._generation:
                    self._results.put(_BatchDone(generation))
                    return
                try:
                    decoded = decoder(item)
                except Exception:
                    decoded = None
                if self._closed:
                    return
                if generation != self._generation:
                    self._results.put(_BatchDone(generation))
                    return
                self._results.put(
                    _ImageResult(
                        generation,
                        decoded,
                        realizer,
                        lambda image, value=item: apply(value, image),
                    )
                )
            self._results.put(_BatchDone(generation))

        threading.Thread(target=load, daemon=True).start()

    def submit(
        self,
        item: _Item,
        decoder: Callable[[_Item], object | None],
        *,
        realizer: Callable[[object], object],
        apply: Callable[[_Item, object | None], None],
    ) -> None:
        self.submit_many((item,), decoder, realizer=realizer, apply=apply)

    def invalidate(self) -> None:
        self._require_owner_thread()
        self._generation += 1

    def close(self) -> None:
        self._require_owner_thread()
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        if self._remove_resource is not None:
            self._remove_resource()
            self._remove_resource = None
        if self._poll_job is not None:
            try:
                self._owner.after_cancel(self._poll_job)
            except AttributeError, RuntimeError, tk.TclError:
                pass
            self._poll_job = None
        self._poll_scheduled = False
        self._discard_results()

    def _schedule_poll(self) -> None:
        if self._poll_scheduled:
            return
        self._poll_scheduled = True
        try:
            self._poll_job = self._owner.after(self._poll_interval, self._poll)
        except AttributeError, RuntimeError, tk.TclError:
            self._closed = True
            self._poll_scheduled = False

    def _poll(self) -> None:
        self._require_owner_thread()
        self._poll_scheduled = False
        self._poll_job = None
        if self._closed or not self._owner_exists():
            self._closed = True
            self._discard_results()
            return

        while True:
            try:
                result = self._results.get_nowait()
            except queue.Empty:
                break
            if isinstance(result, _BatchDone):
                self._pending_batches -= 1
                continue
            if result.generation != self._generation:
                continue
            image = None
            if result.decoded is not None:
                try:
                    image = result.realizer(result.decoded)
                except Exception:
                    image = None
            if not self._owner_exists():
                self._closed = True
                self._discard_results()
                return
            result.apply(image)

        if self._pending_batches:
            self._schedule_poll()

    def _owner_exists(self) -> bool:
        try:
            return bool(self._owner.winfo_exists())
        except Exception:
            return False

    def _discard_results(self) -> None:
        while True:
            try:
                self._results.get_nowait()
            except queue.Empty:
                break
        self._pending_batches = 0

    def _require_owner_thread(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("Tk image callbacks must run on the owner thread")

    def _on_destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is self._owner:
            self.close()


__all__ = ["TkImageLoader"]
