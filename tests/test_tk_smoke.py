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

import pytest
from ui_fakes import AppFake

import hoi4_content_maker as main_mod
from hoi4cm.editor.project_codec import read_project
from hoi4cm.editor.workspace_autosave import sibling_autosave_path
from hoi4cm.mod import MOD
from hoi4cm.models import Focus
from hoi4cm.ui import settings_dialog
from hoi4cm.ui.canvas_scheduler import RedrawChannel
from hoi4cm.ui.gfx_browser import (
    open_focus_icon_browser,
    open_gfx_placement_editor,
    open_universal_gfx_browser,
)
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
    assert not app._focus_editor.window.winfo_ismapped()
    assert not hasattr(app, "_sash")
    assert all(button._line.winfo_exists() for button, _panel in app._tab_btns.values())
    assert app._project_sidebar.empty.winfo_ismapped()
    assert list(app._editor_chrome.navigation_buttons) == [
        "Focus Trees",
        "Decisions",
        "Events",
        "Ideas",
        "Dynamic Modifiers",
    ]


def test_validation_preserves_sidebar_theme_and_style(app, opened):
    from tkinter import ttk

    from hoi4cm.ui.project_sidebar import NAVY

    style = ttk.Style(app)
    theme = style.theme_use()
    properties = ("background", "fieldbackground", "foreground", "rowheight")
    before = {name: style.lookup("Project.Treeview", name) for name in properties}
    scrollbar = style.lookup("Project.Vertical.TScrollbar", "troughcolor")
    assert before["background"] == NAVY
    app._validate_tree()
    _assert_built(opened())
    app._refresh_validation_dialog(app._validation_win)
    app.update()
    assert style.theme_use() == theme
    assert {
        name: style.lookup("Project.Treeview", name) for name in properties
    } == before
    assert style.lookup("Project.Vertical.TScrollbar", "troughcolor") == scrollbar
    assert style.lookup("Val.Treeview", "background") == "#050810"


def test_project_explorer_search_expansion_selection_and_keyboard(app, monkeypatch):
    sidebar = app._project_sidebar
    app._new_focus_at(72, 72)
    first = app.selected
    app._new_focus_at(76, 72)
    second = app.selected
    first.name = "EXPLORER_first"
    first.loc_name = ("Long readable name " * 12).strip()
    second.name = "EXPLORER_second"
    app._populate(second)
    second.tree_idx = 1
    app._extra_trees.append(
        {
            "tree_id": "joint_explorer",
            "type": "joint",
            "file_path": "joint.txt",
            "focus_ids": {second.id},
        }
    )
    app.focuses.touch()
    app._invalidate_focus_list_structure()
    app.update()
    tree = sidebar.tree
    before = [focus.to_dict() for focus in app.focuses.values()]
    undo_count = len(app._undo_stack)
    tree.item("tree:0", open=False)
    app._lp_search_var.set("EXPLORER_first")
    sidebar.render()
    assert tree.exists(f"focus:{first.id}")
    assert tree.exists("project")
    assert not tree.exists(f"focus:{second.id}")
    assert tree.item("tree:0", "open")
    app._lp_search_var.set("")
    sidebar.render()
    assert not tree.item("tree:0", "open")
    assert tree.exists(f"focus:{second.id}")
    assert tree.selection() == (f"focus:{second.id}",)
    tree.item("tree:0", open=True)
    tree.selection_set(f"focus:{first.id}")
    tree.focus(f"focus:{first.id}")
    tree.focus_force()
    app.update()
    assert app.selected is first
    assert not app._focus_actions.blocks_canvas
    tree.event_generate("<Down>")
    app.update()
    assert [focus.to_dict() for focus in app.focuses.values()] == before
    assert len(app._undo_stack) == undo_count
    app._select(second)
    app.update()
    assert tree.selection() == (f"focus:{second.id}",)
    called = []
    monkeypatch.setattr(app._focus_actions, "show", lambda fid: called.append(fid))
    sidebar.activate()
    assert called == [second.id]
    app._lp_search_var.set("no-matching-explorer-entry")
    sidebar.render()
    assert "No results" in sidebar.message.cget("text")
    app._lp_search_var.set("")
    sidebar.render()
    app._extra_trees.pop()
    second.tree_idx = 0
    app.focuses.touch()
    sidebar.refresh()


