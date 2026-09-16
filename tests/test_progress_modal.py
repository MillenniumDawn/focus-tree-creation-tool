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
