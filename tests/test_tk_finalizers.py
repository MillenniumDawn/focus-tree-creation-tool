"""Keep deferred Tk garbage on the Tk thread before pool work starts."""

from __future__ import annotations

import gc
import threading
import tkinter as tk

from hoi4cm.core.concurrency import DaemonThreadPoolExecutor

_FINALIZED_ON: list[int] = []


class _TrackedPhotoImage(tk.PhotoImage):
    def __del__(self):
        _FINALIZED_ON.append(threading.get_ident())
        super().__del__()


def test_1_defer_tk_finalizer_until_fixture_teardown(tk_root):
    gc.disable()
    image = _TrackedPhotoImage(master=tk_root, width=1, height=1)
    cycle: list[object] = [image]
    cycle.append(cycle)
    del image, cycle


def test_2_worker_does_not_finalize_deferred_tk_image(tk_root):
    try:
        main_thread_id = threading.main_thread().ident
        assert main_thread_id is not None
        assert _FINALIZED_ON == [main_thread_id]

        executor = DaemonThreadPoolExecutor(2, thread_name_prefix="tk-finalizer")
        try:
            worker_id = executor.submit(threading.get_ident).result(timeout=5)
            executor.submit(gc.collect).result(timeout=5)
        finally:
            executor.shutdown()

        assert worker_id != main_thread_id
        assert _FINALIZED_ON == [main_thread_id]
    finally:
        gc.enable()