def test_project_explorer_invalid_draft_blocks_selection_and_tools(app):
    app._new_focus_at(80, 80)
    first = app.selected
    app._new_focus_at(84, 80)
    second = app.selected
    app._fv_cost.set("invalid draft")
    sidebar = app._project_sidebar
    sidebar.refresh()
    sidebar.tree.selection_set(f"focus:{first.id}")
    app.update()
    assert app.selected is second
    assert app._fv_cost.get() == "invalid draft"
    assert sidebar.tree.selection() == (f"focus:{second.id}",)
    app._editor_chrome.navigate("Decisions", lambda: pytest.fail("invalid draft left"))
    assert app._editor_chrome.active_content == "Focus Trees"
    app._fv_cost.set(str(second.cost))
    app._focus_editor.close()


def test_explorer_rebuilds_never_move_the_canvas(app, monkeypatch):
    sidebar = app._project_sidebar
    app._new_focus_at(150, 60)
    first = app.selected
    app._new_focus_at(154, 60)
    app.update()
    tree = sidebar.tree
    sentinel = [1234.0, 5678.0]
    # A canvas redraw would otherwise move the highlight back to the focus row.
    monkeypatch.setattr(app, "_update_focus_list_selection", lambda: None)

    tree.selection_set("tree:0")
    app.update()
    assert app.offset != sentinel, "choosing a tree row still recenters the canvas"

    def search():
        app._lp_search_var.set(first.name)
        sidebar.render()

    def revision_bump():
        app.focuses.touch()
        sidebar.refresh()

    for rebuild in (sidebar.render, search, revision_bump):
        app.offset[:] = sentinel
        rebuild()
        app.update()
        assert app.offset == sentinel, rebuild.__name__
        assert tree.selection() == ("tree:0",), rebuild.__name__
    app._lp_search_var.set("")
    sidebar.render()
    app.update()

    app.offset[:] = sentinel
    tree.selection_set("tree:0")
    app.update()
    assert app.offset != sentinel, "a real click must still recenter"


def test_explorer_ignores_pure_moves_but_follows_structure(app, monkeypatch):
    sidebar = app._project_sidebar
    app._new_focus_at(160, 60)
    focus = app.selected
    app.update()
    renders = []
    original = sidebar.render
    monkeypatch.setattr(sidebar, "render", lambda: renders.append(1) or original())

    app.focuses.move(focus.id, 160, 61)
    app.focuses.move(focus.id, 161, 61)
    sidebar.refresh()
    assert not renders, "dragging or nudging must not rebuild the explorer"

    focus.name = "EXPLORER_renamed_by_structure"
    app.focuses.touch()
    sidebar.refresh()
    assert len(renders) == 1
    assert sidebar.tree.exists(f"focus:{focus.id}")
    sidebar.refresh()
    assert len(renders) == 1, "a refresh with nothing new must not render"


def test_explorer_label_follows_localized_name_edits(app):
    sidebar = app._project_sidebar
    app._new_focus_at(170, 60)
    focus = app.selected
    key = f"focus:{focus.id}"
    app.update()

    app._fv_loc_name.set("Applied Localized Name")
    app._apply()
    app.update()
    assert sidebar.tree.item(key, "text").strip() == "Applied Localized Name"

    app._fv_loc_name.set("Flushed Localized Name")
    assert app._focus_editor.flush()
    sidebar.refresh()
    assert sidebar.tree.item(key, "text").strip() == "Flushed Localized Name"


def test_project_sidebar_collapse_resize_and_scaled_rows(app):
    sidebar = app._project_sidebar
    geometry = app.geometry()
    selected = app.selected
    query = app._lp_search_var.get()
    sidebar.panes.sash_place(0, 310, 0)
    app.update()

    width = sidebar.panel.winfo_width()
    sidebar.toggle()
    app.update()
    assert not app._left_panel_visible
    sidebar.toggle()
    app.update()
    assert abs(sidebar.panel.winfo_width() - width) <= 5
    assert app.selected is selected
    assert app._lp_search_var.get() == query
    app.geometry("760x640")
    app.update()
    assert sidebar.panel.winfo_width() >= int(230 * sidebar.scale)
    assert app.cv.winfo_width() > 200
    assert int(sidebar.tree.cget("height")) > 0
    assert sidebar.tree.cget("takefocus")
    app.geometry(geometry)
    app.update()


