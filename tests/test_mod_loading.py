"""Headless regression tests for mod-loading UI wiring."""

from __future__ import annotations

import threading
import types
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from ui_fakes import AppFake

import hoi4cm.core.logger as logmod
from hoi4cm.mod.index import ModIndex
from hoi4cm.ui import mod_loading
from hoi4cm.ui.mod_loading import ModLoadingMixin
from hoi4cm.wizards._shared import WizardImageCaches


@pytest.fixture
def error_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[tuple[str, str]]]:
    """Isolate the shared error buffer from callbacks left by earlier Tk tests."""
    monkeypatch.setattr(logmod, "_error_callback", None)
    logmod.clear_errors()
    yield logmod.get_error_entries()
    logmod.clear_errors()


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
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))

    dialog_calls: list[dict[str, object]] = []

    def askdirectory(**kwargs: object) -> str:
        dialog_calls.append(kwargs)
        return root

    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", askdirectory)
    progress = _patch_progress_window(monkeypatch)
    background_calls: list[tuple[Any, Any, dict[str, object]]] = []
    saved: list[bool] = []
    loaded: list[str] = []
    scanned_contexts: list[object] = []
    adopted: list[object] = []
    scan_arguments: dict[str, object] = {}

    def fake_scan(mod, *_args, **kwargs):
        scanned_contexts.append(mod)
        scan_arguments.update(kwargs)
        return True

    def adopt_scan(_mod, candidate) -> None:
        adopted.append(candidate)

    monkeypatch.setattr(ModIndex, "scan", fake_scan)
    monkeypatch.setattr(ModIndex, "adopt_scan", adopt_scan)

    def run_bg(widget, worker, on_done, **kwargs) -> None:
        background_calls.append((worker, on_done, kwargs))

    monkeypatch.setattr(mod_loading, "run_bg", run_bg)
    app = AppFake()
    app.app_config.recent_mods = list(old_recent)

    def save_user_config(window_geometry: str = "") -> bool:
        saved.append(True)
        return True

    monkeypatch.setattr(app, "save_user_config", save_user_config)
    app._lifecycle = _AcceptingLifecycle()
    monkeypatch.setattr(app, "_on_mod_loaded", loaded.append)
    previous_recent = list(app.app_config.recent_mods)

    app._load_mod()

    assert app.app_config.recent_mods == previous_recent
    assert saved == []
    assert dialog_calls and dialog_calls[0]["initialdir"] == str(tmp_path)
    assert app._lifecycle.begun == ["mod"]
    assert len(background_calls) == 1
    worker, on_done, options = background_calls[0]
    assert options["scope"] == "mod"
    assert callable(options["on_finally"])
    assert "self" not in worker.__code__.co_freevars
    assert "pw" not in worker.__code__.co_freevars
    assert worker() is True
    assert scanned_contexts[0] is not app.index
    assert scan_arguments["cancelled"] is progress.cancelled
    on_done(True)
    assert adopted == scanned_contexts
    assert app.app_config.recent_mods == [
        root,
        *(f"/mods/mod-{index}" for index in range(1, 8)),
    ]
    assert len(app.app_config.recent_mods) == 8
    assert len(set(app.app_config.recent_mods)) == 8
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

    def askdirectory(**kwargs: object) -> str:
        dialog_calls.append(True)
        return "/mods/new"

    def save_user_config(window_geometry: str = "") -> bool:
        config_writes.append(True)
        return True

    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", askdirectory)
    app = AppFake()
    app.app_config.recent_mods = list(previous_recent)
    monkeypatch.setattr(app, "save_user_config", save_user_config)
    app._lifecycle = type("ClosedLifecycle", (), {"accepting": False})()

    app._load_mod()

    assert dialog_calls == []
    assert config_writes == []
    assert app.app_config.recent_mods == previous_recent


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
    image_loads: list[tuple[str, int]] = []

    app = AppFake()
    caches = WizardImageCaches()
    caches.window_caches.append(cache)
    caches.event_gfx["stale-gfx"] = "/mod/gfx/stale.png"
    caches.event_imgsize["/mod/gfx/stale.png"] = (64, 64)
    app.wiz_img_caches = caches
    monkeypatch.setattr(
        mod_loading.messagebox, "showinfo", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(mod_loading.os.path, "exists", lambda path: True)
    app.index.is_md = False
    app.index.sprites = {"GFX_sample": "/mod/gfx/sample.dds"}
    monkeypatch.setattr(
        app.images,
        "get_image",
        lambda sprites, name, size=(64, 64): image_loads.append(
            (name, threading.get_ident())
        ),
    )
    app._mod_lbl = FakeLabel()
    from hoi4cm.ui.canvas_renderer import FocusCanvasBundle

    app._focus_bundles = {7: FocusCanvasBundle((), "full")}
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

    monkeypatch.setattr(
        app, "_apply_md_visibility", bump("visibility_updates"), raising=False
    )
    monkeypatch.setattr(
        app, "_refresh_mod_dropdowns", bump("dropdown_refreshes"), raising=False
    )
    monkeypatch.setattr(app, "_update_statusbar", bump("status_updates"))
    monkeypatch.setattr(app, "_invalidate_canvas_images", bump("invalidations"))
    monkeypatch.setattr(app, "_redraw_now", bump("redraws"))
    monkeypatch.setattr(
        app, "after", lambda delay, callback: app.after_calls.append((delay, callback))
    )
    ui_thread = threading.get_ident()

    ModLoadingMixin._on_mod_loaded(app, "/mods/sample-mod")

    assert app._mod_lbl.configurations[0]["text"].startswith("📂 sample-mod")
    assert app._mod_label_base == app._mod_lbl.configurations[0]["text"]
    assert app.visibility_updates == 1
    assert app.dropdown_refreshes == 1
    assert app.status_updates == 1
    assert app.invalidations == 1
    assert app._focus_bundles == {}
    assert app.validation_schedules == 1
    assert app.cv.deleted == ["focus"]
    assert app.redraws == 1
    assert cache == {}
    assert app.wiz_img_caches.event_gfx == {}
    assert app.wiz_img_caches.event_imgsize == {}
    assert image_loads == [("GFX_sample", ui_thread)]
    assert len(app.after_calls) == 1
    assert app.after_calls[0][0] == 150


def test_format_mod_label_appends_targets_without_parsing_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod_loading,
        "tr",
        lambda key, default=None, **kwargs: (default or key).format(**kwargs),
    )
    base = "📂 sample-mod  |  edit: stale"

    text = mod_loading.format_mod_label(
        base,
        {
            "ideas": "/mods/sample/common/ideas/spirits.txt",
            "events": "  ",
            "focus": "/mods/sample/common/national_focus/tree.txt",
            "sloc": "/mods/sample/localisation/english/extra.yml",
        },
    )

    assert text == (
        "📂 sample-mod  |  edit: stale  |  edit: "
        "ideas: spirits.txt  +  focus: tree.txt  +  sloc: extra.yml"
    )
    assert mod_loading.format_mod_label(base, {}) == base


