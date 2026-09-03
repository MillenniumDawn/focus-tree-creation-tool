"""Dynamic-modifier save-path regression tests."""

import tkinter as tk

import pytest

import hoi4cm.core.logger as logmod
import hoi4cm.wizards.dyn_mod as dm_mod
from hoi4cm.wizards.dyn_mod import open_dyn_mod_wizard


@pytest.fixture
def isolated_error_buffer():
    original_entries = list(logmod.get_error_entries())
    original_callback = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        yield
    finally:
        logmod.clear_errors()
        logmod.get_error_entries().extend(original_entries)
        logmod.set_error_callback(original_callback)


def _save_button(window):
    pending = [window]
    while pending:
        current = pending.pop()
        if isinstance(current, tk.Button) and current.cget("text") == dm_mod.tr(
            "common.generate_all_files", "Generate All Files ->"
        ):
            return current
        pending.extend(current.winfo_children())
    raise AssertionError("dynamic-modifier save button not found")


def _open_and_save(tk_root, tmp_path, monkeypatch):
    info_messages = []
    monkeypatch.setattr(dm_mod.filedialog, "askdirectory", lambda **_: str(tmp_path))
    monkeypatch.setattr(
        dm_mod.messagebox,
        "showinfo",
        lambda *args, **kwargs: info_messages.append(args),
    )
    monkeypatch.setattr(dm_mod.messagebox, "showerror", lambda *args, **kwargs: None)
    open_dyn_mod_wizard(tk_root)
    tk_root.update_idletasks()
    window = next(
        child for child in tk_root.winfo_children() if isinstance(child, tk.Toplevel)
    )
    _save_button(window).invoke()
    return window, info_messages


def test_read_existing_file_distinguishes_missing_content_and_failure(
    tmp_path, monkeypatch
):
    missing = tmp_path / "missing.txt"
    existing = tmp_path / "existing.txt"
    existing.write_text("existing = {}\n", encoding="utf-8")

    assert dm_mod._read_existing_file(missing) == (dm_mod._READ_MISSING, None)
    assert dm_mod._read_existing_file(existing) == (
        dm_mod._READ_CONTENT,
        "existing = {}\n",
    )

    monkeypatch.setattr(dm_mod, "read_file", lambda _path: None)
    assert dm_mod._read_existing_file(existing) == (dm_mod._READ_FAILED, None)


def test_save_skips_unreadable_dynamic_modifier(
    tmp_path, monkeypatch, tk_root, isolated_error_buffer
):
    target = tmp_path / "common" / "dynamic_modifiers" / "TAG_my_dynamic_modifier.txt"
    target.parent.mkdir(parents=True)
    original = b"\xff\xfeexisting modifier bytes\n"
    target.write_bytes(original)
    monkeypatch.setattr(dm_mod, "read_file", lambda _path: None)

    _, info_messages = _open_and_save(tk_root, tmp_path, monkeypatch)

    assert target.read_bytes() == original
    entries = logmod.get_error_entries()
    assert any("Could not read existing file" in message for _, message in entries)
    assert any(str(target.relative_to(tmp_path)) in message for _, message in entries)
    summary = "\n".join(str(arg) for call in info_messages for arg in call)
    assert str(target.relative_to(tmp_path)) not in summary


def test_save_creates_missing_dynamic_modifier(tmp_path, monkeypatch, tk_root):
    _open_and_save(tk_root, tmp_path, monkeypatch)

    target = tmp_path / "common" / "dynamic_modifiers" / "TAG_my_dynamic_modifier.txt"
    assert target.exists()
    assert b"TAG_my_dynamic_modifier = {" in target.read_bytes()
