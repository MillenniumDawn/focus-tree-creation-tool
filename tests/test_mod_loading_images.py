"""Mod load image ownership survives rejected completion during close."""

from __future__ import annotations

import gc
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

import pytest
from ui_fakes import ModLoadingAppFake

from hoi4cm.mod.context import ModContext
from hoi4cm.ui import mod_loading, tasks
from hoi4cm.ui.lifecycle import ApplicationLifecycle


class FakeProgress:
    def __init__(self):
        self.cancelled = threading.Event()
        self.closed = False

    def set_text(self, _value):
        pass

    def set_fraction(self, _value):
        pass

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "closing,managed,failing",
    [
        (False, True, False),
        (True, True, False),
        (False, False, False),
        (False, True, True),
    ],
    ids=["normal", "close", "unmanaged", "failure"],
)
def test_mod_load_finalizes_images_on_tk(
    monkeypatch, tmp_path, closing, managed, failing
):
    finalized_on = []
    main_thread = threading.get_ident()
    scanned = threading.Event()
    resume = threading.Event()
    futures = []
    app = ModLoadingAppFake()
    mod = ModContext()
    mod.use_cache = False
    mod._recent_mods = []
    monkeypatch.setattr(mod, "save_config", lambda: True)
    monkeypatch.setattr(mod_loading, "MOD", mod)
    monkeypatch.setattr(
        mod_loading.filedialog, "askdirectory", lambda **_kw: str(tmp_path)
    )

    class TrackedImage:
        def __del__(self):
            finalized_on.append(threading.get_ident())

    mod.sprite_imgs["old"] = TrackedImage()
    original_scan = ModContext.scan

    def blocked_scan(context, root, **kwargs):
        assert threading.get_ident() != main_thread
        result = original_scan(context, root, **kwargs)
        scanned.set()
        assert resume.wait(5)
        if failing:
            raise ValueError("scan failed")
        return result

    monkeypatch.setattr(ModContext, "scan", blocked_scan)
    original_run_bg = tasks.run_bg

    def capture_job(*args, **kwargs):
        future = original_run_bg(*args, **kwargs)
        futures.append(future)
        return future

    monkeypatch.setattr(mod_loading, "run_bg", capture_job)
    monkeypatch.setattr(tasks, "add_error", lambda _message: None)
    progress = FakeProgress()
    monkeypatch.setattr(mod_loading, "progress_modal", lambda *_args, **_kw: progress)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *_args, **_kw: lambda *_a: None
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        if managed:
            app._lifecycle = ApplicationLifecycle(
                cast(Any, app), executor_factory=lambda: executor
            )
        else:
            monkeypatch.setattr(tasks, "get_executor", lambda _owner: executor)
        try:
            app._load_mod()
            assert scanned.wait(5)
            assert finalized_on == []
            if closing:
                assert app._lifecycle is not None
                assert app._lifecycle.begin_close()
                app._lifecycle.finish_close()
                assert finalized_on == [main_thread]
            resume.set()
            futures.pop().result(timeout=5)
            gc.collect()
            if closing:
                assert app.callbacks == []
                assert app.loaded_roots == []
            else:
                assert finalized_on == []
                app.flush()
                assert app.loaded_roots == ([] if failing else [str(tmp_path)])
                if failing:
                    assert mod.sprite_imgs.get("old") is not None
                    assert finalized_on == []
                else:
                    assert finalized_on == [main_thread]
            assert progress.closed
        finally:
            resume.set()
            if managed:
                assert app._lifecycle is not None
                app._lifecycle.close()
