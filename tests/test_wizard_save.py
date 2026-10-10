"""Headless coverage for wizard writes and code-apply rollback paths."""

from __future__ import annotations

import copy
import json
import tkinter as tk

import pytest

import hoi4cm.wizards.decision as decision_mod
import hoi4cm.wizards.event as event_mod
import hoi4cm.wizards.national_spirit as spirit_mod
from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    MOD.is_md = False
    monkeypatch.setattr(event_mod, "autosave_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(spirit_mod, "autosave_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(
        decision_mod, "autosave_path", lambda name: str(tmp_path / name)
    )
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: False)
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


def _ensure_dnd_available():
    if not hasattr(tk.Frame, "drop_target_register"):
        tk.Frame.drop_target_register = lambda self, *a, **k: None  # type: ignore[attr-defined]
    if not hasattr(tk.Frame, "dnd_bind"):
        tk.Frame.dnd_bind = lambda self, *a, **k: None  # type: ignore[attr-defined]


def _button_by_text(root: tk.Misc, needle: str) -> tk.Button | None:
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and needle in cur.cget("text"):
            return cur
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return None


def _entries_by_value(root: tk.Misc, value: str) -> list[tk.Entry]:
    found = []
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Entry) and cur.get() == value:
            found.append(cur)
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return found


def _labels(root: tk.Misc) -> list[str]:
    found = []
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Label):
            found.append(cur.cget("text"))
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return found


def _code_texts(root: tk.Misc, bg="#080b10") -> list[tk.Text]:
    found = []
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Text) and cur.cget("bg") == bg:
            found.append(cur)
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return found


def _flush_after(root: tk.Tk) -> None:
    root.after(120, root.quit)
    root.mainloop()


def _cleanup(root: tk.Tk) -> None:
    for child in list(root.winfo_children()):
        if isinstance(child, tk.Toplevel):
            try:
                child.grab_release()
            except tk.TclError:
                pass
            child.destroy()
    root.update_idletasks()


def test_existing_event_id_is_skipped_without_changing_user_files(
    tk_root, tmp_path, monkeypatch
):
    root = tmp_path / "mod"
    event_path = root / "events" / "my_namespace.txt"
    loc_path = root / "localisation" / "english" / "my_namespace_l_english.yml"
    event_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    event_path.write_text(
        "add_namespace = my_namespace\n\ncountry_event = {\n\tid = my_namespace.1\n}\n",
        encoding="utf-8",
    )
    loc_path.write_text(
        "l_english:\n"
        ' my_namespace.1.t: "Existing title"\n'
        ' my_namespace.1.d: "Existing description"\n'
        ' my_namespace.1.a: "Existing option"\n',
        encoding="utf-8",
    )
    before_event = event_path.read_bytes()
    before_loc = loc_path.read_bytes()
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_events_file = str(event_path)
    MOD.edit_loc_file = str(loc_path)

    event_mod.open_event_wizard(tk_root)
    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    assert event_path.read_bytes() == before_event
    assert loc_path.read_bytes() == before_loc
    _cleanup(tk_root)


def test_event_append_preserves_one_source_utf8_bom(tk_root, tmp_path):
    root = tmp_path / "mod"
    event_path = root / "events" / "my_namespace.txt"
    loc_path = root / "localisation" / "english" / "my_namespace_l_english.yml"
    event_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    event_path.write_bytes(
        (
            "add_namespace = my_namespace\n\n"
            "country_event = {\n\tid = my_namespace.99\n}\n"
        ).encode("utf-8-sig")
    )
    loc_path.write_text("l_english:\n", encoding="utf-8")
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_events_file = str(event_path)
    MOD.edit_loc_file = str(loc_path)

    event_mod.open_event_wizard(tk_root)
    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    assert event_path.read_bytes().count(bytes((0xEF, 0xBB, 0xBF))) == 1
    assert "my_namespace.1" in event_path.read_text(encoding="utf-8-sig")
    _cleanup(tk_root)


