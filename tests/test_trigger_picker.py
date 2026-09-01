"""Tk behavior tests for the shared trigger picker."""

import tkinter as tk

import hoi4cm.wizards.national_spirit as national_spirit
from hoi4cm.wizards._shared import open_trigger_picker, render_script_snippet
from hoi4cm.wizards.national_spirit import open_national_spirit_wizard


def _widgets(widget, kind):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found.extend(_widgets(child, kind))
    return found


def test_render_trigger_snippets_without_tk():
    from hoi4cm.data import TRIGGER_DEFS

    assert render_script_snippet(
        "always", TRIGGER_DEFS["always"], {}, is_trigger=True
    ) == ("\talways = yes\n")
    assert (
        render_script_snippet(
            "has_country_flag",
            TRIGGER_DEFS["has_country_flag"],
            {"flag": "my_flag"},
            is_trigger=True,
        )
        == "\thas_country_flag = my_flag\n"
    )
    assert (
        render_script_snippet(
            "has_war_support",
            TRIGGER_DEFS["has_war_support"],
            {"amount": "> 0.5"},
            is_trigger=True,
        )
        == "\thas_war_support > 0.5\n"
    )
    assert (
        render_script_snippet(
            "AND", TRIGGER_DEFS["AND"], {"conditions": "always = yes"}, is_trigger=True
        )
        == "\tAND = {\n\t\talways = yes\n\t}\n"
    )


def test_national_spirit_trigger_fields_use_picker(tk_root, monkeypatch):
    calls = []
    monkeypatch.setattr(
        national_spirit,
        "open_trigger_picker",
        lambda parent, target, on_insert=None: calls.append((parent, target)),
    )
    open_national_spirit_wizard(tk_root)
    picker_buttons = [
        button
        for button in _widgets(tk_root, tk.Button)
        if button.cget("text") == "+ Insert trigger"
    ]
    assert len(picker_buttons) == 4
    for button in picker_buttons:
        button.invoke()
    assert len(calls) == 4
    assert all(isinstance(target, tk.Text) for _, target in calls)

    for child in list(tk_root.winfo_children()):
        if isinstance(child, tk.Toplevel):
            child.destroy()


def test_trigger_picker_renders_comparison_trigger(tk_root):
    target = tk.Text(tk_root)
    picker = open_trigger_picker(tk_root, target)
    search = _widgets(picker, tk.Entry)[0]
    search.delete(0, "end")
    search.insert(0, "has_war_support")
    picker.update_idletasks()
    next(
        button
        for button in _widgets(picker, tk.Button)
        if "Insert Trigger" in button.cget("text")
    ).invoke()
    assert target.get("1.0", "end-1c") == "\thas_war_support > 0.5\n"


def test_trigger_picker_renders_nested_trigger_block(tk_root):
    target = tk.Text(tk_root)
    picker = open_trigger_picker(tk_root, target)
    search = _widgets(picker, tk.Entry)[0]
    search.delete(0, "end")
    search.insert(0, "AND")
    picker.update_idletasks()
    option_menus = _widgets(picker, tk.OptionMenu)
    option_menus[1]["menu"].invoke(0)
    picker.update_idletasks()
    insert_button = next(
        button
        for button in _widgets(picker, tk.Button)
        if "Insert Trigger" in button.cget("text")
    )
    insert_button.invoke()
    assert target.get("1.0", "end-1c") == "\tAND = {\n\t\talways = yes\n\t}\n"


def test_trigger_picker_inserts_into_selected_text_and_preserves_text(tk_root):
    target = tk.Text(tk_root)
    target.insert("1.0", "already_here = yes\n")
    picker = open_trigger_picker(tk_root, target)

    search = _widgets(picker, tk.Entry)[0]
    search.delete(0, "end")
    search.insert(0, "has_country_flag")
    picker.update_idletasks()
    option_menus = _widgets(picker, tk.OptionMenu)
    assert len(option_menus) >= 2
    trigger_menu = option_menus[1]["menu"]
    assert trigger_menu.entrycget(0, "label").startswith("[Script]")
    trigger_menu.invoke(0)
    picker.update_idletasks()

    entries = _widgets(picker, tk.Entry)
    assert entries
    entries[-1].delete(0, "end")
    entries[-1].insert(0, "my_flag")
    insert_buttons = [
        button
        for button in _widgets(picker, tk.Button)
        if "Insert Trigger" in button.cget("text")
    ]
    assert len(insert_buttons) == 1
    insert_buttons[0].invoke()

    assert target.get("1.0", "end-1c") == (
        "already_here = yes\n\thas_country_flag = my_flag\n"
    )
    assert not picker.winfo_exists()
