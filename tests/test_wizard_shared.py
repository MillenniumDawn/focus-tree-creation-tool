from hoi4cm.wizards._shared import notifying_workspace_files


class FakeMod:
    def __init__(self, *, loaded, root):
        self.loaded = loaded
        self.root = root
        self.written = []

    def note_file_written(self, path):
        self.written.append(path)


def test_write_into_loaded_mod_notifies_catalog(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path))
    files = notifying_workspace_files(mod, str(tmp_path))
    target = tmp_path / "common" / "ideas" / "spirit.txt"

    files.write_text(target, "content", encoding="utf-8")

    assert mod.written == [str(target)]


def test_append_into_loaded_mod_notifies_catalog(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path))
    files = notifying_workspace_files(mod, str(tmp_path))
    target = tmp_path / "note.yml"
    target.write_text("l_english:\n")

    files.append_text(target, ' key: "v"\n', encoding="utf-8-sig")

    assert mod.written == [str(target)]


def test_write_into_other_root_does_not_notify(tmp_path):
    mod = FakeMod(loaded=True, root=str(tmp_path / "mod"))
    other = tmp_path / "elsewhere"
    files = notifying_workspace_files(mod, str(other))

    files.write_text(other / "note.txt", "content", encoding="utf-8")

    assert mod.written == []


def test_unloaded_mod_does_not_notify(tmp_path):
    mod = FakeMod(loaded=False, root="")
    files = notifying_workspace_files(mod, str(tmp_path))

    files.write_text(tmp_path / "note.txt", "content", encoding="utf-8")

    assert mod.written == []


def test_helper_is_reachable_from_the_mod_package():
    """Non-wizard callers (the monolith's export path, ui/mod_loading) reach
    it from hoi4cm.mod; _shared only re-exports it."""
    from hoi4cm.mod import notifying_workspace_files as canonical

    assert notifying_workspace_files is canonical


def test_empty_mod_root_does_not_notify(tmp_path, monkeypatch):
    """An unset save root must not accidentally match the cwd."""
    monkeypatch.chdir(tmp_path)
    mod = FakeMod(loaded=True, root=str(tmp_path))

    files = notifying_workspace_files(mod, "")
    files.write_text(tmp_path / "note.txt", "content", encoding="utf-8")

    assert mod.written == []
