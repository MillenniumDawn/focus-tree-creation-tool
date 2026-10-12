"""Tk smoke: the real App and every dialog it opens build without raising.

The only file allowed to construct Tk. It guards the #45 class of bug, a
missing name that only surfaces on click. It runs in its own process so Tk
objects never share an interpreter with the headless suite:

    xvfb-run -a pytest -m tk
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

import pytest

import hoi4_content_maker as main_mod
from hoi4cm.mod import MOD
from hoi4cm.ui.gfx_browser import (
    open_focus_icon_browser,
    open_gfx_placement_editor,
    open_universal_gfx_browser,
)
from hoi4cm.wizards._shared import open_effect_picker, open_trigger_picker

pytestmark = pytest.mark.tk


@pytest.fixture(scope="module")
def app():
    with pytest.MonkeyPatch.context() as patch:
        # The 800 ms startup prompts would open the tutorial mid-test.
        patch.setattr(main_mod.App, "_run_startup_prompts", lambda self: None)
        root = main_mod.App()
        root.update()
        yield root
        root.destroy()
        gc.collect()


@pytest.fixture(autouse=True)
def quiet_dialogs(monkeypatch):
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(f"tkinter.messagebox.{name}", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **kw: False)
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: "")
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: "")


@pytest.fixture
def opened(app):
    """Return the Toplevels a test opened, and destroy them afterwards."""
    before = set(app.winfo_children())

    def new_windows() -> list[tk.Toplevel]:
        app.update()
        return [
            child
            for child in app.winfo_children()
            if child not in before and isinstance(child, tk.Toplevel)
        ]

    yield new_windows
    for window in new_windows():
        window.destroy()
    app.update()


def _assert_built(windows: list[tk.Toplevel]) -> None:
    assert windows, "no Toplevel was created"
    assert windows[0].winfo_children(), "the Toplevel is empty"


def test_app_builds_its_chrome(app):
    assert app.cv.winfo_exists()
    assert app._add_focus_btn.winfo_exists()
    assert app._errlog_btn.winfo_exists()


@pytest.mark.parametrize(
    "command",
    [
        "_new_tree_dialog",
        "_open_settings",
        "_show_error_log",
        "_validate_tree",
        "_national_spirit_wizard",
        "_dyn_mod_wizard",
        "_decision_wizard",
        "_event_wizard",
    ],
)
def test_app_command_opens_its_dialog(app, opened, command):
    getattr(app, command)()
    _assert_built(opened())


def test_additional_income_wizard_opens_in_md_mode(app, opened, monkeypatch):
    monkeypatch.setattr(MOD, "is_md", True)
    app._additional_income_wizard()
    _assert_built(opened())


def test_character_wizard_opens_with_a_loaded_mod(app, opened, tmp_path, monkeypatch):
    monkeypatch.setattr(MOD, "loaded", True)
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    app._character_wizard()
    _assert_built(opened())


def test_edit_targets_prompt_opens_with_a_loaded_mod(
    app, opened, tmp_path, monkeypatch
):
    for rel in ("common/ideas/a.txt", "events/b.txt", "common/national_focus/f.txt"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(MOD, "loaded", True)
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    app._show_post_load_prompt()
    _assert_built(opened())


@pytest.mark.parametrize("picker", [open_effect_picker, open_trigger_picker])
def test_script_picker_opens(app, opened, picker):
    target = tk.Text(app)
    try:
        picker(app, target)
        _assert_built(opened())
    finally:
        target.destroy()


def test_gfx_browsers_open(app, opened, tmp_path, monkeypatch):
    goals = tmp_path / "gfx" / "interface" / "goals"
    goals.mkdir(parents=True)
    (goals / "icon.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(goals))
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    monkeypatch.setattr(MOD, "path_goals", os.path.join("gfx", "interface", "goals"))

    open_universal_gfx_browser(app, on_select=lambda *a: None)
    open_gfx_placement_editor(app, initial_items=[], on_confirm=lambda *a: None)
    open_focus_icon_browser(app, on_select=lambda *a: None, current_gfx="")

    windows = opened()
    assert len(windows) == 3
    assert all(window.winfo_children() for window in windows)


def test_tutorial_starts_and_closes(app, opened):
    assert app._tutorial.start(manual=True)
    _assert_built(opened())
    app._tutorial.close()


def test_entry_point_smoke_check(tmp_path):
    # The real entry point in a fresh process, as the frozen build runs it.
    entry = Path(main_mod.__file__).resolve()
    subprocess.run(
        [sys.executable, str(entry), "--smoke-test"],
        cwd=tmp_path,
        check=True,
        timeout=30,
    )
