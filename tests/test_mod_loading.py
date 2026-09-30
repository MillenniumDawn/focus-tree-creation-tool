"""Headless regression tests for mod-loading UI wiring."""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from typing import Any

import pytest

from hoi4cm.mod import MOD
from hoi4cm.ui import mod_loading
from hoi4cm.ui.mod_loading import ModLoadingMixin


@pytest.fixture(autouse=True)
def isolate_mod():
    snapshot = copy.deepcopy(MOD.__dict__)
    MOD.loaded = False
    MOD.root = None
    yield
    MOD.__dict__.clear()
    MOD.__dict__.update(snapshot)


class _FakeWidget:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    def title(self, value: str) -> None:
        pass

    def configure(self, **kwargs: object) -> None:
        pass

    def geometry(self, value: str) -> None:
        pass

    def resizable(self, width: bool, height: bool) -> None:
        pass

    def grab_set(self) -> None:
        pass

    def protocol(self, name: str, callback: Callable[[], None]) -> None:
        pass

    def pack(self, **kwargs: object) -> None:
        pass

    def place(self, **kwargs: object) -> None:
        pass

    def place_configure(self, **kwargs: object) -> None:
        pass

    def update_idletasks(self) -> None:
        pass


class _FakeApp(ModLoadingMixin):
    _lifecycle: Any
    _mod_lbl: Any
    _focus_bundles: Any
    cv: Any
    visibility_updates: int
    dropdown_refreshes: int
    status_updates: int
    invalidations: int
    redraws: int
    after_calls: list[tuple[int, Callable[[], None]]]
    _apply_md_visibility: Any
    _refresh_mod_dropdowns: Any
    _update_statusbar: Any
    _invalidate_canvas_images: Any
    _redraw_now: Any
    after: Any


class _AcceptingLifecycle:
    accepting = True

    def __init__(self) -> None:
        self.begun: list[str] = []

    def begin(self, scope: str) -> None:
        self.begun.append(scope)

    def add_resource(self, cleanup: Callable[[], None]) -> Callable[[], None]:
        return lambda: None


def _patch_progress_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod_loading.tk, "Toplevel", _FakeWidget)
    monkeypatch.setattr(mod_loading.tk, "Label", _FakeWidget)
    monkeypatch.setattr(mod_loading.tk, "Frame", _FakeWidget)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *args, **kwargs: lambda: None
    )


def test_load_mod_moves_duplicate_to_front_and_caps_recent_mods(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = str(tmp_path / "selected-mod")
    (tmp_path / "selected-mod").mkdir()
    old_recent = [root, *(f"/mods/mod-{index}" for index in range(1, 9))]
    MOD._recent_mods = old_recent  # type: ignore[attr-defined]
    monkeypatch.setattr(MOD, "save_config", lambda: True)
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))

    dialog_calls: list[dict[str, object]] = []

    def askdirectory(**kwargs: object) -> str:
        dialog_calls.append(kwargs)
        return root

    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", askdirectory)
    _patch_progress_window(monkeypatch)
    background_calls: list[tuple[object, object, str]] = []

    def run_bg(widget, worker, on_done, on_error, *, scope: str) -> None:
        background_calls.append((worker, on_done, scope))

    monkeypatch.setattr(mod_loading, "run_bg", run_bg)
    app = _FakeApp()
    app._lifecycle = _AcceptingLifecycle()

    app._load_mod()

    assert MOD._recent_mods == [  # type: ignore[attr-defined]
        root,
        *(f"/mods/mod-{index}" for index in range(1, 8)),
    ]
    assert len(MOD._recent_mods) == 8  # type: ignore[attr-defined]
    assert len(set(MOD._recent_mods)) == 8  # type: ignore[attr-defined]
    assert dialog_calls and dialog_calls[0]["initialdir"] == str(tmp_path)
    assert app._lifecycle.begun == ["mod"]
    assert len(background_calls) == 1
    assert background_calls[0][2] == "mod"


