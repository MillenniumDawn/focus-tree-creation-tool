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


def read_file_with_encoding(
    path: str, max_bytes: int | None = MAX_READ_BYTES
) -> tuple[str | None, str | None]:
    """Read *path* once as text and return ``(text, encoding)``.

    Missing files return ``("", None)`` for compatibility with ``read_file``.
    Unreadable or oversized files return ``(None, None)``. Existing empty files
    return an encoding, so callers can distinguish them from missing files.
    The cap is enforced on bytes, including when stat is unavailable or the
    file changes while it is being read.
    """
    try:
        with open(path, "rb") as stream:
            if max_bytes is None:
                data = stream.read()
            else:
                data = stream.read(max_bytes + 1)
                if len(data) > max_bytes:
                    _log.warning("skipping oversize/streaming file: %s", path)
                    return None, None
    except FileNotFoundError:
        return "", None
    except OSError, ValueError:
        return None, None

    if data.startswith(b"\xef\xbb\xbf"):
        try:
            return data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def read_file(path: str, max_bytes: int | None = MAX_READ_BYTES) -> str | None:
    """Read *path* as text, trying several encodings.

    Missing files return ``""``. Files that cannot be read or exceed
    *max_bytes* return ``None``. Pass ``max_bytes=None`` to disable the cap.
    """
    return read_file_with_encoding(path, max_bytes)[0]


def newline_style(text: str) -> str:
    """Return the first newline style in *text*, defaulting to LF."""
    for index, char in enumerate(text):
        if char == "\r":
            return "\r\n" if index + 1 < len(text) and text[index + 1] == "\n" else "\r"
        if char == "\n":
            return "\n"
    return "\n"


def convert_newlines(text: str, style: str) -> str:
    """Convert line endings in generated *text* to *style*."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", style)


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
