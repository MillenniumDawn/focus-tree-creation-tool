from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from concurrent.futures import Executor, Future
from dataclasses import dataclass


@dataclass(frozen=True)
class _WorkItem:
    future: Future[object]
    work: Callable[[], object]


class DaemonThreadPoolExecutor(Executor):
    def __init__(self, max_workers: int = 2, *, thread_name_prefix: str) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix
        self._queue: queue.Queue[_WorkItem | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._shutdown = False

    def submit(
        self, fn: Callable[..., object], /, *args: object, **kwargs: object
    ) -> Future[object]:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("cannot schedule new futures after shutdown")
            self._start_workers_locked()
            future: Future[object] = Future()
            self._queue.put(_WorkItem(future, lambda: fn(*args, **kwargs)))
            return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        with self._lock:
            if not self._shutdown:
                self._shutdown = True
                if cancel_futures:
                    self._cancel_pending_locked()
                for _ in self._threads:
                    self._queue.put(None)
            threads = tuple(self._threads)
        if wait:
            for thread in threads:
                thread.join()

    def _start_workers_locked(self) -> None:
        if self._threads:
            return
        for index in range(self._max_workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"{self._thread_name_prefix}_{index}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _cancel_pending_locked(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is not None:
                item.future.cancel()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            if not item.future.set_running_or_notify_cancel():
                continue
            try:
                result = item.work()
            except BaseException as error:
                item.future.set_exception(error)
            else:
                item.future.set_result(result)


__all__ = ["DaemonThreadPoolExecutor"]
