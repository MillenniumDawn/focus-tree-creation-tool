"""Tests for hoi4cm.ui.widgets._safe_after / _safe_after_idle.

Headless: no real Tk widget is created. A fake widget stands in for one,
with `winfo_exists()` / `after()` / `after_idle()` that can raise the
destroyed-widget errors the helpers swallow.
"""

import _tkinter

import pytest

from hoi4cm.ui.widgets import _safe_after, _safe_after_idle


class FakeWidget:
    def __init__(self, exists=True, fail_after=False):
        self._exists = exists
        self._fail_after = fail_after
        self.scheduled = []
        self.calls = []

    def winfo_exists(self):
        if not self._exists:
            raise _tkinter.TclError("bad window path name")
        return self._exists

    def after(self, ms, fn):
        if self._fail_after:
            raise _tkinter.TclError("invalid command name")
        self.scheduled.append(("after", ms, fn))
        fn()

    def after_idle(self, fn):
        if self._fail_after:
            raise _tkinter.TclError("invalid command name")
        self.scheduled.append(("idle", fn))
        fn()


def test_safe_after_runs_fn_when_widget_exists():
    widget = FakeWidget()
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))

    assert calls == ["ran"]
    assert widget.scheduled == [("after", 100, widget.scheduled[0][2])]


def test_safe_after_idle_runs_fn_when_widget_exists():
    widget = FakeWidget()
    calls = []

    _safe_after_idle(widget, lambda: calls.append("ran"))

    assert calls == ["ran"]


def test_safe_after_skips_fn_when_widget_destroyed():
    widget = FakeWidget(exists=False)
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))

    assert calls == []


def test_safe_after_idle_skips_fn_when_widget_destroyed():
    widget = FakeWidget(exists=False)
    calls = []

    _safe_after_idle(widget, lambda: calls.append("ran"))

    assert calls == []


def test_safe_after_swallows_error_from_after_call():
    widget = FakeWidget(fail_after=True)
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))

    assert calls == []


def test_safe_after_idle_swallows_error_from_after_idle_call():
    widget = FakeWidget(fail_after=True)
    calls = []

    _safe_after_idle(widget, lambda: calls.append("ran"))

    assert calls == []


def test_safe_after_does_not_swallow_fn_errors():
    class RaisingWidget(FakeWidget):
        def winfo_exists(self):
            return True

    widget = RaisingWidget()
    with pytest.raises(ValueError, match="boom"):
        _safe_after(widget, 0, lambda: (_ for _ in ()).throw(ValueError("boom")))
