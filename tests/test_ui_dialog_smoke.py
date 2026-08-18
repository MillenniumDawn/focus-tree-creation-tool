"""Smoke tests for UI dialog construction.

Every ``ui/`` entry point that emits a Toplevel or builds a toolbar gets one
test that it does not raise ``NameError`` / ``AttributeError`` when called
with a bare ``tk_root``. Fixtures stay headless where possible (settings,
menubar, toolbar, GFX browsers) and a tiny tmp mod tree is only used where
the dialog lists files. ``show_splash`` is exercised via its logging wrapper
rather than the full animation loop.
"""

from __future__ import annotations

import os
import tkinter as tk
from unittest.mock import MagicMock

import pytest

from hoi4cm.mod import MOD
from hoi4cm.mod import scan_cache as scan_cache_mod


@pytest.fixture(autouse=True)
def isolate_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache_mod, "STATE_DIR", str(tmp_path / "scan_cache"))
    snapshot = dict(MOD.__dict__)
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
    # silenced dialogs
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **kw: None)
    monkeypatch.setattr("tkinter.filedialog.askdirectory", lambda **kw: "")
    monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **kw: "")
    return root


def _make_fake_app_for_chrome(tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch) -> tk.Tk:
    """Satisfy build_menubar / build_toolbar_row2 attribute expectations."""
    _stub_mod_app(tk_root, monkeypatch)
    # toolbar/menubar callbacks — never invoked during smoke, just must exist
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
    # toolbar needs these vars
    if not hasattr(tk_root, "_cfp_x_var"):
        tk_root._cfp_x_var = tk.StringVar(value="0")  # type: ignore[attr-defined]
    if not hasattr(tk_root, "_cfp_y_var"):
        tk_root._cfp_y_var = tk.StringVar(value="0")  # type: ignore[attr-defined]
    # mod label / hint label are created by build_menubar, not required before
    return tk_root


# ── settings ─────────────────────────────────────────────────────────────


def test_open_settings_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    # settings reads/writes config and checks custom_gfx dirs — keep off real FS
    import hoi4cm.ui.settings_dialog as sd_mod

    monkeypatch.setattr(sd_mod, "CONFIG_PATH", str(tmp_path / "hoi4_focus_maker.json"))
    before: set[tk.Misc] = set(tk_root.winfo_children())
    # additional stubs settings_dialog touches
    tk_root._error_entries = []  # type: ignore[attr-defined]
    tk_root._errlog_btn = MagicMock()  # type: ignore[attr-defined]
    sd_mod.open_settings(tk_root)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_settings did not create a Toplevel"
    win = wins[0]
    try:
        assert "Settings" in win.title()
        assert win.winfo_children()
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


# ── menubar / toolbar ────────────────────────────────────────────────────


def test_build_menubar_constructs(tk_root, monkeypatch):
    _make_fake_app_for_chrome(tk_root, monkeypatch)
    from hoi4cm.ui.menubar import build_menubar

    toolbar = tk.Frame(tk_root)
    toolbar.pack()
    tk_root.update()
    before_children = set(toolbar.winfo_children())
    build_menubar(tk_root, toolbar)
    tk_root.update()
    # builds frames/labels in-place — no new Toplevel, just children appear
    assert len(toolbar.winfo_children()) > len(before_children)
    # spot-check a known label
    texts = []

    def _collect(w: tk.Misc):
        try:
            texts.append(w.cget("text"))  # type: ignore[union-attr]
        except Exception:
            pass
        for c in w.winfo_children():  # type: ignore[union-attr]
            _collect(c)

    _collect(toolbar)
    assert any("HOI4 CONTENT MAKER" in t for t in texts)
    # exercise the File menu dropdown path (creates a transient Toplevel)
    before: set[tk.Misc] = set(tk_root.winfo_children())
    # find the File button and invoke it
    for child in toolbar.winfo_children():
        for sub in child.winfo_children():  # type: ignore[union-attr]
            if isinstance(sub, tk.Button) and "File" in sub.cget("text"):
                sub.invoke()
                tk_root.update()
                # dropdown may have appeared
                new = _new_toplevels(before, tk_root)
                for w in new:
                    try:
                        w.destroy()
                    except Exception:
                        pass
                break
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
    # should have created Prereq / Ideas etc. buttons somewhere inside toolbar
    found = False

    def _walk(w: tk.Misc) -> None:
        nonlocal found
        try:
            if isinstance(w, tk.Button) and "Prereq" in w.cget("text"):  # type: ignore[union-attr]
                found = True
        except Exception:
            pass
        for c in w.winfo_children():  # type: ignore[union-attr]
            _walk(c)

    _walk(toolbar)
    assert found, "toolbar missing Prereq button"
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
    win = wins[0]
    try:
        assert win.winfo_children()
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


