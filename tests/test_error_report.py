"""Tests for hoi4cm.ui.error_report — the generic error reporter (issue #52).

Headless: the dialog call is stubbed, no Tk root is ever created.
"""

import pytest

import hoi4cm.core.logger as logmod
import hoi4cm.ui.error_report as error_report


@pytest.fixture
def shown(monkeypatch):
    """Capture the messagebox call and isolate the shared error buffer."""
    calls = []
    monkeypatch.setattr(
        error_report.messagebox,
        "showerror",
        lambda title, message, **options: calls.append((title, message, options)),
    )
    logmod.clear_errors()
    yield calls
    logmod.clear_errors()


def test_message_is_logged_and_shown(shown):
    message = error_report.report_error("Could not parse XML")

    assert shown == [("Error", "Could not parse XML", {})]
    assert message == "Could not parse XML"
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    assert entries[0][1] == "Could not parse XML"


def test_exception_appends_traceback_to_log_entry_only(shown):
    try:
        raise ValueError("bad value")
    except ValueError as exc:
        error_report.report_error("Parse failed", exc)

    entry = logmod.get_error_entries()[0][1]
    assert entry.startswith("Parse failed\nTraceback")
    assert "ValueError: bad value" in entry
    # The dialog shows the message only, not the traceback.
    assert shown[0][1] == "Parse failed"


def test_parent_is_omitted_rather_than_passed_as_none(shown):
    # Tk rejects `-parent None`; the reporter has to leave the option out.
    error_report.report_error("boom")

    assert shown[0][2] == {}


def test_parent_window_is_forwarded_when_given(shown):
    sentinel = object()

    error_report.report_error("boom", parent=sentinel)

    assert shown[0][2] == {"parent": sentinel}


def test_custom_title_overrides_the_default(shown):
    error_report.report_error("boom", title="Parse Error")

    assert shown[0][0] == "Parse Error"


def test_non_exception_error_object_does_not_crash(shown):
    # The old add_error pattern sometimes logged strings; the reporter must
    # survive whatever error object a caller hands it.
    message = error_report.report_error("Write failed: x", "disk full")

    assert message == "Write failed: x"
    assert len(logmod.get_error_entries()) == 1
    assert shown[0][1] == "Write failed: x"
