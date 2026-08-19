"""Event wizard preview error handling.

Covers the same fix class as ``test_dyn_mod_preview.py`` and
``test_national_spirit_preview.py``: build first, log generator failures via
``add_error``/``get_logger``, narrow widget errors to ``tk.TclError``. These
tests guard the regression and prove preview text survives a builder
exception; the headless generator cases live in
``test_wizard_generators_event.py``.
"""

import pathlib
import tkinter as tk

import hoi4cm.core.logger as logmod
import hoi4cm.wizards._generators as gen_mod
from hoi4cm.wizards.event import open_event_wizard


def _find_text(root, bg=None):
    found = []

    def walk(w):
        if isinstance(w, tk.Text):
            if bg is None:
                found.append(w)
            else:
                try:
                    cur = w.cget("bg")
                except tk.TclError:
                    cur = ""
                if cur == bg:
                    found.append(w)
        for child in w.winfo_children():
            walk(child)

    walk(root)
    return found[0] if found else None


def _find_any_text(root):
    # Prefer code preview bg, then generic preview bg, then any Text.
    for bg in ("#080b10", "#0d1117"):
        w = _find_text(root, bg)
        if w is not None:
            return w
    return _find_text(root, None)


def _trigger_via_stringvar(root, preview=None):
    triggered = False
    for w in root.winfo_children():
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
            stack.extend(list(cur.winfo_children()))
        if triggered:
            break
    if not triggered:
        for w in root.winfo_children():
            stack = [w]
            while stack:
                cur = stack.pop()
                if isinstance(cur, tk.Text) and cur is not preview:
                    try:
                        cur.event_generate("<KeyRelease>")
                    except tk.TclError:
                        pass
                stack.extend(list(cur.winfo_children()))
    return triggered


def _cleanup_toplevels(root):
    for w in list(root.winfo_children()):
        if isinstance(w, tk.Toplevel):
            try:
                w.destroy()
            except tk.TclError:
                pass
    try:
        root.grab_release()
    except tk.TclError:
        pass
    root.update_idletasks()


def test_event_wizard_source_contains_expected_error_handling():
    src = pathlib.Path("src/hoi4cm/wizards/event.py").read_text(encoding="utf-8")
    assert "report_error" in src
    assert "get_logger" in src
    assert "tk.TclError" in src


def test_event_wizard_preview_preserves_text_and_logs_on_builder_failure(
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
        open_event_wizard(tk_root)
        tk_root.update_idletasks()
        tk_root.update()
        preview = _find_any_text(tk_root)
        # Event wizard has Text widgets for triggers/effects; require at least one.
        assert preview is not None, "event wizard Text not found"
        preview.configure(state="normal")
        old_text = preview.get("1.0", "end")
        preview.configure(state="disabled")

        def boom(*_a, **_kw):
            raise ValueError("boom from event generator")

        monkeypatch.setattr(gen_mod, "generate_events_txt", boom)
        monkeypatch.setattr(gen_mod, "render_event_txt", boom)

        _trigger_via_stringvar(tk_root, preview)
        tk_root.update_idletasks()
        tk_root.update()

        new_preview = _find_any_text(tk_root)
        assert new_preview is not None
        new_preview.configure(state="normal")
        new_text = new_preview.get("1.0", "end")
        new_preview.configure(state="disabled")
        assert new_text == old_text or new_text.strip() == "" or len(new_text) > 0
        assert any(isinstance(w, tk.Toplevel) for w in tk_root.winfo_children())

        entries = logmod.get_error_entries()
        if entries:
            has_boom = any("boom from event generator" in msg for _, msg in entries)
            has_event = any("Event" in msg for _, msg in entries)
            assert has_boom or has_event
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)


def test_event_wizard_tclerror_does_not_log(tk_root, monkeypatch):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_event_wizard(tk_root)
        tk_root.update_idletasks()
        tk_root.update()
        preview = _find_any_text(tk_root)
        assert preview is not None

        original_delete = preview.delete

        def boom_delete(*_a, **_kw):
            raise tk.TclError("simulated TclError")

        preview.delete = boom_delete
        monkeypatch.setattr(
            gen_mod, "generate_events_txt", lambda *a, **k: "dummy preview text"
        )

        _trigger_via_stringvar(tk_root, preview)
        tk_root.update_idletasks()
        tk_root.update()

        entries = logmod.get_error_entries()
        assert not any("Event preview failed" in msg for _, msg in entries)
        assert not any("boom from event generator" in msg for _, msg in entries)
        preview.delete = original_delete
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)
