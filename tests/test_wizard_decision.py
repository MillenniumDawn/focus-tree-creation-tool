"""Tk integration coverage for decision/category imports and paired saves."""

from __future__ import annotations

import copy
import tkinter as tk

import pytest

import hoi4cm.wizards.decision as decision_mod
from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_decision_wizard(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = True
    MOD.root = None
    MOD.edit_decisions_file = ""
    MOD.edit_decisions_cat_file = ""
    MOD.edit_loc_file = ""
    MOD.edit_scripted_loc_file = ""
    monkeypatch.setattr(
        decision_mod, "autosave_path", lambda name: str(tmp_path / name)
    )
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


def _ensure_dnd_available(monkeypatch):
    if not hasattr(tk.Frame, "drop_target_register"):
        monkeypatch.setattr(
            tk.Frame,
            "drop_target_register",
            lambda self, *a, **k: None,
            raising=False,
        )
    if not hasattr(tk.Frame, "dnd_bind"):
        monkeypatch.setattr(
            tk.Frame, "dnd_bind", lambda self, *a, **k: None, raising=False
        )


def _button_by_text(root: tk.Misc, needle: str) -> tk.Button | None:
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and needle in cur.cget("text"):
            return cur
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return None


def _parent_with_label(root: tk.Misc, value: str) -> tk.Misc | None:
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Label) and cur.cget("text") == value:
            return cur.master
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return None


def _entry_for_label(root: tk.Misc, value: str) -> tk.Entry | None:
    stack: list[tk.Misc] = [root]
    while stack:
        cur = stack.pop()
        labels = [
            child
            for child in cur.winfo_children()
            if isinstance(child, tk.Label) and child.cget("text") == value
        ]
        entries = [
            child for child in cur.winfo_children() if isinstance(child, tk.Entry)
        ]
        if labels and entries:
            return entries[0]
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return None


def _cleanup(root: tk.Tk) -> None:
    for child in list(root.winfo_children()):
        if isinstance(child, tk.Toplevel):
            try:
                child.grab_release()
            except tk.TclError:
                pass
            child.destroy()
    root.update_idletasks()


def _write_decision_pair(root, *, bom=False):
    decisions = root / "common" / "decisions" / "TAG_decisions.txt"
    categories = root / "common" / "decisions" / "categories" / "TAG_decisions.txt"
    decisions.parent.mkdir(parents=True)
    categories.parent.mkdir(parents=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    decisions.write_text(
        "TAG_cat = {\n\tTAG_decision = {\n\t\tallowed = { always = yes }\n\t}\n}\n",
        encoding=encoding,
    )
    categories.write_text(
        "TAG_cat = {\n"
        "\tallowed = { always = yes }\n"
        "\tpriority = 5\n"
        "\tcustom_category_key = { category_flag = yes }\n"
        "\tcustom_category_key = category_value\n"
        "}\n",
        encoding=encoding,
    )
    return decisions, categories


def test_imported_category_fields_and_extras_survive_paired_save(
    tk_root, tmp_path, monkeypatch
):
    _ensure_dnd_available(monkeypatch)
    mod_root = tmp_path / "mod"
    decisions, categories = _write_decision_pair(mod_root, bom=True)
    MOD.root = str(mod_root)
    monkeypatch.setattr(
        "tkinter.filedialog.askopenfilenames",
        lambda **kwargs: (str(decisions), str(categories)),
    )
    confirmation_calls = []
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno",
        lambda *args, **kwargs: confirmation_calls.append(args) or True,
    )

    decision_mod.open_decision_wizard(tk_root)
    import_button = _button_by_text(tk_root, "Import .txt")
    assert import_button is not None
    import_button.invoke()

    category_row = _parent_with_label(tk_root, "TAG_cat")
    assert category_row is not None
    category_row.winfo_toplevel().deiconify()
    tk_root.update_idletasks()
    category_row.event_generate("<Button-1>", when="now")
    priority = _entry_for_label(tk_root, "PRIORITY")
    assert priority is not None
    assert priority.get() == "5"
    priority.delete(0, "end")
    priority.insert(0, "7")

    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    assert confirmation_calls == []
    saved_categories = categories.read_text(encoding="utf-8")
    saved_decisions = decisions.read_text(encoding="utf-8")
    assert "\tallowed = {" in saved_categories
    assert "\tpriority = 7" in saved_categories
    assert "custom_category_key = {" in saved_categories
    assert "category_flag = yes" in saved_categories
    assert saved_categories.count("custom_category_key =") == 2
    assert "TAG_decision" not in saved_categories
    assert "TAG_decision" in saved_decisions
    assert "custom_category_key" not in saved_decisions
    bom = b"\xef\xbb\xbf"
    assert decisions.read_bytes().count(bom) == 1
    assert categories.read_bytes().count(bom) == 1
    _cleanup(tk_root)


def test_unimported_auto_detected_categories_cancel_before_decision_write(
    tk_root, tmp_path, monkeypatch
):
    _ensure_dnd_available(monkeypatch)
    mod_root = tmp_path / "mod"
    decisions, categories = _write_decision_pair(mod_root)
    before_decisions = decisions.read_bytes()
    before_categories = categories.read_bytes()
    MOD.root = str(mod_root)
    monkeypatch.setattr(
        "tkinter.filedialog.askopenfilenames", lambda **kwargs: (str(decisions),)
    )
    confirmations = []
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno",
        lambda *args, **kwargs: confirmations.append(args) or False,
    )

    decision_mod.open_decision_wizard(tk_root)
    import_button = _button_by_text(tk_root, "Import .txt")
    assert import_button is not None
    import_button.invoke()

    save_button = _button_by_text(tk_root, "Save to Mod")
    assert save_button is not None
    save_button.invoke()

    overwrite_confirmations = [
        call for call in confirmations if call[0].startswith("Overwrite")
    ]
    assert len(overwrite_confirmations) == 1
    assert "categories" in overwrite_confirmations[0][0].lower()
    assert decisions.read_bytes() == before_decisions
    assert categories.read_bytes() == before_categories
    _cleanup(tk_root)
