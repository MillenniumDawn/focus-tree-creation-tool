"""Background worker infrastructure: run blocking work off the Tk thread.

Generalizes the ad hoc worker in ``ui/mod_loading.py`` (``_load_mod``'s
``threading.Thread`` + ``_safe_after`` pair) into a small, reusable shape:
``run_bg`` submits a zero-arg callable to a shared thread pool and marshals
the result (or exception) back onto the Tk thread.

Hard rules for anything that runs inside ``work`` (i.e. on a worker thread):

- Never touch Tk objects: no widgets, ``StringVar``/``BooleanVar``, canvas
  items, dialogs. Tkinter is not thread-safe.
- Never call ``MOD.get_image`` (or anything that constructs a
  ``PhotoImage``) -- that's Tk-thread-only.
- Never mutate ``App`` state (``self.focuses``, ``self._extra_trees``,
  ``self._shared_focuses``, ...). Read a snapshot taken on the Tk thread
  before submitting, compute against it, and hand the result to ``on_done``.
  All mutation happens in ``on_done``, which ``run_bg`` always runs on the
  Tk thread.

A worker is allowed to construct plain-data objects that aren't Tk-bound --
``Focus`` instances, ``ParsedFocusTree`` results, etc. -- since ``App`` only
adopts them once ``on_done`` inserts them into its own dicts/lists. Note that
``Focus.__init__`` bumps the shared ``Focus._next`` class counter; building
focuses on a worker thread is only safe because a ``progress_modal``'s
``grab_set()`` prevents the user from creating a focus (and bumping the same
counter) concurrently on the Tk thread.
"""

import tkinter as tk
import traceback
from concurrent.futures import Future
from types import SimpleNamespace

from hoi4cm.core.logger import add_error, get_logger
from hoi4cm.ui.lifecycle import ApplicationLifecycle, find_lifecycle
from hoi4cm.ui.theme import BG_DARK, BLUE, BORDER_G, TEXT, TEXT_DIM
from hoi4cm.ui.widgets import _safe_after

log = get_logger("tasks")

_default_lifecycle = ApplicationLifecycle()
_executor = None


def get_executor(owner=None):
    """Return the shared background executor, creating it on first use."""
    global _default_lifecycle, _executor
    lifecycle = find_lifecycle(owner)
    if lifecycle is not None:
        return lifecycle.executor
    if _executor is None:
        if not _default_lifecycle.accepting:
            _default_lifecycle = ApplicationLifecycle()
        _executor = _default_lifecycle.executor
    return _executor


def shutdown_executor():
    """Tear down the shared executor, if one was ever created. Idempotent.

    ``cancel_futures=True`` needs Python 3.9+, well under this project's
    3.14 floor. Pending
    (not-yet-started) work is dropped rather than waited on, so app close
    isn't blocked by a background parse.
    """
    global _executor
    if _executor is not None:
        _default_lifecycle.close()
        _executor = None


def run_bg(widget, work, on_done, on_error=None, *, scope="application"):
    """Run ``work`` on a background thread; marshal the outcome to ``widget``.

    ``work`` is a zero-arg callable. Callers that need progress reporting can
    close over a callable built with :func:`make_progress`.

    On success, ``on_done(result)`` runs on the Tk thread. On any exception
    from ``work``, it is logged and recorded via ``add_error`` so it reaches
    the in-app error log, and ``on_error(exc)`` (if given) runs on the Tk
    thread; otherwise the logged entry is the only trace.

    ``on_done`` (and ``on_error``) run exactly once, and only if ``widget``
    still exists by the time the result is ready. Exceptions raised inside
    ``on_done``/``on_error`` are not swallowed here -- they propagate out of
    the worker thread's job, same as an uncaught exception in any other Tk
    callback.

    Returns the submitted ``Future``. Production call sites can ignore it;
    it exists mainly so tests can wait for completion deterministically
    (``future.result(timeout=...)``) instead of sleeping.
    """

    lifecycle = find_lifecycle(widget)
    token = lifecycle.token(scope) if lifecycle is not None else None

    def schedule(callback):
        if lifecycle is not None:
            lifecycle.after(widget, 0, callback, token=token)
        else:
            _safe_after(widget, 0, callback)

    def _job():
        try:
            result = work()
        except Exception as exc:
            log.exception("background task failed")
            error_trace = traceback.format_exc()
            schedule(lambda error_trace=error_trace: add_error(error_trace))
            if on_error is not None:
                schedule(lambda exc=exc: on_error(exc))
            return
        schedule(lambda result=result: on_done(result))

    try:
        future = get_executor(widget).submit(_job)
        if lifecycle is not None and token is not None:
            lifecycle.track_future(future, token)
        return future
    except RuntimeError:
        future = Future()
        future.cancel()
        return future


def make_progress(widget, fn, *, scope="application"):
    """Return a callable safe to invoke from a worker thread.

    Calling the returned callable marshals ``fn(*args, **kwargs)`` onto the
    Tk thread via ``_safe_after``, in the order the calls were made.
    """

    lifecycle = find_lifecycle(widget)
    token = lifecycle.token(scope) if lifecycle is not None else None

    def _progress(*args, **kwargs):
        def callback():
            fn(*args, **kwargs)

        if lifecycle is not None:
            lifecycle.after(widget, 0, callback, token=token)
        else:
            _safe_after(widget, 0, callback)

    return _progress


def progress_modal(parent, title, *, determinate=True):
    """Open a small modal progress dialog; return a handle to drive it.

    Mirrors the Toplevel built inline in ``ui/mod_loading.py``'s
    ``_load_mod``: dark theme, ``grab_set()``, ``WM_DELETE_WINDOW`` blocked
    so the user can't dismiss it mid-task.

    The grab is load-bearing, not cosmetic: it is what makes it safe for a
    worker to compute against a snapshot of ``self.focuses`` without the
    user mutating the live dict concurrently on the Tk thread.

    Returns a ``SimpleNamespace`` with:
      - ``set_text(msg)``: update the status label.
      - ``set_fraction(frac)``: move a determinate bar to ``frac`` (0.0-1.0).
      - ``close()``: release the grab and destroy the window.
    """
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=BG_DARK)
    win.geometry("420x140")
    win.resizable(False, False)
    win.grab_set()
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    tk.Label(
        win,
        text=title,
        bg=BG_DARK,
        fg=TEXT,
        font=("Helvetica", 10, "bold"),
        pady=12,
    ).pack()
    status_lbl = tk.Label(win, text="", bg=BG_DARK, fg=TEXT_DIM, font=("Helvetica", 9))
    status_lbl.pack()
    bar_frame = tk.Frame(win, bg=BORDER_G, height=6, width=380)
    bar_frame.pack(pady=8)
    bar_fill = tk.Frame(bar_frame, bg=BLUE, height=6, width=0 if determinate else 40)
    bar_fill.place(x=0, y=0, height=6)

    def set_text(msg):
        status_lbl.config(text=msg)
        win.update_idletasks()

    def set_fraction(frac):
        frac = max(0.0, min(1.0, frac))
        bar_fill.place_configure(width=int(frac * 380))
        win.update_idletasks()

    def close():
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    return SimpleNamespace(
        set_text=set_text,
        set_fraction=set_fraction,
        close=close,
    )


__all__ = [
    "get_executor",
    "make_progress",
    "progress_modal",
    "run_bg",
    "shutdown_executor",
]
