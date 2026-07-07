"""Reusable Tk widgets: dark tooltip and safe ``after()`` wrappers.

These helpers were inlined as closures in the monolith — they're now plain
functions here so the App and every wizard can share them.
"""

import tkinter as tk

# ── Safe after() wrappers ────────────────────────────────────────
# Guard only a destroyed widget (TclError, or AttributeError from the
# Python 3.14 _tclCommands bug) -- not exceptions from *fn* itself.
_DESTROYED_WIDGET_ERRORS = (AttributeError, tk.TclError)


def _safe_after(widget, ms, fn):
    """Schedule *fn* after *ms* milliseconds, only if *widget* still exists."""

    def guarded():
        try:
            exists = widget.winfo_exists()
        except _DESTROYED_WIDGET_ERRORS:
            return
        if exists:
            fn()

    try:
        widget.after(ms, guarded)
    except _DESTROYED_WIDGET_ERRORS:
        pass


def _safe_after_idle(widget, fn):
    """Schedule *fn* via ``after_idle``, only if *widget* still exists."""

    def guarded():
        try:
            exists = widget.winfo_exists()
        except _DESTROYED_WIDGET_ERRORS:
            return
        if exists:
            fn()

    try:
        widget.after_idle(guarded)
    except _DESTROYED_WIDGET_ERRORS:
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


__all__ = [
    "Tooltip",
    "_safe_after",
    "_safe_after_idle",
]
