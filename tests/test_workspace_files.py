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


def test_append_text_notifies_after_write(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("first")
    notifications = []

    WorkspaceFiles(on_written=notifications.append).append_text(
        target, " second", encoding="utf-8"
    )

    assert target.read_text() == "first second"
    assert notifications == [str(target)]
