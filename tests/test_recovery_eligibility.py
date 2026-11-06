"""Revocation remains responsive even after a final rename has entered the OS."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from functools import partial
from pathlib import Path
from queue import Queue
from typing import cast
from unittest.mock import Mock

import pytest
from test_background_recovery import _finish, _finish_one, _Owner
from test_background_recovery import (  # pylint: disable=useless-import-alias,unused-import
    dispatch as dispatch,
)

import hoi4_content_maker as app_module
from hoi4cm.editor import recovery as writer
from hoi4cm.editor import recovery_eligibility as eligibility
from hoi4cm.editor.project_codec import (
    decode_project,
    encode_project,
    read_project,
    write_project,
)
from hoi4cm.editor.workspace_autosave import clear_workspace_autosave
from hoi4cm.mod import workspace_files
from hoi4cm.models import EditorWorkspace, Focus, FocusDocument
from hoi4cm.ui import recovery as recovery_ui


def _snapshot(workspace, paths):
    gate = writer.RecoveryCommitGate()
    snapshot = writer.capture_recovery_snapshot(
        workspace, paths, gate.generation, eligibility=gate.eligibility()
    )
    gate.activate(paths)
    return gate, snapshot


@pytest.mark.parametrize("failure", ["capture", "write"])
def test_failed_first_attempt_preserves_previously_committed_recovery(
    dispatch, monkeypatch, failure
):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    _finish(tasks)
    old_bytes = primary.read_bytes()
    replacement = _Owner(primary.parent)
    try:
        with monkeypatch.context() as patch:
            if failure == "capture":
                patch.setattr(
                    recovery_ui,
                    "capture_recovery_snapshot",
                    Mock(side_effect=ValueError("bad snapshot")),
                )
            else:
                patch.setattr(
                    writer,
                    "write_recovery_bytes",
                    Mock(side_effect=OSError("full disk")),
                )
            replacement._recovery.tick()
            if tasks:
                assert _finish_one(tasks).primary_error is not None
        assert primary.read_bytes() == old_bytes
        assert read_project(primary).focuses[1].id == 1
    finally:
        replacement._lifecycle.close()


def test_restore_strips_metadata_and_fresh_controller_preserves_crash_recovery(
    tmp_path,
):
    primary = str(tmp_path / "workspace.json")
    workspace = EditorWorkspace(focuses=FocusDocument([Focus(id=1)]))
    gate, snapshot = _snapshot(workspace, (primary,))
    assert writer.write_recovery(snapshot, gate) == writer.RecoveryResult()
    fresh = _Owner(tmp_path)
    try:
        restored = read_project(primary)
        assert eligibility.RECOVERY_KEY not in restored.extras
        manual = tmp_path / "manual.json"
        write_project(manual, restored)
        gate.invalidate()
        assert read_project(manual).focuses[1].id == 1
        with pytest.raises(eligibility.RevokedRecoveryError):
            read_project(primary)
        with pytest.raises(eligibility.RevokedRecoveryError):
            decode_project(json.loads(snapshot.content))
    finally:
        fresh._lifecycle.close()


@pytest.mark.parametrize("token", [None, False, {}, "../../path", "x" * 32])
def test_malformed_metadata_is_rejected_without_changing_ordinary_projects(token):
    data = encode_project(EditorWorkspace())
    assert decode_project(data).focuses == {}
    data[eligibility.RECOVERY_KEY] = token
    with pytest.raises(eligibility.RevokedRecoveryError):
        decode_project(data)


def test_tokens_stay_bounded_and_never_resurrect_revoked_bytes(tmp_path):
    primary = str(tmp_path / "workspace.json")
    workspace = EditorWorkspace()
    old_gate, old = _snapshot(workspace, (primary,))
    writer.write_recovery(old, old_gate)
    old_gate.invalidate()
    # This models the physical output of an already-entered old rename.
    Path(primary).write_bytes(old.content)
    for _ in range(25):
        gate, snapshot = _snapshot(workspace, (primary,))
        with pytest.raises(eligibility.RevokedRecoveryError):
            read_project(primary)
        gate.invalidate()
    with closing(sqlite3.connect(eligibility._store_path())) as connection:
        assert connection.execute("SELECT COUNT(*) FROM recovery").fetchone()[0] == 0
    assert snapshot.eligibility != old.eligibility
    assert (
        len(list(Path(eligibility._store_path()).parent.glob("recovery-eligibility*")))
        == 1
    )


def test_sqlite_contention_fails_promptly_and_revocation_can_retry(tmp_path):
    primary = str(tmp_path / "workspace.json")
    gate, snapshot = _snapshot(EditorWorkspace(), (primary,))
    writer.write_recovery(snapshot, gate)
    with closing(sqlite3.connect(eligibility._store_path())) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        with pytest.raises(eligibility.RecoveryEligibilityError):
            gate.invalidate()
        assert time.monotonic() - started < 0.5
        with pytest.raises(eligibility.RecoveryEligibilityError):
            read_project(primary)
    gate.invalidate()
    with pytest.raises(eligibility.RevokedRecoveryError):
        read_project(primary)


@pytest.mark.parametrize("blocked_index", [0, 1])
@pytest.mark.parametrize("action", ["invalidate", "clear", "manual_save", "close"])
def test_blocked_final_rename_cannot_restore_eligibility_after_transition(
    dispatch, monkeypatch, blocked_index, action
):
    owner, _, _, primary = dispatch
    sibling = primary.with_name("project.autosave.json")
    blocked = (primary, sibling)[blocked_index]
    ready, release = threading.Event(), threading.Event()
    callbacks: Queue = Queue()
    original_replace = workspace_files.os.replace

    def replace(source, target):
        if target == blocked:
            ready.set()
            assert release.wait(timeout=5)
        original_replace(source, target)

    monkeypatch.setattr(workspace_files.os, "replace", replace)
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    monkeypatch.setattr(
        app_module,
        "clear_workspace_autosave",
        lambda path=None: clear_workspace_autosave(path or str(primary)),
    )
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
            if blocked_index == 1:
                callbacks.get(timeout=5)()
            assert ready.wait(timeout=5)
            started = time.monotonic()
            if action == "invalidate":
                owner._recovery.invalidate()
            elif action == "clear":
                clear_workspace_autosave(str(blocked))
            elif action == "manual_save":
                assert app_module.App._save(cast(app_module.App, owner))
                assert read_project(owner._last_project_path).focuses[1].id == 1
            else:
                owner._lifecycle.close()
            assert time.monotonic() - started < 0.5
        finally:
            release.set()
        callbacks.get(timeout=5)()
    assert blocked.is_file()  # An entered rename cannot be physically cancelled.
    with pytest.raises(eligibility.RevokedRecoveryError):
        read_project(blocked)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; "
            "from hoi4cm.editor.project_codec import read_project; "
            "read_project(sys.argv[1])",
            str(blocked),
        ],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert probe.returncode != 0
    assert "RevokedRecoveryError" in probe.stderr


@pytest.mark.parametrize("blocked_index", [0, 1])
def test_new_generation_waits_for_same_destination_and_survives_old_completion(
    dispatch, monkeypatch, blocked_index
):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    if blocked_index:
        _finish_one(tasks)
    work, done, _ = tasks.pop(0)
    ready, release = threading.Event(), threading.Event()
    original_replace = workspace_files.os.replace
    sibling = primary.with_name("project.autosave.json")
    blocked = (primary, sibling)[blocked_index]
    results = []

    def replace(source, target):
        if target == blocked and not release.is_set():
            ready.set()
            assert release.wait(timeout=5)
        original_replace(source, target)

    monkeypatch.setattr(workspace_files.os, "replace", replace)
    thread = threading.Thread(target=lambda: results.append(work()))
    thread.start()
    try:
        assert ready.wait(timeout=5)
        app_module.App._begin_document_generation(cast(app_module.App, owner))
        owner.workspace = EditorWorkspace(focuses=FocusDocument([Focus(id=2)]))
        owner.focuses = owner.workspace.focuses
        owner._recovery.tick()
        if blocked_index:
            _finish_one(tasks)
            assert set(read_project(primary).focuses) == {2}
        assert tasks == []  # Never start another writer for the blocked destination.
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert results[0].cancelled
    done(results[0])
    while tasks:
        _finish_one(tasks)
    assert set(read_project(primary).focuses) == {2}
    assert primary.read_bytes() == sibling.read_bytes()


@pytest.mark.parametrize("operation", ["close", "save"])
def test_revocation_failure_prevents_false_success(dispatch, monkeypatch, operation):
    owner, tasks, _, primary = dispatch
    owner._recovery.tick()
    _finish(tasks)
    owner.destroy = Mock()
    owner.save_user_config = Mock()
    owner.geometry = Mock(return_value="geometry")
    errors = Mock()
    monkeypatch.setattr(app_module, "report_error", errors)
    monkeypatch.setattr(
        app_module.messagebox, "askyesnocancel", lambda *_a, **_k: False
    )
    monkeypatch.setattr(app_module.messagebox, "showinfo", Mock())
    original_revoke = writer.revoke_recovery
    with monkeypatch.context() as patch:
        patch.setattr(
            writer,
            "revoke_recovery",
            Mock(side_effect=eligibility.RecoveryEligibilityError("busy")),
        )
        if operation == "close":
            app_module.App._on_app_close(cast(app_module.App, owner))
            owner.destroy.assert_not_called()
            assert owner._lifecycle.accepting
            assert not owner._recovery._closed
        else:
            assert not app_module.App._save(cast(app_module.App, owner))
            assert owner.dirty
            assert read_project(owner._last_project_path).focuses[1].id == 1
        assert primary.is_file()
        errors.assert_called_once()
    assert writer.revoke_recovery is original_revoke


def test_production_daemon_executor_exits_with_final_rename_stalled(tmp_path):
    script = r"""
