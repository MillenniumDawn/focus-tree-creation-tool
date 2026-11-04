"""Candidate mod-scan cancellation and adoption regressions."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import pytest
from ui_fakes import AppFake

from hoi4cm.mod import scan_cache
from hoi4cm.mod.graphics_catalog import GraphicsScanConfig, ScanCancelled
from hoi4cm.mod.index import ModIndex
from hoi4cm.ui import mod_loading, tasks
from hoi4cm.ui.lifecycle import ApplicationLifecycle
from hoi4cm.ui.sprite_images import SpriteImageCache


@pytest.fixture
def loaded_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_cache, "STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "old-mod"
    focus_file = root / "common" / "national_focus" / "old.txt"
    focus_file.parent.mkdir(parents=True)
    focus_file.write_text("focus = { id = OLD_FOCUS }\n")
    index = ModIndex()
    index.use_cache = False
    index.scan(str(root))
    return index, root


def _unchanged_state(index: ModIndex):
    return (
        index.root,
        dict(index.sprites),
        list(index.focus_ids),
        index.graphics_catalog,
    )


def test_cancel_before_scan_preserves_loaded_state_and_warm_cache(loaded_mod, tmp_path):
    index, old_root = loaded_mod
    cache = SpriteImageCache()
    image = object()
    cache.images["warm"] = image
    before = _unchanged_state(index)
    cancelled = threading.Event()
    cancelled.set()

    candidate = index.new_scan_candidate()
    result = candidate.scan(str(tmp_path / "new-mod"), cancelled=cancelled)

    assert result is None
    assert not candidate.loaded
    assert _unchanged_state(index) == before
    assert cache.images["warm"] is image
    assert index.root == str(old_root)


def test_cancel_between_steps_preserves_loaded_state(loaded_mod, tmp_path, monkeypatch):
    index, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    root.mkdir()
    cancelled = threading.Event()
    before = _unchanged_state(index)
    monkeypatch.setattr(
        ModIndex, "_scan_national_focus", lambda _candidate: cancelled.set()
    )
    candidate = index.new_scan_candidate()

    result = candidate.scan(str(root), cancelled=cancelled)

    assert result is None
    assert not candidate.loaded
    assert _unchanged_state(index) == before


def test_cancel_during_final_step_rejects_candidate(loaded_mod, tmp_path, monkeypatch):
    index, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    root.mkdir()
    before = _unchanged_state(index)
    cancelled = threading.Event()
    monkeypatch.setattr(ModIndex, "_scan_tags", lambda _candidate: cancelled.set())
    candidate = index.new_scan_candidate()

    assert candidate.scan(str(root), cancelled=cancelled) is None
    assert not candidate.loaded
    assert candidate._cache is None
    assert _unchanged_state(index) == before


def test_cancel_during_gfx_inventory_preserves_loaded_state(
    loaded_mod, tmp_path, monkeypatch
):
    index, old_root = loaded_mod
    root = tmp_path / "new-mod"
    gfx = root / "interface" / "test.gfx"
    gfx.parent.mkdir(parents=True)
    gfx.write_text(
        'spriteType = { name = "GFX_focus_new" '
        'texturefile = "gfx/interface/goals/new.dds" }\n'
    )
    cancelled = threading.Event()
    original_read = ModIndex._read
    before = _unchanged_state(index)

    def cancel_on_gfx(candidate, path):
        text = original_read(candidate, path)
        if path == str(gfx):
            cancelled.set()
        return text

    monkeypatch.setattr(ModIndex, "_read", cancel_on_gfx)
    candidate = index.new_scan_candidate()
    result = candidate.scan(str(root), cancelled=cancelled)

    assert result is None
    assert not candidate.loaded
    assert _unchanged_state(index) == before
    assert index.root == str(old_root)


def test_cancelled_refresh_preserves_warm_catalog(loaded_mod, tmp_path):
    index, _old_root = loaded_mod
    catalog = index.graphics_catalog
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

    def cancel_read(path):
        text = index._read(path)
        if path == str(gfx):
            cancelled.set()
        return text

    with pytest.raises(ScanCancelled):
        catalog.refresh(
            str(root),
            GraphicsScanConfig(
                path_goals="gfx/interface/goals", path_ideas_gfx="gfx/interface/ideas"
            ),
            read_text=cancel_read,
            cancelled=cancelled,
        )

    assert catalog._snapshot is old_snapshot
    assert catalog.generation == old_generation
    assert catalog.last_metrics is old_metrics
    assert catalog._sprite_refs == old_refs


def test_failed_step_does_not_abort_the_remaining_steps(
    loaded_mod, tmp_path, monkeypatch
):
    index, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    events = root / "events" / "new.txt"
    events.parent.mkdir(parents=True)
    events.write_text("country_event = { id = new.1 }\n")
    before = _unchanged_state(index)

    def fail_focus_step(_candidate):
        raise OSError("scan failed")

    monkeypatch.setattr(ModIndex, "_scan_national_focus", fail_focus_step)
    candidate = index.new_scan_candidate()

    assert candidate.scan(str(root)) is not None
    assert candidate.loaded
    assert candidate.focus_ids == []
    assert candidate.event_ids == {"new": ["new.1"]}
    assert _unchanged_state(index) == before


def test_unexpected_scan_error_preserves_loaded_state(
    loaded_mod, tmp_path, monkeypatch
):
    index, _old_root = loaded_mod
    root = tmp_path / "new-mod"
    root.mkdir()
    before = _unchanged_state(index)

    def fail_focus_step(_candidate):
        raise KeyError("scan failed")

    monkeypatch.setattr(ModIndex, "_scan_national_focus", fail_focus_step)

    with pytest.raises(KeyError, match="scan failed"):
        index.new_scan_candidate().scan(str(root))

    assert _unchanged_state(index) == before


def test_adoption_does_not_persist_replaced_catalog(loaded_mod, monkeypatch):
    index, root = loaded_mod
    image = root / "gfx" / "interface" / "goals" / "new.dds"
    image.parent.mkdir(parents=True)
    image.touch()
    index.graphics_catalog.note_written(str(image), read_text=index._read)
    candidate = index.new_scan_candidate()
    assert candidate.scan(str(root)) is not None
    assert index.graphics_catalog._cache_dirty

    def fail_flush():
        raise AssertionError("catalog persistence must not block Tk adoption")

    monkeypatch.setattr(index.graphics_catalog, "flush_cache", fail_flush)

    assert index.adopt_scan(candidate) is None
    assert index.graphics_catalog is candidate.graphics_catalog
    assert index.focus_ids == ["OLD_FOCUS"]


def test_success_adopts_candidate_and_releases_warm_images_on_tk(loaded_mod, tmp_path):
    index, old_root = loaded_mod
    app = AppFake()
    app.index = index
    app.edit_ideas_file = "old-ideas.txt"
    app.edit_events_file = "old-events.txt"
    finalized_on: list[int] = []
    main_thread = threading.get_ident()

    class TrackedImage:
        def __del__(self):
            finalized_on.append(threading.get_ident())

    app.images.images["warm"] = TrackedImage()
    focus_file = tmp_path / "new-mod" / "common" / "national_focus" / "new.txt"
    focus_file.parent.mkdir(parents=True)
    focus_file.write_text("focus = { id = NEW_FOCUS }\n")

    old_generation = index.graphics_catalog.generation
    candidate = index.new_scan_candidate()
    with ThreadPoolExecutor(max_workers=1) as executor:
        scanned = executor.submit(candidate.scan, str(focus_file.parents[2])).result(
            timeout=5
        )

    assert scanned is not None
    assert candidate.root == str(focus_file.parents[2])
    assert "NEW_FOCUS" in candidate.focus_ids
    assert index.root == str(old_root)
    assert app.images.images.get("warm") is not None
    assert not hasattr(candidate, "get_image")
    assert not hasattr(candidate, "images")
    assert finalized_on == []

    evicted = app.images.clear()
    index.adopt_scan(candidate)
    assert index.root == str(focus_file.parents[2])
    assert "NEW_FOCUS" in index.focus_ids
    assert app.edit_ideas_file == "old-ideas.txt"
    assert app.edit_events_file == "old-events.txt"
    assert index.graphics_catalog.generation > old_generation
    assert app.images.images.get("warm") is None
    assert finalized_on == []
    evicted.clear()
    assert finalized_on == [main_thread]


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


def _prepare_load(monkeypatch, tmp_path, root):
    monkeypatch.setattr(mod_loading, "_default_hoi4_mod_dir", lambda: str(tmp_path))
    monkeypatch.setattr(mod_loading.filedialog, "askdirectory", lambda **_kw: root)
    progress = _FakeProgress()
    monkeypatch.setattr(mod_loading, "progress_modal", lambda *_a, **_kw: progress)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *_args, **_kwargs: lambda *_a: None
    )
    futures = []
    original_run_bg = tasks.run_bg

    def capture_run_bg(*args, **kwargs):
        future = original_run_bg(*args, **kwargs)
        futures.append(future)
        return future

    monkeypatch.setattr(mod_loading, "run_bg", capture_run_bg)
    return progress, futures


@pytest.mark.parametrize("window", ["final_step", "after_completion"])
def test_late_cancel_discards_a_completed_scan(monkeypatch, tmp_path, window):
    root = str(tmp_path / "late")
    Path(root).mkdir()
    progress, futures = _prepare_load(monkeypatch, tmp_path, root)

    def scan(_index, _root, _settings, **_kwargs):
        if window == "final_step":
            progress.cancelled.set()
        return True

    monkeypatch.setattr(ModIndex, "scan", scan)
    adopted: list[object] = []
    monkeypatch.setattr(ModIndex, "adopt_scan", lambda _i, value: adopted.append(value))
    saved: list[bool] = []
    app = AppFake()

    def save_user_config(window_geometry=""):
        saved.append(True)
        return True

    monkeypatch.setattr(app, "save_user_config", save_user_config)
    previous_recent = list(app.app_config.recent_mods)
    with ThreadPoolExecutor(max_workers=1) as executor:
        app._lifecycle = ApplicationLifecycle(
            cast(Any, app), executor_factory=lambda: executor
        )
        try:
            app._load_mod()
            assert futures[0].result(timeout=5) is None
            if window == "after_completion":
                progress.cancelled.set()
            app.flush()
            assert adopted == []
            assert app.loaded_roots == []
            assert saved == []
            assert app.app_config.recent_mods == previous_recent
            assert progress.closed
        finally:
            app._lifecycle.close()


def test_superseded_result_is_discarded_and_modal_cleanup_runs(monkeypatch, tmp_path):
    first_root = str(tmp_path / "first")
    second_root = str(tmp_path / "second")
    Path(first_root).mkdir()
    Path(second_root).mkdir()
    _progress, futures = _prepare_load(monkeypatch, tmp_path, first_root)
    selected = iter((first_root, second_root))
    monkeypatch.setattr(
        mod_loading.filedialog, "askdirectory", lambda **_kw: next(selected)
    )
    progress_handles: list[_FakeProgress] = []

    def new_progress(*_args, **_kwargs):
        handle = _FakeProgress()
        progress_handles.append(handle)
        return handle

    monkeypatch.setattr(mod_loading, "progress_modal", new_progress)
    first_started = threading.Event()
    release_first = threading.Event()
    candidates: list[ModIndex] = []

    def scan(index, root, _settings, **_kwargs):
        candidates.append(index)
        if root == first_root:
            first_started.set()
            assert release_first.wait(5)
        return True

    monkeypatch.setattr(ModIndex, "scan", scan)
    adopted: list[object] = []
    monkeypatch.setattr(ModIndex, "adopt_scan", lambda _i, value: adopted.append(value))
    app = AppFake()
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
            assert adopted == [candidates[1]]
            assert [handle.closed for handle in progress_handles] == [True, True]
        finally:
            release_first.set()
            app._lifecycle.close()


def test_worker_error_closes_modal_without_adopting_or_recording_recent(
    monkeypatch, tmp_path
):
    root = str(tmp_path / "broken")
    Path(root).mkdir()
    progress, futures = _prepare_load(monkeypatch, tmp_path, root)

    def failed_scan(_index, *_args, **_kwargs):
        raise OSError("broken")

    monkeypatch.setattr(ModIndex, "scan", failed_scan)
    monkeypatch.setattr(tasks, "add_error", lambda _error: None)
    saved: list[bool] = []
    app = AppFake()

    def save_user_config(window_geometry=""):
        saved.append(True)
        return True

    monkeypatch.setattr(app, "save_user_config", save_user_config)
    before = _unchanged_state(app.index)
    previous_recent = list(app.app_config.recent_mods)
    previous_ideas_target = app.edit_ideas_file
    previous_events_target = app.edit_events_file
    warm_image = object()
    app.images.images["warm"] = warm_image
    with ThreadPoolExecutor(max_workers=1) as executor:
        app._lifecycle = ApplicationLifecycle(
            cast(Any, app), executor_factory=lambda: executor
        )
        try:
            app._load_mod()
            assert futures[0].result(timeout=5) is None
            app.flush()
            assert progress.closed
            assert app.loaded_roots == []
            assert saved == []
            assert app.app_config.recent_mods == previous_recent
            assert _unchanged_state(app.index) == before
            assert app.edit_ideas_file == previous_ideas_target
            assert app.edit_events_file == previous_events_target
            assert app.images.images.get("warm") is warm_image
        finally:
            app._lifecycle.close()
