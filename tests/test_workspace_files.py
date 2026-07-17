import os
import stat

import pytest

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


def test_append_text_notifies_after_write(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("first")
    notifications = []

    WorkspaceFiles(on_written=notifications.append).append_text(
        target, " second", encoding="utf-8"
    )

    assert target.read_text() == "first second"
    assert notifications == [str(target)]
