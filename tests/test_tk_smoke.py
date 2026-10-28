"""Tk smoke: the real App, its dialogs, and the canvas regressions.

The only file allowed to construct Tk. It guards the #45 class of bug, a
missing name that only surfaces on click, and keeps the focus-callback and
wheel-zoom regressions that need a real canvas. It runs in its own process
so Tk objects never share an interpreter with the headless suite:

    xvfb-run -a pytest -m tk
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ui_fakes import AppFake

import hoi4_content_maker as main_mod
from hoi4cm.mod import MOD
from hoi4cm.models import Focus
from hoi4cm.ui import settings_dialog
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.gfx_browser import (
    open_focus_icon_browser,
    open_gfx_placement_editor,
    open_universal_gfx_browser,
)
from hoi4cm.ui.theme import XGRID, YGRID
from hoi4cm.ui.widgets import grab_when_visible
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
    # Finalize dead widgets here, before a worker thread's collection can (#319).
    gc.collect()


def _assert_built(windows: list[tk.Toplevel]) -> None:
    assert windows, "no Toplevel was created"
    assert windows[0].winfo_children(), "the Toplevel is empty"


def test_app_builds_its_chrome(app):
    assert app.cv.winfo_exists()
    assert app._add_focus_btn.winfo_exists()
    assert app._errlog_btn.winfo_exists()


def test_dialog_grab_is_deferred_until_mapping(app):
    dialog = tk.Toplevel(app)
    dialog.after(300, lambda: dialog.destroy() if dialog.winfo_exists() else None)

    assert grab_when_visible(dialog)
    if not dialog.winfo_viewable():
        assert app.grab_current() is not dialog
    app.update()
    assert dialog.winfo_viewable()
    assert app.grab_current() is dialog


def test_withdrawn_before_mapping_does_not_block_or_grab(app):
    dialog = tk.Toplevel(app)
    dialog.after_idle(dialog.withdraw)
    dialog.after(300, lambda: dialog.destroy() if dialog.winfo_exists() else None)

    assert grab_when_visible(dialog)
    app.update()
    assert dialog.winfo_exists()
    assert dialog.state() == "withdrawn"
    assert app.grab_current() is not dialog


def test_destroy_before_mapping_cancels_deferred_grab(app):
    app.tk.eval(
        "set ::dialog_map_bgerrors {}; "
        "proc bgerror {message} {lappend ::dialog_map_bgerrors $message}"
    )
    dialog = tk.Toplevel(app)
    dialog.after_idle(dialog.destroy)
    dialog.after(300, lambda: dialog.destroy() if dialog.winfo_exists() else None)

    assert grab_when_visible(dialog)
    app.update()
    assert not dialog.winfo_exists()
    assert app.tk.eval("llength $::dialog_map_bgerrors") == "0"


def test_settings_builder_survives_dialog_destroy_during_idle(app, monkeypatch):
    original_toplevel = tk.Toplevel
    created = []

    def destroy_after_idle(parent):
        dialog = original_toplevel(parent)
        dialog.after_idle(dialog.destroy)
        dialog.after(300, lambda: dialog.destroy() if dialog.winfo_exists() else None)
        created.append(dialog)
        return dialog

    monkeypatch.setattr(settings_dialog.tk, "Toplevel", destroy_after_idle)

    settings_dialog.open_settings(app)
    app.update()

    assert len(created) == 1
    assert not created[0].winfo_exists()


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
    image = pytest.importorskip("PIL.Image")
    goals = tmp_path / "gfx" / "interface" / "goals"
    goals.mkdir(parents=True)
    # A real image: a failed decode would log from a worker thread (#319).
    image.new("RGBA", (8, 8), "#123456").save(goals / "icon.png")
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


def test_minimap_first_show_uses_requested_size_before_geometry_settles(monkeypatch):
    monkeypatch.setattr(main_mod.App, "_run_startup_prompts", lambda self: None)
    root = main_mod.App()
    try:
        parent = Focus(id=1, x=1, y=1)
        child = Focus(id=2, x=2, y=2)
        child.prereqs = [[parent.id]]
        root.focuses.extend([parent, child])
        root.update_idletasks()

        root._toggle_minimap()

        mm = root._mm_canvas
        assert mm is not None and mm.winfo_exists()
        assert root._mm_world_bounds == (0.0, 0.0, 3.0, 3.0)
        assert root._mm_scale > 0
        assert root._mm_scale == pytest.approx(min(200 / 3, 130 / 3))
        assert len(root._mm_dot_pool) == 2
        for item in root._mm_dot_pool:
            left, top, right, bottom = mm.coords(item)
            assert 0 <= left < right <= 220
            assert 0 <= top < bottom <= 150

        root._mm_click(SimpleNamespace(x=110, y=75))
        assert root.offset[0] == pytest.approx(
            root.cv.winfo_width() / 2 - 1.5 * XGRID * root.zoom
        )
        assert root.offset[1] == pytest.approx(
            root.cv.winfo_height() / 2 - 1.5 * YGRID * root.zoom
        )
        root._toggle_minimap()
        assert root._mm_visible is False
        root._toggle_minimap()
        assert root._mm_canvas is mm
        assert root._mm_scale > 0
    finally:
        assert root._lifecycle is not None
        root._lifecycle.finish_close()
        root.destroy()
        gc.collect()


@pytest.mark.parametrize(
    "reported_size,expected_size",
    [
        ((0, 0), (220, 150)),
        ((1, 1), (220, 150)),
        ((1, 300), (220, 300)),
        ((400, 1), (400, 150)),
        ((400, 300), (400, 300)),
    ],
)
def test_minimap_keeps_each_realized_dimension(reported_size, expected_size):
    cv = Mock()
    cv.winfo_width.return_value = 800
    cv.winfo_height.return_value = 600
    fake = AppFake([Focus(id=1, x=1, y=1), Focus(id=2, x=2, y=2)], cv=cv)
    mm = Mock()
    mm.winfo_exists.return_value = 1
    mm.winfo_width.return_value, mm.winfo_height.return_value = reported_size
    fake._mm_visible = True
    fake._mm_canvas = mm

    fake._draw_minimap()

    assert fake._mm_content_key[-2:] == expected_size
    width, height = expected_size
    assert fake._mm_scale == pytest.approx(min((width - 20) / 3, (height - 20) / 3))


_FAR_RECT = (0.0, 0.0, 10.0, 10.0)


def _tcl_commands(cv: tk.Canvas) -> set[str]:
    """tk.Canvas._tclCommands is a private Tk attribute (not in stubs)."""
    return set(getattr(cv, "_tclCommands", None) or ())


def test_focus_callbacks_released_on_cull_lod_and_external_delete(app):
    cv = tk.Canvas(app)
    try:
        fake = AppFake(cv=cv)
        focus = Focus(id=1, x=1, y=1)
        baseline = _tcl_commands(cv)
        for _ in range(3):
            fake.zoom = 1.0
            fake._draw_focus(focus, _FAR_RECT)
            full_commands = _tcl_commands(cv) - baseline
            assert len(full_commands) == 70
            fake.zoom = 0.3
            fake._draw_focus(focus, _FAR_RECT)
            assert len(_tcl_commands(cv) - baseline) == 15
            # Tkinter names use Python object IDs, which can be reused after free.
            retired = full_commands - _tcl_commands(cv)
            assert not any(cv.tk.call("info", "commands", cmd) for cmd in retired)
            cv.delete("all")
            fake._validate_canvas_probe()
            assert _tcl_commands(cv) == baseline
            fake.zoom = 1.0
            fake._draw_focus(focus, _FAR_RECT)
            fake._reclaim_focus_bundles(set())
            assert _tcl_commands(cv) == baseline
            fake._reclaim_focus_bundles(set())
    finally:
        cv.destroy()
        gc.collect()


def test_scroll_burst_coalesces_and_keeps_pointer_anchor(app, monkeypatch):
    cv = tk.Canvas(app)
    try:
        fake = AppFake(cv=cv)
        fake._canvas_runtime()
        jobs = []
        frames = []
        monkeypatch.setattr(cv, "after", lambda delay, cb: jobs.append(cb) or "job")
        monkeypatch.setattr(fake, "_render_frame", frames.append)
        fake._redraw(RedrawChannel.SCENE, reason="edit")
        for x, y, num, delta in [(70, 90, 4, 120), (90, 30, 5, -120)] * 6:
            world = ((x - fake.offset[0]) / fake.zoom, (y - fake.offset[1]) / fake.zoom)
            fake._scroll(SimpleNamespace(x=x, y=y, num=num, delta=delta))
            assert (x - fake.offset[0]) / fake.zoom == pytest.approx(world[0])
            assert (y - fake.offset[1]) / fake.zoom == pytest.approx(world[1])
        assert len(jobs) == 1
        assert frames == []
        jobs[0]()
        assert frames == [RedrawChannel.SCENE | RedrawChannel.VIEW]
        fake.zoom = 4.0
        fake._scroll(SimpleNamespace(x=70, y=90, num=4, delta=120))
        assert len(jobs) == 1
    finally:
        cv.destroy()
        gc.collect()
