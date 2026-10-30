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
from typing import cast

import pytest
from ui_fakes import AppFake

import hoi4_content_maker as main_mod
from hoi4cm.models import Focus
from hoi4cm.ui import settings_dialog
from hoi4cm.ui.canvas import CanvasMixin
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.gfx_browser import (
    open_focus_icon_browser,
    open_gfx_placement_editor,
    open_universal_gfx_browser,
)
from hoi4cm.ui.lifecycle import TkOwner
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
    monkeypatch.setattr(app.index, "is_md", True)
    app._additional_income_wizard()
    _assert_built(opened())


def test_character_wizard_opens_with_a_loaded_mod(app, opened, tmp_path, monkeypatch):
    monkeypatch.setattr(app.index, "loaded", True)
    monkeypatch.setattr(app.index, "root", str(tmp_path))
    app._character_wizard()
    _assert_built(opened())


def test_edit_targets_prompt_opens_with_a_loaded_mod(
    app, opened, tmp_path, monkeypatch
):
    for rel in ("common/ideas/a.txt", "events/b.txt", "common/national_focus/f.txt"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(app.index, "loaded", True)
    monkeypatch.setattr(app.index, "root", str(tmp_path))
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


def test_gfx_browsers_open(app, opened, tmp_path, monkeypatch) -> None:
    image = pytest.importorskip("PIL.Image")
    goals = tmp_path / "gfx" / "interface" / "goals"
    goals.mkdir(parents=True)
    # A real image: a failed decode would log from a worker thread (#319).
    image.new("RGBA", (8, 8), "#123456").save(goals / "icon.png")
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(goals))
    monkeypatch.setattr(app.index, "root", str(tmp_path))
    monkeypatch.setattr(
        app.app_config, "path_goals", os.path.join("gfx", "interface", "goals")
    )

    open_universal_gfx_browser(
        app, on_select=lambda *a: None, index=app.index, config=app.app_config
    )
    open_gfx_placement_editor(
        app,
        initial_items=[],
        on_confirm=lambda *a: None,
        index=app.index,
        config=app.app_config,
    )
    open_focus_icon_browser(
        app,
        on_select=lambda *a: None,
        current_gfx="",
        index=app.index,
        config=app.app_config,
    )

    windows = opened()
    assert len(windows) == 3
    assert all(window.winfo_children() for window in windows)


def test_tutorial_starts_and_closes(app, opened):
    assert app._tutorial.start(manual=True)
    _assert_built(opened())
    app._tutorial.close()


def test_canvas_state_initializes_and_pools_recover(app):
    """#167: canvas-owned state is ready once and pools recover after a sweep."""
    cv = tk.Canvas(app)
    try:
        fake = AppFake(cv=cv)
        # One shared initializer must have produced the whole contract.
        for attribute in (
            "_canvas_probe",
            "_scene_index",
            "_redraw_state",
            "_lines",
            "_lines_used",
            "_lines_key",
            "_grid_pool",
            "_grid_used",
            "_grid_key",
            "_legend_pool",
            "_legend_used",
            "_legend_key",
            "_legend_stack_key",
            "_coord_label_pools",
            "_coord_label_key",
            "_mm_visible",
            "_mm_canvas",
            "_image_broker",
            "_image_poll_job",
            "_focus_bounds_cache",
        ):
            assert hasattr(fake, attribute), attribute
        assert fake._mm_visible is False and fake._mm_canvas is None
        assert fake._cfp_x is None and fake._cfp_y is None

        # Immediate first render: schedulers, scene index and pools all live.
        CanvasMixin._redraw_now(
            fake, RedrawChannel.VIEW | RedrawChannel.SCENE, reason="test"
        )
        assert fake._rendering_frame is False
        probe = fake._canvas_probe
        assert fake._canvas_item_exists(probe)

        # An external cv.delete("all") sweep invalidates pooled item ids; the
        # sentinel probe recovers and the pools reset without re-initializing.
        cv.delete("all")
        fake._validate_canvas_probe()
        assert fake._canvas_probe != probe
        assert fake._canvas_item_exists(fake._canvas_probe)
        assert fake._lines == [] and fake._lines_used == 0
        assert fake._grid_pool == [] and fake._grid_used == 0
        assert fake._legend_pool == [] and fake._legend_used == 0
    finally:
        cv.destroy()
        gc.collect()


def test_minimap_toggle_and_cfp_are_optional_handles(app):
    """#167: genuinely optional handles stay optional but typed."""
    cv = tk.Canvas(app)
    try:
        fake = AppFake(cv=cv)
        assert fake._mm_scale is None  # geometry only after a visible render
        fake._toggle_minimap()
        assert fake._mm_visible is True
        assert fake._mm_canvas is not None
        assert fake._mm_canvas in cv.winfo_children()
        fake._draw_minimap()  # no focuses: overlay cleared, no geometry yet
        assert fake._mm_scale is None or fake._mm_scale > 0
        fake._toggle_minimap()
        assert fake._mm_visible is False

        # CFP values are host-owned document state drawn only when set.
        fake._cfp_x, fake._cfp_y = 96, 260
        fake.zoom = 1.0
        fake._draw_cfp_markers()
        assert cv.find_withtag("cfp_marker")
    finally:
        cv.destroy()
        gc.collect()


