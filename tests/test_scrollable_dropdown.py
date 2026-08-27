"""ScrollableDropdown — issue #72.

The Idea Wizard's modifier picker used to be a native tk.OptionMenu: with a
category holding 150+ entries the menu was taller than the screen, wheel
events unposted it while selecting whatever was under the pointer, and
off-screen entries were reachable only via keyboard. The dropdown now posts
a scrollable Listbox popup sized to the screen.
"""

import tkinter as tk

import pytest

from hoi4cm.ui import ScrollableDropdown
from hoi4cm.wizards.national_spirit import open_national_spirit_wizard

ITEMS = [(f"mod_{i}", f"mod_{i}  (float)") for i in range(120)]


def _dropdowns(root):
    found = []

    def _walk(w):
        if isinstance(w, ScrollableDropdown):
            found.append(w)
        for child in w.winfo_children():
            _walk(child)

    _walk(root)
    return found


def _make(tk_root, items=None, value="mod_0"):
    var = tk.StringVar(value=value)
    dd = ScrollableDropdown(tk_root, variable=var, items=items or ITEMS)
    dd.pack()
    tk_root.update_idletasks()
    return dd, var


def _open(dd):
    dd.btn.invoke()
    dd.update_idletasks()
    assert dd._popup is not None and dd._popup.winfo_exists()
    assert dd._lb is not None
    return dd._popup, dd._lb


def test_button_shows_label_for_current_value(tk_root):
    dd, var = _make(tk_root, value="mod_3")
    assert dd.btn.cget("text") == "mod_3  (float)  ▾"
    var.set("mod_7")
    assert dd.btn.cget("text") == "mod_7  (float)  ▾"


def test_open_popup_lists_every_item_in_a_capped_listbox(tk_root):
    dd, _var = _make(tk_root)
    popup, lb = _open(dd)
    assert lb.size() == len(ITEMS)
    assert lb.cget("height") <= ScrollableDropdown.MAX_ROWS
    assert lb.cget("height") < len(ITEMS)
    popup.destroy()


@pytest.mark.visible_tk
def test_popup_geometry_stays_on_screen(tk_root):
    dd, _var = _make(tk_root)
    popup, lb = _open(dd)
    popup.update_idletasks()
    x = popup.winfo_rootx()
    y = popup.winfo_rooty()
    assert x >= 0
    assert y >= 0
    assert x + popup.winfo_width() <= dd.winfo_screenwidth()
    assert y + popup.winfo_height() <= dd.winfo_screenheight()
    popup.destroy()


def test_wheel_scrolls_without_committing_or_closing(tk_root):
    dd, var = _make(tk_root)
    popup, lb = _open(dd)
    start = var.get()

    lb.event_generate("<MouseWheel>", delta=-120)
    dd.update_idletasks()

    assert popup.winfo_exists()  # must not close on scroll (issue #72)
    assert var.get() == start  # and must not commit the highlighted entry
    assert lb.yview()[1] > 0.0
    popup.destroy()


@pytest.mark.visible_tk
def test_arrow_keys_move_highlight_without_committing(tk_root):
    dd, var = _make(tk_root)
    popup, lb = _open(dd)

    lb.selection_clear(0, "end")
    lb.selection_set(0)
    lb.event_generate("<Down>")
    dd.update_idletasks()

    assert popup.winfo_exists()
    assert var.get() == "mod_0"
    assert lb.curselection() == (1,)
    popup.destroy()


@pytest.mark.visible_tk
def test_return_commits_highlighted_entry_and_closes(tk_root):
    dd, var = _make(tk_root)
    popup, lb = _open(dd)

    lb.selection_clear(0, "end")
    lb.selection_set(4)
    lb.event_generate("<Return>")
    dd.update_idletasks()

    assert var.get() == "mod_4"
    assert not popup.winfo_exists()


@pytest.mark.visible_tk
def test_escape_closes_without_committing(tk_root):
    dd, var = _make(tk_root)
    popup, lb = _open(dd)
    start = var.get()

    lb.event_generate("<Escape>")
    dd.update_idletasks()

    assert var.get() == start
    assert not popup.winfo_exists()


@pytest.mark.visible_tk
def test_click_release_commits_clicked_entry(tk_root):
    dd, var = _make(tk_root)
    popup, lb = _open(dd)

    lb.selection_clear(0, "end")
    lb.selection_set(9)  # the class binding does this on press
    lb.event_generate("<ButtonRelease-1>")
    dd.update_idletasks()

    assert var.get() == "mod_9"
    assert not popup.winfo_exists()


def test_destroy_removes_trace_from_shared_variable(tk_root):
    """The wizard rebuilds the dropdown on every search keystroke; a stale
    trace on the surviving StringVar must not outlive the widget."""
    dd, var = _make(tk_root)
    dd.destroy()
    var.set("mod_42")  # must not raise on the destroyed widget


def test_destroy_closes_popup(tk_root):
    dd, _var = _make(tk_root)
    popup, _lb = _open(dd)
    dd.destroy()
    assert not popup.winfo_exists()


def test_wizard_uses_scrollable_dropdown_for_modifiers(tk_root):
    """Regression test for issue #72: the Idea Wizard's modifier picker must
    be a ScrollableDropdown, and its popup must survive a wheel scroll."""
    open_national_spirit_wizard(tk_root)
    try:
        dropdowns = _dropdowns(tk_root)
        assert dropdowns, "idea wizard has no ScrollableDropdown"
        dd = dropdowns[0]
        dd.btn.invoke()
        dd.update_idletasks()
        assert dd._popup is not None and dd._popup.winfo_exists()
        assert dd._lb is not None
        dd._lb.event_generate("<MouseWheel>", delta=-120)
        dd.update_idletasks()
        assert dd._popup.winfo_exists()
        dd._close_popup()
    finally:
        for w in tk_root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
