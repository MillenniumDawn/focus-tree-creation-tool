"""Reusable Tk widgets: dark tooltip, scrollable dropdown, safe ``after()``.

These helpers were inlined as closures in the monolith — they're now plain
functions/classes here so the App and every wizard can share them.
"""

import time
import tkinter as tk
import tkinter.font as tkfont

from hoi4cm.ui.theme import BG_CARD, BORDER_G, SEL_BG, TEXT

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


# ── Scrollable dropdown ─────────────────────────────────────────
class ScrollableDropdown(tk.Frame):
    """An OptionMenu replacement that scales to hundreds of entries.

    Native Tk menus cannot scroll: a category with 150+ modifiers posts a
    menu taller than the screen, entries below the bottom are unreachable
    except via keyboard, and a wheel event unposts the menu while selecting
    whatever is under the pointer (issue #72). This widget instead posts a
    borderless popup holding a scrollable Listbox, sized to the remaining
    screen space and flipped above the anchor when there is more room up
    there. The wheel scrolls, arrows move the highlight, Return commits,
    Escape or focus loss closes without selecting.

    ``items`` is a list of ``(value, label)`` pairs. ``variable`` is the
    StringVar holding the selected value; writing it from outside updates
    the displayed label.
    """

    POPUP_MARGIN = 8  # px gap between popup and screen edges
    ROW_PAD = 3  # extra px per listbox row
    MIN_ROWS = 1
    MAX_ROWS = 40

    def __init__(
        self,
        master,
        variable=None,
        items=None,
        width=26,
        bg=BG_CARD,
        fg=TEXT,
        activebg=SEL_BG,
        font=("Helvetica", 9),
    ):
        super().__init__(master)
        self._items = list(items or [])
        self._var = variable if variable is not None else tk.StringVar(master=self)
        self._width = width
        self._bg = bg
        self._fg = fg
        self._activebg = activebg
        self._font = font
        self._popup: tk.Toplevel | None = None
        self._lb: tk.Listbox | None = None
        self._closed_at = 0.0
        self._trace_id = None
        self.btn = tk.Button(
            self,
            text=self._display(self._var.get()),
            command=self._toggle,
            bg=bg,
            fg=fg,
            activebackground=activebg,
            font=font,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER_G,
            anchor="w",
            width=width,
            cursor="hand2",
            padx=6,
        )
        self.btn.pack(fill="x", expand=True)
        self._register_trace()
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _display(self, value):
        for v, label in self._items:
            if v == value:
                return f"{label}  ▾"
        return f"{value}  ▾"

    def _register_trace(self):
        if self._trace_id is None:
            self._trace_id = self._var.trace_add("write", self._on_var_write)

    def _on_var_write(self, *_):
        if not self.winfo_exists():
            return
        self.btn.config(text=self._display(self._var.get()))

    def _on_destroy(self, *_):
        if self._trace_id is not None:
            try:
                self._var.trace_remove("write", self._trace_id)
            except tk.TclError:
                pass
            self._trace_id = None
        self._close_popup()

    def _toggle(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._close_popup()
            return
        # The click that landed here first moved focus off the popup and
        # closed it via FocusOut; don't immediately reopen it.
        if time.monotonic() - self._closed_at < 0.15:
            return
        self._open_popup()

    def _open_popup(self):
        self._close_popup()
        if not self._items:
            return
        pop = tk.Toplevel(self)
        self._popup = pop
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg=BORDER_G)
        lb = tk.Listbox(
            pop,
            bg=self._bg,
            fg=self._fg,
            selectbackground=self._activebg,
            selectforeground=TEXT,
            font=self._font,
            relief="flat",
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            width=self._width,
        )
        sb = tk.Scrollbar(pop, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        for _v, label in self._items:
            lb.insert("end", label)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._lb = lb

        def _wheel(e):
            if e.delta:
                lb.yview_scroll(int(-e.delta / 120), "units")
            elif e.num == 4:
                lb.yview_scroll(-1, "units")
            elif e.num == 5:
                lb.yview_scroll(1, "units")
            return "break"

        def _move(delta):
            sel = lb.curselection()
            idx = sel[0] if sel else -1 if delta > 0 else len(self._items)
            nxt = max(0, min(len(self._items) - 1, idx + delta))
            lb.selection_clear(0, "end")
            lb.selection_set(nxt)
            lb.see(nxt)
            return "break"

        lb.bind("<ButtonRelease-1>", lambda e: self._commit())
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            lb.bind(ev, _wheel)
            pop.bind(ev, _wheel)
        lb.bind("<Up>", lambda e: _move(-1))
        lb.bind("<Down>", lambda e: _move(1))
        lb.bind("<Return>", lambda e: self._commit())
        lb.bind("<KP_Enter>", lambda e: self._commit())
        lb.bind("<Escape>", lambda e: self._close_popup())
        pop.bind("<Escape>", lambda e: self._close_popup())
        pop.bind("<FocusOut>", self._on_popup_focus_out)

        # Size to the remaining screen space, flipping above the anchor
        # when there is more room there than below it.
        self.btn.update_idletasks()
        row_h = tkfont.Font(font=self._font).metrics("linespace") + self.ROW_PAD
        screen_h = self.winfo_screenheight()
        anchor_y = self.btn.winfo_rooty()
        below = screen_h - anchor_y - self.btn.winfo_height() - self.POPUP_MARGIN
        above = anchor_y - self.POPUP_MARGIN
        wanted = min(len(self._items), self.MAX_ROWS)
        rows_below = min(wanted, max(self.MIN_ROWS, int(below // row_h)))
        rows_above = min(wanted, max(self.MIN_ROWS, int(above // row_h)))
        if rows_below >= rows_above:
            rows, y = rows_below, anchor_y + self.btn.winfo_height()
        else:
            rows, y = rows_above, None
        lb.configure(height=rows)
        pop.update_idletasks()
        if y is None:
            y = max(self.POPUP_MARGIN, anchor_y - pop.winfo_reqheight())
        x = self.btn.winfo_rootx()
        x = max(
            self.POPUP_MARGIN,
            min(x, self.winfo_screenwidth() - pop.winfo_reqwidth() - self.POPUP_MARGIN),
        )
        pop.geometry(f"+{x}+{y}")

        cur = self._var.get()
        for i, (v, _label) in enumerate(self._items):
            if v == cur:
                lb.selection_set(i)
                lb.see(i)
                break
        lb.focus_force()

    def _commit(self):
        if self._lb is None:
            return
        sel = self._lb.curselection()
        if sel:
            self._var.set(self._items[sel[0]][0])
        self._close_popup()

    def _close_popup(self):
        pop = self._popup
        self._popup = None
        self._lb = None
        if pop is not None:
            try:
                if pop.winfo_exists():
                    pop.destroy()
            except tk.TclError:
                pass

    def _on_popup_focus_out(self, _e):
        pop = self._popup
        if pop is None:
            return
        try:
            focused = pop.focus_get()
        except tk.TclError:
            focused = None
        if focused is None or not (
            str(focused) == str(pop) or str(focused).startswith(str(pop) + ".")
        ):
            self._close_popup()
            self._closed_at = time.monotonic()


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
