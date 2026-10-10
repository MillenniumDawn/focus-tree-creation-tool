"""Real project files through the load task, installer, and undo engine."""

import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest
from test_document_reset_undo import _DocumentApp, _seed_history, _workspace
from test_project_load_progress import ControlledExecutor

import hoi4_content_maker as app_module
from hoi4cm.editor.project_codec import write_project
from hoi4cm.models import Focus, TreeDocument, TreeMetadata
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class ProjectApp(_DocumentApp):
    def __init__(self, executor, focuses):
        super().__init__(focuses)
        self.master = None
        self.callbacks: list[Callable[[], None]] = []
        self._lifecycle = ApplicationLifecycle(executor_factory=lambda: executor)
        self._invalidate_canvas_images = Mock()
        self._begin_document_generation.side_effect = lambda: (
            app_module.App._begin_document_generation(cast(app_module.App, self))
        )

    def winfo_exists(self):
        return True

    def after(self, _delay, callback):
        self.callbacks.append(callback)
        return len(self.callbacks)

    def after_cancel(self, _identifier):
        pass

    def drain(self):
        for callback in self.callbacks:
            callback()
        self.callbacks.clear()


@pytest.fixture
def project_case(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.MOD, "root", None)
    old = Focus()
    old.name = "OLD_existing"
    executor = ControlledExecutor()
    app = ProjectApp(executor, [old])
    app._last_project_path = "old.json"
    app.selected = old
    app._lines = [123]
    app._grid_item = app._grid_key = app._grid_img = object()

    new = Focus()
    new.name = "NEW_loaded"
    new.x, new.y = 2, 3
    source = _workspace(focuses=[new])
    meta = source.main_tree.metadata
    meta.country_name = "Loaded Country"
    meta.country_raw = "tag = NEW"
    meta.cfp_x = 4
    meta.shared_focuses = ["shared_loaded"]
    meta.joint_focuses = ["joint_loaded"]
    source.main_tree.extras = {"tree_extras": {"default": "no"}}
    source.main_tree.had_wrapper = False
    source.extra_trees = [
        TreeDocument(
            tree_type="shared",
            metadata=TreeMetadata(tree_id="shared_loaded", country_tag="NEW"),
            extras={"custom": "kept"},
        )
    ]
    source.canvas_min = (-2, -3)
    source.canvas_max = (20, 30)
    source.default_focus_prefix = "FILE_"
    path = tmp_path / "project.json"
    write_project(path, source)

    tk_thread = threading.current_thread()

    def close():
        assert threading.current_thread() is tk_thread
        modal.grabbed = False

    modal = SimpleNamespace(close=Mock(side_effect=close), grabbed=True)
    errors = Mock()
    cleared = Mock()
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilename", Mock(return_value=str(path))
    )
    monkeypatch.setattr(app_module, "progress_modal", lambda *_a, **_kw: modal)
    monkeypatch.setattr(app_module, "report_error", errors)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", cleared)
    yield app, executor, path, new.id, modal, errors, cleared
    app._lifecycle.close()
    executor.shutdown()


