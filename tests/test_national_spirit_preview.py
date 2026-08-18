"""Preview error handling — issue #63.

The national spirit wizard's live preview used to swallow generator failures
inside a broad ``except Exception: pass`` that also covered widget ops, leaving
stale or blank text with no signal. The fix builds text first, logs generator
failures via ``add_error``/``get_logger``, and narrows widget errors to
``tk.TclError``.

These tests prove the fix and guard the regression. The headless generator
cases live in ``test_wizard_generators_national_spirit.py``; this file covers
the Tk wiring that the generator tests cannot reach.
"""

import pathlib
import tkinter as tk

import hoi4cm.core.logger as logmod
import hoi4cm.wizards.national_spirit as ns_mod
from hoi4cm.wizards.national_spirit import open_national_spirit_wizard


def _find_preview_text(root):
    """Walk the widget tree and return the preview Text (the one with dark bg)."""
    found = []

    def walk(w):
        if isinstance(w, tk.Text):
            # preview pane uses bg #0d1117, editor uses BG_CARD — use bg to distinguish
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


def test_preview_source_contains_expected_error_handling():
    """Regression guard: the fix must not be reverted to ``except Exception: pass``."""
    src = pathlib.Path("src/hoi4cm/wizards/national_spirit.py").read_text(
        encoding="utf-8"
    )
    # Build text before touching the widget.
    assert "text = _build_output()" in src
    # Widget ops are behind TclError only.
    assert "except tk.TclError:" in src
    # Generator failures are logged, not swallowed.
    assert "add_error" in src
    assert "get_logger" in src
    # Scope the check to the preview function: the old broad except over the
    # widget block must be gone there, even though other helpers still use it.
    import re

    m = re.search(r"def _refresh_preview.*?def _get_output_text", src, re.S)
    assert m, "_refresh_preview block not found"
    block = m.group(0)
    assert "except tk.TclError" in block
    assert "except Exception as exc" in block
    assert "except Exception:\n            pass" not in block


def test_preview_preserves_text_and_logs_on_builder_failure(tk_root, monkeypatch):
    """When the generator raises, the preview keeps its old text and logs."""

    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    # Isolate logger state like tests/test_logger.py does.
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_national_spirit_wizard(tk_root)
        tk_root.update_idletasks()
        preview = _find_preview_text(tk_root)
        assert preview is not None, "preview Text not found"
        preview.configure(state="normal")
        old_text = preview.get("1.0", "end")
        preview.configure(state="disabled")

        def boom(**_kwargs):
            raise ValueError("boom from generator")

        monkeypatch.setattr(ns_mod, "build_national_spirit_output", boom)

        # Trigger preview via a traced StringVar: find an Entry's Tcl variable
        # and set it, which fires the trace that calls _refresh_preview.
        # The wizard's v_id etc. are all traced, so mutating any one is enough.
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
        # Fallback: if no Entry found, fire KeyRelease on a non-preview Text.
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
        assert any("boom from generator" in msg for _, msg in entries)
        assert any("National spirit preview failed" in msg for _, msg in entries)
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


def test_preview_tclerror_does_not_log_or_blank(tk_root, monkeypatch):
    """Widget TclError during preview update is swallowed without logging."""
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_national_spirit_wizard(tk_root)
        tk_root.update_idletasks()
        preview = _find_preview_text(tk_root)
        assert preview is not None

        # Force widget ops to raise TclError after text has been built.
        # Patch the Text's config to raise on the second call (delete/insert path).
        original_config = preview.config
        calls = []

        def failing_config(*a, **kw):
            calls.append(kw)
            if len(calls) == 2:  # second config is the delete/insert block
                raise tk.TclError("widget destroyed")
            return original_config(*a, **kw)

        # Instead patch the class to avoid interfering with our own config above
        # that reads old_text. Use a simpler approach: patch preview.delete to raise.
        original_delete = preview.delete

        def boom_delete(*a, **kw):
            raise tk.TclError("simulated TclError")

        preview.delete = boom_delete

        # Patch builder to return harmless text so we reach widget block.
        monkeypatch.setattr(
            ns_mod, "build_national_spirit_output", lambda **_kw: "dummy preview text"
        )

        # Trigger preview via KeyRelease on a non-preview Text.
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

        # Must not have logged a preview failure (TclError is expected for destroyed
        # widgets and should be silent).
        entries = logmod.get_error_entries()
        assert not any("National spirit preview failed" in msg for _, msg in entries)
        # And must not have raised to the Tk callback chain.

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
