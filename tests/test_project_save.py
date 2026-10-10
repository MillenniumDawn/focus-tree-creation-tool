"""Save-target routing and save-state regression tests."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

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


def _replacement_app(root, monkeypatch):
    from hoi4cm.models import Focus, FocusDocument

    app = cast(Any, root)
    for name, value in vars(_fake_app()).items():
        setattr(app, name, value)
    old_focus = Focus()
    old_focus.name = "OLD_focus"
    app.focuses = FocusDocument([old_focus])
    app.cv = MagicMock()
    app._lines = set()
    app._extra_trees = []
    app._focus_bundles = {}
    app._shared_focuses = []
    app._joint_focuses = []
    app._tree_id = app_module.tk.StringVar(master=root)
    app._cfp_x_var = app_module.tk.StringVar(master=root)
    app._cfp_y_var = app_module.tk.StringVar(master=root)
    app._default_focus_prefix = ""
    app._tree_country_tag = "OLD"
    app._import_generation = 0
    app._is_dirty = MagicMock(return_value=True)
    app._confirm_discard = lambda **_kwargs: app_module.App._save(app)
    app._save = lambda: app_module.App._save(app)
    for name in (
        "_begin_document_generation",
        "_reset_canvas_bounds",
        "_invalidate_tree_badges",
        "_refresh_loaded_trees_panel",
        "_hide_form",
        "_update_title",
        "_detect_and_apply_tag",
        "_refresh_tree_meta_panel",
        "_redraw",
        "_redraw_now",
        "_invalidate_focus_list_structure",
        "_fit_all",
        "_push_undo",
        "_hint",
        "_draw_grid",
    ):
        setattr(app, name, MagicMock())
    app._capture_workspace.side_effect = lambda: tuple(
        focus.name for focus in app.focuses.values()
    )
    monkeypatch.setattr(app_module.MOD, "loaded", False)
    monkeypatch.setattr(app_module.MOD, "edit_focus_file", "")
    monkeypatch.setattr(app_module.messagebox, "showinfo", MagicMock())
    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", lambda *a, **kw: True)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", lambda *a: None)
    monkeypatch.setattr(
        app_module,
        "progress_modal",
        lambda *a, **kw: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        app_module, "run_bg", lambda app, work, done, **kw: done(work())
    )
    return app


def _widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from _widgets(child)


def _dialog_action(window, button_text):
    widgets = list(_widgets(window))
    entries = [w for w in widgets if isinstance(w, app_module.tk.Entry)]
    if entries:
        entries[0].insert(0, "NEW")
    button = next(
        w
        for w in widgets
        if isinstance(w, app_module.tk.Button) and w.cget("text") == button_text
    )
    button.invoke()


def _replace(app, route, monkeypatch, tmp_path, *, cancel=False):
    if route == "new":
        app_module.App._new_tree_dialog(app)
        window = next(
            w for w in app.winfo_children() if isinstance(w, app_module.tk.Toplevel)
        )
        _dialog_action(window, "Cancel" if cancel else "Create Tree")
    elif route.startswith("drawio"):
        from hoi4cm.focus_tree.drawio import DrawioGraph, DrawioVertex

        def advance(window):
            if cancel and (route == "drawio" or "Preview" in window.title()):
                _dialog_action(window, "Cancel")
            else:
                _dialog_action(
                    window,
                    "Next" if "Setup" in window.title() else "Import as Skeleton",
                )

        monkeypatch.setattr(app_module.tk.Toplevel, "wait_window", advance)
        graph = DrawioGraph({"1": DrawioVertex("1", "new_focus", 0, 0)}, [])
        app_module.App._import_drawio_continue(app, graph, "new.drawio")
    else:
        path = tmp_path / "new.txt"
        path.write_text(
            "focus_tree = { id = new_tree focus = { id = NEW_focus x = 0 y = 0 } }",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            app_module.filedialog,
            "askopenfilename",
            lambda **kw: "" if cancel else str(path),
        )
        app_module.App._import_txt(app)


@pytest.mark.parametrize("route", ["new", "drawio", "txt"])
def test_replacement_then_quick_save_prompts_for_new_destination(
    route, tk_root, monkeypatch, tmp_path
):
    app = _replacement_app(tk_root, monkeypatch)
    write = MagicMock()
    picker = MagicMock(return_value="/saved/replacement.json")
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", picker)

    _replace(app, route, monkeypatch, tmp_path)

    assert app._last_project_path is None
    picker.assert_not_called()
    if route in ("new", "txt"):
        write.assert_called_once_with("/saved/project.json", ("OLD_focus",))
    else:
        write.assert_not_called()
    write.reset_mock()
    assert app_module.App._save(app) is True
    picker.assert_called_once()
    write.assert_called_once_with("/saved/replacement.json", app._capture_workspace())
    assert app._last_project_path == "/saved/replacement.json"


@pytest.mark.parametrize("route", ["new", "drawio", "drawio-preview", "txt"])
def test_cancelled_replacement_retains_quick_save_destination(
    route, tk_root, monkeypatch, tmp_path
):
    app = _replacement_app(tk_root, monkeypatch)
    write = MagicMock()
    picker = MagicMock(side_effect=AssertionError("picker should not open"))
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", picker)

    _replace(app, route, monkeypatch, tmp_path, cancel=True)

    assert [f.name for f in app.focuses.values()] == ["OLD_focus"]
    assert app._last_project_path == "/saved/project.json"
    write.reset_mock()
    assert app_module.App._save(app) is True
    write.assert_called_once_with("/saved/project.json", ("OLD_focus",))
    picker.assert_not_called()


@pytest.mark.visible_tk
def test_new_tree_escape_closes_when_called_on_plain_tk_root(tk_root):
    app_module.App._new_tree_dialog(tk_root)
    window = next(
        w for w in tk_root.winfo_children() if isinstance(w, app_module.tk.Toplevel)
    )
    entry = next(w for w in _widgets(window) if isinstance(w, app_module.tk.Entry))
    window.update()
    assert entry.winfo_viewable()
    entry.focus_force()
    window.update()

    entry.event_generate("<Escape>")
    window.update()

    assert not window.winfo_exists()


@pytest.mark.parametrize("route", ["new", "txt"])
def test_failed_outgoing_save_prevents_replacement(
    route, tk_root, monkeypatch, tmp_path
):
    app = _replacement_app(tk_root, monkeypatch)
    monkeypatch.setattr(
        app_module, "write_project", MagicMock(side_effect=OSError("disk full"))
    )
    monkeypatch.setattr(app_module, "report_write_failure", MagicMock())

    _replace(app, route, monkeypatch, tmp_path)

    assert [f.name for f in app.focuses.values()] == ["OLD_focus"]
    assert app._last_project_path == "/saved/project.json"


def test_clear_all_is_an_edit_and_retains_quick_save_destination(tk_root, monkeypatch):
    app = _replacement_app(tk_root, monkeypatch)
    write = MagicMock()
    monkeypatch.setattr(app_module, "write_project", write)
    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *a: True)
    monkeypatch.setattr(
        app_module.filedialog,
        "asksaveasfilename",
        MagicMock(side_effect=AssertionError("picker should not open")),
    )

    app_module.App._clear_all(app)
    assert app_module.App._save(app) is True
    write.assert_called_once_with("/saved/project.json", ())
