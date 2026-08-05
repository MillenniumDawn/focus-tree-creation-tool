"""Tests for hoi4cm.ui.widgets._safe_after / _safe_after_idle.

Headless: no real Tk widget is created. A fake widget stands in for one,
with `winfo_exists()` / `after()` / `after_idle()` that can raise the
destroyed-widget errors the helpers swallow.
"""

import _tkinter

import pytest

from hoi4cm.ui.widgets import _safe_after, _safe_after_idle


class FakeWidget:
    """Stand-in for a Tk widget; `after`/`after_idle` fire straight away.

    A destroyed widget reports `winfo_exists() == 0` like Tk does;
    `exists_raises=True` covers the rarer case where the lookup itself
    blows up. `defer=True` queues the guarded callback instead of running
    it, so a test can destroy the widget between scheduling and firing,
    which is the race the wrappers exist for.
    """

    def __init__(self, exists=True, fail_after=False, defer=False, exists_raises=False):
        self._exists = exists
        self._fail_after = fail_after
        self._defer = defer
        self._exists_raises = exists_raises
        self.scheduled = []
        self.calls = []

    def winfo_exists(self):
        if self._exists_raises:
            raise _tkinter.TclError("bad window path name")
        return 1 if self._exists else 0

    def destroy(self):
        self._exists = False

    def fire(self):
        for guarded in self.calls:
            guarded()
        self.calls.clear()

    def _run(self, fn):
        if self._defer:
            self.calls.append(fn)
        else:
            fn()

    def after(self, ms, fn):
        if self._fail_after:
            raise _tkinter.TclError("invalid command name")
        self.scheduled.append(("after", ms, fn))
        self._run(fn)

    def after_idle(self, fn):
        if self._fail_after:
            raise _tkinter.TclError("invalid command name")
        self.scheduled.append(("idle", fn))
        self._run(fn)


def test_safe_after_runs_fn_when_widget_exists():
    widget = FakeWidget()
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))

    assert calls == ["ran"]


def test_safe_after_schedules_with_the_requested_delay():
    widget = FakeWidget()

    _safe_after(widget, 100, lambda: None)

    assert [(kind, ms) for kind, ms, _fn in widget.scheduled] == [("after", 100)]


def test_safe_after_skips_fn_when_widget_dies_before_the_callback_fires():
    widget = FakeWidget(defer=True)
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))
    widget.destroy()
    widget.fire()

    assert calls == []


def test_safe_after_idle_skips_fn_when_widget_dies_before_the_callback_fires():
    widget = FakeWidget(defer=True)
    calls = []

    _safe_after_idle(widget, lambda: calls.append("ran"))
    widget.destroy()
    widget.fire()

    assert calls == []


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


def test_safe_after_skips_fn_when_the_exists_check_raises():
    widget = FakeWidget(exists_raises=True)
    calls = []

    _safe_after(widget, 100, lambda: calls.append("ran"))

    assert calls == []


def test_safe_after_idle_skips_fn_when_the_exists_check_raises():
    widget = FakeWidget(exists_raises=True)
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
