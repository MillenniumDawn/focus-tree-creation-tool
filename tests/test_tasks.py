"""Tests for hoi4cm.ui.tasks: the run_bg worker-thread infrastructure.

Headless: no real Tk widget is created. ``FakeWidget`` stands in for one,
with ``after()`` invoking its callback synchronously so tests don't need a
running Tk mainloop or real-time sleeps. Background work still goes through
the real ``ThreadPoolExecutor``; tests wait on the returned ``Future``
instead of sleeping.
"""

import pytest

import hoi4cm.core.logger as logmod
from hoi4cm.ui import tasks


class FakeWidget:
    """Stands in for a Tk widget: ``after()`` records the call and invokes
    ``fn()`` synchronously. ``winfo_exists()`` is a fixed True/False."""

    def __init__(self, exists=True):
        self._exists = exists
        self.after_calls = []

    def winfo_exists(self):
        return self._exists

    def after(self, delay, fn):
        self.after_calls.append((delay, fn))
        fn()


@pytest.fixture(autouse=True)
def _reset_executor():
    """Isolate the module-level executor singleton across tests."""
    tasks.shutdown_executor()
    yield
    tasks.shutdown_executor()


@pytest.fixture
def log_state():
    """Isolate the error-buffer/callback globals (same pattern as test_logger.py)."""
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    yield logmod
    logmod._error_callback = orig_cb
    logmod.clear_errors()


# ── executor lifecycle ────────────────────────────────────────────────


def test_executor_lazily_created():
    assert tasks._executor is None
    ex = tasks.get_executor()
    assert ex is not None
    assert tasks._executor is ex


def test_executor_max_workers_is_two():
    ex = tasks.get_executor()
    assert ex._max_workers == 2


def test_get_executor_returns_same_instance():
    assert tasks.get_executor() is tasks.get_executor()


def test_shutdown_executor_idempotent():
    tasks.shutdown_executor()  # no executor created yet -- must not raise
    tasks.get_executor()
    tasks.shutdown_executor()
    tasks.shutdown_executor()  # already torn down -- must not raise
    assert tasks._executor is None


# ── run_bg: success path ──────────────────────────────────────────────


def test_on_done_receives_result_and_runs_exactly_once():
    widget = FakeWidget()
    calls = []
    future = tasks.run_bg(widget, lambda: 42, calls.append)
    future.result(timeout=2)
    assert calls == [42]


def test_on_done_skipped_when_widget_destroyed():
    widget = FakeWidget(exists=False)
    calls = []
    future = tasks.run_bg(widget, lambda: 1, calls.append)
    future.result(timeout=2)
    assert calls == []


# ── run_bg: error path ────────────────────────────────────────────────


def test_worker_exception_logs_and_calls_on_error(log_state):
    widget = FakeWidget()
    errors = []

    def work():
        raise ValueError("kaboom")

    future = tasks.run_bg(widget, work, lambda r: None, on_error=errors.append)
    future.result(timeout=2)  # handled internally -- must not raise

    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "kaboom"
    entries = logmod.get_error_entries()
    assert any("kaboom" in msg for _, msg in entries)


def test_worker_exception_without_on_error_still_logs(log_state):
    widget = FakeWidget()

    def work():
        raise ZeroDivisionError("nope")

    future = tasks.run_bg(widget, work, lambda r: None)
    future.result(timeout=2)  # no on_error given -- must still not raise

    entries = logmod.get_error_entries()
    assert any("ZeroDivisionError" in msg for _, msg in entries)


def test_worker_exception_marshals_error_logging_to_widget(monkeypatch, log_state):
    widget = FakeWidget()
    scheduled = []
    logged = []

    def work():
        raise ValueError("kaboom")

    monkeypatch.setattr(
        tasks,
        "_safe_after",
        lambda _widget, _delay, callback: scheduled.append(callback),
    )
    monkeypatch.setattr(tasks, "add_error", logged.append)

    future = tasks.run_bg(widget, work, lambda _result: None)
    future.result(timeout=2)

    assert logged == []
    for callback in scheduled:
        callback()
    assert len(logged) == 1
    assert "ValueError: kaboom" in logged[0]


# ── progress ──────────────────────────────────────────────────────────


def test_make_progress_marshals_calls_in_order():
    widget = FakeWidget()
    seen = []
    progress = tasks.make_progress(
        widget, lambda i, total, label: seen.append((i, total, label))
    )
    for i in range(1, 6):
        progress(i, 5, f"file{i}.txt")
    assert seen == [(i, 5, f"file{i}.txt") for i in range(1, 6)]
