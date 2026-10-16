"""Recovery token invalidation and failure retry coverage."""

import json

import pytest

import hoi4cm.editor.autosave_writer as aw
from hoi4cm.models import EditorWorkspace, Focus


def test_recovery_encodes_once_and_invalidates_all_state(tmp_path, monkeypatch):
    workspace = EditorWorkspace()
    workspace.focuses.add(Focus(id=1))
    calls = []
    serialize = aw.serialize_project

    def encode(ws):
        calls.append(ws.focuses.revision)
        return serialize(ws)

    monkeypatch.setattr(aw, "serialize_project", encode)
    paths = tuple(str(tmp_path / name) for name in ("global.json", "sibling.json"))
    writer = aw.AutosaveWriter()
    errors = []
    assert writer.save(workspace, paths, lambda: errors.append(True))
    assert len(calls) == 1
    assert not writer.save(workspace, paths, lambda: errors.append(True))
    assert (tmp_path / "global.json").read_bytes() == (
        tmp_path / "sibling.json"
    ).read_bytes()
    workspace.main_tree.extras["nested"] = {"a": [1]}
    assert writer.save(workspace, paths, lambda: errors.append(True))
    workspace.main_tree.extras["nested"]["a"].append(2)
    assert writer.save(workspace, paths, lambda: errors.append(True))
    workspace.focuses.move(1, 2, 3)
    assert writer.save(workspace, paths, lambda: errors.append(True))
    (tmp_path / "global.json").unlink()
    assert writer.save(workspace, paths, lambda: errors.append(True))
    replacement = EditorWorkspace()
    replacement.focuses.add(Focus(id=2))
    assert writer.save(replacement, paths, lambda: errors.append(True))
    assert (
        json.loads((tmp_path / "global.json").read_text(encoding="utf-8"))["workspace"][
            "focuses"
        ][0]["id"]
        == 2
    )
    assert not errors


@pytest.mark.parametrize("failed_index", [0, 1])
def test_failed_pair_retries_without_marking_success(
    tmp_path, monkeypatch, failed_index
):
    workspace = EditorWorkspace()
    paths = tuple(str(tmp_path / name) for name in ("global.json", "sibling.json"))
    original = aw.write_project_text
    calls = []

    def fail(path, text):
        calls.append(path)
        if path == paths[failed_index]:
            raise OSError("disk full")
        original(path, text)

    monkeypatch.setattr(aw, "write_project_text", fail)
    writer = aw.AutosaveWriter()
    errors = []
    if failed_index == 0:
        with pytest.raises(OSError):
            writer.save(workspace, paths, lambda: errors.append(True))
    else:
        writer.save(workspace, paths, lambda: errors.append(True))
        assert errors == [True]
    monkeypatch.setattr(aw, "write_project_text", original)
    assert writer.save(workspace, paths, lambda: errors.append(True))
    assert not writer.save(workspace, paths, lambda: errors.append(True))


def test_partial_pair_then_metadata_revert_rewrites_both(tmp_path, monkeypatch):
    workspace = EditorWorkspace()
    paths = tuple(str(tmp_path / name) for name in ("global.json", "sibling.json"))
    writer = aw.AutosaveWriter()
    writer.save(workspace, paths, lambda: None)
    original_bytes = (tmp_path / "global.json").read_bytes()
    original_write = aw.write_project_text

    def fail_sibling(path, text):
        if path == paths[1]:
            raise OSError("sibling full")
        original_write(path, text)

    workspace.main_tree.metadata.tree_id = "changed"
    monkeypatch.setattr(aw, "write_project_text", fail_sibling)
    writer.save(workspace, paths, lambda: None)
    workspace.main_tree.metadata.tree_id = "TAG_focus_tree"
    monkeypatch.setattr(aw, "write_project_text", original_write)
    assert writer.save(workspace, paths, lambda: None)
    assert (tmp_path / "global.json").read_bytes() == original_bytes
    assert (tmp_path / "sibling.json").read_bytes() == original_bytes