def _mod_loaded_app(monkeypatch: pytest.MonkeyPatch) -> tuple[AppFake, list[str]]:
    """A fake app whose Mod Loaded dialog text is collected into the list."""
    dialogs: list[str] = []
    monkeypatch.setattr(
        mod_loading.messagebox,
        "showinfo",
        lambda _title, message, **_kwargs: dialogs.append(message),
    )
    app = AppFake()
    app.wiz_img_caches = WizardImageCaches()
    app.index.is_md = False
    app.index.sprites = {}
    app.index.failed_steps = []
    app.index.unparsable_files = []
    app._lifecycle = None
    app._mod_lbl = types.SimpleNamespace(config=lambda **_kwargs: None)
    app.cv.delete = lambda _tag: None
    app_any = cast(Any, app)
    app_any._apply_md_visibility = lambda: None
    app_any._refresh_mod_dropdowns = lambda: None
    app_any._update_statusbar = lambda: None
    app_any._invalidate_canvas_images = lambda: None
    app_any._redraw_now = lambda: None
    app_any.after = lambda _delay, _callback: None
    return app, dialogs


def test_on_mod_loaded_names_failed_steps_and_unparsable_files(
    monkeypatch: pytest.MonkeyPatch, error_buffer: list[tuple[str, str]]
) -> None:
    app, dialogs = _mod_loaded_app(monkeypatch)
    paths = [f"/mod/common/ideas/{name}.txt" for name in ("a", "b", "c", "d")]
    app.index.failed_steps = ["Events", "Characters"]
    app.index.unparsable_files = paths

    ModLoadingMixin._on_mod_loaded(app, "/mods/sample-mod")

    assert len(dialogs) == 1
    assert "Events, Characters" in dialogs[0]
    assert "(4, first 3)" in dialogs[0]
    assert all(path in dialogs[0] for path in paths[:3])
    assert paths[3] not in dialogs[0]
    assert len(error_buffer) == 1
    assert "Events, Characters" in error_buffer[0][1]
    assert paths[0] in error_buffer[0][1]


def test_on_mod_loaded_adds_nothing_for_a_clean_scan(
    monkeypatch: pytest.MonkeyPatch, error_buffer: list[tuple[str, str]]
) -> None:
    app, dialogs = _mod_loaded_app(monkeypatch)

    ModLoadingMixin._on_mod_loaded(app, "/mods/sample-mod")

    assert len(dialogs) == 1
    assert "failed" not in dialogs[0]
    assert "parsed" not in dialogs[0]
    assert error_buffer == []


def test_on_mod_loaded_records_a_failed_validation_and_still_prompts(
    monkeypatch: pytest.MonkeyPatch, error_buffer: list[tuple[str, str]]
) -> None:
    app, _dialogs = _mod_loaded_app(monkeypatch)
    prompts: list[int] = []
    cast(Any, app).after = lambda delay, _callback: prompts.append(delay)

    def validate() -> None:
        raise RuntimeError("validation exploded")

    cast(Any, app)._schedule_validation = validate

    ModLoadingMixin._on_mod_loaded(app, "/mods/sample-mod")

    assert len(error_buffer) == 1
    assert "validation exploded" in error_buffer[0][1]
    assert prompts == [150]
