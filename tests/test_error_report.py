"""Tests for hoi4cm.ui.error_report — the generic error reporter (issue #52).

Headless: the dialog call is stubbed, no Tk root is ever created.
"""

import json
from pathlib import Path

import pytest

import hoi4cm.core.i18n as i18n_mod
import hoi4cm.core.logger as logmod
import hoi4cm.ui.error_report as error_report


@pytest.fixture
def shown(monkeypatch):
    """Capture the messagebox call and isolate the shared error buffer."""
    calls = []
    english = Path(__file__).parents[1] / "locales" / "en.json"
    monkeypatch.setattr(
        i18n_mod, "I18N_STRINGS", json.loads(english.read_text(encoding="utf-8"))
    )
    monkeypatch.setattr(
        error_report.messagebox,
        "showerror",
        lambda title, message, **options: calls.append((title, message, options)),
    )
    logmod.clear_errors()
    yield calls
    logmod.clear_errors()


def test_message_is_logged_and_points_to_visible_log_controls(shown):
    message = error_report.report_error("Could not parse XML")

    assert shown == [
        (
            "Error",
            "Could not parse XML\n\n"
            "See Settings -> SESSION LOG -> Open Full Log Window for details.",
            {},
        )
    ]
    assert message == "Could not parse XML"
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    assert entries[0][1] == "Could not parse XML"


def test_english_hint_names_settings_controls(shown):
    error_report.report_error("boom")

    hint = shown[0][1]
    assert i18n_mod.tr("settings.session_log") in hint
    assert i18n_mod.tr("settings.open_full_log") in hint
    assert "Error Log" not in hint


def test_missing_translation_uses_visible_log_controls(shown, monkeypatch):
    monkeypatch.setattr(i18n_mod, "I18N_STRINGS", {})

    message = error_report.report_error("boom")

    assert message == "boom"
    assert shown[0][1] == (
        "boom\n\nSee Settings -> SESSION LOG -> Open Full Log Window for details."
    )


def test_exception_appends_traceback_to_log_entry_only(shown):
    try:
        raise ValueError("bad value")
    except ValueError as exc:
        error_report.report_error("Parse failed", exc)

    entry = logmod.get_error_entries()[0][1]
    assert entry.startswith("Parse failed\nTraceback")
    assert "ValueError: bad value" in entry
    # The dialog points to the log, where the full traceback is available.
    assert shown[0][1] == (
        "Parse failed\n\n"
        "See Settings -> SESSION LOG -> Open Full Log Window for details."
    )


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
    assert shown[0][1] == (
        "Write failed: x\n\n"
        "See Settings -> SESSION LOG -> Open Full Log Window for details."
    )
