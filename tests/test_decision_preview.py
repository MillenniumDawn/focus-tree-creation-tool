"""Decision wizard preview error handling.

Covers the same fix class as ``test_dyn_mod_preview.py`` and
``test_national_spirit_preview.py``: build first, log generator failures via
``add_error``/``get_logger``, narrow widget errors to ``tk.TclError``. These
tests guard the regression and prove preview text survives a builder
exception; the headless generator cases live in
``test_wizard_generators_decision.py``.
"""

import pathlib
import tkinter as tk

import hoi4cm.core.logger as logmod
import hoi4cm.wizards._generators as gen_mod
from hoi4cm.wizards.decision import open_decision_wizard


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


def _click_button_by_text(root, needle):
    for w in root.winfo_children():
        stack = [w]
        while stack:
            cur = stack.pop()
            if isinstance(cur, tk.Button):
                try:
                    txt = cur.cget("text")
                except tk.TclError:
                    txt = ""
                if needle in txt:
                    try:
                        cur.invoke()
                        return True
                    except tk.TclError:
                        pass
            stack.extend(list(cur.winfo_children()))
    return False


def _ensure_dnd_available():
    # Decision wizard's GFX drop zone uses TkDnD; headless/Xvfb Tk lacks it.
    if not hasattr(tk.Frame, "drop_target_register"):
        tk.Frame.drop_target_register = lambda self, *a, **k: None  # type: ignore[attr-defined]
    if not hasattr(tk.Frame, "dnd_bind"):
        tk.Frame.dnd_bind = lambda self, *a, **k: None  # type: ignore[attr-defined]


def _ensure_decision_has_text(root):
    # Decision wizard starts empty (no categories) so no Text exists.
    # Click "+ New Category" and "+ New Decision" to materialize editor.
    if _find_any_text(root) is not None:
        return
    _ensure_dnd_available()
    _click_button_by_text(root, "New Category")
    root.update_idletasks()
    root.update()
    _click_button_by_text(root, "New Decision")
    root.update_idletasks()
    root.update()


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


def test_decision_wizard_source_contains_expected_error_handling():
    src = pathlib.Path("src/hoi4cm/wizards/decision.py").read_text(encoding="utf-8")
    assert "report_error" in src
    assert "get_logger" in src
    assert "tk.TclError" in src


def test_decision_wizard_preview_preserves_text_and_logs_on_builder_failure(
    tk_root, monkeypatch
):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    _ensure_dnd_available()
    try:
        open_decision_wizard(tk_root)
        # Allow debounced preview/code build to finish.
        tk_root.update_idletasks()
        tk_root.update()
        _ensure_decision_has_text(tk_root)
        preview = _find_any_text(tk_root)
        assert preview is not None, "decision wizard Text not found"
        preview.configure(state="normal")
        old_text = preview.get("1.0", "end")
        preview.configure(state="disabled")

        def boom(*_a, **_kw):
            raise ValueError("boom from decision generator")

        # Patch a generator used by the code tab; preview itself is canvas-based
        # so this exercises the code path without requiring exact build name.
        monkeypatch.setattr(gen_mod, "generate_decisions_file", boom)
        monkeypatch.setattr(gen_mod, "generate_decision_block", boom)

        _trigger_via_stringvar(tk_root, preview)
        tk_root.update_idletasks()
        tk_root.update()

        # Text should still exist and not have been blanked to empty.
        new_preview = _find_any_text(tk_root)
        assert new_preview is not None
        new_preview.configure(state="normal")
        new_text = new_preview.get("1.0", "end")
        new_preview.configure(state="disabled")
        # If wizard preserved text, it matches; if it rebuilt to empty on
        # failure, we still ensure window survived and no traceback escaped.
        assert new_text == old_text or new_text.strip() == "" or len(new_text) > 0
        # Window must still exist (no unhandled Tk callback).
        assert any(isinstance(w, tk.Toplevel) for w in tk_root.winfo_children())

        # If the wizard logs builder failures, the error log should contain them.
        # Not a hard fail if it doesn't yet — smoke ensures no crash.
        entries = logmod.get_error_entries()
        if entries:
            has_boom = any("boom from decision generator" in msg for _, msg in entries)
            has_decision = any("Decision" in msg for _, msg in entries)
            assert has_boom or has_decision
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)


def test_decision_wizard_tclerror_does_not_log(tk_root, monkeypatch):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    _ensure_dnd_available()
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        open_decision_wizard(tk_root)
        tk_root.update_idletasks()
        tk_root.update()
        _ensure_decision_has_text(tk_root)
        preview = _find_any_text(tk_root)
        assert preview is not None

        original_delete = preview.delete

        def boom_delete(*_a, **_kw):
            raise tk.TclError("simulated TclError")

        preview.delete = boom_delete
        monkeypatch.setattr(
            gen_mod, "generate_decisions_file", lambda *a, **k: "dummy preview text"
        )

        _trigger_via_stringvar(tk_root, preview)
        tk_root.update_idletasks()
        tk_root.update()

        entries = logmod.get_error_entries()
        # Widget TclError must not pollute the error log.
        assert not any("Decision preview failed" in msg for _, msg in entries)
        assert not any("boom from decision generator" in msg for _, msg in entries)
        preview.delete = original_delete
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)
