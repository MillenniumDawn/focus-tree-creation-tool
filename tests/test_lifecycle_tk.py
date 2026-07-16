from __future__ import annotations

import tkinter as tk

import pytest

from hoi4cm.ui.lifecycle import ApplicationLifecycle


def test_close_cancels_delayed_tk_callback_before_destroy() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    lifecycle = ApplicationLifecycle(root)
    called: list[bool] = []
    lifecycle.after(root, 1, lambda: called.append(True))

    lifecycle.close()
    root.destroy()

    assert called == []
