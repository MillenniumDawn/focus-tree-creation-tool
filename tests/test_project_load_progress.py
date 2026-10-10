"""Project-load cleanup outlives document results, but not the application."""

import threading
from concurrent.futures import Executor, Future
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

import hoi4_content_maker as app_module
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class ControlledExecutor(Executor):
    """Keep work pending until the test starts a real worker thread."""

    def __init__(self):
        self.future = Future()
        self.work = None
        self.thread = None

    def submit(self, fn, /, *args, **kwargs):
        self.work = lambda: fn(*args, **kwargs)
        return self.future

    def start(self):
        def run():
            if self.future.set_running_or_notify_cancel():
                try:
                    self.future.set_result(self.work())
                except BaseException as exc:
                    self.future.set_exception(exc)

        self.thread = threading.Thread(target=run)
        self.thread.start()

    def shutdown(self, wait=True, *, cancel_futures=False):
        if cancel_futures:
            self.future.cancel()
        if wait and self.thread is not None:
            self.thread.join(timeout=5)
            assert not self.thread.is_alive()


class LoadShell(SimpleNamespace):
    def __init__(self, executor):
        super().__init__(
            master=None,
            callbacks=[],
            exists=True,
            _confirm_discard=Mock(return_value=True),
            cv=Mock(),
            _lines={},
            _install_workspace=Mock(),
            _mark_clean=Mock(),
            _detect_and_apply_tag=Mock(),
            _refresh_tree_meta_panel=Mock(),
            _refresh_loaded_trees_panel=Mock(),
            _hide_form=Mock(),
            _redraw=Mock(),
            _invalidate_focus_list_structure=Mock(),
        )
        self._lifecycle = ApplicationLifecycle(executor_factory=lambda: executor)

    def _begin_document_generation(self):
        self._lifecycle.begin("document")

    def winfo_exists(self):
        return self.exists

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
def load_case(monkeypatch):
    executor = ControlledExecutor()
    shell = LoadShell(executor)
    tk_thread = threading.current_thread()

    def close():
        assert threading.current_thread() is tk_thread
        modal.grabbed = False

    modal = SimpleNamespace(close=Mock(side_effect=close), grabbed=True)
    errors = Mock()
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", lambda **_k: "p.json")
    monkeypatch.setattr(app_module, "progress_modal", lambda *_a, **_k: modal)
    monkeypatch.setattr(app_module, "report_error", errors)
    monkeypatch.setattr(app_module, "clear_workspace_autosave", Mock())
    yield shell, executor, modal, errors
    shell._lifecycle.close()
    executor.shutdown()


@pytest.mark.parametrize("action", ["supersede", "cancel"])
def test_pending_load_releases_modal_without_reading_or_installing(
    load_case, monkeypatch, action
):
    shell, executor, modal, errors = load_case
    read = Mock()
    monkeypatch.setattr(app_module, "read_project", read)
    app_module.App._load(cast(app_module.App, shell))

    if action == "supersede":
        shell._begin_document_generation()
    else:
        assert executor.future.cancel()
    assert executor.future.cancelled()
    modal.close.assert_not_called()
    shell.drain()

    modal.close.assert_called_once()
    read.assert_not_called()
    shell._install_workspace.assert_not_called()
    errors.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_running_superseded_load_releases_modal_without_stale_result(
    load_case, monkeypatch, fails
):
    shell, executor, modal, errors = load_case
    started = threading.Event()
    release = threading.Event()

    def read(_path):
        started.set()
        assert release.wait(timeout=5)
        if fails:
            raise ValueError("old document failed")
        return SimpleNamespace()

    monkeypatch.setattr(app_module, "read_project", read)
    app_module.App._load(cast(app_module.App, shell))
    executor.start()
    try:
        assert started.wait(timeout=5)
        shell._begin_document_generation()
        modal.close.assert_not_called()
        assert modal.grabbed
    finally:
        release.set()
        executor.shutdown()
    shell.drain()

    modal.close.assert_called_once()
    assert not modal.grabbed
    shell._install_workspace.assert_not_called()
    errors.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_load_outcome_closes_modal_before_install_or_error(
    load_case, monkeypatch, fails
):
    shell, executor, modal, errors = load_case
    workspace = SimpleNamespace()

    def read(_path):
        if fails:
            raise ValueError("broken project")
        return workspace

    def assert_closed(*_args, **_kwargs):
        modal.close.assert_called_once()

    shell._install_workspace.side_effect = assert_closed
    errors.side_effect = assert_closed
    monkeypatch.setattr(app_module, "read_project", read)
    app_module.App._load(cast(app_module.App, shell))
    executor.start()
    executor.shutdown()
    modal.close.assert_not_called()
    shell.drain()

    modal.close.assert_called_once()
    if fails:
        errors.assert_called_once()
        shell._install_workspace.assert_not_called()
    else:
        errors.assert_not_called()
        shell._install_workspace.assert_called_once_with(workspace)
        assert shell._last_project_path == "p.json"


def test_running_load_cannot_be_cancelled_and_cleans_up_when_finished(
    load_case, monkeypatch
):
    shell, executor, modal, errors = load_case
    started = threading.Event()
    release = threading.Event()
    workspace = SimpleNamespace()

    def read(_path):
        started.set()
        assert release.wait(timeout=5)
        return workspace

    monkeypatch.setattr(app_module, "read_project", read)
    app_module.App._load(cast(app_module.App, shell))
    executor.start()
    try:
        assert started.wait(timeout=5)
        assert not executor.future.cancel()
        shell.drain()
        modal.close.assert_not_called()
    finally:
        release.set()
        executor.shutdown()
    shell.drain()

    modal.close.assert_called_once()
    shell._install_workspace.assert_called_once_with(workspace)
    errors.assert_not_called()


def test_completed_load_superseded_before_delivery_still_closes_modal(
    load_case, monkeypatch
):
    shell, executor, modal, errors = load_case
    monkeypatch.setattr(app_module, "read_project", lambda _path: SimpleNamespace())
    app_module.App._load(cast(app_module.App, shell))
    executor.start()
    executor.shutdown()
    shell._begin_document_generation()
    shell.drain()

    modal.close.assert_called_once()
    shell._install_workspace.assert_not_called()
    errors.assert_not_called()


@pytest.mark.parametrize("action", ["close", "destroy"])
def test_finished_load_skips_cleanup_and_outcome_after_app_close_or_destroy(
    load_case, monkeypatch, action
):
    shell, executor, modal, errors = load_case
    monkeypatch.setattr(app_module, "read_project", lambda _path: SimpleNamespace())
    app_module.App._load(cast(app_module.App, shell))
    executor.start()
    executor.shutdown()
    if action == "close":
        shell._lifecycle.close()
    else:
        shell.exists = False
    shell.drain()

    modal.close.assert_not_called()
    shell._install_workspace.assert_not_called()
    errors.assert_not_called()


def test_raising_discard_guard_blocks_the_load(load_case, monkeypatch):
    shell, _executor, _modal, _errors = load_case
    picker = Mock()
    monkeypatch.setattr(app_module.filedialog, "askopenfilename", picker)
    shell._confirm_discard = Mock(side_effect=AttributeError("guard is broken"))

    with pytest.raises(AttributeError, match="guard is broken"):
        app_module.App._load(cast(app_module.App, shell))

    picker.assert_not_called()
    shell._install_workspace.assert_not_called()