def test_load_mod_is_rejected_when_lifecycle_is_not_accepting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog_calls: list[bool] = []
    config_writes: list[bool] = []
    previous_recent = ["/mods/previous"]
    MOD._recent_mods = previous_recent.copy()  # type: ignore[attr-defined]

    def askdirectory(**kwargs: object) -> str:
        dialog_calls.append(True)
        return "/mods/new"

    def save_config() -> bool:
        config_writes.append(True)
        return True

    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", askdirectory)
    monkeypatch.setattr(MOD, "save_config", save_config)
    app = _FakeApp()
    app._lifecycle = type("ClosedLifecycle", (), {"accepting": False})()

    app._load_mod()

    assert dialog_calls == []
    assert config_writes == []
    assert MOD._recent_mods == previous_recent  # type: ignore[attr-defined]


def test_on_mod_loaded_invalidates_canvas_and_wizard_images_on_ui_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCanvas:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def delete(self, tag: str) -> None:
            self.deleted.append(tag)

    class FakeWindow:
        def __init__(self) -> None:
            self.grab_released = False
            self.destroyed = False

        def grab_release(self) -> None:
            self.grab_released = True

        def destroy(self) -> None:
            self.destroyed = True

    class FakeLabel:
        def __init__(self) -> None:
            self.configurations: list[dict[str, object]] = []

        def config(self, **kwargs: object) -> None:
            self.configurations.append(kwargs)

    cache = {"old-gfx": object()}
    monkeypatch.setattr(mod_loading._wiz_shared, "_app_img_caches", [cache])
    monkeypatch.setattr(
        mod_loading.messagebox, "showinfo", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(mod_loading.os.path, "exists", lambda path: True)
    monkeypatch.setattr(MOD, "summary", lambda: "loaded summary")
    MOD.is_md = False
    MOD.sprites = {"GFX_sample": "/mod/gfx/sample.dds"}
    MOD._img_errors = []
    image_loads: list[tuple[str, int]] = []
    monkeypatch.setattr(
        MOD,
        "get_image",
        lambda name: image_loads.append((name, threading.get_ident())),
    )

    app = _FakeApp()
    app._mod_lbl = FakeLabel()
    app._focus_bundles = {"stale": object()}
    app.cv = FakeCanvas()
    app.visibility_updates = 0
    app.dropdown_refreshes = 0
    app.status_updates = 0
    app.invalidations = 0
    app.redraws = 0
    app.after_calls = []
    app._apply_md_visibility = lambda: setattr(
        app, "visibility_updates", app.visibility_updates + 1
    )
    app._refresh_mod_dropdowns = lambda: setattr(
        app, "dropdown_refreshes", app.dropdown_refreshes + 1
    )
    app._update_statusbar = lambda: setattr(
        app, "status_updates", app.status_updates + 1
    )
    app._invalidate_canvas_images = lambda: setattr(
        app, "invalidations", app.invalidations + 1
    )
    app._redraw_now = lambda: setattr(app, "redraws", app.redraws + 1)
    app.after = lambda delay, callback: app.after_calls.append((delay, callback))
    pw = FakeWindow()
    ui_thread = threading.get_ident()

    app._on_mod_loaded(pw, "/mods/sample-mod")

    assert pw.grab_released and pw.destroyed
    assert app._mod_lbl.configurations[0]["text"].startswith("📂 sample-mod")
    assert app.visibility_updates == 1
    assert app.dropdown_refreshes == 1
    assert app.status_updates == 1
    assert app.invalidations == 1
    assert app._focus_bundles == {}
    assert app.cv.deleted == ["focus"]
    assert app.redraws == 1
    assert cache == {}
    assert image_loads == [("GFX_sample", ui_thread)]
    assert len(app.after_calls) == 1
    assert app.after_calls[0][0] == 150
