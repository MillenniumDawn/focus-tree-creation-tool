"""Tests for cooperative cancel and the progress modal grab lifecycle."""

import tkinter as tk

import pytest

from hoi4cm.focus_tree.batch_load import make_cancel_handle
from hoi4cm.ui.tasks import progress_modal


def test_non_cancellable_handle_ignores_request_cancel():
    handle = make_cancel_handle()
    handle.request_cancel()
    assert not handle.cancelled.is_set()


def test_cancellable_handle_sets_flag_and_notifies_once():
    calls = []
    handle = make_cancel_handle(cancellable=True, on_cancel=lambda: calls.append(1))
    handle.request_cancel()
    handle.request_cancel()
    assert handle.cancelled.is_set()
    assert calls == [1]


def test_cancellable_handle_works_without_callback():
    handle = make_cancel_handle(cancellable=True)
    handle.request_cancel()
    assert handle.cancelled.is_set()


@pytest.mark.visible_tk
def test_progress_modal_grabs_only_once_viewable(tk_root, monkeypatch):
    # Tk issues a real XGrabPointer only while a mouse button is down, and the
    # server refuses it on an unmapped window. Check the cause, not the mouse.
    grab_set = tk.Misc.grab_set
    viewable_at_grab = []

    def spy(self):
        viewable_at_grab.append(self.winfo_viewable())
        grab_set(self)

    monkeypatch.setattr(tk.Misc, "grab_set", spy)
    modal = progress_modal(tk_root, "Progress")
    try:
        assert viewable_at_grab == [1]
    finally:
        modal.close()


def test_progress_modal_does_not_wait_on_withdrawn_window(tk_root):
    # The conftest shim withdraws every Toplevel, which can never become viewable.
    modal = progress_modal(tk_root, "Progress")
    modal.close()
    assert tk_root.grab_current() is None
    assert not any(isinstance(c, tk.Toplevel) for c in tk_root.winfo_children())


@pytest.mark.visible_tk
def test_progress_modal_grab_lifecycle(tk_root):
    before = set(tk_root.winfo_children())
    modal = None
    try:
        modal = progress_modal(tk_root, "Progress", cancellable=True)
        tk_root.update()
        grabbed = tk_root.grab_current()
        assert grabbed is not None
        assert isinstance(grabbed, tk.Toplevel)

        modal.request_cancel()
        assert modal.cancelled.is_set()
        assert tk_root.grab_current() == grabbed

        modal.close()
        modal = None
        tk_root.update()
        assert tk_root.grab_current() is None
    finally:
        if modal is not None:
            modal.close()
        for child in tk_root.winfo_children():
            if child in before or not isinstance(child, tk.Toplevel):
                continue
            try:
                child.grab_release()
            except tk.TclError:
                pass
            try:
                child.destroy()
            except tk.TclError:
                pass
