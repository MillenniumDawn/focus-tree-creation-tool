"""Decision code-tab and export error coverage.

The code tab is refreshed through its real controls, then a failed export
proves the existing code remains intact while the handled error is logged.
The decision canvas preview does not use the file generator. Headless
behavior lives in ``test_wizard_generators_decision.py``.
"""

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


def _find_code_text(root):
    return _find_text(root, "#080b10")


def _button_by_text(root, needle):
    stack = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and needle in cur.cget("text"):
            return cur
        stack.extend(cur.winfo_children())
    return None


def _click_button_by_text(root, needle):
    button = _button_by_text(root, needle)
    if button is None:
        return False
    button.invoke()
    return True


def _flush_after(root):
    root.after(120, root.quit)
    root.mainloop()


def _ensure_dnd_available():
    # Decision wizard's GFX drop zone uses TkDnD; headless/Xvfb Tk lacks it.
    if not hasattr(tk.Frame, "drop_target_register"):
        tk.Frame.drop_target_register = lambda self, *a, **k: None  # type: ignore[attr-defined]
    if not hasattr(tk.Frame, "dnd_bind"):
        tk.Frame.dnd_bind = lambda self, *a, **k: None  # type: ignore[attr-defined]


def _ensure_decision_has_text(root):
    """Create a decision so the code preview has something to render."""
    _ensure_dnd_available()
    if _button_by_text(root, "New Category") is not None:
        _click_button_by_text(root, "New Category")
        root.update_idletasks()
    if _button_by_text(root, "New Decision") is not None:
        _click_button_by_text(root, "New Decision")
        root.update_idletasks()


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


def test_decision_export_failure_preserves_code_tab_and_logs(
    tk_root, tmp_path, monkeypatch
):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
    _ensure_dnd_available()
    try:
        open_decision_wizard(tk_root)
        _ensure_decision_has_text(tk_root)
        assert _click_button_by_text(tk_root, "Code")
        _flush_after(tk_root)
        preview = _find_code_text(tk_root)
        assert preview is not None, "decision code preview not found"
        old_text = preview.get("1.0", "end")
        assert old_text.strip()

        # Refresh through the actual tab control before forcing the generator
        # to fail. This proves the text came from the production preview path.
        assert _click_button_by_text(tk_root, "Refresh")
        _flush_after(tk_root)
        preview = _find_code_text(tk_root)
        assert preview is not None
        assert preview.get("1.0", "end") == old_text

        def boom(*_args, **_kwargs):
            raise ValueError("boom from decision generator")

        monkeypatch.setattr(gen_mod, "generate_decisions_file", boom)
        export_path = str(tmp_path / "decision-preview.txt")
        monkeypatch.setattr(
            "tkinter.filedialog.asksaveasfilename", lambda **_kwargs: export_path
        )
        assert _click_button_by_text(tk_root, "Export .txt")
        tk_root.update_idletasks()

        assert preview.winfo_exists()
        assert preview.get("1.0", "end") == old_text
        entries = logmod.get_error_entries()
        assert entries
        assert any("boom from decision generator" in msg for _, msg in entries)
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)
