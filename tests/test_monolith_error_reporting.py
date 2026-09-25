"""Integration tests: monolith error shells report instead of raising (issue #52).

Drives the monolith's `_load` and `_apply_focus_code` failure paths through
the real reporter: the dialog call is the only stub, the error buffer and
`report_error` are the production ones. Both failure paths return before
touching any widget state, so a bare shell stands in for the App.
"""

import threading
from types import SimpleNamespace
from typing import cast

import pytest

import hoi4_content_maker as m
import hoi4cm.core.logger as logmod
import hoi4cm.ui.error_report as error_report
from hoi4cm.editor import decode_project
from hoi4cm.models import Focus, FocusDocument


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


def _patch_load_background(monkeypatch):
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
    )

    def run_background(_app, work, on_done, on_error=None, **_kwargs):
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
        else:
            on_done(result)

    monkeypatch.setattr(m, "run_bg", run_background)


def test_load_reports_a_corrupt_project(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "bad.json")
    _patch_load_background(monkeypatch)

    def boom(path):
        raise ValueError(f"invalid JSON in {path}")

    monkeypatch.setattr(m, "read_project", boom)
    shell = SimpleNamespace(_begin_document_generation=lambda: None)

    m.App._load(cast(m.App, shell))

    assert len(shown) == 1
    title, message, _options = shown[0]
    assert title == "Load Project Error"
    assert "invalid JSON" in message
    entries = logmod.get_error_entries()
    assert len(entries) == 1
    assert "invalid JSON" in entries[0][1]
    assert "Traceback" in entries[0][1]


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
    _patch_load_background(monkeypatch)
    shell = type(
        "Shell",
        (),
        {
            "_begin_document_generation": lambda self: None,
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


def test_load_parses_on_worker_before_installing_workspace(monkeypatch):
    workspace = decode_project(
        {
            "format": "hoi4cm-project",
            "version": 2,
            "workspace": {"main_tree": {"metadata": {"tree_id": "loaded_tree"}}},
        }
    )
    events = []
    parse_threads = []
    shell = SimpleNamespace(
        _begin_document_generation=lambda: events.append("begin"),
        cv=SimpleNamespace(delete=lambda *_args: events.append("delete")),
        selected=None,
        _lines=set(),
        _grid_item=None,
        _grid_key=None,
        _grid_img=None,
        _install_workspace=lambda value: events.append(("install", value)),
        _last_project_path=None,
        _mark_clean=lambda: events.append("clean"),
        _detect_and_apply_tag=lambda: events.append("tag"),
        _refresh_tree_meta_panel=lambda: events.append("meta"),
        _refresh_loaded_trees_panel=lambda: events.append("trees"),
        _hide_form=lambda: events.append("hide"),
        _redraw=lambda: events.append("redraw"),
        _invalidate_focus_list_structure=lambda: events.append("focus-list"),
    )
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "project.json")
    monkeypatch.setattr(
        m,
        "read_project",
        lambda _path: parse_threads.append(threading.current_thread()) or workspace,
    )
    monkeypatch.setattr(
        m,
        "progress_modal",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: events.append("close")),
    )
    monkeypatch.setattr(
        m, "clear_workspace_autosave", lambda: events.append("autosave")
    )

    def run_background(_app, work, on_done, on_error=None, **_kwargs):
        result = []
        errors = []

        def worker():
            try:
                result.append(work())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        if errors:
            if on_error is not None:
                on_error(errors[0])
        else:
            assert events == ["begin"]
            on_done(result[0])

    monkeypatch.setattr(m, "run_bg", run_background)

    m.App._load(cast(m.App, shell))

    assert parse_threads and parse_threads[0] is not threading.current_thread()
    install_index = next(
        i
        for i, event in enumerate(events)
        if isinstance(event, tuple) and event[0] == "install"
    )
    assert install_index > events.index("close")
    assert events[install_index:] == [
        ("install", workspace),
        "clean",
        "autosave",
        "tag",
        "meta",
        "trees",
        "hide",
        "redraw",
        "focus-list",
    ]


def test_load_cancel_shows_nothing(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "askopenfilename", lambda **_kw: "")

    m.App._load(cast(m.App, object()))

    assert shown == []
    assert logmod.get_error_entries() == []


def test_save_reports_a_write_failure(shown, monkeypatch):
    monkeypatch.setattr(m.filedialog, "asksaveasfilename", lambda **_kw: "out.json")

    def boom(path, workspace):
        raise PermissionError("read-only folder")

    monkeypatch.setattr(m, "write_project", boom)
    shell = type("Shell", (), {"_capture_workspace": lambda self: None})()

    m.App._save(cast(m.App, shell))

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

    assert (
        m.App._apply_focus_code(cast(m.App, shell), focus, "not a focus block") is False
    )

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

    assert m.App._apply_focus_code(cast(m.App, shell), focus, "id = x") is True
    assert redraw_now == [(1.25, [10, 20])]
    assert draws == []
