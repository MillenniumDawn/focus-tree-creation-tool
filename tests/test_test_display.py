"""Test display isolation without substituting fake Tk geometry."""

import os
import subprocess
import sys
import tkinter as tk
from types import SimpleNamespace

import conftest
import pytest
import test_display
from test_display import DISPLAY_ENV, TestDisplay


def test_direct_roots_are_hidden_and_cleaned_up(tk_root, monkeypatch):
    # Exercise the fixture's failure teardown independently of pytest's own
    # outer fixture, including a root that the test forgot to destroy.
    monkeypatch.setenv("HOI4CM_SHOW_TK", "0")
    request = SimpleNamespace(
        node=SimpleNamespace(get_closest_marker=lambda _: None),
        config=SimpleNamespace(getoption=lambda _: False),
    )
    guard = conftest.hide_tk_windows.__wrapped__(request, monkeypatch)
    next(guard)
    root = tk.Tk()
    dialog = tk.Toplevel(root)
    root.update()
    assert root.state() == dialog.state() == "withdrawn"
    assert not root.winfo_viewable()
    guard.close()
    with pytest.raises(tk.TclError):
        root.winfo_exists()


def test_pure_test_mode_rejects_tk(monkeypatch):
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda _: True))
    guard = conftest.hide_tk_windows.__wrapped__(request, monkeypatch)
    next(guard)
    try:
        with pytest.raises(pytest.fail.Exception, match="forbidden"):
            tk.Tk()
    finally:
        guard.close()


@pytest.mark.visible_tk
def test_explicit_ui_tests_still_map_and_take_real_grabs(tk_root):
    dialog = tk.Toplevel(tk_root)
    tk_root.update()
    try:
        assert tk_root.winfo_viewable()
        assert dialog.winfo_viewable()
        dialog.grab_set()
        assert tk_root.grab_current() == dialog
    finally:
        dialog.destroy()


@pytest.mark.skipif(sys.platform != "linux", reason="Xvfb is Linux-only")
def test_private_display_and_children_restore_environment():
    before = {name: os.environ.get(name) for name in ("DISPLAY", DISPLAY_ENV)}
    display = TestDisplay()
    try:
        display.start()
        process = display.process
        assert process is not None
        assert os.environ["DISPLAY"] != before["DISPLAY"]
        # A fresh interpreter inherits the private server and can map real UI.
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import tkinter as t; r=t.Tk(); r.update(); "
                "assert r.winfo_viewable(); r.destroy()",
            ],
            check=True,
            timeout=30,
        )
    finally:
        display.close()
    assert process.poll() is not None
    assert {name: os.environ.get(name) for name in before} == before
    display.close()  # Idempotent pytest/atexit cleanup.


def test_missing_xvfb_is_actionable(monkeypatch):
    monkeypatch.setattr(test_display.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Install xvfb"):
        TestDisplay().start()


@pytest.mark.skipif(sys.platform != "linux", reason="Xvfb is Linux-only")
@pytest.mark.parametrize(
    "script", ["import time; time.sleep(30)", "raise SystemExit(2)"]
)
def test_failed_display_start_reaps_child_and_preserves_environment(
    monkeypatch, script
):
    before = {name: os.environ.get(name) for name in ("DISPLAY", DISPLAY_ENV)}
    popen = subprocess.Popen
    children = []

    def launch(*args, **kwargs):
        child = popen([sys.executable, "-c", script], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(test_display.shutil, "which", lambda _: "Xvfb")
    monkeypatch.setattr(test_display.subprocess, "Popen", launch)
    display = TestDisplay()
    with pytest.raises(RuntimeError, match="Xvfb"):
        display.start(timeout=0.2)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert display.output is None
    assert display.errors is None
    assert {name: os.environ.get(name) for name in before} == before
