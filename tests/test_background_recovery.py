"""Owned recovery snapshots, bounded requests, and guarded commit ordering."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from queue import Queue
from typing import cast
from unittest.mock import Mock

import pytest

import hoi4_content_maker as app_module
from hoi4cm.editor import recovery as recovery_editor
from hoi4cm.editor.project_codec import encode_project, read_project
from hoi4cm.editor.workspace_autosave import clear_workspace_autosave
from hoi4cm.mod import workspace_files
from hoi4cm.models import EditorWorkspace, Focus, FocusDocument
from hoi4cm.ui import recovery as recovery_ui
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class _Owner:
    def __init__(self, tmp_path):
        self.workspace = EditorWorkspace(focuses=FocusDocument([Focus(id=1)]))
        self.focuses = self.workspace.focuses
        self.dirty = True
        self._autosave_job = None
        self._last_project_path = str(tmp_path / "project.json")
        self._lifecycle = ApplicationLifecycle(None)
        self._capture_workspace = lambda: self.workspace
        self._is_dirty = lambda: self.dirty
        self._schedule_autosave = Mock()
        self._cancel_autosave = Mock()
        self._log_error = Mock()
        self._invalidate_canvas_images = Mock()
        self._recovery = recovery_ui.RecoveryController(self)
        self.saved_revision = -1

    def _mark_clean(self):
        self.saved_revision = self.focuses.content_revision
        self.dirty = False


@pytest.fixture
def dispatch(tmp_path, monkeypatch):
    owner = _Owner(tmp_path)
    primary = tmp_path / "workspace.json"
    monkeypatch.setattr(recovery_ui, "workspace_autosave_path", lambda: str(primary))
    tasks = []
    captures = Mock(wraps=recovery_ui.capture_recovery_snapshot)
    monkeypatch.setattr(recovery_ui, "capture_recovery_snapshot", captures)

    def submit(_owner, work, on_done, *, on_error):
        tasks.append((work, on_done, on_error))

    monkeypatch.setattr(recovery_ui, "run_bg", submit)
    yield owner, tasks, captures, primary
    owner._lifecycle.close()


def _finish_one(tasks):
    work, done, _ = tasks.pop(0)
    result = work()
    done(result)
    return result


def _finish(tasks):
    result = _finish_one(tasks)
    if result == recovery_editor.RecoveryResult():
        return _finish_one(tasks)
    return result


def test_snapshot_owns_all_serialized_state(tmp_path):
    workspace = EditorWorkspace(focuses=FocusDocument([Focus(id=1)]))
    focus = workspace.focuses[1]
    nested = ["old"]
    focus.effects = [{"type": "raw", "fields": {"nested": nested}}]
    workspace.main_tree.extras["unknown"] = {"nested": ["old"]}
    workspace.workspace_extras["custom"] = {"nested": ["old"]}
    paths = tuple(str(tmp_path / name) for name in ("primary.json", "sibling.json"))
    expected = encode_project(workspace)
    expected_text = json.dumps(expected)
    gate = recovery_editor.RecoveryCommitGate()
    snapshot = recovery_editor.capture_recovery_snapshot(
        workspace, paths, gate.generation
    )
    assert isinstance(snapshot.content, bytes)
    nested.append("later")
    focus.name = "edited later"
    workspace.main_tree.extras["unknown"]["nested"].append("later")
    workspace.workspace_extras["custom"]["nested"].append("later")

    result = recovery_editor.write_recovery(snapshot, gate)

    assert result == recovery_editor.RecoveryResult()
    assert json.loads((tmp_path / "primary.json").read_text()) == json.loads(
        expected_text
    )
    assert (tmp_path / "primary.json").read_bytes() == (
        tmp_path / "sibling.json"
    ).read_bytes()


def test_unchanged_success_skips_capture_and_missing_file_recreates_pair(dispatch):
    owner, tasks, captures, primary = dispatch
    owner._recovery.tick()
    _finish(tasks)
    owner._recovery.tick()
    assert tasks == []
    assert captures.call_count == 1
    assert owner.dirty
    primary.unlink()
    owner._recovery.tick()
    _finish(tasks)
    assert captures.call_count == 2
    assert primary.is_file()
    assert (
        primary.read_bytes() == primary.with_name("project.autosave.json").read_bytes()
    )


def test_in_flight_edits_queue_one_latest_capture_without_marking_clean(dispatch):
    owner, tasks, captures, primary = dispatch
    owner._recovery.tick()
    assert owner._recovery.busy
    for number in range(20):
        owner.focuses[1].desc = str(number)
        owner.focuses.mark_content_changed()
        owner._recovery.tick()
    assert captures.call_count == 1
    assert len(tasks) == 1
    _finish(tasks)
    assert len(tasks) == 1
    assert captures.call_count == 2
    _finish(tasks)
    assert read_project(primary).focuses[1].desc == "19"
    assert owner.dirty
    assert owner.saved_revision == -1
    assert not owner._recovery.busy


@pytest.mark.parametrize("phase", ["stage", "replace"])
def test_stalled_sibling_does_not_block_new_primary_snapshots(
    dispatch, monkeypatch, phase
):
    owner, _, captures, primary = dispatch
    sibling = primary.with_name("project.autosave.json")
    ready = threading.Event()
    release = threading.Event()
    callbacks: Queue = Queue()
    original_stage = workspace_files._stage_bytes
    original_replace = workspace_files.os.replace

    def wait(target):
        if target == sibling and not release.is_set():
            ready.set()
            assert release.wait(timeout=5)

    def blocked_stage(target, *args):
        temporary = original_stage(target, *args)
        wait(target)
        return temporary

    def blocked_replace(source, target):
        wait(target)
        return original_replace(source, target)

    if phase == "stage":
        monkeypatch.setattr(workspace_files, "_stage_bytes", blocked_stage)
    else:
        monkeypatch.setattr(workspace_files.os, "replace", blocked_replace)
    with ThreadPoolExecutor(max_workers=2) as executor:

        def submit(_owner, work, on_done, *, on_error):
            def run():
                try:
                    result = work()
                except Exception as error:
                    callbacks.put(partial(on_error, error))
                else:
                    callbacks.put(partial(on_done, result))

            executor.submit(run)

        monkeypatch.setattr(recovery_ui, "run_bg", submit)
        try:
            owner._recovery.tick()
            callbacks.get(timeout=5)()
            assert ready.wait(timeout=5)
            for number in range(5):
                owner.focuses[1].desc = str(number)
                owner.focuses.mark_content_changed()
                owner._recovery.tick()
                callbacks.get(timeout=5)()
                assert read_project(primary).focuses[1].desc == str(number)
            owner._recovery.tick()
            assert captures.call_count == 6
            assert callbacks.empty()
        finally:
            release.set()
        callbacks.get(timeout=5)()
        callbacks.get(timeout=5)()
    assert sibling.read_bytes() == primary.read_bytes()
    assert not owner._recovery.busy


def test_invalidation_discards_queued_sibling_and_staged_old_write(dispatch):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    _finish_one(tasks)
    sibling_task = tasks.pop(0)
    owner.focuses[1].desc = "latest"
    owner.focuses.mark_content_changed()
    owner._recovery.tick()
    _finish_one(tasks)
    assert tasks == []
    owner._recovery.invalidate()
    clear_workspace_autosave(str(primary))
    clear_workspace_autosave(str(primary.with_name("project.autosave.json")))
    tasks.append(sibling_task)
    assert _finish_one(tasks).cancelled
    assert tasks == []
    assert not primary.exists()
    assert not primary.with_name("project.autosave.json").exists()
    assert not owner._recovery.busy


def test_coalesced_follow_up_replaces_the_existing_autosave_timer(dispatch):
    owner, tasks, _, _ = dispatch
    jobs = set()
    next_job = 0

    def schedule():
        nonlocal next_job
        next_job += 1
        owner._autosave_job = next_job
        jobs.add(next_job)

    def cancel():
        jobs.discard(owner._autosave_job)
        owner._autosave_job = None

    owner._schedule_autosave = schedule
    owner._cancel_autosave = cancel
    owner._recovery.tick()
    jobs.remove(owner._autosave_job)
    owner.focuses.mark_content_changed()
    owner._recovery.tick()
    assert len(jobs) == 1

    _finish(tasks)

    assert jobs == {owner._autosave_job}
    assert len(tasks) == 1
    _finish(tasks)
    assert jobs == {owner._autosave_job}


@pytest.mark.parametrize("failure_index", [0, 1])
def test_failed_pair_and_metadata_revert_retry_both_destinations(
    dispatch, monkeypatch, failure_index
):
    owner, tasks, captures, primary = dispatch
    owner._recovery.tick()
    _finish(tasks)
    old_bytes = primary.read_bytes()
    original = recovery_editor.write_recovery_bytes
    writes = []
    paths = (str(primary), str(primary.with_name("project.autosave.json")))

    def fail(path, text, **kwargs):
        writes.append(path)
        if path == paths[failure_index]:
            raise OSError("disk full")
        original(path, text, **kwargs)

    monkeypatch.setattr(recovery_editor, "write_recovery_bytes", fail)
    owner.workspace.main_tree.metadata.tree_id = "changed"
    owner._recovery.tick()
    result = _finish(tasks)
    assert result.primary_error is not None or result.sibling_error is not None
    assert owner._log_error.call_count == 1
    owner.workspace.main_tree.metadata.tree_id = "TAG_focus_tree"
    monkeypatch.setattr(recovery_editor, "write_recovery_bytes", original)
    owner._recovery.tick()
    _finish(tasks)
    assert captures.call_count == 3
    assert primary.read_bytes() == old_bytes
    assert primary.with_name("project.autosave.json").read_bytes() == old_bytes


def test_manual_save_cancels_older_recovery_and_preserves_clean_state(
    dispatch, monkeypatch
):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    owner.focuses[1].desc = "manual-save edit"
    owner.focuses.mark_content_changed()
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    monkeypatch.setattr(
        app_module,
        "clear_workspace_autosave",
        lambda path=None: clear_workspace_autosave(path or str(primary)),
    )

    assert app_module.App._save(cast(app_module.App, owner))
    assert _finish(tasks).cancelled

    assert not primary.exists()
    assert not primary.with_name("project.autosave.json").exists()
    assert read_project(owner._last_project_path).focuses[1].desc == "manual-save edit"
    assert not owner.dirty
    assert owner.saved_revision == owner.focuses.content_revision
    owner._recovery.tick()
    assert tasks == []


def test_declining_restore_prevents_old_work_from_recreating_primary(
    dispatch, monkeypatch
):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    _finish(tasks)
    owner.focuses[1].desc = "pending recovery"
    owner.focuses.mark_content_changed()
    owner._recovery.tick()
    owner.dirty = False
    monkeypatch.setattr(app_module, "workspace_autosave_path", lambda: str(primary))
    monkeypatch.setattr(
        app_module.messagebox, "askyesnocancel", lambda *_args, **_kwargs: False
    )

    app_module.App._maybe_offer_autosave_restore(cast(app_module.App, owner))

    assert _finish(tasks).cancelled
    assert not primary.exists()


def test_document_replacement_cancels_old_snapshot_and_adopts_only_new_data(dispatch):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    app_module.App._begin_document_generation(cast(app_module.App, owner))
    owner.workspace = EditorWorkspace(focuses=FocusDocument([Focus(id=2)]))
    owner.focuses = owner.workspace.focuses
    owner._recovery.tick()
    assert len(tasks) == 1
    assert _finish(tasks).cancelled
    assert len(tasks) == 1
    _finish(tasks)
    assert set(read_project(primary).focuses) == {2}


def test_shutdown_discards_late_work_and_does_not_reschedule(dispatch):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    calls = owner._schedule_autosave.call_count
    owner._lifecycle.close()
    assert _finish(tasks).cancelled
    owner._recovery.tick()
    assert not primary.exists()
    assert owner._schedule_autosave.call_count == calls


def test_capture_failure_releases_slot_and_retry_resets_failure_streak(
    dispatch, monkeypatch
):
    owner, tasks, _, _ = dispatch
    with monkeypatch.context() as patch:
        patch.setattr(
            recovery_ui,
            "capture_recovery_snapshot",
            Mock(side_effect=ValueError("invalid snapshot")),
        )
        owner._recovery.tick()
    assert tasks == []
    assert not owner._recovery.busy
    assert owner._log_error.call_count == 1
    owner._recovery.tick()
    _finish(tasks)
    assert not owner._autosave_failing


@pytest.mark.parametrize("blocked_index", [0, 1])
def test_invalidation_during_staging_prevents_recreation_after_clear(
    tmp_path, monkeypatch, blocked_index
):
    paths = tuple(str(tmp_path / name) for name in ("primary.json", "sibling.json"))
    gate = recovery_editor.RecoveryCommitGate()
    snapshot = recovery_editor.capture_recovery_snapshot(
        EditorWorkspace(), paths, gate.generation
    )
    ready = threading.Event()
    release = threading.Event()
    original = workspace_files._stage_bytes
    results = []

    def blocked(target, *args):
        temporary = original(target, *args)
        if str(target) == paths[blocked_index]:
            ready.set()
            assert release.wait(timeout=5)
        return temporary

    monkeypatch.setattr(workspace_files, "_stage_bytes", blocked)
    thread = threading.Thread(
        target=lambda: results.append(recovery_editor.write_recovery(snapshot, gate))
    )
    thread.start()
    try:
        assert ready.wait(timeout=5)
        gate.invalidate()
        for path in paths:
            clear_workspace_autosave(path)
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert results[0].cancelled
    assert list(tmp_path.iterdir()) == []
