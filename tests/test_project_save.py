"""Save-target routing and save-state regression tests."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import hoi4_content_maker as app_module
from hoi4cm.editor.project_codec import choose_project_save_path


def _fake_app():
    app = SimpleNamespace(
        _last_project_path="/saved/project.json",
        _saved_revision=7,
        _saved_fingerprint=("dirty",),
    )
    app._capture_workspace = MagicMock(return_value=object())
    app._mark_clean = MagicMock()
    return app


def test_quick_save_path_reuses_current_path_without_opening_picker():
    choose_path = MagicMock(side_effect=AssertionError("picker should not open"))

    path = choose_project_save_path(
        "/saved/project.json", save_as=False, choose_path=choose_path
    )

    assert path == "/saved/project.json"
    choose_path.assert_not_called()


def test_first_save_and_save_as_choose_a_path():
    choose_path = MagicMock(return_value="/saved/new-project.json")

    first_path = choose_project_save_path(None, save_as=False, choose_path=choose_path)
    save_as_path = choose_project_save_path(
        "/saved/project.json", save_as=True, choose_path=choose_path
    )

    assert first_path == "/saved/new-project.json"
    assert save_as_path == "/saved/new-project.json"
    assert choose_path.call_count == 2


def test_app_quick_save_writes_existing_path_without_picker(monkeypatch):
    app = _fake_app()
    write = MagicMock()
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", lambda *_args: None)
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        app_module.filedialog,
        "asksaveasfilename",
        MagicMock(side_effect=AssertionError("picker should not open")),
    )

    assert cast(Any, app_module.App)._save(app) is True

    write.assert_called_once_with("/saved/project.json", app._capture_workspace())
    app._mark_clean.assert_called_once_with()
    assert app._last_project_path == "/saved/project.json"


def test_first_save_prompts_then_remembers_selected_path(monkeypatch):
    app = _fake_app()
    app._last_project_path = None
    dialog = MagicMock(return_value="/saved/first-project.json")
    write = MagicMock()
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", dialog)
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", lambda *_args: None)
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *_args, **_kwargs: None
    )

    assert cast(Any, app_module.App)._save(app) is True

    dialog.assert_called_once()
    write.assert_called_once_with("/saved/first-project.json", app._capture_workspace())
    assert app._last_project_path == "/saved/first-project.json"
    app._mark_clean.assert_called_once_with()


def test_save_as_uses_new_path_after_success(monkeypatch):
    app = _fake_app()
    dialog = MagicMock(return_value="/saved/copy.json")
    write = MagicMock()
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", dialog)
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", lambda *_args: None)
    monkeypatch.setattr(
        app_module.messagebox, "showinfo", lambda *_args, **_kwargs: None
    )

    assert cast(Any, app_module.App)._save(app, save_as=True) is True

    dialog.assert_called_once()
    write.assert_called_once_with("/saved/copy.json", app._capture_workspace())
    assert app._last_project_path == "/saved/copy.json"
    app._mark_clean.assert_called_once_with()


def test_cancelled_save_as_preserves_current_path_and_dirty_state(monkeypatch):
    app = _fake_app()
    write = MagicMock()
    monkeypatch.setattr(
        app_module.filedialog,
        "asksaveasfilename",
        MagicMock(return_value=""),
    )
    monkeypatch.setattr(app_module, "write_project", write)

    assert cast(Any, app_module.App)._save(app, save_as=True) is False

    assert app._last_project_path == "/saved/project.json"
    assert app._saved_revision == 7
    assert app._saved_fingerprint == ("dirty",)
    app._mark_clean.assert_not_called()
    write.assert_not_called()


def test_failed_save_as_preserves_current_path_and_dirty_state(monkeypatch):
    app = _fake_app()
    report_failure = MagicMock()
    monkeypatch.setattr(
        app_module.filedialog,
        "asksaveasfilename",
        MagicMock(return_value="/saved/copy.json"),
    )
    monkeypatch.setattr(
        app_module,
        "write_project",
        MagicMock(side_effect=OSError("disk full")),
    )
    monkeypatch.setattr(app_module, "report_write_failure", report_failure)

    assert cast(Any, app_module.App)._save(app, save_as=True) is False

    assert app._last_project_path == "/saved/project.json"
    assert app._saved_revision == 7
    assert app._saved_fingerprint == ("dirty",)
    app._mark_clean.assert_not_called()
    report_failure.assert_called_once()


def test_failed_quick_save_preserves_path_and_dirty_state(monkeypatch):
    app = _fake_app()
    saved_revision = app._saved_revision
    saved_fingerprint = app._saved_fingerprint
    report_failure = MagicMock()
    monkeypatch.setattr(
        app_module,
        "write_project",
        MagicMock(side_effect=OSError("disk full")),
    )
    monkeypatch.setattr(app_module, "report_write_failure", report_failure)
    monkeypatch.setattr(
        app_module.filedialog,
        "asksaveasfilename",
        MagicMock(side_effect=AssertionError("picker should not open")),
    )

    assert cast(Any, app_module.App)._save(app) is False

    assert app._last_project_path == "/saved/project.json"
    assert app._saved_revision == saved_revision
    assert app._saved_fingerprint == saved_fingerprint
    app._mark_clean.assert_not_called()
    report_failure.assert_called_once()
