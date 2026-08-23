"""Tk tests for cancellable progress_modal."""

from __future__ import annotations

import tkinter as tk

from hoi4cm.core.i18n import tr
from hoi4cm.ui.tasks import progress_modal


def _collect_texts(win: tk.Misc) -> list[str]:
    texts: list[str] = []
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        try:
            texts.append(cur.cget("text"))
        except tk.TclError:
            pass
        try:
            stack.extend(cur.winfo_children())
        except tk.TclError:
            pass
    return texts


def _find_button(win: tk.Misc, text: str) -> tk.Button:
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and cur.cget("text") == text:
            return cur
        try:
            stack.extend(cur.winfo_children())
        except tk.TclError:
            pass
    raise AssertionError(f"no button with text {text!r}")


def _modal_window(root: tk.Tk) -> tk.Toplevel:
    wins = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    assert len(wins) == 1
    return wins[0]


def test_default_progress_modal_has_no_cancel_button(tk_root):
    modal = progress_modal(tk_root, "Import")
    try:
        tk_root.update_idletasks()
        win = _modal_window(tk_root)
        texts = _collect_texts(win)
        assert tr("common.cancel", "Cancel") not in texts
        assert not modal.cancelled.is_set()
        modal.request_cancel()
        assert not modal.cancelled.is_set()
        assert win.winfo_exists()
        assert tk_root.grab_current() == win
    finally:
        modal.close()


def test_cancellable_modal_requests_cancel_without_closing(tk_root):
    modal = progress_modal(tk_root, "Load All Trees", cancellable=True)
    try:
        tk_root.update_idletasks()
        win = _modal_window(tk_root)
        button = _find_button(win, tr("common.cancel", "Cancel"))
        button.invoke()
        tk_root.update_idletasks()
        assert modal.cancelled.is_set()
        assert win.winfo_exists()
        assert tk_root.grab_current() == win
        assert button.cget("state") == "disabled"
        assert button.cget("text") == tr("common.cancelling", "Cancelling...")
    finally:
        modal.close()


def test_cancellable_modal_window_close_requests_cancel(tk_root):
    modal = progress_modal(tk_root, "Load All Trees", cancellable=True)
    try:
        tk_root.update_idletasks()
        win = _modal_window(tk_root)
        handler = win.protocol("WM_DELETE_WINDOW")
        assert handler
        win.tk.call(handler)
        tk_root.update_idletasks()
        assert modal.cancelled.is_set()
        assert win.winfo_exists()
        assert tk_root.grab_current() == win
    finally:
        modal.close()
