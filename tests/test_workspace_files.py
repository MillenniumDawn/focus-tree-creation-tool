import os
import stat

import pytest

import hoi4cm.mod.workspace_files as workspace_files_module
from hoi4cm.mod.workspace_files import WorkspaceFiles


def test_write_text_replaces_file_and_notifies(tmp_path):
    target = tmp_path / "nested" / "data.txt"
    target.parent.mkdir()
    target.write_text("old")
    notifications = []
    files = WorkspaceFiles(on_written=notifications.append)

    files.write_text(target, "new", encoding="utf-8")

    assert target.read_text() == "new"
    assert notifications == [str(target)]
    assert list(target.parent.glob("*.tmp")) == []


def test_write_text_failure_keeps_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "data.txt"
    target.write_text("old")
    notifications = []
    files = WorkspaceFiles(on_written=notifications.append)
    monkeypatch.setattr(
        "hoi4cm.mod.workspace_files.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        files.write_text(target, "new", encoding="utf-8")

    assert target.read_text() == "old"
    assert notifications == []
    assert list(target.parent.glob("*.tmp")) == []


def test_write_text_encoding_failure_removes_temporary_file(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("old")

    with pytest.raises(UnicodeEncodeError):
        WorkspaceFiles().write_text(target, "not ascii: é", encoding="ascii")

    assert target.read_text() == "old"
    assert list(target.parent.glob("*.tmp")) == []


def test_atomic_write_uses_umask_permissions_not_owner_only(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permission model only")
    old_mask = os.umask(0o022)
    try:
        target = tmp_path / "data.txt"
        WorkspaceFiles().write_text(target, "content", encoding="utf-8")
    finally:
        os.umask(old_mask)

    # 0o666 & ~0o022 == 0o644: group/other readable, not NamedTemporaryFile's
    # owner-only 0o600.
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o644


def test_atomic_write_does_not_change_process_umask(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hoi4cm.mod.workspace_files.os.umask",
        lambda _mask: pytest.fail("atomic writes must not change the process umask"),
    )

    WorkspaceFiles().write_text(tmp_path / "data.txt", "content", encoding="utf-8")


def test_atomic_write_preserves_existing_permissions(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permission model only")
    target = tmp_path / "private.txt"
    target.write_text("old")
    os.chmod(target, 0o600)

    WorkspaceFiles().write_text(target, "new", encoding="utf-8")

    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


def test_write_texts_replaces_every_target_and_notifies_in_order(tmp_path):
    tree = tmp_path / "common" / "national_focus" / "05_TAG.txt"
    loc = tmp_path / "localisation" / "english" / "TAG_l_english.yml"
    notifications = []
    files = WorkspaceFiles(on_written=notifications.append)

    files.write_texts(
        [(tree, "focus_tree = {}", "utf-8"), (loc, "l_english:\n", "utf-8-sig")]
    )

    assert tree.read_text(encoding="utf-8") == "focus_tree = {}"
    assert loc.read_text(encoding="utf-8-sig") == "l_english:\n"
    assert notifications == [str(tree), str(loc)]


def test_write_texts_leaves_every_target_untouched_when_one_cannot_be_staged(tmp_path):
    tree = tmp_path / "tree.txt"
    loc = tmp_path / "loc.yml"
    tree.write_text("old tree")
    loc.write_text("old loc")
    notifications = []
    files = WorkspaceFiles(on_written=notifications.append)

    # The second entry cannot be encoded, so the group must abort during
    # staging — before the first (perfectly writable) target is swapped.
    with pytest.raises(UnicodeEncodeError):
        files.write_texts([(tree, "new tree", "utf-8"), (loc, "not ascii: é", "ascii")])

    assert tree.read_text() == "old tree"
    assert loc.read_text() == "old loc"
    assert notifications == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_write_texts_rolls_back_committed_targets_when_a_swap_fails(
    tmp_path, monkeypatch
):
    tree = tmp_path / "tree.txt"
    loc = tmp_path / "loc.yml"
    tree.write_text("old tree")
    loc.write_text("old loc")
    notifications = []
    files = WorkspaceFiles(on_written=notifications.append)
    real_replace = os.replace
    calls = []

    def failing_replace(source, target):
        calls.append(target)
        if len(calls) == 1:
            return real_replace(source, target)
        raise OSError("replace failed")

    monkeypatch.setattr("hoi4cm.mod.workspace_files.os.replace", failing_replace)

    with pytest.raises(OSError, match="replace failed"):
        files.write_texts([(tree, "new tree", "utf-8"), (loc, "new loc", "utf-8-sig")])

    # The .txt swap succeeded before the .yml failed — a half-applied export
    # is exactly what issue #46 is about, so it gets undone.
    assert tree.read_text() == "old tree"
    assert loc.read_text() == "old loc"
    assert notifications == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_texts_rollback_deletes_targets_that_did_not_exist_before(
    tmp_path, monkeypatch
):
    created = tmp_path / "created.txt"
    loc = tmp_path / "loc.yml"
    loc.write_text("old loc")
    real_replace = os.replace
    calls = []

    def failing_replace(source, target):
        calls.append(target)
        if len(calls) == 1:
            return real_replace(source, target)
        raise OSError("replace failed")

    monkeypatch.setattr("hoi4cm.mod.workspace_files.os.replace", failing_replace)

    with pytest.raises(OSError, match="replace failed"):
        WorkspaceFiles().write_texts(
            [(created, "new", "utf-8"), (loc, "new loc", "utf-8-sig")]
        )

    assert not created.exists()
    assert loc.read_text() == "old loc"


def test_write_texts_with_no_entries_is_a_no_op():
    WorkspaceFiles(
        on_written=lambda _path: pytest.fail("nothing to notify")
    ).write_texts([])


def test_write_text_still_takes_the_single_entry_path(tmp_path, monkeypatch):
    # write_text delegates to write_texts, but a lone target has nothing to
    # roll back to — it must not pay for a pre-write snapshot read.
    target = tmp_path / "data.txt"
    target.write_text("old")
    monkeypatch.setattr(
        "hoi4cm.mod.workspace_files._read_bytes",
        lambda _target: pytest.fail("single writes must not snapshot the target"),
    )

    WorkspaceFiles().write_text(target, "new", encoding="utf-8")

    assert target.read_text() == "new"


def test_append_text_preserves_existing_bytes(tmp_path):
    target = tmp_path / "data.txt"
    original = bytes((0xFF, 0xFE)) + b"existing" + bytes((13, 10))
    appended = "second" + chr(10)
    target.write_bytes(original)

    WorkspaceFiles().append_text(target, appended, encoding="utf-8")

    assert target.read_bytes() == original + appended.encode("utf-8")


def test_append_text_creates_missing_file(tmp_path):
    target = tmp_path / "nested" / "data.txt"

    WorkspaceFiles().append_text(target, "created", encoding="utf-8")

    assert target.read_bytes() == b"created"


def test_append_text_staging_failure_keeps_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "data.txt"
    original = b"original" + bytes((0,)) + b"bytes"
    target.write_bytes(original)
    notifications = []
    real_fdopen = workspace_files_module.os.fdopen

    class FailingWriter:
        def __init__(self, stream):
            self._stream = stream

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, *args):
            return self._stream.__exit__(*args)

        def write(self, content):
            self._stream.write(content[:1])
            raise OSError("write failed")

        def flush(self):
            return self._stream.flush()

        def fileno(self):
            return self._stream.fileno()

    def failing_fdopen(*args, **kwargs):
        return FailingWriter(real_fdopen(*args, **kwargs))

    monkeypatch.setattr(workspace_files_module.os, "fdopen", failing_fdopen)

    with pytest.raises(OSError, match="write failed"):
        WorkspaceFiles(on_written=notifications.append).append_text(
            target, " appended", encoding="utf-8"
        )

    assert target.read_bytes() == original
    assert notifications == []
    assert list(target.parent.glob("*.tmp")) == []


def test_append_text_notifies_after_write(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("first")
    notifications = []

    WorkspaceFiles(on_written=notifications.append).append_text(
        target, " second", encoding="utf-8"
    )

    assert target.read_text() == "first second"
    assert notifications == [str(target)]
