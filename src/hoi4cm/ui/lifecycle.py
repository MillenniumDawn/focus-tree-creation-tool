from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from typing import Protocol

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor
from hoi4cm.core.logger import get_logger

log = get_logger("lifecycle")


class TclInterpreter(Protocol):
    def call(self, *args: object) -> object: ...


class TkOwner(Protocol):
    tk: TclInterpreter

    def after(self, milliseconds: int, callback: Callable[[], None]) -> object: ...

    def after_cancel(self, identifier: object) -> None: ...

    def winfo_exists(self) -> int: ...


@dataclass(frozen=True)
class GenerationToken:
    scope: str
    value: int


class ApplicationLifecycle:
    def __init__(
        self,
        owner: TkOwner | None = None,
        *,
        executor_factory: Callable[[], Executor] | None = None,
    ) -> None:
        self._owner = owner
        self._executor_factory = executor_factory or (
            lambda: DaemonThreadPoolExecutor(
                max_workers=2, thread_name_prefix="hoi4cm-bg"
            )
        )
        self._executor: Executor | None = None
        self._accepting = True
        self._finished = False
        self._generations: dict[str, int] = {}
        self._scope_futures: dict[str, set[Future]] = {}
        self._after_jobs: list[tuple[TkOwner, object]] = []
        self._resources: list[Callable[[], None]] = []
        self._lock = threading.RLock()

    @property
    def accepting(self) -> bool:
        with self._lock:
            return self._accepting

    @property
    def executor(self) -> Executor:
        with self._lock:
            if not self._accepting:
                raise RuntimeError("application is closing")
            if self._executor is None:
                self._executor = self._executor_factory()
            return self._executor

    def token(self, scope: str = "application") -> GenerationToken:
        with self._lock:
            return GenerationToken(scope, self._generations.get(scope, 0))

    def begin(self, scope: str) -> GenerationToken:
        self.invalidate(scope)
        return self.token(scope)

    def invalidate(self, scope: str) -> None:
        with self._lock:
            self._generations[scope] = self._generations.get(scope, 0) + 1
            futures = tuple(self._scope_futures.pop(scope, ()))
        for future in futures:
            future.cancel()

    def is_current(self, token: GenerationToken) -> bool:
        with self._lock:
            current = self._generations.get(token.scope, 0)
            return self._accepting and current == token.value

    def track_future(self, future: Future, token: GenerationToken) -> None:
        with self._lock:
            if (
                not self._accepting
                or self._generations.get(token.scope, 0) != token.value
            ):
                cancel = True
            else:
                self._scope_futures.setdefault(token.scope, set()).add(future)
                future.add_done_callback(
                    lambda completed: self._forget_future(token.scope, completed)
                )
                cancel = False
        if cancel:
            future.cancel()

    def add_resource(self, close: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            if not self._accepting:
                close()
                return lambda: None
            self._resources.append(close)

        def remove() -> None:
            with self._lock:
                try:
                    self._resources.remove(close)
                except ValueError:
                    pass

        return remove

    def after(
        self,
        owner: TkOwner,
        milliseconds: int,
        callback: Callable[[], None],
        *,
        token: GenerationToken | None = None,
    ) -> object | None:
        with self._lock:
            if not self._accepting:
                return None
        active_token = token or self.token()
        job: object | None = None

        def guarded() -> None:
            if job is not None:
                self._forget_after(owner, job)
            if self.is_current(active_token) and self._owner_exists(owner):
                callback()

        try:
            job = owner.after(milliseconds, guarded)
        except (AttributeError, RuntimeError, tk.TclError):
            return None
        with self._lock:
            if self._accepting:
                self._after_jobs.append((owner, job))
            else:
                self._cancel_after(owner, job)
        return job

    def begin_close(self) -> bool:
        with self._lock:
            if not self._accepting:
                return False
            self._accepting = False
            for scope in tuple(self._generations):
                self._generations[scope] += 1
            futures = tuple(
                future
                for scope_futures in self._scope_futures.values()
                for future in scope_futures
            )
            self._scope_futures.clear()
        for future in futures:
            future.cancel()
        return True

    def finish_close(self) -> None:
        self.begin_close()
        with self._lock:
            if self._finished:
                return
            self._finished = True
            jobs = tuple(self._after_jobs)
            self._after_jobs.clear()
            resources = tuple(reversed(self._resources))
            self._resources.clear()
            executor = self._executor
            self._executor = None

        for owner, job in jobs:
            self._cancel_after(owner, job)
        self._cancel_tk_after_jobs()
        for close in resources:
            try:
                close()
            except Exception:
                log.exception("resource close failed")
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def close(self) -> None:
        self.begin_close()
        self.finish_close()

    def _forget_after(self, owner: TkOwner, job: object) -> None:
        with self._lock:
            try:
                self._after_jobs.remove((owner, job))
            except ValueError:
                pass

    def _forget_future(self, scope: str, future: Future) -> None:
        with self._lock:
            futures = self._scope_futures.get(scope)
            if futures is not None:
                futures.discard(future)
                if not futures:
                    self._scope_futures.pop(scope, None)

    @staticmethod
    def _owner_exists(owner: TkOwner) -> bool:
        try:
            return bool(owner.winfo_exists())
        except (AttributeError, RuntimeError, tk.TclError):
            return False

    @staticmethod
    def _cancel_after(owner: TkOwner, job: object) -> None:
        try:
            owner.after_cancel(job)
        except (AttributeError, RuntimeError, tk.TclError):
            pass

    def _cancel_tk_after_jobs(self) -> None:
        owner = self._owner
        if owner is None:
            return
        try:
            jobs = owner.tk.call("after", "info")
        except (AttributeError, RuntimeError, tk.TclError):
            return
        for job in jobs if isinstance(jobs, tuple) else ():
            self._cancel_after(owner, job)


def find_lifecycle(owner: object | None) -> ApplicationLifecycle | None:
    current = owner
    while current is not None:
        lifecycle = getattr(current, "_lifecycle", None)
        if isinstance(lifecycle, ApplicationLifecycle):
            return lifecycle
        current = getattr(current, "master", None)
    return None


__all__ = [
    "ApplicationLifecycle",
    "DaemonThreadPoolExecutor",
    "GenerationToken",
    "find_lifecycle",
]
