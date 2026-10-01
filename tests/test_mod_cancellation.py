"""Transactional mod-load cancellation and adoption regressions."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pytest

from hoi4cm.mod import context as context_module
from hoi4cm.mod import scan_cache
from hoi4cm.mod.context import ModContext
from hoi4cm.mod.graphics_catalog import GraphicsScanConfig, ScanCancelled
from hoi4cm.ui import mod_loading, tasks
from hoi4cm.ui.lifecycle import ApplicationLifecycle
from hoi4cm.ui.mod_loading import ModLoadingMixin


@pytest.fixture(autouse=True)
def preserve_mod_ui_state():
    mod = mod_loading.MOD
    recent = list(mod._recent_mods)
    images = dict(mod.sprite_imgs._data)
    yield
    mod._recent_mods = recent
    mod.sprite_imgs.clear()
    for key, image in images.items():
        mod.sprite_imgs[key] = image


@pytest.fixture
def loaded_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(context_module, "cfg_load", lambda: {})
    monkeypatch.setattr(scan_cache, "STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "old-mod"
    focus_file = root / "common" / "national_focus" / "old.txt"
    focus_file.parent.mkdir(parents=True)
    focus_file.write_text("focus = { id = OLD_FOCUS }\n")
    context = ModContext()
    context.use_cache = False
    context.scan(str(root))
    context.edit_ideas_file = "old-ideas.txt"
    context.edit_events_file = "old-events.txt"
    context._recent_mods = [str(root)]
    return context, root


def _unchanged_state(context: ModContext):
    return (
        context.root,
        dict(context.sprites),
        list(context.focus_ids),
        context.graphics_catalog,
        context.edit_ideas_file,
        context.edit_events_file,
        list(context._recent_mods),
    )


def test_cancel_before_scan_preserves_loaded_state_and_warm_cache(loaded_mod, tmp_path):
    context, old_root = loaded_mod
    image = object()
    context.sprite_imgs["warm"] = image
    before = _unchanged_state(context)
    cancelled = threading.Event()
    cancelled.set()

    candidate = context.scan(
        str(tmp_path / "new-mod"), cancelled=cancelled, transactional=True
    )

    assert candidate is None
    assert _unchanged_state(context) == before
    assert context.sprite_imgs["warm"] is image
    assert context.root == str(old_root)


def test_cancel_between_steps_preserves_loaded_state(loaded_mod, tmp_path, monkeypatch):
    context, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    root.mkdir()
    cancelled = threading.Event()
    before = _unchanged_state(context)

    def cancel_after_gfx(_candidate):
        cancelled.set()

    monkeypatch.setattr(ModContext, "_scan_national_focus", cancel_after_gfx)

    result = context.scan(str(root), cancelled=cancelled, transactional=True)

    assert result is None
    assert _unchanged_state(context) == before


def test_cancel_during_gfx_inventory_preserves_loaded_state(
    loaded_mod, tmp_path, monkeypatch
):
    context, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    gfx = root / "interface" / "test.gfx"
    gfx.parent.mkdir(parents=True)
    gfx.write_text(
        'spriteType = { name = "GFX_focus_new" '
        'texturefile = "gfx/interface/goals/new.dds" }\n'
    )
    cancelled = threading.Event()
    original_read = context._read
    before = _unchanged_state(context)

    def cancel_on_gfx(path):
        text = original_read(path)
        if path == str(gfx):
            cancelled.set()
        return text

    monkeypatch.setattr(context, "_read", cancel_on_gfx)

    result = context.scan(str(root), cancelled=cancelled, transactional=True)

    assert result is None
    assert _unchanged_state(context) == before
    assert context.root == str(_old_root)


def test_cancelled_refresh_preserves_warm_catalog(loaded_mod, tmp_path):
    context, _old_root = loaded_mod
    catalog = context.graphics_catalog
    old_snapshot = catalog._snapshot
    old_generation = catalog.generation
    old_metrics = catalog.last_metrics
    old_refs = dict(catalog._sprite_refs)
    root = tmp_path / "new-mod"
    gfx = root / "interface" / "cancel.gfx"
    gfx.parent.mkdir(parents=True)
    gfx.write_text(
        'spriteType = { name = "GFX_focus_cancel" '
        'texturefile = "gfx/interface/goals/cancel.dds" }\n'
    )
    cancelled = threading.Event()
    config = GraphicsScanConfig(
        path_goals=context.path_goals,
        path_ideas_gfx=context.path_ideas_gfx,
        path_event_pictures=context.path_event_pictures,
        custom_gfx_dirs=tuple(context.custom_gfx_dirs),
    )

    def cancel_read(path):
        text = context._read(path)
        if path == str(gfx):
            cancelled.set()
        return text

    with pytest.raises(ScanCancelled):
        catalog.refresh(str(root), config, read_text=cancel_read, cancelled=cancelled)

    assert catalog._snapshot is old_snapshot
    assert catalog.generation == old_generation
    assert catalog.last_metrics is old_metrics
    assert catalog._sprite_refs == old_refs


def test_failed_candidate_scan_preserves_loaded_state(
    loaded_mod, tmp_path, monkeypatch
):
    context, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    root.mkdir()
    before = _unchanged_state(context)

    def fail_focus_step(_candidate):
        raise OSError("scan failed")

    monkeypatch.setattr(ModContext, "_scan_national_focus", fail_focus_step)

    with pytest.raises(OSError, match="scan failed"):
        context.scan(str(root), transactional=True)

    assert _unchanged_state(context) == before


def test_success_adopts_candidate_and_releases_warm_images_on_tk(loaded_mod, tmp_path):
    context, old_root = loaded_mod
    finalized_on: list[int] = []
    main_thread = threading.get_ident()

    class TrackedImage:
        def __del__(self):
            finalized_on.append(threading.get_ident())

    context.sprite_imgs["warm"] = TrackedImage()
    del_image = context.sprite_imgs["warm"]
    del del_image
    focus_file = tmp_path / "new-mod" / "common" / "national_focus" / "new.txt"
    focus_file.parent.mkdir(parents=True)
    focus_file.write_text("focus = { id = NEW_FOCUS }\n")

    scan_context = context.new_scan_candidate()
    with ThreadPoolExecutor(max_workers=1) as executor:
        candidate = executor.submit(
            context.scan,
            str(focus_file.parents[2]),
            transactional=True,
            candidate=scan_context,
        ).result(timeout=5)

    assert candidate is not None
    assert candidate.root == str(focus_file.parents[2])
    assert "NEW_FOCUS" in candidate.focus_ids
    assert context.root == str(old_root)
    assert context.sprite_imgs.get("warm") is not None
    assert candidate.sprite_imgs.get("warm") is None
    assert finalized_on == []

    evicted = context.adopt_scan(candidate)
    assert context.root == str(focus_file.parents[2])
    assert "NEW_FOCUS" in context.focus_ids
    assert context.edit_ideas_file == "old-ideas.txt"
    assert context.edit_events_file == "old-events.txt"
    assert context.sprite_imgs.get("warm") is None
    assert finalized_on == []
    evicted.clear()
    assert finalized_on == [main_thread]


class _FakeTcl:
    def call(self, *_args: object) -> object:
        return ()


class _FakeProgress:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.closed = False

    def set_text(self, _value: str) -> None:
        pass

    def set_fraction(self, _value: float) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeApp(ModLoadingMixin):
    _lifecycle: ApplicationLifecycle | None

    def __init__(self) -> None:
        self._lifecycle = None
        self.tk = _FakeTcl()
        self.callbacks: list[Any] = []
        self.loaded_roots: list[str] = []

    def after(self, milliseconds: int, callback):
        self.callbacks.append(callback)
        return callback

    def after_cancel(self, identifier: object) -> None:
        self.callbacks = [
            callback for callback in self.callbacks if callback is not identifier
        ]

    def winfo_exists(self) -> int:
        return 1

    def _on_mod_loaded(self, pw, root):
        self.loaded_roots.append(root)

    def flush(self) -> None:
        while self.callbacks:
            self.callbacks.pop(0)()


def test_superseded_result_is_discarded_and_modal_cleanup_runs(monkeypatch, tmp_path):
    first_root = str(tmp_path / "first")
    second_root = str(tmp_path / "second")
    Path(first_root).mkdir()
    Path(second_root).mkdir()
    selected = iter((first_root, second_root))
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        mod_loading.filedialog, "askdirectory", lambda **_kw: next(selected)
    )
    progress_handles: list[_FakeProgress] = []

    def new_progress(*_args, **_kwargs):
        handle = _FakeProgress()
        progress_handles.append(handle)
        return handle

    monkeypatch.setattr(mod_loading, "progress_modal", new_progress)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *_args, **_kwargs: lambda *_a: None
    )
    first_started = threading.Event()
    release_first = threading.Event()
    first_candidate = object()
    second_candidate = object()

    def scan(_mod, root, **_kwargs):
        if root == first_root:
            first_started.set()
            assert release_first.wait(5)
            return first_candidate
        return second_candidate

    monkeypatch.setattr(type(mod_loading.MOD), "scan", scan)
    adopted: list[object] = []
    monkeypatch.setattr(
        type(mod_loading.MOD),
        "adopt_scan",
        lambda _mod, value: adopted.append(value) or [],
    )
    monkeypatch.setattr(type(mod_loading.MOD), "save_config", lambda _mod: True)
    app = _FakeApp()
    futures = []
    original_run_bg = tasks.run_bg

    def capture_run_bg(*args, **kwargs):
        future = original_run_bg(*args, **kwargs)
        futures.append(future)
        return future

    monkeypatch.setattr(mod_loading, "run_bg", capture_run_bg)

    with ThreadPoolExecutor(max_workers=2) as executor:
        app._lifecycle = ApplicationLifecycle(
            cast(Any, app), executor_factory=lambda: executor
        )
        try:
            app._load_mod()
            assert first_started.wait(5)
            app._load_mod()
            assert futures[1].result(timeout=5) is None
            app.flush()
            release_first.set()
            assert futures[0].result(timeout=5) is None
            app.flush()

            assert app.loaded_roots == [second_root]
            assert adopted == [second_candidate]
            assert [handle.closed for handle in progress_handles] == [True, True]
        finally:
            release_first.set()
            assert app._lifecycle is not None
            app._lifecycle.close()


def test_worker_error_closes_modal_without_adopting_or_recording_recent(
    monkeypatch, tmp_path
):
    root = str(tmp_path / "broken")
    Path(root).mkdir()
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", lambda **_kw: root)
    progress = _FakeProgress()
    monkeypatch.setattr(
        mod_loading, "progress_modal", lambda *_args, **_kwargs: progress
    )
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *_args, **_kwargs: lambda *_a: None
    )

    def failed_scan(_mod, *_args, **_kwargs):
        raise OSError("broken")

    monkeypatch.setattr(type(mod_loading.MOD), "scan", failed_scan)
    monkeypatch.setattr(tasks, "add_error", lambda _error: None)
    saved: list[bool] = []

    def save_config(_mod) -> bool:
        saved.append(True)
        return True

    monkeypatch.setattr(type(mod_loading.MOD), "save_config", save_config)
    app = _FakeApp()
    loaded_mod = mod_loading.MOD
    previous_recent = loaded_mod._recent_mods.copy()
    previous_root = loaded_mod.root
    previous_loaded = loaded_mod.loaded
    previous_ideas_target = loaded_mod.edit_ideas_file
    previous_events_target = loaded_mod.edit_events_file
    warm_image = object()
    loaded_mod.sprite_imgs["warm"] = warm_image

    with ThreadPoolExecutor(max_workers=1) as executor:
        app._lifecycle = ApplicationLifecycle(
            cast(Any, app), executor_factory=lambda: executor
        )
        futures = []
        original_run_bg = tasks.run_bg

        def capture_run_bg(*args, **kwargs):
            future = original_run_bg(*args, **kwargs)
            futures.append(future)
            return future

        monkeypatch.setattr(mod_loading, "run_bg", capture_run_bg)
        try:
            app._load_mod()
            assert futures[0].result(timeout=5) is None
            app.flush()
            assert progress.closed
            assert app.loaded_roots == []
            assert saved == []
            assert loaded_mod._recent_mods == previous_recent
            assert loaded_mod.root == previous_root
            assert loaded_mod.loaded == previous_loaded
            assert loaded_mod.edit_ideas_file == previous_ideas_target
            assert loaded_mod.edit_events_file == previous_events_target
            assert loaded_mod.sprite_imgs.get("warm") is warm_image
        finally:
            assert app._lifecycle is not None
            app._lifecycle.close()
