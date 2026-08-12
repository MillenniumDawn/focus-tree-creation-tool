import tkinter as tk

from hoi4cm.core import tr
from hoi4cm.wizards._shared import notifying_workspace_files, open_effect_picker


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


# ── open_effect_picker (issue #45: decision wizard's "+ Effect Picker"
# button called this as a bare, never-defined name and crashed with
# NameError; event wizard's own copy is now this same shared function) ──


def _find_button(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == text:
            return child
        found = _find_button(child, text)
        if found is not None:
            return found
    return None


def _find_entry_with_value(widget, value):
    for child in widget.winfo_children():
        if isinstance(child, tk.Entry) and child.get() == value:
            return child
        found = _find_entry_with_value(child, value)
        if found is not None:
            return found
    return None


def _find_label_with_text(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, tk.Label) and child.cget("text") == text:
            return child
        found = _find_label_with_text(child, text)
        if found is not None:
            return found
    return None


def _search_entry(popup):
    placeholder = tr("focus.effects.search_placeholder", "Search effects...")
    entry = _find_entry_with_value(popup, placeholder)
    assert entry is not None
    return entry


def test_open_effect_picker_opens_without_on_insert(tk_root):
    """Regression test for the decision wizard's crash: decision.py's call
    sites pass no on_insert callback at all (unlike event.py)."""
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)
    try:
        assert popup.winfo_exists()
    finally:
        popup.destroy()


def test_open_effect_picker_insert_writes_snippet_and_closes_popup(tk_root):
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)
    assert target.get("1.0", "end-1c") == ""

    insert_btn = _find_button(
        popup, tr("effect_picker.insert_effect", "+ Insert Effect")
    )
    assert isinstance(insert_btn, tk.Button)
    insert_btn.invoke()

    assert target.get("1.0", "end-1c") != ""
    assert not popup.winfo_exists()  # the button closes its own popup


def test_open_effect_picker_insert_calls_on_insert_callback(tk_root):
    """event.py wires on_insert=_schedule_preview to refresh its live
    preview after a snippet lands in the text box. on_insert is called with
    no arguments, matching _schedule_preview's own signature."""
    target = tk.Text(tk_root)
    calls = []
    popup = open_effect_picker(tk_root, target, on_insert=lambda: calls.append(True))

    insert_btn = _find_button(
        popup, tr("effect_picker.insert_effect", "+ Insert Effect")
    )
    assert isinstance(insert_btn, tk.Button)
    insert_btn.invoke()

    assert calls == [True]


def test_open_effect_picker_cancel_closes_without_inserting(tk_root):
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)

    cancel_btn = _find_button(popup, tr("common.cancel", "Cancel"))
    assert isinstance(cancel_btn, tk.Button)
    cancel_btn.invoke()

    assert target.get("1.0", "end-1c") == ""
    assert not popup.winfo_exists()


def test_open_effect_picker_search_narrows_to_matching_effect(tk_root):
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)

    entry = _search_entry(popup)
    entry.delete(0, "end")
    entry.insert(0, "add_political_power")
    popup.update_idletasks()

    insert_btn = _find_button(
        popup, tr("effect_picker.insert_effect", "+ Insert Effect")
    )
    assert isinstance(insert_btn, tk.Button)
    insert_btn.invoke()

    assert "add_political_power" in target.get("1.0", "end-1c")


def test_open_effect_picker_search_with_no_matches_shows_none_found(tk_root):
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)

    entry = _search_entry(popup)
    entry.delete(0, "end")
    entry.insert(0, "no_such_effect_xyz")
    popup.update_idletasks()

    none_found = tr("focus.effects.none_found", "No effects found")
    assert _find_label_with_text(popup, none_found) is not None
    popup.destroy()


def test_open_effect_picker_clearing_search_restores_full_dropdown(tk_root):
    """Blank search text is treated as "no filter", not "match nothing"."""
    target = tk.Text(tk_root)
    popup = open_effect_picker(tk_root, target)

    entry = _search_entry(popup)
    entry.delete(0, "end")
    entry.insert(0, "no_such_effect_xyz")
    popup.update_idletasks()
    entry.delete(0, "end")
    popup.update_idletasks()

    none_found = tr("focus.effects.none_found", "No effects found")
    assert _find_label_with_text(popup, none_found) is None
    popup.destroy()