def test_spirit_append_preserves_one_source_utf8_bom(tk_root, tmp_path):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_path.write_bytes(
        (
            "ideas = {\n\tcountry = {\n"
            "\t\tOTHER_spirit = {\n\t\t\tname = OTHER_spirit\n\t\t}\n"
            "\t}\n}\n"
        ).encode("utf-8-sig")
    )
    loc_path.write_text("l_english:\n", encoding="utf-8")
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_ideas_file = str(ideas_path)
    MOD.edit_loc_file = str(loc_path)

    spirit_mod.open_national_spirit_wizard(tk_root)
    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    assert ideas_path.read_bytes().count(bytes((0xEF, 0xBB, 0xBF))) == 1
    assert "TAG_my_spirit" in ideas_path.read_text(encoding="utf-8-sig")
    _cleanup(tk_root)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_spirit_save_preserves_existing_blocks_and_localisation(
    tk_root, tmp_path, monkeypatch, newline
):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_before = (
        (
            "# Keep this header\n"
            "ideas = {\n\tcountry = {\n\t\tOTHER_spirit = {\n"
            '\t\t\tcustom_field = "keep } # literal"\n'
            "\t\t\tmodifier = { stability_factor = 0.2 }\n\t\t}\n"
            "\t}\n\thidden = {\n\t\tOTHER_hidden = { cost = 10 }\n\t}\n}\n"
            "# Keep this footer\n"
        )
        .replace("\n", newline)
        .encode("utf-8-sig")
    )
    loc_before = (
        (
            "l_english:\n # Keep this comment\n"
            ' OTHER_spirit:0 "Existing spirit"\n'
            ' OTHER_spirit_desc:0 "Existing description"\n'
        )
        .replace("\n", newline)
        .encode("utf-8-sig")
    )
    ideas_path.write_bytes(ideas_before)
    loc_path.write_bytes(loc_before)
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_ideas_file = str(ideas_path)
    MOD.edit_loc_file = str(loc_path)
    messages = []
    monkeypatch.setattr(
        "tkinter.messagebox.showinfo",
        lambda _title, message, **_kwargs: messages.append(message),
    )

    spirit_mod.open_national_spirit_wizard(tk_root)
    name_entries = _entries_by_value(tk_root, "My National Spirit")
    assert len(name_entries) == 1
    name_entries[0].delete(0, "end")
    name_entries[0].insert(0, 'New "quoted" spirit')
    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    ideas_after = ideas_path.read_bytes()
    loc_after = loc_path.read_bytes()
    slot_close = ("\t}" + newline + "\thidden").encode("utf-8")
    prefix, tail = ideas_before.split(slot_close, 1)
    assert ideas_after.startswith(prefix)
    assert ideas_after.endswith(slot_close + tail)
    assert ideas_after.count(b"TAG_my_spirit = {") == 1
    assert ideas_after.count(bytes((0xEF, 0xBB, 0xBF))) == 1
    expected_loc = (
        (
            ' TAG_my_spirit: "New \\"quoted\\" spirit"\n'
            ' TAG_my_spirit_desc: "A spirit granting special bonuses."\n'
        )
        .replace("\n", newline)
        .encode("utf-8")
    )
    assert loc_after == loc_before + expected_loc
    assert len(messages) == 1
    assert "Saved:" in messages[0]
    assert "Errors:" not in messages[0]

    save_button.invoke()

    assert ideas_path.read_bytes() == ideas_after
    assert loc_path.read_bytes() == loc_after
    assert len(messages) == 2
    assert "already exists" in messages[1]
    assert "Localisation keys already present" in messages[1]
    assert "Errors:" not in messages[1]
    _cleanup(tk_root)


