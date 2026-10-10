"""Widget-tree helpers shared by the Tk dialog and wizard tests."""

from __future__ import annotations

import tkinter as tk


def new_toplevels(before: set[tk.Misc], root: tk.Misc) -> list[tk.Toplevel]:
    return [
        w
        for w in root.winfo_children()
        if w not in before and isinstance(w, tk.Toplevel)
    ]


def destroy_toplevels(wins: list[tk.Toplevel], root: tk.Misc) -> None:
    for w in wins:
        try:
            w.grab_release()
        except Exception:
            pass
        try:
            w.destroy()
        except Exception:
            pass
    try:
        root.update()
    except Exception:
        pass


def release_grab(root: tk.Misc) -> None:
    try:
        root.grab_release()
    except tk.TclError:
        pass


def cleanup_toplevels(root: tk.Misc) -> None:
    release_grab(root)
    for w in list(root.winfo_children()):
        if isinstance(w, tk.Toplevel):
            try:
                w.destroy()
            except tk.TclError:
                pass
    root.update_idletasks()


def collect_texts(win: tk.Misc) -> list[str]:
    texts: list[str] = []
    stack: list[tk.Misc] = [win]
    while stack:
        cur = stack.pop()
        try:
            texts.append(cur.cget("text"))
        except Exception:
            pass
        try:
            stack.extend(cur.winfo_children())
        except Exception:
            pass
    return texts


def find_text(root: tk.Misc, bg: str | None = None) -> tk.Text | None:
    found: list[tk.Text] = []

    def walk(w: tk.Misc) -> None:
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


def key_release_on_other_texts(root: tk.Misc, preview: tk.Text) -> None:
    for w in root.winfo_children():
        stack: list[tk.Misc] = [w]
        while stack:
            cur = stack.pop()
            if isinstance(cur, tk.Text) and cur is not preview:
                try:
                    cur.event_generate("<KeyRelease>")
                except tk.TclError:
                    pass
            stack.extend(cur.winfo_children())


def trigger_preview_refresh(root: tk.Misc, preview: tk.Text) -> None:
    """Set a traced Entry variable; fall back to a key release on another Text."""
    triggered = False
    for w in root.winfo_children():
        stack: list[tk.Misc] = [w]
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
        key_release_on_other_texts(root, preview)