@pytest.mark.parametrize("history", ["undo", "redo", "both"])
def test_real_file_load_installs_document_and_resets_history(project_case, history):
    app, executor, path, focus_id, modal, errors, cleared = project_case
    _seed_history(app, with_redo=history == "both")
    app.focuses.touch()
    if history == "redo":
        app_module.App._undo(cast(app_module.App, app))
        app_module.App._undo(cast(app_module.App, app))
        assert len(app._undo_stack) == 0
    app.cv.reset_mock()
    old_workspace = app.workspace
    before = path.read_bytes()

    app_module.App._load(cast(app_module.App, app))
    assert app.workspace is old_workspace
    executor.start()
    executor.shutdown()
    assert app.workspace is old_workspace
    modal.close.assert_not_called()
    app.drain()

    modal.close.assert_called_once()
    assert not modal.grabbed
    errors.assert_not_called()
    cleared.assert_called_once()
    assert path.read_bytes() == before
    assert app.workspace is not old_workspace
    assert app.focuses is app.workspace.focuses
    assert set(app.focuses) == {focus_id}
    assert app.focuses[focus_id].name == "NEW_loaded"
    assert app.focuses.validate_indexes()
    assert app._last_project_path == str(path)
    assert app._tree_id.value == "NEW_tree"
    assert app._tree_country_tag == "NEW"
    assert app._tree_country_name == "Loaded Country"
    assert app._tree_country_raw == "tag = NEW"
    assert app._tree_focus_prefix == "NEW_"
    assert app._tree_extras == {"default": "no"}
    assert not app._tree_had_wrapper
    assert (app._cfp_x, app._cfp_y) == (4, None)
    assert (app._cfp_x_var.value, app._cfp_y_var.value) == ("4", "")
    assert app._shared_focuses == ["shared_loaded"]
    assert app._joint_focuses == ["joint_loaded"]
    assert app._extra_trees[0]["tree_id"] == "shared_loaded"
    assert app._extra_trees[0]["custom"] == "kept"
    assert app._canvas_min == [-2, -3]
    assert app._canvas_max == [20, 30]
    assert app._default_focus_prefix == "FILE_"
    assert app.selected is None
    assert app._lines == []
    assert (app._grid_item, app._grid_key, app._grid_img) == (None, None, None)
    app.cv.delete.assert_called_once_with("all")
    app._mark_clean.assert_called_once()
    app._begin_document_generation.assert_has_calls([(), ()])
    assert len(app._undo_stack) == 0
    loaded = app.focuses[focus_id]
    app_module.App._undo(cast(app_module.App, app))
    app_module.App._redo(cast(app_module.App, app))
    assert app.focuses[focus_id] is loaded
    assert set(app.focuses) == {focus_id}

    app_module.App._push_undo(
        cast(app_module.App, app), "move loaded", touched_ids=(focus_id,)
    )
    assert app.focuses.move(focus_id, 8, 9)
    app_module.App._undo(cast(app_module.App, app))
    assert (app.focuses[focus_id].x, app.focuses[focus_id].y) == (2, 3)
    assert app.focuses.validate_indexes()
    app_module.App._redo(cast(app_module.App, app))
    assert (app.focuses[focus_id].x, app.focuses[focus_id].y) == (8, 9)
    assert app.focuses.validate_indexes()
    assert set(app.focuses) == {focus_id}


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_real_file_load_failure_preserves_document_and_history(
    project_case, monkeypatch, failure
):
    app, executor, path, _focus_id, modal, errors, cleared = project_case
    created = _seed_history(app, with_redo=True)
    app.focuses.touch()
    app.cv.reset_mock()
    old_workspace = app.workspace
    old_document = app.focuses
    bad_path = path.parent / "bad.json"
    if failure == "corrupt":
        bad_path.write_text("{invalid JSON", encoding="utf-8")
    monkeypatch.setattr(
        app_module.filedialog, "askopenfilename", Mock(return_value=str(bad_path))
    )

    app_module.App._load(cast(app_module.App, app))
    executor.start()
    executor.shutdown()
    app.drain()

    modal.close.assert_called_once()
    errors.assert_called_once()
    assert isinstance(errors.call_args.args[1], (FileNotFoundError, ValueError))
    assert app.workspace is old_workspace
    assert app.focuses is old_document
    assert app._last_project_path == "old.json"
    app.cv.delete.assert_not_called()
    app._mark_clean.assert_not_called()
    cleared.assert_not_called()
    assert len(app._undo_stack) == 1
    app_module.App._redo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_renamed"
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"
    assert app.focuses.validate_indexes()


@pytest.mark.parametrize("cancel", ["picker", "discard", "pending", "superseded"])
def test_real_file_load_cancellation_preserves_document_and_history(
    project_case, monkeypatch, cancel
):
    app, executor, _path, _focus_id, modal, errors, cleared = project_case
    created = _seed_history(app, with_redo=True)
    app.focuses.touch()
    app.cv.reset_mock()
    old_workspace = app.workspace
    old_document = app.focuses
    if cancel == "picker":
        monkeypatch.setattr(
            app_module.filedialog, "askopenfilename", Mock(return_value="")
        )
    elif cancel == "discard":
        app._confirm_discard.return_value = False
    loaded = []
    read_project = app_module.read_project
    monkeypatch.setattr(
        app_module,
        "read_project",
        lambda project_path: loaded.append(read_project(project_path)) or loaded[-1],
    )
    app_module.App._load(cast(app_module.App, app))
    if cancel == "pending":
        assert executor.future.cancel()
        executor.start()
        executor.shutdown()
        app.drain()
    elif cancel == "superseded":
        executor.start()
        executor.shutdown()
        assert loaded[0].focuses
        app._begin_document_generation()
        app.drain()
    else:
        assert executor.work is None
    if cancel != "superseded":
        assert not loaded

    if cancel in ("pending", "superseded"):
        modal.close.assert_called_once()
    else:
        modal.close.assert_not_called()
        app._begin_document_generation.assert_not_called()
    errors.assert_not_called()
    cleared.assert_not_called()
    app.cv.delete.assert_not_called()
    app._mark_clean.assert_not_called()
    assert app.workspace is old_workspace
    assert app.focuses is old_document
    assert app._last_project_path == "old.json"
    assert len(app._undo_stack) == 1
    app_module.App._redo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_renamed"
    app_module.App._undo(cast(app_module.App, app))
    assert app.focuses[created.id].name == "seed_created"
    assert app.focuses.validate_indexes()