@pytest.mark.parametrize("version", ["", "0"])
@pytest.mark.parametrize(
    ("title", "description"),
    [
        ("Raw title", "Raw description"),
        ('A "quoted" name', 'A "quoted" description\\path\n§YColored§!'),
    ],
)
def test_spirit_raw_save_roundtrips_localisation_and_preserves_override(
    tk_root, tmp_path, version, title, description
):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_path.write_text("ideas = {\n\tcountry = {\n\t}\n}\n", encoding="utf-8")
    loc_before = 'l_english:\n OTHER_spirit:0 "Existing spirit"\n'
    loc_path.write_text(loc_before, encoding="utf-8-sig")
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_ideas_file = str(ideas_path)
    MOD.edit_loc_file = str(loc_path)

    spirit_mod.open_national_spirit_wizard(tk_root)
    previews = _code_texts(tk_root, "#0d1117")
    assert len(previews) == 1
    preview = previews[0]
    raw = preview.get("1.0", "end").strip()
    raw = raw.replace(
        'TAG_my_spirit: "My National Spirit"',
        f"TAG_my_spirit:{version} {json.dumps(title, ensure_ascii=False)}",
    ).replace(
        'TAG_my_spirit_desc: "A spirit granting special bonuses."',
        f"TAG_my_spirit_desc:{version} {json.dumps(description, ensure_ascii=False)}",
    )
    raw = raw.replace(
        "TAG_my_spirit = {", 'TAG_my_spirit = {\n\t\t\tcustom_field = "kept"'
    )
    edit = _button_by_text(tk_root, "Edit")
    assert edit is not None
    edit.invoke()
    preview.delete("1.0", "end")
    preview.insert("1.0", raw)
    save_raw = _button_by_text(tk_root, "Save Raw")
    assert save_raw is not None
    save_raw.invoke()

    assert _entries_by_value(tk_root, title)
    assert _entries_by_value(tk_root, description)
    assert preview.get("1.0", "end").strip() == raw
    assert preview.cget("state") == "disabled"
    save_mod = _button_by_text(tk_root, "Save to Mod")
    assert save_mod is not None
    save_mod.invoke()

    localisation = loc_path.read_text(encoding="utf-8-sig")
    assert localisation.startswith(loc_before)
    values = {
        key: json.loads(value)
        for line in localisation.splitlines()[2:]
        for key, value in [line.strip().split(": ", 1)]
    }
    assert values == {"TAG_my_spirit": title, "TAG_my_spirit_desc": description}
    assert 'custom_field = "kept"' in ideas_path.read_text(encoding="utf-8")
    assert preview.get("1.0", "end").strip() == raw
    _cleanup(tk_root)


@pytest.mark.parametrize("failed_target", ["ideas", "localisation"])
def test_spirit_save_reports_directory_failure(
    tk_root, tmp_path, monkeypatch, failed_target
):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_before = b"ideas = { country = { } }\n"
    loc_before = b"l_english:\n"
    ideas_path.write_bytes(ideas_before)
    loc_path.write_bytes(loc_before)
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_ideas_file = str(ideas_path)
    MOD.edit_loc_file = str(loc_path)
    failed_path = ideas_path if failed_target == "ideas" else loc_path
    mkdir = spirit_mod.os.makedirs

    def fail_directory(path, **kwargs):
        if path == str(failed_path.parent):
            raise PermissionError("read-only directory")
        return mkdir(path, **kwargs)

    monkeypatch.setattr(spirit_mod.os, "makedirs", fail_directory)
    messages = []
    monkeypatch.setattr(
        "tkinter.messagebox.showinfo",
        lambda _title, message, **_kwargs: messages.append(message),
    )
    spirit_mod.open_national_spirit_wizard(tk_root)
    save_mod = _button_by_text(tk_root, "Save to Mod")
    assert save_mod is not None
    save_mod.invoke()

    assert len(messages) == 1
    assert "Errors:" in messages[0]
    assert "read-only directory" in messages[0]
    if failed_target == "ideas":
        assert ideas_path.read_bytes() == ideas_before
    else:
        assert loc_path.read_bytes() == loc_before
    _cleanup(tk_root)