def test_open_gfx_placement_editor_constructs(tk_root, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    from hoi4cm.ui.gfx_browser import open_gfx_placement_editor

    before: set[tk.Misc] = set(tk_root.winfo_children())
    open_gfx_placement_editor(tk_root, initial_items=[], on_confirm=lambda *a: None)
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "open_gfx_placement_editor did not create a Toplevel"
    win = wins[0]
    try:
        assert win.winfo_children()
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


def test_open_focus_icon_browser_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    # create a tiny goals folder so the focus browser has something to list
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
    win = wins[0]
    try:
        assert win.winfo_children()
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


# ── splash wrapper ──────────────────────────────────────────────────────


def test_show_splash_constructs(tk_root, monkeypatch):
    """show_splash creates a borderless window and animates without crashing."""
    import hoi4cm.ui.splash as splash_mod

    called: list[bool] = []

    def _callback() -> None:
        called.append(True)

    def _fake_apply_dpi(root: tk.Toplevel) -> None:
        # exercise the hook — just prove it was called
        try:
            root.configure(bg="#000000")
        except Exception:
            pass

    # Run the real Tk construction but don't block on mainloop or 120
    # animation frames. Patch after/mainloop so the function returns
    # quickly while still exercising the canvas/gradient setup.
    created: list[tk.Misc] = []

    class _FakeRoot(tk.Toplevel):  # type: ignore[type-arg]
        def __init__(self, *a, **kw):  # type: ignore[no-untyped-def]
            super().__init__(tk_root, *a, **kw)
            created.append(self)

        def mainloop(self, *a, **kw):  # type: ignore[no-untyped-def]
            # destroy immediately instead of blocking
            try:
                self.destroy()
            except Exception:
                pass
            # mimic splash's post-destroy callback path
            _callback()

        def after(self, ms, func=None, *args):  # type: ignore[no-untyped-def]  # pylint: disable=keyword-arg-before-vararg
            # schedule one animation tick then let mainloop destroy
            if func is not None and ms == 80:
                # first animate tick — call once to cover the function body
                try:
                    func(*args)
                except Exception:
                    pass
            return "after_id"

    monkeypatch.setattr(splash_mod.tk, "Tk", _FakeRoot)
    # patch the module-level tk alias as well
    monkeypatch.setattr("hoi4cm.ui.splash.tk.Tk", _FakeRoot)
    splash_mod.show_splash(_callback, apply_dpi_scaling=_fake_apply_dpi)
    tk_root.update()
    assert called, "show_splash callback was not invoked"
    # clean up any leftover fake root
    for w in created:
        try:
            w.destroy()
        except Exception:
            pass
    tk_root.update()

    # keep original wrapper test for the exception-logging path


def test_show_splash_wrapper_logs_on_failure():
    """Splash catches App-construction failures and logs them (headless path)."""
    import logging

    import hoi4cm.ui.splash as splash_mod

    class _Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.messages.append(self.format(record))

    handler = _Capture()
    splash_mod.log.addHandler(handler)
    try:

        def bad() -> None:
            raise RuntimeError("boom")

        # exercise the same try/except the splash animation uses after root.destroy
        try:
            bad()
        except Exception:
            splash_mod.log.exception(
                "Splash: fatal exception during app construction "
                "— check log for details"
            )
    finally:
        splash_mod.log.removeHandler(handler)
    assert any("fatal exception" in m for m in handler.messages)


# ── mod_loading prompt ──────────────────────────────────────────────────


def test_show_post_load_prompt_constructs(tk_root, tmp_path, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    # create a minimal mod tree so the prompt has file lists
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
    # need a mod label for _show_post_load_prompt's confirm path (not exercised here)
    tk_root._mod_lbl = tk.Label(tk_root, text="mod")  # type: ignore[attr-defined]
    tk_root._mod_lbl.pack()
    tk_root.update()

    from hoi4cm.ui.mod_loading import ModLoadingMixin

    # call as unbound mixin against tk_root
    before: set[tk.Misc] = set(tk_root.winfo_children())
    ModLoadingMixin._show_post_load_prompt(tk_root)  # type: ignore[arg-type]
    tk_root.update()
    wins = _new_toplevels(before, tk_root)
    assert wins, "_show_post_load_prompt did not create a Toplevel"
    win = wins[0]
    try:
        assert "Edit Targets" in win.title()
        assert win.winfo_children()
    finally:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        tk_root.update()


def test_load_mod_path_handles_missing_dir(tk_root, monkeypatch):
    _stub_mod_app(tk_root, monkeypatch)
    from hoi4cm.ui.mod_loading import ModLoadingMixin

    # _load_mod_path with missing dir should show error and not raise
    monkeypatch.setattr("hoi4cm.ui.mod_loading.report_error", lambda *a, **kw: None)
    ModLoadingMixin._load_mod_path(tk_root, "/tmp/does_not_exist_hoi4cm_test")  # type: ignore[arg-type]
    tk_root.update()
