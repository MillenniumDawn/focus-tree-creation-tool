"""App bootstrap keeps Tk first in the runtime mixin chain."""

from __future__ import annotations

import tkinter as tk
from typing import Protocol

import hoi4_content_maker as app_module


def test_app_initializer_reaches_tk_before_ui_setup(monkeypatch) -> None:
    tk_initializations: list[bool] = []

    def tk_init(_self: tk.Tk, *_args: object, **_kwargs: object) -> None:
        tk_initializations.append(True)

    monkeypatch.setattr(tk.Tk, "__init__", tk_init)
    monkeypatch.setattr(app_module, "_apply_tk_dpi_scaling", lambda _root: None)
    for method in (
        "title",
        "geometry",
        "configure",
        "resizable",
        "protocol",
        "after",
        "_build_ui",
        "_redraw",
        "_schedule_validation",
        "_update_title",
        "_schedule_autosave",
        "_workspace_fingerprint",
    ):
        monkeypatch.setattr(app_module.App, method, lambda *_args, **_kwargs: None)

    app = app_module.App()

    assert tk_initializations == [True]
    assert app._extra_trees == []
    assert app._grid_on is True
    assert Protocol not in app_module.App.__mro__
