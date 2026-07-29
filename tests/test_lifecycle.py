from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Executor, Future

from hoi4cm.ui.lifecycle import ApplicationLifecycle, DaemonThreadPoolExecutor


class FakeTkOwner:
    def __init__(self) -> None:
        self.exists = True
        self.callbacks: dict[object, Callable[[], None]] = {}
        self.cancelled: list[object] = []

    def after(self, milliseconds: int, callback: Callable[[], None]) -> object:
        identifier = f"after-{len(self.callbacks)}"
        self.callbacks[identifier] = callback
        return identifier

    def after_cancel(self, identifier: object) -> None:
        self.cancelled.append(identifier)
        self.callbacks.pop(identifier, None)

    def winfo_exists(self) -> int:
        return int(self.exists)


class FakeExecutor(Executor):
    def __init__(self) -> None:
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        future.set_result(fn(*args, **kwargs))
        return future

    def shutdown(self, wait=True, *, cancel_futures=False) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


def test_stale_generation_callback_is_not_applied() -> None:
    owner = FakeTkOwner()
    lifecycle = ApplicationLifecycle(owner)
    token = lifecycle.token("document")
    called: list[str] = []

    lifecycle.after(owner, 0, lambda: called.append("old"), token=token)
    lifecycle.invalidate("document")
    callback = next(iter(owner.callbacks.values()))
    callback()

    assert called == []


def test_close_cancels_after_jobs_closes_resources_and_executor() -> None:
    owner = FakeTkOwner()
    executor = FakeExecutor()
    lifecycle = ApplicationLifecycle(owner, executor_factory=lambda: executor)
    closed: list[str] = []
    lifecycle.add_resource(lambda: closed.append("resource"))
    lifecycle.after(owner, 100, lambda: None)
    assert lifecycle.executor is executor

    lifecycle.close()

    assert lifecycle.accepting is False
    assert owner.callbacks == {}
    assert owner.cancelled == ["after-0"]
    assert closed == ["resource"]
    assert executor.shutdown_calls == [(False, True)]


def test_daemon_executor_close_does_not_wait_for_running_work() -> None:
    executor = DaemonThreadPoolExecutor(1, thread_name_prefix="test-daemon")
    started = threading.Event()
    release = threading.Event()

    def work() -> None:
        started.set()
        release.wait(timeout=2)

    future = executor.submit(work)
    assert started.wait(timeout=1)

    before = time.monotonic()
    executor.shutdown(wait=False, cancel_futures=True)
    elapsed = time.monotonic() - before
    release.set()
    future.result(timeout=1)

    assert elapsed < 0.1
    assert all(thread.daemon for thread in executor._threads)


def test_close_rejects_new_executor_work() -> None:
    lifecycle = ApplicationLifecycle()
    lifecycle.close()

    try:
        executor = lifecycle.executor
    except RuntimeError as error:
        assert str(error) == "application is closing"
    else:
        raise AssertionError(f"closed lifecycle returned executor {executor!r}")