def test_real_app_recovers_a_populated_canvas_after_external_delete(monkeypatch):
    monkeypatch.setattr(main_mod.App, "_run_startup_prompts", lambda self: None)
    root = main_mod.App()
    try:
        parent = Focus(id=1, x=1, y=1)
        child = Focus(id=2, x=2, y=2)
        child.tree_idx = 1
        child.prereqs = [[parent.id]]
        root.focuses.extend([parent, child])
        root._extra_trees = [
            {"type": "shared", "tree_id": "EXTRA", "focus_ids": {child.id}}
        ]
        root.update_idletasks()
        root._redraw_now(RedrawChannel.VIEW | RedrawChannel.SCENE, reason="test")
        assert root._lines and root._grid_pool and root._legend_pool
        assert set(root._focus_bundles) == {parent.id, child.id}
        old_line = root._lines[0]
        scene = root._scene_index
        scheduler = root._redraw_state

        root.cv.delete("all")
        root._redraw_now(RedrawChannel.VIEW | RedrawChannel.SCENE, reason="test")

        assert not root.cv.type(old_line)
        assert root._scene_index is scene
        assert root._redraw_state is scheduler
        assert set(root._focus_bundles) == {parent.id, child.id}
        assert root.focuses[child.id].prereqs == [[parent.id]]
        for pool in (root._lines, root._grid_pool, root._legend_pool):
            assert pool and all(root.cv.type(item) for item in pool)
    finally:
        assert root._lifecycle is not None
        root._lifecycle.finish_close()
        root.destroy()
        gc.collect()


def test_close_with_pending_canvas_after_jobs_destroys_cleanly(monkeypatch):
    """Close sweeps widget-scheduled canvas timers and leaves their commands
    destroyable."""
    monkeypatch.setattr(main_mod.App, "_run_startup_prompts", lambda self: None)
    root = main_mod.App()
    nested = tk.Canvas(root.cv)
    tracked_owner = tk.Canvas(root.cv)
    try:
        root.cv.after(500, lambda: None)
        root.cv.after_idle(lambda: None)
        nested.after(500, lambda: None)
        nested.after_idle(lambda: None)
        assert root._lifecycle is not None
        # Canvas matches TkOwner at runtime; the stub signatures differ.
        root._lifecycle.after(cast(TkOwner, tracked_owner), 500, lambda: None)
        assert root.tk.call("after", "info"), "no pending jobs were scheduled"

        root._lifecycle.finish_close()
        assert not root.tk.call("after", "info"), "pending jobs survived close"
        for canvas in (root.cv, nested, tracked_owner):
            for name in _tcl_commands(canvas):
                assert canvas.tk.call(
                    "info", "commands", name
                ), "stale command left in a widget registry by close"
        root.destroy()
        gc.collect()
    finally:
        for window in (nested, tracked_owner):
            try:
                window.destroy()
            except tk.TclError:
                pass
        try:
            root.destroy()
        except tk.TclError:
            pass
        gc.collect()


def test_close_tolerates_owner_cancelled_and_destroyed_jobs(monkeypatch):
    """Close sweeps past jobs already cancelled or left by destroyed owners."""
    monkeypatch.setattr(main_mod.App, "_run_startup_prompts", lambda self: None)
    root = main_mod.App()
    dead = tk.Canvas(root.cv)
    try:
        job = root.cv.after(500, lambda: None)
        root.cv.after_cancel(job)
        assert root._lifecycle is not None
        assert root._lifecycle.after(cast(TkOwner, dead), 500, lambda: None)
        dead.destroy()

        root._lifecycle.finish_close()
        assert not root.tk.call("after", "info")
        root.destroy()
        gc.collect()
    finally:
        try:
            dead.destroy()
        except tk.TclError:
            pass
        try:
            root.destroy()
        except tk.TclError:
            pass
        gc.collect()


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
        assert root._mm_scale is not None
        assert root._mm_scale > 0
        assert root._mm_scale == pytest.approx(min(200 / 3, 130 / 3))
        assert len(root._mm_dot_pool) == 2
        for item in root._mm_dot_pool:
            left, top, right, bottom = mm.coords(item)
            assert 0 <= left < right <= 220
            assert 0 <= top < bottom <= 150

        scale = root._mm_scale
        root.update_idletasks()
        assert (mm.winfo_width(), mm.winfo_height()) == (220, 150)
        root._draw_minimap()
        assert root._mm_scale == scale

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
        assert root._mm_scale is not None
        assert root._mm_scale > 0
    finally:
        assert root._lifecycle is not None
        root._lifecycle.finish_close()
        root.destroy()
        gc.collect()


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
