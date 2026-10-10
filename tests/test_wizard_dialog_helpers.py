import tkinter as tk

import pytest

from hoi4cm.core import tr
from hoi4cm.wizards._shared import (
    format_save_summary,
    make_scrolled_listbox,
    pack_action_footer,
)


@pytest.mark.parametrize(
    ("saved", "warnings", "errs", "expected"),
    [
        (["a.txt"], [], [], "Saved:\na.txt"),
        (["a.txt", "b.txt"], [], [], "Saved:\na.txt\nb.txt"),
        (
            ["a.txt"],
            ["no new keys"],
            ["boom"],
            "Saved:\na.txt\n\nNotes:\nno new keys\n\nErrors:\nboom",
        ),
        ([], ["no new keys"], [], "Notes:\nno new keys"),
        ([], [], ["boom"], "Errors:\nboom"),
        (["a.txt"], [], ["boom"], "Saved:\na.txt\n\nErrors:\nboom"),
        ([], [], [], "Nothing to save."),
    ],
)
def test_format_save_summary(saved, warnings, errs, expected):
    assert format_save_summary(saved, warnings, errs) == expected


def test_format_save_summary_accepts_any_sequence():
    assert format_save_summary(("a.txt",), (), ("boom",)) == (
        "Saved:\na.txt\n\nErrors:\nboom"
    )


def test_scrolled_listbox_packs_listbox_and_vertical_scrollbar(tk_root):
    frame = tk.Frame(tk_root)
    frame.pack()

    listbox = make_scrolled_listbox(frame)

    scrollbars = [w for w in frame.winfo_children() if isinstance(w, tk.Scrollbar)]
    assert len(scrollbars) == 1
    assert scrollbars[0].cget("orient") == "vertical"
    assert scrollbars[0].pack_info()["side"] == "right"
    assert listbox.master is frame
    assert listbox.pack_info()["side"] == "left"
    assert listbox.pack_info()["expand"]


def test_scrolled_listbox_defaults(tk_root):
    listbox = make_scrolled_listbox(tk.Frame(tk_root))

    assert listbox.cget("selectmode") == "browse"
    assert listbox.cget("activestyle") == "none"
    assert str(listbox.cget("font")) == "Courier 10"


def test_scrolled_listbox_options_override_defaults(tk_root):
    listbox = make_scrolled_listbox(
        tk.Frame(tk_root), selectmode="extended", font=("Courier", 9)
    )

    assert listbox.cget("selectmode") == "extended"
    assert str(listbox.cget("font")) == "Courier 9"
    assert listbox.cget("activestyle") == "none"


def test_scrolled_listbox_scrollbar_drives_listbox(tk_root):
    frame = tk.Frame(tk_root)
    listbox = make_scrolled_listbox(frame)
    for n in range(50):
        listbox.insert("end", f"row {n}")
    scrollbar = next(w for w in frame.winfo_children() if isinstance(w, tk.Scrollbar))

    scrollbar.tk.call(scrollbar.cget("command"), "moveto", "0.5")

    assert listbox.yview()[0] > 0
    assert listbox.cget("yscrollcommand")


def test_action_footer_buttons_and_commands(tk_root):
    dlg = tk.Toplevel(tk_root)
    calls = []

    footer = pack_action_footer(dlg, "Import Selected", lambda: calls.append("go"))

    buttons = footer.winfo_children()
    assert len(buttons) == 2
    action, cancel = buttons[0], buttons[1]
    assert isinstance(action, tk.Button)
    assert action.cget("text") == "Import Selected"
    assert action.pack_info()["side"] == "left"
    assert cancel.cget("text") == tr("common.cancel", "Cancel")
    assert cancel.pack_info()["side"] == "right"
    assert footer.master is dlg

    action.invoke()
    assert calls == ["go"]
    assert dlg.winfo_exists()

    cancel.invoke()
    assert not dlg.winfo_exists()