import sys, threading
from hoi4cm.editor import recovery as r
from hoi4cm.models import EditorWorkspace
from hoi4cm.mod import workspace_files
from hoi4cm.ui.lifecycle import ApplicationLifecycle
path = sys.argv[1]
gate = r.RecoveryCommitGate()
snapshot = r.capture_recovery_snapshot(
    EditorWorkspace(), (path,), gate.generation, eligibility=gate.eligibility()
)
gate.activate((path,))
ready = threading.Event()
def replace(*args):
    ready.set()
    threading.Event().wait()
workspace_files.os.replace = replace
lifecycle = ApplicationLifecycle()
lifecycle.add_resource(gate.invalidate)
lifecycle.executor.submit(r.write_recovery, snapshot, gate)
assert ready.wait(timeout=5)
lifecycle.close()
print("closed", flush=True)
"""
    probe = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "workspace.json")],
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    assert probe.stdout.strip().endswith("closed")


def test_parallel_destination_operations_do_not_contend_with_local_store(tmp_path):
    paths = tuple(str(tmp_path / name) for name in ("primary.json", "sibling.json"))
    gate, snapshot = _snapshot(EditorWorkspace(), paths)
    barrier = threading.Barrier(2)

    def writes(path):
        for _ in range(25):
            barrier.wait(timeout=5)
            result = writer.write_recovery(replace(snapshot, paths=(path,)), gate)
            assert result == writer.RecoveryResult()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(writes, path) for path in paths]
        for future in futures:
            future.result(timeout=10)
    assert Path(paths[0]).read_bytes() == Path(paths[1]).read_bytes()


def test_async_writer_refuses_snapshot_without_eligibility(tmp_path):
    primary = str(tmp_path / "workspace.json")
    gate = writer.RecoveryCommitGate()
    snapshot = writer.capture_recovery_snapshot(
        EditorWorkspace(), (primary,), gate.generation
    )
    result = writer.write_recovery(snapshot, gate)
    assert isinstance(result.primary_error, eligibility.RecoveryEligibilityError)
    assert not Path(primary).exists()
