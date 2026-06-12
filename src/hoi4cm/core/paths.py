"""Filesystem helpers: default mod directory and tolerant file reading."""
import os
import sys


def default_hoi4_mod_dir():
    base = os.path.join("Paradox Interactive", "Hearts of Iron IV", "mod")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", base)
    elif sys.platform.startswith("linux"):
        return os.path.join(os.path.expanduser("~"), ".local", "share", base)
    return os.path.join(os.path.expanduser("~"), "Documents", base)


def read_file(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc, errors="replace") as f:
                return f.read()
        except Exception:
            pass
    return ""
