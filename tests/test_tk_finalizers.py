"""Keep deferred Tk garbage on the Tk thread before pool work starts."""

from __future__ import annotations

import gc
import threading
import tkinter as tk

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor


class _TrackedPhotoImage(tk.PhotoImage):
    _finalized_on: list[int] | None = None

    def __del__(self):
        if self._finalized_on is not None:
            self._finalized_on.append(threading.get_ident())
        super().__del__()


def _defer_cyclic_image(tk_root: tk.Misc, finalized_on: list[int]) -> None:
    image = _TrackedPhotoImage(master=tk_root, width=1, height=1)
    image._finalized_on = finalized_on
    cycle: list[object] = [image]
    cycle.append(cycle)
    del image, cycle


def test_defer_tk_finalizer_until_fixture_teardown(tk_root):
    finalized_on: list[int] = []
    gc.disable()
    try:
        _defer_cyclic_image(tk_root, finalized_on)
        assert finalized_on == []
    finally:
        gc.enable()


def test_worker_does_not_finalize_deferred_tk_image(tk_root):
    finalized_on: list[int] = []
    main_thread_id = threading.main_thread().ident
    assert main_thread_id is not None
    gc.disable()
    try:
        _defer_cyclic_image(tk_root, finalized_on)
        gc.collect()
        assert finalized_on == [main_thread_id]

        executor = DaemonThreadPoolExecutor(2, thread_name_prefix="tk-finalizer")
        try:
            worker_id = executor.submit(threading.get_ident).result(timeout=5)
            executor.submit(gc.collect).result(timeout=5)
        finally:
            executor.shutdown()

        assert worker_id != main_thread_id
        assert finalized_on == [main_thread_id]
    finally:
        gc.enable()
