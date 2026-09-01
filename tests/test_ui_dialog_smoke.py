"""Smoke tests for UI dialog construction.

Every ``ui/`` entry point that emits a Toplevel or builds a toolbar gets one
test that it does not raise ``NameError`` / ``AttributeError`` when called
with a bare ``tk_root``. Fixtures stay headless where possible (settings,
menubar, toolbar, GFX browsers) and a tiny tmp mod tree is only used where
the dialog lists files. ``show_splash`` is exercised via a fake Tk that
avoids blocking on animation.
"""

from __future__ import annotations

import copy
import os
import tkinter as tk
from unittest.mock import MagicMock

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod
from hoi4cm.ui.theme import YELLOW


@pytest.fixture(autouse=True)
def isolate_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    MOD.is_md = False
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


def _new_toplevels(before: set[tk.Misc], root: tk.Misc) -> list[tk.Toplevel]:
    return [
        w
        for w in root.winfo_children()  # type: ignore[union-attr]
        if w not in before and isinstance(w, tk.Toplevel)
    ]


def _destroy_toplevels(wins: list[tk.Toplevel], root: tk.Misc) -> None:
    for w in wins:
        try:
            w.grab_release()
        except Exception:
            pass
        try:
            w.destroy()
        except Exception:
            pass
    try:
        root.update()  # type: ignore[union-attr]
    except Exception:
        pass


def _collect_texts(win: tk.Misc) -> list[str]:
    texts: list[str] = []
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        try:
            texts.append(cur.cget("text"))  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            stack.extend(cur.winfo_children())  # type: ignore[union-attr]
        except Exception:
            pass
    return texts


def _find_button(win: tk.Misc, needle: str) -> tk.Button | None:
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and needle in cur.cget("text"):
            return cur
        stack.extend(cur.winfo_children())  # type: ignore[union-attr]
    return None


def _stub_mod_app(root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> tk.Tk:
    """Add the handful of attrs the dialogs read off ``app``."""
    root._error_entries = []  # type: ignore[attr-defined]
    root._errlog_btn = MagicMock()  # type: ignore[attr-defined]
    root._show_error_log = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._apply_md_visibility = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._refresh_mod_dropdowns = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._update_statusbar = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._invalidate_canvas_images = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._redraw_now = lambda *a, **kw: None  # type: ignore[attr-defined]
    root._hint = lambda *a, **kw: None  # type: ignore[attr-defined]
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: "")
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: "")
    return root


