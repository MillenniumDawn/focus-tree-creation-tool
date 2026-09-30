"""Mod load image ownership survives rejected completion during close."""

import gc
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from hoi4cm.mod.context import ModContext
from hoi4cm.ui import mod_loading, tasks
from hoi4cm.ui.lifecycle import ApplicationLifecycle
from hoi4cm.ui.mod_loading import ModLoadingMixin


class FakeApp(ModLoadingMixin):
    def __init__(self):
        self._lifecycle = None
        self.callbacks = []
        self.loaded_roots = []
        self.tk = Mock()
        self.tk.call.return_value = ()

    def after(self, _delay, callback):
        self.callbacks.append(callback)
        return callback

    def after_cancel(self, callback):
        self.callbacks.remove(callback)

    def winfo_exists(self):
        return True

    def _on_mod_loaded(self, _pw, root):
        self.loaded_roots.append(root)

    def flush(self):
        while self.callbacks:
            self.callbacks.pop(0)()


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
    app = FakeApp()
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
    original_scan = mod.scan

    def blocked_scan(root, **kwargs):
        assert threading.get_ident() != main_thread
        result = original_scan(root, **kwargs)
        scanned.set()
        assert resume.wait(5)
        if failing:
            raise ValueError("scan failed")
        return result

    monkeypatch.setattr(mod, "scan", blocked_scan)
    original_run_bg = tasks.run_bg

    def capture_job(*args, **kwargs):
        future = original_run_bg(*args, **kwargs)
        futures.append(future)
        return future

    monkeypatch.setattr(mod_loading, "run_bg", capture_job)
    monkeypatch.setattr(tasks, "add_error", lambda _message: None)
    monkeypatch.setattr(
        mod_loading, "make_progress", lambda *_args, **_kw: lambda *_a: None
    )
    widget = Mock()
    widget.master = app
    widget._lifecycle = None
    widget.after = app.after
    widget.after_cancel = app.after_cancel
    widget.winfo_exists = app.winfo_exists
    for name in ("Toplevel", "Label", "Frame"):
        monkeypatch.setattr(mod_loading.tk, name, lambda *_args, **_kw: widget)

    with ThreadPoolExecutor(max_workers=1) as executor:
        if managed:
            app._lifecycle = ApplicationLifecycle(
                app, executor_factory=lambda: executor
            )
        else:
            monkeypatch.setattr(tasks, "get_executor", lambda _owner: executor)
        try:
            app._load_mod()
            assert scanned.wait(5)
            assert finalized_on == []
            if closing:
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
            assert finalized_on == [main_thread]
        finally:
            resume.set()
            if managed:
                app._lifecycle.close()
