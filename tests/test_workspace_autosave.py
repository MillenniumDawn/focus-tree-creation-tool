import os

import hoi4cm.editor.workspace_autosave as wa  # type: ignore[import-untyped]
from hoi4cm.editor import read_project, write_project
from hoi4cm.models import (
    EditorWorkspace,
    Focus,
    FocusDocument,
    TreeDocument,
    TreeMetadata,
)

AUTOSAVE_NAME = wa.AUTOSAVE_NAME
clear_workspace_autosave = wa.clear_workspace_autosave
sibling_autosave_path = wa.sibling_autosave_path
workspace_autosave_path = wa.workspace_autosave_path


def test_workspace_autosave_path_uses_autosave_name(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    got = workspace_autosave_path()
    assert got == os.path.join(str(tmp_path), ".hoi4cm", "autosave", AUTOSAVE_NAME)
    assert os.path.isdir(os.path.dirname(got))


def test_workspace_autosave_path_custom_name(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    assert workspace_autosave_path("custom.json").endswith("custom.json")


def test_sibling_autosave_path_with_json_extension():
    assert sibling_autosave_path("/tmp/proj/project.json") == (
        "/tmp/proj/project.autosave.json"
    )
    assert sibling_autosave_path("a.json") == "a.autosave.json"


def test_sibling_autosave_path_without_json_extension():
    assert sibling_autosave_path("/tmp/proj/project") == (
        "/tmp/proj/project.autosave.json"
    )
    assert sibling_autosave_path("/tmp/proj/archive.txt") == (
        "/tmp/proj/archive.txt.autosave.json"
    )


def test_sibling_autosave_path_preserves_directory():
    assert sibling_autosave_path("/a/b/c.json") == "/a/b/c.autosave.json"


def test_clear_workspace_autosave_removes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    path = workspace_autosave_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # test tmp is safe — not a user-controlled traversal sink
    open(path, "w", encoding="utf-8").write("x")  # nosemgrep: python-path-traversal
    assert os.path.isfile(path)
    clear_workspace_autosave()
    assert not os.path.isfile(path)


def test_clear_workspace_autosave_noop_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    path = workspace_autosave_path()
    if os.path.isfile(path):
        os.unlink(path)
    clear_workspace_autosave()  # must not raise
    clear_workspace_autosave(path)  # explicit path variant


def test_clear_workspace_autosave_ignores_os_error(monkeypatch, tmp_path):
    # OSError on unlink (e.g. permission) must be swallowed — best-effort.
    monkeypatch.setattr(
        os, "unlink", lambda _p: (_ for _ in ()).throw(OSError("denied"))
    )
    clear_workspace_autosave(str(tmp_path / "ghost.json"))


def test_clear_workspace_autosave_explicit_path(tmp_path):
    target = tmp_path / "sibling.autosave.json"
    target.write_text("x")
    clear_workspace_autosave(str(target))
    assert not target.exists()
    clear_workspace_autosave(str(target))  # second clear is no-op


def _one_focus_workspace():
    focus = Focus(1, 2)
    focus.name = "TAG_start"
    return EditorWorkspace(
        focuses=FocusDocument([focus]),
        main_tree=TreeDocument(metadata=TreeMetadata(tree_id="TAG_focus_tree")),
    )


def test_workspace_autosave_roundtrips_via_write_project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    path = workspace_autosave_path()
    write_project(path, _one_focus_workspace())
    restored = read_project(path)
    assert [f.name for f in restored.focuses.values()] == ["TAG_start"]
    clear_workspace_autosave()
    assert not os.path.isfile(path)


def test_sibling_autosave_roundtrips(tmp_path):
    project = tmp_path / "project.json"
    sibling = sibling_autosave_path(str(project))
    ws = _one_focus_workspace()
    write_project(sibling, ws)
    restored = read_project(sibling)
    assert restored.main_tree.metadata.tree_id == "TAG_focus_tree"
    clear_workspace_autosave(sibling)
    assert not os.path.isfile(sibling)
