"""Headless regression tests for mod-loading UI wiring."""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from typing import Any

import pytest
from ui_fakes import ModLoadingAppFake

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


class _AcceptingLifecycle:
    accepting = True

    def __init__(self) -> None:
        self.begun: list[str] = []

    def begin(self, scope: str) -> None:
        self.begun.append(scope)

    def add_resource(self, cleanup: Callable[[], None]) -> Callable[[], None]:
        return lambda: None


class _FakeProgress:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.texts: list[str] = []
        self.fractions: list[float] = []
        self.closed = False

    def set_text(self, value: str) -> None:
        self.texts.append(value)

    def set_fraction(self, value: float) -> None:
        self.fractions.append(value)

    def close(self) -> None:
        self.closed = True


def _patch_progress_window(monkeypatch: pytest.MonkeyPatch) -> _FakeProgress:
    progress = _FakeProgress()

    def make_modal(*_args, **kwargs):
        assert kwargs["cancellable"] is True
        return progress

    monkeypatch.setattr(mod_loading, "progress_modal", make_modal)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *args, **kwargs: lambda: None
    )
    return progress


def test_load_mod_moves_duplicate_to_front_and_caps_recent_mods(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    root = str(tmp_path / "selected-mod")
    (tmp_path / "selected-mod").mkdir()
    old_recent = [root, *(f"/mods/mod-{index}" for index in range(1, 9))]
    MOD._recent_mods = old_recent  # type: ignore[attr-defined]
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))

    dialog_calls: list[dict[str, object]] = []

    def askdirectory(**kwargs: object) -> str:
        dialog_calls.append(kwargs)
        return root

    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", askdirectory)
    progress = _patch_progress_window(monkeypatch)
    background_calls: list[tuple[Any, Any, dict[str, object]]] = []
    evicted: list[object] = []
    saved: list[bool] = []
    loaded: list[str] = []
    scanned_contexts: list[object] = []
    adopted: list[object] = []
    scan_arguments: dict[str, object] = {}

    def fake_scan(mod, *_args, **kwargs):
        scanned_contexts.append(mod)
        scan_arguments.update(kwargs)
        return evicted

    def adopt_scan(_mod, candidate) -> list[object]:
        adopted.append(candidate)
        return []

    monkeypatch.setattr(type(MOD), "scan", fake_scan)
    monkeypatch.setattr(type(MOD), "adopt_scan", adopt_scan)

    def save_config(_mod) -> bool:
        saved.append(True)
        return True

    monkeypatch.setattr(type(MOD), "save_config", save_config)

    def run_bg(widget, worker, on_done, **kwargs) -> None:
        background_calls.append((worker, on_done, kwargs))

    monkeypatch.setattr(mod_loading, "run_bg", run_bg)
    app = ModLoadingAppFake()
    app._lifecycle = _AcceptingLifecycle()
    monkeypatch.setattr(app, "_on_mod_loaded", loaded.append)
    previous_recent = MOD._recent_mods.copy()  # type: ignore[attr-defined]

    app._load_mod()

    assert MOD._recent_mods == previous_recent  # type: ignore[attr-defined]
    assert saved == []
    assert dialog_calls and dialog_calls[0]["initialdir"] == str(tmp_path)
    assert app._lifecycle.begun == ["mod"]
    assert len(background_calls) == 1
    worker, on_done, options = background_calls[0]
    assert options["scope"] == "mod"
    assert callable(options["on_finally"])
    assert worker() is evicted
    assert scanned_contexts[0] is not MOD
    assert scan_arguments["cancelled"] is progress.cancelled
    on_done(evicted)
    assert adopted == scanned_contexts
    assert MOD._recent_mods == [  # type: ignore[attr-defined]
        root,
        *(f"/mods/mod-{index}" for index in range(1, 8)),
    ]
    assert len(MOD._recent_mods) == 8  # type: ignore[attr-defined]
    assert len(set(MOD._recent_mods)) == 8  # type: ignore[attr-defined]
    assert saved == [True]
    assert loaded == [root]
    options["on_finally"]()
    assert progress.closed


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
    app = ModLoadingAppFake()
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
    monkeypatch.setattr(type(MOD), "summary", lambda _mod: "loaded summary")
    MOD.is_md = False
    MOD.sprites = {"GFX_sample": "/mod/gfx/sample.dds"}
    MOD._img_errors = []
    image_loads: list[tuple[str, int]] = []
    monkeypatch.setattr(
        type(MOD),
        "get_image",
        lambda _mod, name: image_loads.append((name, threading.get_ident())),
    )

    app = ModLoadingAppFake()
    app._mod_lbl = FakeLabel()
    app._focus_bundles = {7: object()}
    app.cv = FakeCanvas()
    app.visibility_updates = 0
    app.dropdown_refreshes = 0
    app.status_updates = 0
    app.invalidations = 0
    app.redraws = 0
    app.after_calls = []

    def bump(attribute: str) -> Callable[[], None]:
        def update() -> None:
            setattr(app, attribute, getattr(app, attribute) + 1)

        return update

    app._apply_md_visibility = bump("visibility_updates")
    app._refresh_mod_dropdowns = bump("dropdown_refreshes")
    app._update_statusbar = bump("status_updates")
    app._invalidate_canvas_images = bump("invalidations")
    app._redraw_now = bump("redraws")
    monkeypatch.setattr(
        app, "after", lambda delay, callback: app.after_calls.append((delay, callback))
    )
    ui_thread = threading.get_ident()

    ModLoadingMixin._on_mod_loaded(app, "/mods/sample-mod")

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
