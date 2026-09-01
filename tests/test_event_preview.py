"""Event canvas and export error coverage.

A real form apply refreshes the canvas preview. A failed export then proves
that rendered text remains intact while the handled error is logged. The
canvas preview does not use the file generator. Headless behavior lives in
``test_wizard_generators_event.py``.
"""

import tkinter as tk

import hoi4cm.core.logger as logmod
import hoi4cm.wizards._generators as gen_mod
from hoi4cm.wizards.event import open_event_wizard


def _canvas_texts(root):
    found = []
    stack = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Canvas):
            for item in cur.find_all():
                if cur.type(item) == "text":
                    found.append(cur.itemcget(item, "text"))
        stack.extend(cur.winfo_children())
    return found


def _entry_by_value(root, value):
    stack = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Entry) and cur.get() == value:
            return cur
        stack.extend(cur.winfo_children())
    return None


def _button_by_text(root, needle):
    stack = [root]
    while stack:
        cur = stack.pop()
        if isinstance(cur, tk.Button) and needle in cur.cget("text"):
            return cur
        stack.extend(cur.winfo_children())
    return None


def _flush_after(root):
    root.after(120, root.quit)
    root.mainloop()


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


def test_event_export_failure_preserves_canvas_and_logs(tk_root, tmp_path, monkeypatch):
    try:
        tk_root.grab_release()
    except tk.TclError:
        pass
    orig_cb = logmod._error_callback
    logmod.clear_errors()
    logmod.set_error_callback(None)
    try:
        monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
        open_event_wizard(tk_root)
        _flush_after(tk_root)
        title_entry = _entry_by_value(tk_root, "My Event Title")
        assert title_entry is not None
        title_entry.delete(0, "end")
        title_entry.insert(0, "Changed event title")
        apply_button = _button_by_text(tk_root, "Apply Changes")
        assert apply_button is not None
        apply_button.invoke()
        _flush_after(tk_root)
        before_text = _canvas_texts(tk_root)
        assert "CHANGED EVENT TITLE" in before_text

        def boom(*_args, **_kwargs):
            raise ValueError("boom from event generator")

        monkeypatch.setattr(gen_mod, "generate_events_txt", boom)
        export_path = str(tmp_path / "event-preview.txt")
        monkeypatch.setattr(
            "tkinter.filedialog.asksaveasfilename", lambda **_kwargs: export_path
        )
        export_button = _button_by_text(tk_root, "Export .txt")
        assert export_button is not None
        export_button.invoke()
        tk_root.update_idletasks()

        assert _canvas_texts(tk_root) == before_text
        entries = logmod.get_error_entries()
        assert entries
        assert any("boom from event generator" in msg for _, msg in entries)
    finally:
        logmod.clear_errors()
        logmod.set_error_callback(orig_cb)
        _cleanup_toplevels(tk_root)
