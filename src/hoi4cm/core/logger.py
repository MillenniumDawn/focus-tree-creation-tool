"""Logging + uncaught-error capture for the HOI4 Content Maker.

This is the base logging module for the app. It configures the ``HOI4CM``
logger with a console handler and a rotating file handler, exposes namespaced
child loggers via :func:`get_logger`, and keeps an in-memory buffer of captured
errors that the in-app error log reads from.

Handlers are attached directly to the ``HOI4CM`` logger with ``propagate=False``
(no ``logging.basicConfig``), so each line logs exactly once.
"""

import datetime
import logging
import os
import sys
import tkinter as tk
from logging.handlers import RotatingFileHandler

_LOG_NAME = "HOI4CM"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"
_LOG_DIR = os.path.join(os.path.expanduser("~"), ".hoi4cm")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

log = logging.getLogger(_LOG_NAME)


def _configure():
    """Attach handlers to the HOI4CM logger once. Safe to call repeatedly."""
    if log.handlers:
        return

    log.setLevel(logging.DEBUG)
    log.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATEFMT))
    log.addHandler(console)

    # File logging is best-effort: a read-only HOME must not crash startup.
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        fileh = RotatingFileHandler(
            _LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fileh.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATEFMT))
        log.addHandler(fileh)
    except (OSError, ValueError, RuntimeError) as exc:
        log.warning("File logging disabled: %s", exc)


_configure()


def get_logger(name):
    """Return a namespaced child logger, e.g. ``HOI4CM.<name>``."""
    return log.getChild(name)


def log_startup():
    log.info("=== HOI4 Content Maker starting ===")
    log.info("Python %s", sys.version)
    log.info("Platform: %s", sys.platform)
    log.info("DISPLAY=%s", os.environ.get("DISPLAY", "(unset)"))


# ── In-memory error buffer ───────────────────────────────────────────
# Single shared list so the excepthook and the GUI error log read the same
# entries. Entries are (HH:MM:SS, message) tuples — the shape the Tk viewer
# expects. The core is the sole writer.
_error_entries: list[tuple[str, str]] = []
_error_callback = None


def _timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def add_error(msg):
    """Record an error in the buffer and notify the GUI callback. Returns count."""
    _error_entries.append((_timestamp(), msg.strip()))
    count = len(_error_entries)
    if _error_callback is not None:
        try:
            _error_callback(count)
        except tk.TclError, RuntimeError, AttributeError, ValueError, TypeError:
            pass
    return count


def get_error_entries():
    """Return the live buffer list (same object every call)."""
    return _error_entries


def clear_errors():
    """Empty the buffer in place (keeps the list identity)."""
    _error_entries.clear()


def set_error_callback(fn):
    """Register a callback invoked with the new error count after each add_error."""
    global _error_callback
    _error_callback = fn


_excepthook_installed = False


def install_excepthook():
    """Capture uncaught exceptions into the buffer, then chain to the prior hook."""
    global _excepthook_installed
    if _excepthook_installed:
        return
    import traceback as _tb

    _prev_hook = sys.excepthook

    def _hook(exc_type, exc_val, exc_tb):
        msg = "".join(_tb.format_exception(exc_type, exc_val, exc_tb))
        add_error(msg)
        log.error("Uncaught exception:\n%s", msg)
        _prev_hook(exc_type, exc_val, exc_tb)

    sys.excepthook = _hook
    _excepthook_installed = True
