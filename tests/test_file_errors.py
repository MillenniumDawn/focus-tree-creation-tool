"""Tests for hoi4cm.ui.file_errors — the failed-write reporter (issue #46).

Headless: the dialog call is stubbed, no Tk root is ever created.
"""

import pytest

import hoi4cm.core.logger as logmod
import hoi4cm.ui.file_errors as file_errors


@pytest.fixture
def shown(monkeypatch):
    """Capture the messagebox call and isolate the shared error buffer."""
    calls = []
    monkeypatch.setattr(
        file_errors.messagebox,
        "showerror",
        lambda title, message, **options: calls.append((title, message, options)),
    )
    logmod.clear_errors()
    yield calls
    logmod.clear_errors()


def test_failure_is_logged_and_shown_with_the_file_name(shown):
    error = PermissionError(13, "Permission denied")

    message = file_errors.report_write_failure(
        None, "/mods/md/common/national_focus/05_USA.txt", error
    )

    assert len(shown) == 1
    title, shown_message, _options = shown[0]
    assert title == "Write Failed"
    assert shown_message == message
    assert "05_USA.txt" in message
    assert "Permission denied" in message
    # And it lands in the in-app error log, not just a dialog the user dismisses.
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    assert "05_USA.txt" in entries[0][1]


def test_message_promises_the_target_survived(shown):
    message = file_errors.report_write_failure(None, "tree.txt", OSError("disk full"))

    assert "left unchanged" in message


def test_parent_is_omitted_rather_than_passed_as_none(shown):
    # Tk rejects `-parent None`; the reporter has to leave the option out.
    file_errors.report_write_failure(None, "tree.txt", OSError("nope"))

    assert shown[0][2] == {}


def test_parent_window_is_forwarded_when_given(shown):
    sentinel = object()

    file_errors.report_write_failure(sentinel, "tree.txt", OSError("nope"))

    assert shown[0][2] == {"parent": sentinel}


def test_custom_title_overrides_the_default(shown):
    file_errors.report_write_failure(None, "tree.txt", OSError("nope"), title="Export")

    assert shown[0][0] == "Export"
