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

import hoi4cm.core.logger as logmod
import hoi4cm.wizards.dyn_mod as dm_mod
from hoi4cm.wizards.dyn_mod import open_dyn_mod_wizard


def _find_preview_text(root):
    found = []

    def walk(w):
        if isinstance(w, tk.Text):
            try:
                bg = w.cget("bg")
            except tk.TclError:
                bg = ""
            if bg == "#0d1117":
                found.append(w)
        for child in w.winfo_children():
            walk(child)

    walk(root)
    return found[0] if found else None


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
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
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

        triggered = False
        for w in tk_root.winfo_children():
            stack = [w]
            while stack:
                cur = stack.pop()
                if isinstance(cur, tk.Entry):
                    try:
                        var_name = cur.cget("textvariable")
                    except tk.TclError:
                        var_name = ""
                    if var_name:
                        try:
                            cur.tk.call("set", var_name, "TRIGGER_VAL")
                            triggered = True
                            break
                        except tk.TclError:
                            pass
                stack.extend(cur.winfo_children())
            if triggered:
                break
        if not triggered:
            for w in tk_root.winfo_children():
                stack = [w]
                while stack:
                    cur = stack.pop()
                    if isinstance(cur, tk.Text) and cur is not preview:
                        try:
                            cur.event_generate("<KeyRelease>")
                        except tk.TclError:
                            pass
                    stack.extend(cur.winfo_children())
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
        try:
            tk_root.grab_release()
        except tk.TclError:
            pass
        for w in list(tk_root.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        tk_root.update_idletasks()


def test_dyn_mod_preview_tclerror_does_not_log(tk_root, monkeypatch):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
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

        for w in tk_root.winfo_children():
            stack = [w]
            while stack:
                cur = stack.pop()
                if isinstance(cur, tk.Text) and cur is not preview:
                    try:
                        cur.event_generate("<KeyRelease>")
                    except tk.TclError:
                        pass
                stack.extend(cur.winfo_children())
        tk_root.update_idletasks()

        entries = logmod.get_error_entries()
        assert not any("Dynamic modifier preview failed" in msg for _, msg in entries)
        preview.delete = original_delete
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        try:
            tk_root.grab_release()
        except tk.TclError:
            pass
        for w in list(tk_root.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        tk_root.update_idletasks()
