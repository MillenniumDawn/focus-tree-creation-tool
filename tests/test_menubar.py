"""Behavioral checks for menu ownership."""

from __future__ import annotations

import tkinter as tk
from unittest.mock import MagicMock

from hoi4cm.ui.menubar import build_menubar

_MENU_CALLBACKS = (
    "_new_tree_dialog",
    "_save",
    "_load",
    "_load_mod_path",
    "_export",
    "_import_txt",
    "_import_drawio",
    "_undo",
    "_duplicate_focus",
    "_bulk_rename_dialog",
    "_select_all_focuses",
    "_delete_selected",
    "_toggle_grid",
    "_toggle_minimap",
    "_toggle_focus_list",
    "_fit_all",
    "_national_spirit_wizard",
    "_dyn_mod_wizard",
    "_decision_wizard",
    "_event_wizard",
    "_validate_tree",
    "_load_mod",
    "_show_post_load_prompt",
    "_open_settings",
    "_show_error_log",
)


def _descendants(parent: tk.Misc):
    for child in parent.winfo_children():
        yield child
        yield from _descendants(child)


def test_load_mod_is_only_in_file_import_export(tk_root):
    callbacks = {name: MagicMock() for name in _MENU_CALLBACKS}
    for name, callback in callbacks.items():
        setattr(tk_root, name, callback)

    toolbar = tk.Frame(tk_root)
    toolbar.pack()
    controller = build_menubar(tk_root, toolbar)

    file_rows = controller.show_preview("file", ("load_mod",))
    tk_root.update()
    assert len(file_rows) == 1
    load_mod_button = next(
        widget for widget in _descendants(file_rows[0]) if isinstance(widget, tk.Button)
    )
    assert load_mod_button.cget("text") == "Load Mod"

    controller.close()
    assert controller.show_preview("tools", ("load_mod",)) == []
    controller.close()

    controller.buttons["file"].invoke()
    tk_root.update()
    load_mod_button = next(
        widget
        for widget in _descendants(tk_root)
        if isinstance(widget, tk.Button) and widget.cget("text") == "Load Mod"
    )
    load_mod_button.invoke()
    tk_root.after(50, tk_root.quit)
    tk_root.mainloop()
    callbacks["_load_mod"].assert_called_once_with()
