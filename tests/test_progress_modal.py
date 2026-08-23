"""Headless tests for cooperative cancel. Does not construct Tk widgets."""

from hoi4cm.focus_tree.batch_load import make_cancel_handle


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
