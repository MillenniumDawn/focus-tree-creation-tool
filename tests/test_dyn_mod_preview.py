"""Preview error handling — dyn_mod parity for issue #63.

``dyn_mod.py`` had the opposite failure mode to ``national_spirit.py``:
no try at all, so a generator error surfaced as a Tk callback traceback
and never reached the in-app error log. The fix mirrors the national
spirit wizard: build first, log via ``add_error``/``get_logger``, narrow
widget errors to ``tk.TclError``.
"""

import pathlib
import re
import tkinter as tk

from tk_helpers import (
    cleanup_toplevels,
    find_text,
    key_release_on_other_texts,
    release_grab,
    trigger_preview_refresh,
)

import hoi4cm.core.logger as logmod
import hoi4cm.wizards.dyn_mod as dm_mod
from hoi4cm.wizards.dyn_mod import open_dyn_mod_wizard


def _find_preview_text(root):
    return find_text(root, "#0d1117")


def test_dyn_mod_preview_source_contains_expected_error_handling():
    src = pathlib.Path("src/hoi4cm/wizards/dyn_mod.py").read_text(encoding="utf-8")
    assert "text = _build_output()" in src
    assert "text = _dm_get_output()" in src
    assert "except tk.TclError:" in src
    assert "add_error" in src
    assert "get_logger" in src
    for name in ("def _preview", "def _dm_show_preview"):
        m = re.search(rf"{re.escape(name)}.*?def ", src, re.S)
        assert m, f"{name} block not found"
        block = m.group(0)
        assert "except tk.TclError" in block
        assert "except Exception as exc" in block


def test_dyn_mod_preview_preserves_text_and_logs_on_builder_failure(
    tk_root, monkeypatch
):
    release_grab(tk_root)
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_dyn_mod_wizard(tk_root)
        tk_root.update_idletasks()
        preview = _find_preview_text(tk_root)
        assert preview is not None, "preview Text not found"
        preview.configure(state="normal")
        old_text = preview.get("1.0", "end")
        preview.configure(state="disabled")

        def boom(**_kwargs):
            raise ValueError("boom from dyn_mod generator")

        monkeypatch.setattr(dm_mod, "build_dyn_mod_output", boom)

        trigger_preview_refresh(tk_root, preview)
        tk_root.update_idletasks()

        preview.configure(state="normal")
        new_text = preview.get("1.0", "end")
        preview.configure(state="disabled")
        assert new_text == old_text

        entries = logmod.get_error_entries()
        assert any("boom from dyn_mod generator" in msg for _, msg in entries)
        assert any("Dynamic modifier preview failed" in msg for _, msg in entries)
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        cleanup_toplevels(tk_root)


def test_dyn_mod_preview_tclerror_does_not_log(tk_root, monkeypatch):
    release_grab(tk_root)
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_dyn_mod_wizard(tk_root)
        tk_root.update_idletasks()
        preview = _find_preview_text(tk_root)
        assert preview is not None

        original_delete = preview.delete

        def boom_delete(*a, **kw):
            raise tk.TclError("simulated TclError")

        preview.delete = boom_delete
        monkeypatch.setattr(
            dm_mod, "build_dyn_mod_output", lambda **_kw: "dummy preview text"
        )

        key_release_on_other_texts(tk_root, preview)
        tk_root.update_idletasks()

        entries = logmod.get_error_entries()
        assert not any("Dynamic modifier preview failed" in msg for _, msg in entries)
        preview.delete = original_delete
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        cleanup_toplevels(tk_root)