def _make_fake_app_for_chrome(tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> tk.Tk:
    """Satisfy build_menubar / build_toolbar_row2 attribute expectations."""
    _stub_mod_app(tk_root, monkeypatch)
    for name in (
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
        "_additional_income_wizard",
        "_validate_tree",
        "_load_mod",
        "_show_post_load_prompt",
        "_open_settings",
        "_add_focus",
        "_toggle_connect",
        "_toggle_mutex",
        "_toggle_multisel",
        "_clear_all",
        "_load_extra_tree",
        "_load_all_trees",
        "_save_all_trees",
    ):
        if not hasattr(tk_root, name):
            setattr(tk_root, name, lambda *a, **kw: None)
    if not hasattr(tk_root, "_cfp_x_var"):
        tk_root._cfp_x_var = tk.StringVar(value="0")  # type: ignore[attr-defined]
    if not hasattr(tk_root, "_cfp_y_var"):
        tk_root._cfp_y_var = tk.StringVar(value="0")  # type: ignore[attr-defined]
    return tk_root


# ── settings ─────────────────────────────────────────────────────────────


def test_open_settings_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    import hoi4cm.ui.settings_dialog as sd_mod

    monkeypatch.setattr(sd_mod, "CONFIG_PATH", str(tmp_path / "hoi4_focus_maker.json"))
    before: set[tk.Misc] = set(tk_root.winfo_children())
    sd_mod.open_settings(tk_root)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_settings did not create a Toplevel"
    win = wins[0]
    try:
        assert "Settings" in win.title()
        texts = _collect_texts(win)
        assert any("SETTINGS" in t for t in texts)
    finally:
        _destroy_toplevels(wins, tk_root)


# ── menubar / toolbar ────────────────────────────────────────────────────


def test_build_menubar_constructs(tk_root, monkeypatch):
    _make_fake_app_for_chrome(tk_root, monkeypatch)
    invoked: list[str] = []
    tk_root._national_spirit_wizard = lambda: invoked.append("wizard")  # type: ignore[attr-defined]
    from hoi4cm.ui.menubar import build_menubar

    toolbar = tk.Frame(tk_root)
    toolbar.pack()
    tk_root.update()
    before_children = set(toolbar.winfo_children())
    controller = build_menubar(tk_root, toolbar, tutorial_command=lambda: None)
    tk_root.update()
    assert len(toolbar.winfo_children()) > len(before_children)
    texts = _collect_texts(toolbar)
    assert any("HOI4 CONTENT MAKER" in t for t in texts)
    assert any("Help" in t for t in texts)
    preview_rows = controller.show_preview(
        "tools", ("national_spirit_builder", "validate_tree")
    )
    tk_root.update()
    assert len(preview_rows) == 2
    assert controller.preview_active
    preview_menu = preview_rows[0].master
    assert int(preview_menu.cget("highlightthickness")) == 3
    assert preview_menu.cget("highlightbackground") == YELLOW
    for row in preview_rows:
        assert int(row.cget("highlightthickness")) == 2
        assert row.cget("highlightbackground") == YELLOW
    preview_button = next(
        child
        for child in preview_rows[0].winfo_children()[0].winfo_children()
        if isinstance(child, tk.Button)
    )
    preview_button.invoke()
    tk_root.update()
    assert invoked == []
    controller.close()
    tk_root.update()
    before: set[tk.Misc] = set(tk_root.winfo_children())
    for child in toolbar.winfo_children():
        for sub in child.winfo_children():  # type: ignore[union-attr]
            if isinstance(sub, tk.Button) and "File" in sub.cget("text"):
                sub.invoke()
                tk_root.update()
                _destroy_toplevels(_new_toplevels(before, tk_root), tk_root)
                break
    controller.close()
    toolbar.destroy()
    tk_root.update()


def test_build_toolbar_row2_constructs(tk_root, monkeypatch):
    _make_fake_app_for_chrome(tk_root, monkeypatch)
    from hoi4cm.ui.toolbar import build_toolbar_row2

    toolbar = tk.Frame(tk_root)
    toolbar.pack()
    tk_root.update()
    before = set(toolbar.winfo_children())
    build_toolbar_row2(tk_root, toolbar)
    tk_root.update()
    assert len(toolbar.winfo_children()) > len(before)
    texts = _collect_texts(toolbar)
    assert any("Prereq" in t for t in texts)
    assert any("Ideas" in t for t in texts)
    assert tk_root._additional_income_btn.winfo_manager() == ""  # type: ignore[attr-defined]
    toolbar.destroy()
    tk_root.update()


def test_md_toolbar_and_wizard_follow_mode_changes(tk_root, monkeypatch):
    _make_fake_app_for_chrome(tk_root, monkeypatch)
    import hoi4_content_maker as main_mod
    from hoi4cm.core import EFFECT_CATS
    from hoi4cm.ui.toolbar import build_toolbar_row2

    toolbar = tk.Frame(tk_root)
    toolbar.pack()
    original_categories = list(EFFECT_CATS)
    try:
        build_toolbar_row2(tk_root, toolbar)
        button = tk_root._additional_income_btn  # type: ignore[attr-defined]
        apply_visibility = main_mod.App._apply_md_visibility.__get__(tk_root)

        MOD.is_md = True
        apply_visibility()
        assert button.winfo_manager() == "pack"
        MOD.is_md = False
        apply_visibility()
        assert button.winfo_manager() == ""

        opened = []
        monkeypatch.setattr(
            "hoi4cm.wizards.open_additional_income_wizard",
            lambda app: opened.append(app),
        )
        tk_root._additional_income_wizard = (  # type: ignore[attr-defined]
            main_mod.App._additional_income_wizard.__get__(tk_root)
        )
        tk_root._additional_income_wizard()  # type: ignore[attr-defined]
        assert opened == []
    finally:
        EFFECT_CATS[:] = original_categories
        toolbar.destroy()
        tk_root.update()


# ── GFX browsers ─────────────────────────────────────────────────────────


def test_open_universal_gfx_browser_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    gfx_dir = tmp_path / "gfx_test"
    gfx_dir.mkdir(parents=True)
    (gfx_dir / "a.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(gfx_dir))
    from hoi4cm.ui.gfx_browser import open_universal_gfx_browser

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_universal_gfx_browser(tk_root, on_select=lambda *a: None)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_universal_gfx_browser did not create a Toplevel"
    try:
        assert wins[0].winfo_children()
        assert any("GFX Browser" in wins[0].title() for _ in [1])
    finally:
        _destroy_toplevels(wins, tk_root)


def test_open_universal_gfx_browser_select_flow(tk_root, tmp_path, monkeypatch):
    """Selecting an entry and confirming calls on_select with the gfx key."""
    _stub_mod_app(tk_root, monkeypatch)
    gfx_dir = tmp_path / "gfx_select"
    gfx_dir.mkdir(parents=True)
    (gfx_dir / "alpha.png").write_bytes(b"\x89PNG\r\n")
    (gfx_dir / "beta.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(gfx_dir))
    from hoi4cm.ui.gfx_browser import open_universal_gfx_browser

    seen: list[tuple[str, str]] = []

    def _on_select(key: str, path: str) -> None:
        seen.append((key, path))

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_universal_gfx_browser(tk_root, on_select=_on_select)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "browser did not open"
    win = wins[0]
    try:
        from hoi4cm.ui.thumbnail_grid import VirtualThumbnailGrid

        grids: list[VirtualThumbnailGrid] = []
        stack: list[tk.Misc] = [win]
        while stack:
            cur = stack.pop()
            if isinstance(cur, VirtualThumbnailGrid):
                grids.append(cur)
            stack.extend(cur.winfo_children())
        assert len(grids) == 1
        grid = grids[0]
        grid.select(1)
        select_button = _find_button(win, "Select")
        assert select_button is not None
        assert select_button.cget("state") == "normal"
        select_button.invoke()
        assert seen == [("GFX_beta", str(gfx_dir / "beta.png"))]
        assert not win.winfo_exists()
    finally:
        _destroy_toplevels(wins, tk_root)


def test_open_gfx_placement_editor_constructs(tk_root, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    from hoi4cm.ui.gfx_browser import open_gfx_placement_editor

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_gfx_placement_editor(tk_root, initial_items=[], on_confirm=lambda *a: None)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_gfx_placement_editor did not create a Toplevel"
    try:
        assert wins[0].winfo_children()
    finally:
        _destroy_toplevels(wins, tk_root)


def test_open_gfx_placement_editor_confirm_flow(tk_root, tmp_path, monkeypatch):
    """Confirming the placement editor invokes on_confirm with items."""
    _stub_mod_app(tk_root, monkeypatch)
    from hoi4cm.ui.gfx_browser import open_gfx_placement_editor

    img = tmp_path / "icon.png"
    img.write_bytes(b"\x89PNG\r\n")
    confirmed: list[list[dict]] = []

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_gfx_placement_editor(
        tk_root,
        initial_items=[
            {
                "gfx_key": "GFX_test",
                "path": str(img),
                "role": "icon",
                "x": 10,
                "y": 10,
                "w": 64,
                "h": 64,
            }
        ],
        on_confirm=lambda items, code: confirmed.append(list(items)),
    )
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins
    win = wins[0]
    try:
        confirm_button = _find_button(win, "Confirm Placement")
        assert confirm_button is not None
        confirm_button.invoke()
        tk_root.update()
        assert len(confirmed) == 1
        assert len(confirmed[0]) == 1
        assert confirmed[0][0]["gfx_key"] == "GFX_test"
        assert confirmed[0][0]["role"] == "icon"
        assert not win.winfo_exists()
    finally:
        _destroy_toplevels(wins, tk_root)


def test_open_focus_icon_browser_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    goals = tmp_path / "gfx" / "interface" / "goals"
    goals.mkdir(parents=True)
    (goals / "dummy.png").write_bytes(b"\x89PNG\r\n")
    MOD.root = str(tmp_path)
    MOD.path_goals = os.path.join("gfx", "interface", "goals")
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: str(goals))
    from hoi4cm.ui.gfx_browser import open_focus_icon_browser

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_focus_icon_browser(tk_root, on_select=lambda *a: None, current_gfx="")
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_focus_icon_browser did not create a Toplevel"
    try:
        assert wins[0].winfo_children()
    finally:
        _destroy_toplevels(wins, tk_root)


# ── splash ───────────────────────────────────────────────────────────────


def test_show_splash_constructs(tk_root, monkeypatch):
    """show_splash creates a borderless window and animates without crashing."""
    import hoi4cm.ui.splash as splash_mod

    called: list[bool] = []

    def _callback() -> None:
        called.append(True)

    def _fake_apply_dpi(root: tk.Toplevel) -> None:
        try:
            root.configure(bg="#000000")
        except Exception:
            pass

    created: list[tk.Misc] = []

    class _FakeRoot(tk.Toplevel):  # type: ignore[type-arg]
        def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
            super().__init__(tk_root, *a, **kw)
            created.append(self)

        def mainloop(self, *a, **kw):  # type: ignore[no-untyped-def]
            try:
                self.destroy()
            except Exception:
                pass
            _callback()

        def after(self, ms, func=None, *args):  # type: ignore[no-untyped-def]  # pylint: disable=keyword-arg-before-vararg
            if func is not None and ms == 80:
                try:
                    func(*args)
                except Exception:
                    pass
            return "after_id"

    monkeypatch.setattr(splash_mod.tk, "Tk", _FakeRoot)
    monkeypatch.setattr("hoi4cm.ui.splash.tk.Tk", _FakeRoot)
    splash_mod.show_splash(_callback, apply_dpi_scaling=_fake_apply_dpi)
    tk_root.update()
    assert called, "show_splash callback was not invoked"
    for w in created:
        try:
            w.destroy()
        except Exception:
            pass
    tk_root.update()


def test_show_splash_wrapper_logs_on_failure(monkeypatch):
    """The real splash callback wrapper logs failures without re-raising."""
    import logging

    import hoi4cm.ui.splash as splash_mod

    class _Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.messages.append(self.format(record))

    class _FakeRoot(tk.Tk):  # type: ignore[type-arg]
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            self.withdraw()

        def mainloop(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        def after(self, ms, func=None, *args):  # type: ignore[no-untyped-def]  # pylint: disable=keyword-arg-before-vararg
            if func is not None:
                func(*args)
            return "after_id"

    handler = _Capture()
    splash_mod.log.addHandler(handler)
    called: list[bool] = []

    def bad() -> None:
        called.append(True)
        raise RuntimeError("boom from splash callback")

    monkeypatch.setattr(splash_mod.tk, "Tk", _FakeRoot)
    try:
        splash_mod.show_splash(bad)
    finally:
        splash_mod.log.removeHandler(handler)
    assert called == [True]
    assert any("fatal exception" in m for m in handler.messages)
    assert any("boom from splash callback" in m for m in handler.messages)


# ── mod_loading ──────────────────────────────────────────────────────────


def test_show_post_load_prompt_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    ideas_dir = tmp_path / "common" / "ideas"
    events_dir = tmp_path / "events"
    ideas_dir.mkdir(parents=True)
    events_dir.mkdir(parents=True)
    (ideas_dir / "a.txt").write_text("ideas = { }")
    (events_dir / "b.txt").write_text("add_namespace = foo")
    loc_dir = tmp_path / "localisation"
    loc_dir.mkdir(parents=True)
    (loc_dir / "en.yml").write_text("l_english:\n")
    sloc_dir = tmp_path / "common" / "scripted_localisation"
    sloc_dir.mkdir(parents=True)
    (sloc_dir / "s.txt").write_text("defined_text = { }")
    focus_dir = tmp_path / "common" / "national_focus"
    focus_dir.mkdir(parents=True)
    (focus_dir / "f.txt").write_text("focus_tree = { }")

    MOD.loaded = True
    MOD.root = str(tmp_path)
    MOD.edit_ideas_file = ""
    MOD.edit_events_file = ""
    MOD.edit_focus_file = ""
    MOD.edit_loc_file = ""
    MOD.edit_scripted_loc_file = ""
    tk_root._mod_lbl = tk.Label(tk_root, text="mod")  # type: ignore[attr-defined]
    tk_root._mod_lbl.pack()
    tk_root.update()

    from hoi4cm.ui.mod_loading import ModLoadingMixin

    before: set[tk.Misc] = set(tk_root.winfo_children())
    ModLoadingMixin._show_post_load_prompt(tk_root)  # type: ignore[arg-type]
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "_show_post_load_prompt did not create a Toplevel"
    try:
        assert "Edit Targets" in wins[0].title()
        texts = _collect_texts(wins[0])
        assert any("Quick-pick" in t for t in texts)
    finally:
        _destroy_toplevels(wins, tk_root)


def test_load_mod_path_removes_stale_recent_entry_and_saves_config(
    tk_root, tmp_path, monkeypatch
):
    _stub_mod_app(tk_root, monkeypatch)
    from hoi4cm.ui.mod_loading import ModLoadingMixin

    missing = str(tmp_path / "removed-mod")
    MOD._recent_mods = [missing, str(tmp_path / "still-valid")]  # type: ignore[attr-defined]
    report_calls = []
    save_config = MagicMock()
    monkeypatch.setattr(
        "hoi4cm.ui.mod_loading.report_error",
        lambda *args, **kwargs: report_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(MOD, "save_config", save_config)

    ModLoadingMixin._load_mod_path(tk_root, missing)  # type: ignore[arg-type]
    tk_root.update()

    assert report_calls
    assert missing in str(report_calls[0])
    assert MOD._recent_mods == [str(tmp_path / "still-valid")]  # type: ignore[attr-defined]
    save_config.assert_called_once_with()
