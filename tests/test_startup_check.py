"""The release smoke check must initialize Tk and propagate startup failures."""

import subprocess
import sys
import tkinter as tk
from pathlib import Path

import pytest

from hoi4cm.ui.startup_check import check_tk_startup


def test_check_tk_startup(tk_root, tmp_path):
    # Use the real entry point in a fresh process, as the frozen build does.
    entry = Path(__file__).resolve().parents[1] / "hoi4_content_maker.py"
    subprocess.run(
        [sys.executable, str(entry), "--smoke-test"],
        cwd=tmp_path,
        check=True,
        timeout=30,
    )


def test_check_tk_startup_propagates_missing_tcl(monkeypatch):
    def missing_tcl():
        raise tk.TclError("missing init.tcl")

    monkeypatch.setattr("hoi4cm.ui.startup_check.tk.Tk", missing_tcl)
    with pytest.raises(tk.TclError, match="missing init.tcl"):
        check_tk_startup()