def test_project_resource_discovery_is_cached_and_reveals_existing_sources(
    app, tmp_path, monkeypatch
):
    import hoi4cm.ui.project_sidebar as sidebar_module

    source = tmp_path / "localisation" / "english" / "real_l_english.yml"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"l_english:\n")
    calls = []

    def immediate(_app, work, done):
        calls.append("discover")
        done(work())

    monkeypatch.setattr(sidebar_module, "run_bg", immediate)
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    monkeypatch.setattr(MOD, "mod_name", "Resource test")
    sidebar = app._project_sidebar
    sidebar.refresh()
    assert len(calls) == 1
    app._lp_search_var.set("real_l_english")
    sidebar.render()
    item = next(item for item in sidebar.resources if item.path == str(source))
    assert sidebar.tree.exists(item.key)
    assert sidebar.tree.exists(item.parent)
    sidebar.refresh()
    assert len(calls) == 1
    revealed = []
    monkeypatch.setattr(sidebar_module, "reveal_source", revealed.append)
    sidebar.tree.selection_set(item.key)
    sidebar.activate()
    assert revealed == [str(source)]
    assert source.read_bytes() == b"l_english:\n"
    sidebar.reload_resources()
    assert len(calls) == 2
    app._lp_search_var.set("")
    sidebar.render()