def test_existing_spirit_id_is_skipped_without_changing_user_files(tk_root, tmp_path):
    root = tmp_path / "mod"
    ideas_path = root / "common" / "ideas" / "existing.txt"
    loc_path = root / "localisation" / "english" / "existing_l_english.yml"
    ideas_path.parent.mkdir(parents=True)
    loc_path.parent.mkdir(parents=True)
    ideas_path.write_text(
        "ideas = {\n\tcountry = {\n\t\tTAG_my_spirit = {\n"
        "\t\t\tname = TAG_my_spirit\n\t\t}\n\t}\n}\n",
        encoding="utf-8",
    )
    loc_path.write_text(
        "l_english:\n"
        ' TAG_my_spirit: "Existing spirit"\n'
        ' TAG_my_spirit_desc: "Existing description"\n',
        encoding="utf-8",
    )
    before_ideas = ideas_path.read_bytes()
    before_loc = loc_path.read_bytes()
    MOD.loaded = True
    MOD.root = str(root)
    MOD.edit_ideas_file = str(ideas_path)
    MOD.edit_loc_file = str(loc_path)

    spirit_mod.open_national_spirit_wizard(tk_root)
    entries = _entries_by_value(tk_root, "TAG_my_spirit")
    assert entries
    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    assert ideas_path.read_bytes() == before_ideas
    assert loc_path.read_bytes() == before_loc
    _cleanup(tk_root)


def test_decision_export_writes_decision_and_category_files(
    tk_root, tmp_path, monkeypatch
):
    _ensure_dnd_available()
    decision_mod.open_decision_wizard(tk_root)
    new_category = _button_by_text(tk_root, "New Category")
    assert new_category is not None
    new_category.invoke()
    new_decision = _button_by_text(tk_root, "New Decision")
    assert new_decision is not None
    new_decision.invoke()
    export_path = tmp_path / "decisions.txt"
    monkeypatch.setattr(
        "tkinter.filedialog.asksaveasfilename", lambda **kwargs: str(export_path)
    )

    export_button = _button_by_text(tk_root, "Export .txt")
    assert export_button is not None
    export_button.invoke()

    category_path = tmp_path / "decisions_categories.txt"
    assert export_path.is_file()
    assert category_path.is_file()
    assert "TAG_my_decision" in export_path.read_text(encoding="utf-8")
    assert "TAG_my_category" in category_path.read_text(encoding="utf-8")
    _cleanup(tk_root)


def test_malformed_decision_apply_restores_model_and_reports_failure(
    tk_root, monkeypatch
):
    _ensure_dnd_available()
    decision_mod.open_decision_wizard(tk_root)
    new_category = _button_by_text(tk_root, "New Category")
    assert new_category is not None
    new_category.invoke()
    new_decision = _button_by_text(tk_root, "New Decision")
    assert new_decision is not None
    new_decision.invoke()
    code_button = _button_by_text(tk_root, "Code")
    assert code_button is not None
    code_button.invoke()
    _flush_after(tk_root)

    code_texts = _code_texts(tk_root)
    assert len(code_texts) == 1
    code_text = code_texts[0]
    code_text.configure(state="normal")
    code_text.delete("1.0", "end")
    code_text.insert("1.0", "TAG_broken = {")
    code_text.configure(state="disabled")
    report_calls = []
    monkeypatch.setattr(
        decision_mod,
        "report_error",
        lambda *args, **kwargs: report_calls.append((args, kwargs)),
    )

    apply_button = _button_by_text(tk_root, "Apply edits")
    assert apply_button is not None
    apply_button.invoke()

    labels = _labels(tk_root)
    assert any("TAG_my_category" in text for text in labels)
    assert any("TAG_my_decision" in text for text in labels)
    assert not any("TAG_broken" in text for text in labels)
    assert len(report_calls) == 1
    assert "unbalanced braces" in report_calls[0][0][0]
    assert report_calls[0][1]["title"] == "Parse Error"

    refresh_button = _button_by_text(tk_root, "Refresh")
    assert refresh_button is not None
    refresh_button.invoke()
    _flush_after(tk_root)
    refreshed_code = _code_texts(tk_root)
    assert len(refreshed_code) == 1
    refreshed_text = refreshed_code[0].get("1.0", "end")
    assert "TAG_my_decision" in refreshed_text
    assert "TAG_broken" not in refreshed_text
    _cleanup(tk_root)


def test_decision_save_confirmation_detects_other_existing_target(tmp_path):
    source = tmp_path / "imported.txt"
    target = tmp_path / "other.txt"

    assert not decision_mod.decision_save_needs_confirmation(
        str(source), str(source), True
    )
    assert decision_mod.decision_save_needs_confirmation(str(target), str(source), True)
    assert not decision_mod.decision_save_needs_confirmation(
        str(target), str(source), False
    )
