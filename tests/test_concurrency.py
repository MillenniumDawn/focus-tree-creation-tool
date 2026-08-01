"""Tests for hoi4cm.core.concurrency.DaemonThreadPoolExecutor.

Headless, no Tk: the executor is pure threading + queue. Tests wait on the
returned Future instead of sleeping, and always shut the executor down so
daemon threads don't leak across tests.
"""

import threading
import time

import pytest

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor


def test_submit_runs_work_and_returns_result():
    with DaemonThreadPoolExecutor(max_workers=2, thread_name_prefix="t") as ex:
        future = ex.submit(lambda: 1 + 1)
        assert future.result(timeout=5) == 2


def test_submit_passes_args_and_kwargs():
    with DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t") as ex:
        future = ex.submit(lambda a, b, c=0: a + b + c, 1, 2, c=3)
        assert future.result(timeout=5) == 6


def test_submit_work_raising_sets_future_exception():
    with DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t") as ex:
        future = ex.submit(lambda: 1 / 0)
        with pytest.raises(ZeroDivisionError):
            future.result(timeout=5)


def test_shutdown_waits_for_inflight_work():
    done = threading.Event()

    def work():
        time.sleep(0.01)
        done.set()
        return "ok"

    ex = DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t")
    future = ex.submit(work)
    ex.shutdown(wait=True)
    assert done.is_set()
    assert future.result() == "ok"


def test_submit_after_shutdown_raises():
    ex = DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t")
    ex.shutdown()
    with pytest.raises(RuntimeError):
        ex.submit(lambda: None)


def test_cancel_futures_cancels_pending():
    started = threading.Event()
    gate = threading.Event()

    def slow(x):
        if x == "first":
            started.set()
        gate.wait(timeout=5)
        return x

    ex = DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t")
    first = ex.submit(slow, "first")
    # Wait until the single worker has dequeued `first`, so only `pending`
    # is still in the queue and gets cancelled by cancel_futures.
    assert started.wait(timeout=5)
    pending = ex.submit(slow, "pending")
    ex.shutdown(wait=False, cancel_futures=True)
    gate.set()
    assert pending.cancelled()
    assert first.result(timeout=5) == "first"


def test_threads_are_daemon():
    ex = DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="t")
    try:
        future = ex.submit(threading.current_thread)
        worker_thread = future.result(timeout=5)
        assert isinstance(worker_thread, threading.Thread)
        assert worker_thread.daemon is True
    finally:
        ex.shutdown()


def test_thread_name_prefix():
    ex = DaemonThreadPoolExecutor(max_workers=1, thread_name_prefix="hoi4cm-test")
    try:
        future = ex.submit(threading.current_thread)
        worker_thread = future.result(timeout=5)
        assert isinstance(worker_thread, threading.Thread)
        assert worker_thread.name.startswith("hoi4cm-test_")
    finally:
        ex.shutdown()


def test_multiple_workers_run_concurrently():
    import collections

    seen = collections.deque()
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def work(i):
        barrier.wait(timeout=5)
        with lock:
            seen.append(i)
        return i

    ex = DaemonThreadPoolExecutor(max_workers=2, thread_name_prefix="t")
    try:
        f1 = ex.submit(work, 1)
        f2 = ex.submit(work, 2)
        f1.result(timeout=5)
        f2.result(timeout=5)
    finally:
        ex.shutdown()
    # Both workers crossed the barrier, so they ran on separate threads.
    assert sorted(seen) == [1, 2]


def test_invalid_max_workers_raises():
    with pytest.raises(ValueError):
        DaemonThreadPoolExecutor(max_workers=0, thread_name_prefix="t")
