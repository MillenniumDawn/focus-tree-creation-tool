"""Integration tests: monolith error shells report instead of raising (issue #52).

Drives the monolith's `_load` and `_apply_focus_code` failure paths through
the real reporter: the dialog call is the only stub, the error buffer and
`report_error` are the production ones. Both failure paths return before
touching any widget state, so a bare shell stands in for the App.
"""

import json
from types import SimpleNamespace
from typing import cast

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
import hoi4cm.ui.error_report as error_report
from hoi4cm.editor import decode_project
from hoi4cm.models import Focus, FocusDocument
from hoi4cm.models.focus import MAX_FOCUS_ID


@pytest.fixture
def shown(monkeypatch):
    """Capture the error dialog and isolate the shared error buffer."""
    calls = []
    monkeypatch.setattr(
        error_report.messagebox,
        "showerror",
        lambda title, message, **options: calls.append((title, message, options)),
    )
    orig_cb = logmod._error_callback
    logmod.set_error_callback(None)
    logmod.clear_errors()
    yield calls
    logmod._error_callback = orig_cb
    logmod.clear_errors()


def test_load_reports_a_corrupt_project(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "bad.json")

    def boom(path):
        raise ValueError(f"invalid JSON in {path}")

    monkeypatch.setattr(m, "read_project", boom)

    m.App._load(object())

    assert len(shown) == 1
    title, message, _options = shown[0]
    assert title == "Load Project Error"
    assert "invalid JSON" in message
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    assert "invalid JSON" in entries[0][1]
    assert "Traceback" in entries[0][1]


def test_load_reports_out_of_range_ids_before_touching_live_state(
    shown, monkeypatch, tmp_path
):
    path = tmp_path / "invalid_ids.json"
    path.write_text(
        json.dumps(
            {
                "format": "hoi4cm-project",
                "version": 2,
                "workspace": {
                    "focuses": [{"id": MAX_FOCUS_ID + 1}, {"id": MAX_FOCUS_ID + 2}],
                    "main_tree": {"focus_ids": [MAX_FOCUS_ID + 1]},
                    "extra_trees": [{"focus_ids": [MAX_FOCUS_ID + 2]}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: str(path))
    existing = Focus()
    shell = SimpleNamespace(focuses=FocusDocument([existing]))

    m.App._load(cast(m.App, shell))

    assert list(shell.focuses.values()) == [existing]
    assert Focus._next == existing.id
    assert len(shown) == 1
    assert shown[0][0] == "Load Project Error"
    assert "focus id must be between" in shown[0][1]


@pytest.mark.parametrize("duplicate", [False, True])
def test_exhausted_allocator_reports_before_mutating_widgets_or_undo(shown, duplicate):
    selected = Focus.from_dict({"id": MAX_FOCUS_ID})
    shell = SimpleNamespace(selected=selected)

    if duplicate:
        m.App._duplicate_focus(cast(m.App, shell))
    else:
        m.App._new_focus_at(cast(m.App, shell), 0, 0)

    assert Focus._next == MAX_FOCUS_ID
    assert len(shown) == 1
    assert "focus id allocator exhausted" in shown[0][1]


def test_load_warns_when_stored_export_paths_are_dropped(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "project.json")
    workspace = decode_project(
        {
            "format": "hoi4cm-project",
            "version": 2,
            "workspace": {
                "main_tree": {"file_path": "/outside/main.txt"},
                "extra_trees": [{"file_path": "../outside/shared.txt"}],
            },
        }
    )
    monkeypatch.setattr(m, "read_project", lambda _path: workspace)
    monkeypatch.setattr(m, "clear_workspace_autosave", lambda: None)
    warnings = []
    monkeypatch.setattr(
        m.messagebox,
        "showwarning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    shell = type(
        "Shell",
        (),
        {
            "cv": type("Canvas", (), {"delete": lambda self, *_args: None})(),
            "selected": None,
            "_lines": set(),
            "_grid_item": None,
            "_grid_key": None,
            "_grid_img": None,
            "_install_workspace": lambda self, _workspace: None,
            "_mark_clean": lambda self: None,
            "_detect_and_apply_tag": lambda self: None,
            "_refresh_tree_meta_panel": lambda self: None,
            "_refresh_loaded_trees_panel": lambda self: None,
            "_hide_form": lambda self: None,
            "_redraw": lambda self: None,
            "_invalidate_focus_list_structure": lambda self: None,
        },
    )()

    m.App._load(cast(m.App, shell))

    assert len(warnings) == 1
    assert "Stored export paths were ignored" in warnings[0][0][1]
    assert "/outside/main.txt" in warnings[0][0][1]


def test_load_cancel_shows_nothing(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "")

    m.App._load(object())

    assert shown == []
    assert logmod.get_error_entries() == []


def test_save_reports_a_write_failure(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "asksaveasfilename", lambda **_kw: "out.json")

    def boom(path, workspace):
        raise PermissionError("read-only folder")

    monkeypatch.setattr(m, "write_project", boom)
    shell = type("Shell", (), {"_capture_workspace": lambda self: None})()

    m.App._save(shell)

    assert len(shown) == 1
    title, message, _options = shown[0]
    assert title == "Write Failed"
    assert "read-only folder" in message
    entry = logmod.get_error_entries()[0][1]
    assert "read-only folder" in entry
    assert "Traceback" in entry


def test_apply_focus_code_reports_a_parse_failure(shown):
    shell = type("Shell", (), {"focuses": FocusDocument()})()
    focus = Focus()

    assert m.App._apply_focus_code(shell, focus, "not a focus block") is False

    assert len(shown) == 1
    title, message, _options = shown[0]
    assert title == "Parse Error"
    assert "Check Error Log for details" in message
    entry = logmod.get_error_entries()[0][1]
    assert "Traceback" in entry


def test_apply_focus_code_restore_uses_redraw_now(monkeypatch):
    monkeypatch.setattr(m, "apply_focus_code", lambda *_a, **_k: None)
    draws = []
    redraw_now = []
    focus = Focus()
    extra = Focus(2, 2)
    shell = SimpleNamespace(
        focuses=FocusDocument([focus, extra]),
        selected=focus,
        zoom=1.25,
        offset=[10, 20],
        _invalidate_focus_list_structure=lambda: None,
        _populate=lambda _f: None,
        _redraw=lambda *_a, **_k: None,
        _redraw_now=lambda *_a, **_k: redraw_now.append((shell.zoom, shell.offset[:])),
        _draw_focus=lambda foc: draws.append(foc.id),
        cv=SimpleNamespace(after=lambda _ms, fn: fn()),
    )

    assert m.App._apply_focus_code(shell, focus, "id = x") is True
    assert redraw_now == [(1.25, [10, 20])]
    assert draws == []