def test_project_sidebar_at_simulated_200_percent_dpi():
    code = """
import hoi4_content_maker as main
main.App._run_startup_prompts = lambda self: None

def simulate_dpi(app):
    app.tk.call('tk', 'scaling', 192 / 72)
    app.maxsize(1440, 1000)

main._apply_tk_dpi_scaling = simulate_dpi
app = main.App()
try:
    app.minsize(1440, 1000)
    app.geometry('1440x1000')
    app.update()
    sidebar = app._project_sidebar
    layout = {
        'tk': app.tk.call('package', 'provide', 'Tk'),
        'window': app.geometry(),
        'minimum': app.minsize(),
        'maximum': app.maxsize(),
        'screen': (app.winfo_screenwidth(), app.winfo_screenheight()),
        'scale': sidebar.scale,
        'panel_width': sidebar.panel.winfo_width(),
        'panes_width': sidebar.panes.winfo_width(),
    }
    assert (app.winfo_width(), app.winfo_height()) == (1440, 1000), layout
    assert sidebar.scale > 1.9, layout
    assert sidebar.panel.winfo_width() >= 540, layout
    assert int(sidebar.tree.tk.call('ttk::style', 'configure',
               'Project.Treeview', '-rowheight')) >= 64
    assert sidebar.icons[0].width() >= 60
    assert app.cv.winfo_width() > 600
finally:
    app.destroy()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_mod_tree_files_are_cached_searchable_and_open_explicitly(
    app, tmp_path, monkeypatch, opened
):
    import hoi4cm.ui.project_sidebar as sidebar_module

    root = tmp_path / "common" / "national_focus"
    root.mkdir(parents=True)
    first = root / "alpha.txt"
    second = root / "nested" / "beta.TXT"
    second.parent.mkdir()
    first.write_text("focus_tree = { id = alpha }", encoding="utf-8")
    second.write_text("focus_tree = { id = beta }", encoding="utf-8")
    (root / "notes.md").write_text("Not a focus tree", encoding="utf-8")
    scans = []

    def immediate(_app, work, done):
        scans.append(True)
        done(work())

    monkeypatch.setattr(sidebar_module, "run_bg", immediate)
    monkeypatch.setattr(MOD, "root", str(tmp_path))
    monkeypatch.setattr(MOD, "mod_name", "Tree catalog")
    sidebar = app._project_sidebar
    sidebar.refresh()
    assert {item.path for item in sidebar.catalog if item.kind == "tree_file"} == {
        str(first),
        str(second),
    }
    before = app._workspace_fingerprint()
    imported = []
    monkeypatch.setattr(app, "_import_txt", lambda *, path: imported.append(path))
    app._lp_search_var.set("beta.TXT")
    sidebar.first_result()
    assert sidebar.tree.exists("focus-trees")
    assert not imported  # Arrow/search selection never replaces the workspace.
    sidebar.refresh()
    assert len(scans) == 1
    sidebar.activate()
    assert imported == [str(second)]
    assert app._workspace_fingerprint() == before
    app._lp_search_var.set("")
    sidebar.render()
    sidebar.new_tree_button.invoke()
    assert any(window.title() == "New Focus Tree" for window in opened())
    assert first.read_text(encoding="utf-8") == "focus_tree = { id = alpha }"


def test_context_editor_close_keeps_fields_and_undo(app):
    app._new_focus_at(44, 44)
    focus = app.selected
    before = len(app._undo_stack)
    app._focus_editor.open()
    app._fv_desc.delete("1.0", "end")
    app._fv_desc.insert("1.0", "Context draft survives closing")
    app._fv_cost.set("35")
    app._focus_editor.toggle_advanced()
    app._focus_editor.toggle_advanced()
    assert app._focus_editor.close()
    assert focus.cost == 35
    assert focus.desc == "Context draft survives closing"
    assert len(app._undo_stack) == before + 1
    app._undo()
    assert app.selected.cost != 35
    app._redo()
    assert app.selected.cost == 35


def test_successive_applied_fields_refresh_both_recovery_files(
    app, tmp_path, monkeypatch
):
    primary = tmp_path / "workspace.json"
    project = tmp_path / "project.json"
    sibling = Path(sibling_autosave_path(str(project)))
    monkeypatch.setattr(main_mod, "workspace_autosave_path", lambda: str(primary))
    monkeypatch.setattr(app, "_last_project_path", str(project))
    monkeypatch.setattr(app, "_schedule_autosave", lambda: None)
    app._cancel_autosave()
    app._new_focus_at(48, 44)
    focus = app.selected
    app._mark_clean()
    for cost, description in (
        (25, "First recovery edit"),
        (30, "Second recovery edit"),
    ):
        app._fv_cost.set(str(cost))
        app._fv_desc.delete("1.0", "end")
        app._fv_desc.insert("1.0", description)
        app._apply()
        assert focus.cost == cost
        assert focus.desc == description
        app._autosave_tick()
        assert not app._autosave_failing
        for path in (primary, sibling):
            recovered = read_project(path).focuses[focus.id]
            assert recovered.cost == cost
            assert recovered.desc == description
        assert primary.read_bytes() == sibling.read_bytes()


def test_keyboard_action_list_has_all_labels_and_escape_is_noop(app):
    app._new_focus_at(46, 44)
    before = len(app._undo_stack)
    app._focus_actions.show(app.selected.id)
    app.update()
    assert [button.cget("text") for button in app._focus_actions.buttons] == [
        "Edit Focus",
        "Add Prerequisite",
        "Add Effect",
        "Add Child",
        "Duplicate",
        "Delete",
    ]
    assert len(app._focus_actions.images) == 6
    assert app.focus_get() is app._focus_actions.buttons[0]
    app._focus_actions.buttons[0].event_generate("<Tab>")
    app.update()
    assert app.focus_get() is app._focus_actions.buttons[1]
    app._focus_actions.buttons[1].event_generate("<Shift-Tab>")
    app.update()
    assert app.focus_get() is app._focus_actions.buttons[0]
    app._focus_actions.buttons[0].event_generate("<Escape>")
    app.update()
    assert app._focus_actions.focus_id is None
    assert app.focus_get() is app.cv
    assert len(app._undo_stack) == before


def test_spotlight_reflow_keyboard_and_dismissal_preserve_document(app):
    from hoi4cm.ui.focus_spotlight import TRANSPARENT

    app._new_focus_at(60, 44)
    focus = app.selected
    before = focus.to_dict()
    undo_count = len(app._undo_stack)
    geometry, minimum = app.geometry(), app.minsize()
    original_view = app.zoom, tuple(app.offset)
    try:
        app.minsize(280, 300)
        for zoom, size in ((0.35, "1200x820"), (2.5, "560x600"), (1.0, "320x400")):
            app.zoom = zoom
            app.offset[:] = [-32.5, 67.25]
            app.geometry("1200x820")
            app.update()
            app._add_focus_btn.focus_force()
            app._focus_actions.show(focus.id)
            app.update()
            app.geometry(size)
            app.update()
            spotlight = app._focus_actions.spotlight
            assert spotlight.window.winfo_width() == app.winfo_width()
            if app.tk.call("tk", "windowingsystem") == "win32":
                assert (
                    str(spotlight.window.attributes("-transparentcolor")) == TRANSPARENT
                )
            else:
                assert spotlight.window.cget("background") == TRANSPARENT
                assert float(spotlight.window.attributes("-alpha")) == 1.0
            assert float(app.attributes("-alpha")) == 1.0
            assert int(spotlight.preview.cget("highlightthickness")) == 0
            assert spotlight.name_label.cget("text") == focus.name
            assert not hasattr(spotlight, "id_label")
            # Cycle through all actions and Close in both directions. Even in
            # a short window, the focused action must scroll fully into view.
            for _ in range(7):
                spotlight.step(1)
                app.update()
                button = app.focus_get()
                assert button is not None, (
                    zoom,
                    size,
                    spotlight.window.state(),
                    spotlight.buttons[0].winfo_viewable(),
                    app.grab_current(),
                )
                if button is not spotlight.close_button:
                    assert button.winfo_rooty() >= spotlight.scroll.winfo_rooty()
                    assert button.winfo_rooty() + button.winfo_height() <= (
                        spotlight.scroll.winfo_rooty() + spotlight.scroll.winfo_height()
                    )
            spotlight.step(-1)
            app.update()
            assert app.focus_get() is spotlight.close_button
            spotlight.close_button.invoke()
            app.update()
            assert app.focus_get() is app._add_focus_btn
            assert app.zoom == zoom and app.offset == [-32.5, 67.25]
            assert focus.to_dict() == before
            assert len(app._undo_stack) == undo_count
    finally:
        app._focus_actions.dismiss()
        app.geometry(geometry)
        app.minsize(*minimum)
        app.zoom, offset = original_view
        app.offset[:] = offset
        app._redraw()
        app.cv.focus_force()


@pytest.mark.parametrize(
    "action",
    [
        "edit_focus",
        "add_effect",
        "add_prerequisite",
        "duplicate",
        "add_child",
        "delete",
    ],
)
def test_spotlight_buttons_run_existing_actions(app, opened, action):
    from hoi4cm.ui.focus_actions import ACTIONS

    app._new_focus_at(80 + len(app.focuses) * 2, 44)
    target = app.selected
    target_id = target.id
    before_ids = set(app.focuses)
    undo_count = len(app._undo_stack)
    app._focus_actions.show(target_id)
    app.update()
    index = [key for key, _ in ACTIONS].index(action)
    app._focus_actions.buttons[index].invoke()
    app.update()
    assert app._focus_actions.focus_id is None
    if action in {"edit_focus", "add_effect"}:
        assert app._focus_editor.window.winfo_ismapped()
        assert app._active_tab.get() == (
            "Effects" if action == "add_effect" else "Properties"
        )
        assert app._focus_editor.close()
    elif action == "add_prerequisite":
        windows = opened()
        assert len(windows) == 1
        assert "Prerequisite" in windows[0].title()
        assert app.grab_current() is windows[0]
        windows[0].grab_release()
        windows[0].destroy()
    else:
        assert len(app._undo_stack) == undo_count + 1
        after_ids = set(app.focuses)
        if action == "delete":
            assert after_ids == before_ids - {target_id}
        else:
            assert len(after_ids - before_ids) == 1
            if action == "add_child":
                assert app.selected.prereqs == [[target_id]]
        app._undo()
        assert set(app.focuses) == before_ids
        app._redo()
        assert set(app.focuses) == after_ids


def _buttons(widget: tk.Misc) -> list[tk.Button]:
    found = [widget] if isinstance(widget, tk.Button) else []
    for child in widget.winfo_children():
        found.extend(_buttons(child))
    return found


def test_effects_add_and_remove_through_the_real_app(app, opened):
    from hoi4cm.core.i18n import tr
    from hoi4cm.data.effects import EFFECT_DEFS

    plain = next(key for key, defn in EFFECT_DEFS.items() if not defn.get("fields"))
    with_fields = next(key for key, defn in EFFECT_DEFS.items() if defn.get("fields"))
    app._new_focus_at(120 + len(app.focuses) * 2, 44)
    focus = app.selected
    undo_count = len(app._undo_stack)

    app._open_effect_params(plain)
    assert [effect["type"] for effect in focus.effects] == [plain]

    app._open_effect_params(with_fields)
    (form,) = opened()
    add = next(
        button
        for button in _buttons(form)
        if button.cget("text") == tr("focus.effects.add_this", "＋  Add Effect")
    )
    add.invoke()
    app.update()
    assert not form.winfo_exists(), "the parameter form must close after Add"
    assert [effect["type"] for effect in focus.effects] == [plain, with_fields]

    app._rm_effect(1)
    app._rm_effect(0)
    assert focus.effects == []
    assert len(app._undo_stack) == undo_count + 4


def test_spotlight_background_click_dismisses_without_editing(app):
    x = max((item.x for item in app.focuses.values()), default=0) + 1
    app._new_focus_at(x, 44)
    focus = app.selected
    assert (focus.x, focus.y) == (x, 44)
    before = focus.to_dict()
    undo_count = len(app._undo_stack)
    previous_grab = app.grab_current()
    app._focus_actions.show(focus.id)
    app.update()
    spotlight = app._focus_actions.spotlight
    assert app.grab_current() is spotlight.window
    spotlight.scroll.event_generate("<ButtonRelease-1>", x=0, y=0)
    app.update()
    assert not app._focus_actions.blocks_canvas
    assert app.grab_current() is previous_grab
    assert focus.to_dict() == before
    assert len(app._undo_stack) == undo_count


@pytest.mark.parametrize("route", ["escape", "window-close"])
def test_dismissing_the_editor_asks_before_dropping_an_invalid_draft(
    app, monkeypatch, route
):
    app._new_focus_at(190 + len(app.focuses) * 2, 60)
    focus = app.selected
    editor = app._focus_editor
    editor.open()
    app.update()
    answers = []

    def dismiss():
        if route == "escape":
            editor.window.event_generate("<Escape>")
        else:
            app.tk.call(editor.window.protocol("WM_DELETE_WINDOW"))
        app.update()

    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **kw: answers.pop(0))
    app._fv_cost.set("not a number")

    answers.append(False)
    dismiss()
    assert editor.window.winfo_ismapped(), "No keeps the editor open"
    assert app._fv_cost.get() == "not a number"

    answers.append(True)
    dismiss()
    assert not editor.window.winfo_ismapped(), "Yes discards and closes"
    assert app._fv_cost.get() == str(focus.cost)
    assert not answers


def test_tree_settings_keeps_loaded_trees_and_references_accessible(app):
    app._focus_editor.open_tree_settings()
    app.update()
    assert app._focus_editor.tree_panel.winfo_ismapped()
    assert app._tree_meta_sf_box.winfo_ismapped()
    assert not app._focus_editor.focus_panel.winfo_ismapped()
    assert app._focus_editor.close()


def test_dialog_grab_is_deferred_until_mapping(app, opened):
    dialog = tk.Toplevel(app)
    guard = dialog.after(
        300, lambda: dialog.destroy() if dialog.winfo_exists() else None
    )

    assert grab_when_visible(dialog)
    dialog.after_cancel(guard)
    if not dialog.winfo_viewable():
        assert app.grab_current() is not dialog
    app.update()
    assert dialog.winfo_viewable()
    assert app.grab_current() is dialog


def test_withdrawn_before_mapping_does_not_block_or_grab(app, opened):
    dialog = tk.Toplevel(app)
    dialog.after_idle(dialog.withdraw)
    guard = dialog.after(
        300, lambda: dialog.destroy() if dialog.winfo_exists() else None
    )

    assert grab_when_visible(dialog)
    dialog.after_cancel(guard)
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
    guard = dialog.after(
        300, lambda: dialog.destroy() if dialog.winfo_exists() else None
    )

    assert grab_when_visible(dialog)
    dialog.after_cancel(guard)
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


_FAR_RECT = (0.0, 0.0, 10.0, 10.0)


def _registered_commands(widget: tk.Misc) -> set[str]:
    return set(vars(widget)["_tclCommands"] or ())


def test_focus_callbacks_released_on_cull_lod_and_external_delete(app):
    cv = tk.Canvas(app)
    try:
        fake = AppFake(cv=cv)
        focus = Focus(id=1, x=1, y=1)
        baseline = _registered_commands(cv)
        for _ in range(3):
            fake.zoom = 1.0
            fake._draw_focus(focus, _FAR_RECT)
            full_commands = _registered_commands(cv) - baseline
            assert len(full_commands) == 70
            fake.zoom = 0.3
            fake._draw_focus(focus, _FAR_RECT)
            assert len(_registered_commands(cv) - baseline) == 15
            # Tkinter names use Python object IDs, which can be reused after free.
            retired = full_commands - _registered_commands(cv)
            assert not any(cv.tk.call("info", "commands", cmd) for cmd in retired)
            cv.delete("all")
            fake._validate_canvas_probe()
            assert _registered_commands(cv) == baseline
            fake.zoom = 1.0
            fake._draw_focus(focus, _FAR_RECT)
            fake._reclaim_focus_bundles(set())
            assert _registered_commands(cv) == baseline
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
