"""Reusable Tk widgets: dark tooltip, safe ``after()``, and widget factories.

The App class and every wizard construct the same handful of widgets in the
same dark theme. These helpers were inlined as closures in the monolith —
they're now plain functions here so all wizards can share them.

The widget factories (``mk_btn`` / ``mk_lbl`` / ``mk_entry`` / ``mk_hsep``)
match the look used throughout the App and the existing wizards. They accept
the standard ``bg`` / ``fg`` overrides so call sites can drop in a different
panel colour without rewriting the recipe.
"""

import tkinter as tk

from hoi4cm.ui.theme import (
    BG_CARD,
    BG_PANEL,
    BLUE,
    BORDER_G,
    TEXT,
    TEXT_DIM,
)


# ── Safe after() wrappers ────────────────────────────────────────
# Guard against the Python 3.14 _tclCommands bug where scheduling a callback
# after a widget has been destroyed raises AttributeError.
def _safe_after(widget, ms, fn):
    """Schedule *fn* after *ms* milliseconds, only if *widget* still exists."""

    def guarded():
        try:
            if widget.winfo_exists():
                fn()
        except Exception:
            pass

    try:
        widget.after(ms, guarded)
    except Exception:
        pass


def _safe_after_idle(widget, fn):
    """Schedule *fn* via ``after_idle``, only if *widget* still exists."""

    def guarded():
        try:
            if widget.winfo_exists():
                fn()
        except Exception:
            pass

    try:
        widget.after_idle(guarded)
    except Exception:
        pass


# ── Dark tooltip ─────────────────────────────────────────────────
class Tooltip:
    """Show a dark tooltip after a short hover delay (1.2s by default)."""

    DELAY = 1200  # ms before showing
    BG = "#161b22"
    FG = "#c9d1d9"
    BORDER = "#3b82f6"

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._job = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<Button>", self._cancel, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._job = self.widget.after(self.DELAY, self._show)

    def _cancel(self, _=None):
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def _show(self):
        if self._tip:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        outer = tk.Frame(tw, bg=self.BORDER, bd=1)
        outer.pack()
        tk.Label(
            outer,
            text=self.text,
            bg=self.BG,
            fg=self.FG,
            font=("Helvetica", 9),
            padx=10,
            pady=5,
            justify="left",
            wraplength=260,
        ).pack()
        tw.update_idletasks()
        tw.wm_geometry(f"+{x - tw.winfo_width() // 2}+{y}")


# ── Widget factories ─────────────────────────────────────────────
def mk_btn(
    parent,
    text,
    cmd=None,
    fg=None,
    bg=None,
    font_size=9,
    bold=True,
    padx=10,
    pady=4,
    tip=None,
    **kwargs,
):
    """Flat hand-cursor button. Returns the ``Button`` widget."""
    b = tk.Button(
        parent,
        text=text,
        command=cmd or (lambda: None),
        bg=bg or BG_CARD,
        fg=fg or TEXT,
        activebackground=BORDER_G,
        activeforeground=TEXT,
        font=("Helvetica", font_size, "bold" if bold else "normal"),
        relief="flat",
        padx=padx,
        pady=pady,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=BORDER_G,
        bd=0,
        **kwargs,
    )
    if tip:
        Tooltip(b, tip)
    return b


def mk_lbl(
    parent,
    text,
    fg=None,
    bg=None,
    font_size=9,
    bold=False,
    dim=False,
    anchor="w",
    padx=6,
    pady=2,
    **kwargs,
):
    """Standard label, dim or normal."""
    return tk.Label(
        parent,
        text=text,
        bg=bg or BG_PANEL,
        fg=fg or (TEXT_DIM if dim else TEXT),
        font=("Helvetica", font_size, "bold" if bold else "normal"),
        anchor=anchor,
        padx=padx,
        pady=pady,
        **kwargs,
    )


def mk_entry(parent, var, width=None, **kwargs):
    """Standard dark entry bound to a ``StringVar``."""
    kw = dict(
        textvariable=var,
        bg=BG_CARD,
        fg=TEXT,
        insertbackground=BLUE,
        font=("Helvetica", 10),
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER_G,
    )
    if width:
        kw["width"] = width
    kw.update(kwargs)
    return tk.Entry(parent, **kw)


def mk_hsep(parent, padx=6, pady=4):
    """1px horizontal separator."""
    f = tk.Frame(parent, bg=BORDER_G, height=1)
    f.pack(fill="x", padx=padx, pady=pady)
    return f


__all__ = [
    "Tooltip",
    "_safe_after",
    "_safe_after_idle",
    "mk_btn",
    "mk_lbl",
    "mk_entry",
    "mk_hsep",
]
