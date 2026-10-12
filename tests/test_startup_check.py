"""The release smoke check must propagate Tk startup failures."""

import tkinter as tk

import pytest

from hoi4cm.ui.startup_check import check_tk_startup


def test_check_tk_startup_propagates_missing_tcl(monkeypatch):
    def missing_tcl():
        raise tk.TclError("missing init.tcl")

    monkeypatch.setattr("hoi4cm.ui.startup_check.tk.Tk", missing_tcl)
    with pytest.raises(tk.TclError, match="missing init.tcl"):
        check_tk_startup()
