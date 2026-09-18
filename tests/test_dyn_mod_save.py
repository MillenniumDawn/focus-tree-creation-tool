"""Dynamic-modifier save-path regression tests."""

import os
import tkinter as tk

import pytest

import hoi4cm.core.logger as logmod
import hoi4cm.wizards.dyn_mod as dm_mod
from hoi4cm.wizards.dyn_mod import open_dyn_mod_wizard

_DEFAULT_MID = "TAG_my_dynamic_modifier"
_GFX_REL = os.path.join("interface", "ideas.gfx")


def _loc_rel(mid=_DEFAULT_MID):
    loc_target = dm_mod.MOD.loc_target
    return os.path.join("localisation", loc_target.dirname(), loc_target.filename(mid))


def _unread_paths(monkeypatch, *paths):
    unread = {os.path.abspath(str(path)) for path in paths}
    original = dm_mod.read_file

    def stub(path, *args, **kwargs):
        if os.path.abspath(path) in unread:
            return None
        return original(path, *args, **kwargs)

    monkeypatch.setattr(dm_mod, "read_file", stub)


def _set_icon(window, value):
    pending = [window]
    while pending:
        current = pending.pop()
        if isinstance(current, tk.Entry) and current.get() == "":
            current.insert(0, value)
            return
        pending.extend(current.winfo_children())
    raise AssertionError("dynamic-modifier icon entry not found")


def _assert_read_error(rel):
    entries = logmod.get_error_entries()
    assert any("Could not read existing file" in message for _, message in entries)
    assert any(rel in message for _, message in entries)


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


def _open_and_save(tk_root, tmp_path, monkeypatch, icon=None):
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
    if icon is not None:
        _set_icon(window, icon)
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


def test_save_skips_unreadable_loc(
    tmp_path, monkeypatch, tk_root, isolated_error_buffer
):
    loc_rel = _loc_rel()
    target = tmp_path / loc_rel
    target.parent.mkdir(parents=True)
    original = b"l_english:\n existing loc bytes\n"
    target.write_bytes(original)
    _unread_paths(monkeypatch, target)

    _, info_messages = _open_and_save(tk_root, tmp_path, monkeypatch)

    assert target.read_bytes() == original
    _assert_read_error(loc_rel)
    summary = "\n".join(str(arg) for call in info_messages for arg in call)
    assert loc_rel not in summary
    dm_target = tmp_path / "common" / "dynamic_modifiers" / f"{_DEFAULT_MID}.txt"
    assert dm_target.exists()


def test_save_reports_unreadable_loc_when_keys_already_exist(
    tmp_path, monkeypatch, tk_root, isolated_error_buffer
):
    loc_rel = _loc_rel()
    target = tmp_path / loc_rel
    target.parent.mkdir(parents=True)
    original = b"l_english:\n existing loc bytes\n"
    target.write_bytes(original)
    _unread_paths(monkeypatch, target)

    other = (
        tmp_path
        / "localisation"
        / dm_mod.MOD.loc_target.dirname()
        / "existing_keys_l_english.yml"
    )
    other.write_text(
        "l_english:\n"
        ' TAG_my_dynamic_modifier: "Name"\n'
        ' TAG_my_dynamic_modifier_desc: "Desc"\n'
        ' modifies_dynamic_modifier_tt: "Modifies $MODIFIER$"\n'
        ' stability_factor_tt: "Stability Factor"\n'
        ' industrial_capacity_factory_tt: "Industrial Capacity Factory"\n'
        ' political_power_gain_tt: "Political Power Gain"\n',
        encoding="utf-8-sig",
    )

    _, info_messages = _open_and_save(tk_root, tmp_path, monkeypatch)

    assert target.read_bytes() == original
    _assert_read_error(loc_rel)
    summary = "\n".join(str(arg) for call in info_messages for arg in call)
    assert loc_rel not in summary


def test_save_skips_unreadable_ideas_gfx(
    tmp_path, monkeypatch, tk_root, isolated_error_buffer
):
    target = tmp_path / _GFX_REL
    target.parent.mkdir(parents=True)
    original = b"spriteTypes = {\n existing gfx bytes\n}\n"
    target.write_bytes(original)
    _unread_paths(monkeypatch, target)

    _, info_messages = _open_and_save(tk_root, tmp_path, monkeypatch, icon="my_icon")

    assert target.read_bytes() == original
    _assert_read_error(_GFX_REL)
    summary = "\n".join(str(arg) for call in info_messages for arg in call)
    assert _GFX_REL not in summary
    loc_target = tmp_path / _loc_rel()
    assert loc_target.exists()


def test_save_creates_missing_loc_and_gfx(tmp_path, monkeypatch, tk_root):
    _open_and_save(tk_root, tmp_path, monkeypatch, icon="my_icon")

    loc_target = tmp_path / _loc_rel()
    assert loc_target.exists()
    loc_text = loc_target.read_text(encoding="utf-8-sig")
    assert f" {_DEFAULT_MID}:" in loc_text

    gfx_target = tmp_path / _GFX_REL
    assert gfx_target.exists()
    gfx_text = gfx_target.read_text(encoding="utf-8")
    assert "GFX_idea_my_icon" in gfx_text
    assert "spriteTypes" in gfx_text
