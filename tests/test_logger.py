"""Tests for hoi4cm.core.log — the base logging module."""
import logging
import re
import sys

import pytest

import hoi4cm.core.logger as logmod


class _ListHandler(logging.Handler):
    """Collects emitted records into a list (HOI4CM logger has propagate=False,
    so caplog can't see them — attach directly instead)."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def log_state():
    """Isolate module-level state (buffer, callback, excepthook) per test."""
    orig_hook = sys.excepthook
    orig_installed = logmod._excepthook_installed
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    logmod._excepthook_installed = False
    yield logmod
    sys.excepthook = orig_hook
    logmod._excepthook_installed = orig_installed
    logmod._error_callback = orig_cb
    logmod.clear_errors()


# ── configuration ────────────────────────────────────────────────────

def test_logger_configured_without_double_handlers():
    assert logmod.log.name == "HOI4CM"
    assert logmod.log.level == logging.DEBUG
    assert logmod.log.propagate is False
    assert any(isinstance(h, logging.StreamHandler) for h in logmod.log.handlers)

    before = len(logmod.log.handlers)
    logmod._configure()  # idempotent — must not attach a second set
    assert len(logmod.log.handlers) == before


def test_get_logger_returns_namespaced_child():
    child = logmod.get_logger("widget")
    assert child.name == "HOI4CM.widget"
    assert child.parent is logmod.log


def test_log_startup_emits_four_info_records(log_state):
    h = _ListHandler()
    logmod.log.addHandler(h)
    try:
        logmod.log_startup()
    finally:
        logmod.log.removeHandler(h)

    infos = [r for r in h.records if r.levelno == logging.INFO]
    assert len(infos) == 4
    assert "HOI4 Content Maker starting" in infos[0].getMessage()


# ── error buffer ─────────────────────────────────────────────────────

def test_add_error_appends_timestamped_entry(log_state):
    count = logmod.add_error("  boom  ")
    assert count == 1
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    ts, msg = entries[0]
    assert msg == "boom"  # stripped
    assert re.fullmatch(r"\d\d:\d\d:\d\d", ts)


def test_add_error_fires_callback_with_count(log_state):
    seen = []
    logmod.set_error_callback(seen.append)
    logmod.add_error("one")
    logmod.add_error("two")
    assert seen == [1, 2]


def test_callback_exception_does_not_break_add_error(log_state):
    def boom(_count):
        raise RuntimeError("callback failed")

    logmod.set_error_callback(boom)
    # Must not raise, and the entry must still be recorded.
    assert logmod.add_error("still recorded") == 1
    assert logmod.get_error_entries()[0][1] == "still recorded"


def test_buffer_identity_is_stable_across_clear(log_state):
    buf = logmod.get_error_entries()
    logmod.add_error("x")
    logmod.clear_errors()
    assert logmod.get_error_entries() is buf  # cleared in place, not rebound
    assert len(buf) == 0


# ── excepthook ───────────────────────────────────────────────────────

def test_install_excepthook_records_and_chains(log_state):
    chained = []
    sentinel = lambda *a: chained.append(a)
    sys.excepthook = sentinel

    logmod.install_excepthook()
    assert sys.excepthook is not sentinel  # our hook took over

    try:
        raise ValueError("kaboom")
    except ValueError:
        exc_info = sys.exc_info()
    sys.excepthook(*exc_info)

    entries = logmod.get_error_entries()
    assert any("kaboom" in msg for _, msg in entries)
    assert chained and chained[0][0] is exc_info[0]  # prior hook was called


def test_install_excepthook_is_idempotent(log_state):
    logmod.install_excepthook()
    first = sys.excepthook
    logmod.install_excepthook()
    assert sys.excepthook is first  # second call is a no-op
