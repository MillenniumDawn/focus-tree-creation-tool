from __future__ import annotations

import threading
import time
from collections.abc import Callable

from hoi4cm.wizards._image_loader import TkImageLoader


class FakeOwner:
    def __init__(self) -> None:
        self.exists = True
        self.callbacks: list[Callable[[], None]] = []
        self.cancelled: list[object] = []

    def after(self, milliseconds: int, callback: Callable[[], None]) -> object:
        self.callbacks.append(callback)
        return len(self.callbacks)

    def winfo_exists(self) -> int:
        return int(self.exists)

    def after_cancel(self, identifier: object) -> None:
        self.cancelled.append(identifier)

    def bind(
        self,
        sequence: str,
        callback: Callable[[object], None],
        add: str | None = None,
    ) -> object:
        return None

    def run_next(self) -> None:
        self.callbacks.pop(0)()


def _run_until_applied(owner: FakeOwner, applied: list[object | None]) -> None:
    deadline = time.monotonic() + 2
    while not applied and time.monotonic() < deadline:
        if owner.callbacks:
            owner.run_next()
        time.sleep(0.001)
    assert applied


def test_photo_realization_and_apply_run_on_tk_thread() -> None:
    owner = FakeOwner()
    tk_thread = threading.get_ident()
    decode_threads: list[int] = []
    realize_threads: list[int] = []
    apply_threads: list[int] = []
    applied: list[object | None] = []
    loader = TkImageLoader(owner, poll_interval=0)

    def decode(item: str) -> object:
        decode_threads.append(threading.get_ident())
        return object()

    def realize(decoded: object) -> object:
        realize_threads.append(threading.get_ident())
        return decoded

    def apply(item: str, image: object | None) -> None:
        apply_threads.append(threading.get_ident())
        applied.append(image)

    loader.submit("image", decode, realizer=realize, apply=apply)
    _run_until_applied(owner, applied)

    assert decode_threads
    assert all(thread != tk_thread for thread in decode_threads)
    assert realize_threads == [tk_thread]
    assert apply_threads == [tk_thread]


def test_invalidated_callback_is_not_realized_or_applied() -> None:
    owner = FakeOwner()
    gate = threading.Event()
    realized: list[object] = []
    applied: list[object | None] = []
    loader = TkImageLoader(owner, poll_interval=0)

    def decode(item: str) -> object:
        gate.wait(timeout=2)
        return object()

    def realize(decoded: object) -> object:
        realized.append(decoded)
        return decoded

    loader.submit(
        "image",
        decode,
        realizer=realize,
        apply=lambda item, image: applied.append(image),
    )
    loader.invalidate()
    gate.set()
    deadline = time.monotonic() + 2
    while owner.callbacks and time.monotonic() < deadline:
        owner.run_next()
        time.sleep(0.001)

    assert realized == []
    assert applied == []


def test_destroyed_owner_drops_queued_callback() -> None:
    owner = FakeOwner()
    decoded = threading.Event()
    realized: list[object] = []
    applied: list[object | None] = []
    loader = TkImageLoader(owner, poll_interval=0)

    def decode(item: str) -> object:
        decoded.set()
        return object()

    def realize(decoded: object) -> object:
        realized.append(decoded)
        return decoded

    loader.submit(
        "image",
        decode,
        realizer=realize,
        apply=lambda item, image: applied.append(image),
    )
    assert decoded.wait(timeout=2)
    owner.exists = False
    owner.run_next()

    assert realized == []
    assert applied == []


def test_close_cancels_poll_and_drops_worker_result() -> None:
    owner = FakeOwner()
    gate = threading.Event()
    applied: list[object | None] = []
    loader = TkImageLoader(owner, poll_interval=0)
    loader.submit(
        "image",
        lambda item: gate.wait(timeout=2) or object(),
        realizer=lambda image: image,
        apply=lambda item, image: applied.append(image),
    )

    loader.close()
    gate.set()

    assert owner.cancelled == [1]
    assert applied == []
