"""Filesystem helpers: default mod directory and tolerant file reading."""

import os
import sys

from .logger import get_logger

_log = get_logger("paths")

MAX_READ_BYTES = 32 * 1024 * 1024


def default_hoi4_mod_dir():
    base = os.path.join("Paradox Interactive", "Hearts of Iron IV", "mod")
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", base
        )
    elif sys.platform.startswith("linux"):
        return os.path.join(os.path.expanduser("~"), ".local", "share", base)
    return os.path.join(os.path.expanduser("~"), "Documents", base)


def read_file(path: str, max_bytes: int | None = MAX_READ_BYTES) -> str | None:
    """Read *path* as text, trying several encodings.

    Missing files return ``""``. Files that cannot be read or exceed
    *max_bytes* return ``None``. Pass ``max_bytes=None`` to disable the cap.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        size = None
    if max_bytes is not None and size is not None and size > max_bytes:
        _log.warning("skipping oversize file (%d bytes): %s", size, path)
        return None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc, errors="strict") as f:
                if max_bytes is None:
                    return f.read()
                data = f.read(max_bytes + 1)
                if len(data) > max_bytes:
                    _log.warning("skipping oversize/streaming file: %s", path)
                    return None
                return data
        except FileNotFoundError:
            return ""
        except OSError, ValueError, UnicodeDecodeError:
            pass
    return None


def autosave_path(name):
    """Return a per-user autosave path under ``~/.hoi4cm/autosave/``.

    Replaces the world-writable, fixed-name ``/tmp`` files the wizards used to
    autosave into (a local symlink-clobber vector on shared hosts). Creates the
    directory user-only if missing.
    """
    d = os.path.join(os.path.expanduser("~"), ".hoi4cm", "autosave")
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, name)
