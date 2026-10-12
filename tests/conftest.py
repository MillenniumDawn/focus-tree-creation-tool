"""Import-time user-home isolation and a headless default for every test."""

import atexit
import logging
import os
import sys
import tempfile
import tkinter as tk

import pytest

# Isolate import-time app state before pytest collects test modules.
_HOME_ENV_NAMES = ("HOME", "USERPROFILE")
_ORIGINAL_HOME_ENV = {
    name: os.environ[name] for name in _HOME_ENV_NAMES if name in os.environ
}


def _new_isolated_home() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="hoi4cm-pytest-home-")


_ISOLATED_HOME_DIR = _new_isolated_home()
_ISOLATED_HOME: str | None = _ISOLATED_HOME_DIR.name
os.environ["HOME"] = _ISOLATED_HOME_DIR.name
if sys.platform == "win32":
    os.environ["USERPROFILE"] = _ISOLATED_HOME_DIR.name


def _cleanup_isolated_home() -> None:
    """Restore the home environment and release the temporary directory."""
    global _ISOLATED_HOME
    if _ISOLATED_HOME is None:
        return

    try:
        app_logger = logging.getLogger("HOI4CM")
        for handler in list(app_logger.handlers):
            if isinstance(handler, logging.FileHandler):
                app_logger.removeHandler(handler)
                try:
                    handler.close()
                except OSError, ValueError:
                    pass
        _ISOLATED_HOME_DIR.cleanup()
    finally:
        for name in _HOME_ENV_NAMES:
            original = _ORIGINAL_HOME_ENV.get(name)
            if original is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = original
        _ISOLATED_HOME = None


atexit.register(_cleanup_isolated_home)


def pytest_unconfigure(config):
    """Restore the caller's home after pytest has finished the session."""
    _cleanup_isolated_home()


@pytest.fixture(autouse=True)
def forbid_tk(request, monkeypatch):
    """Fail any test that builds a Tk root unless it is marked `tk`."""
    if request.node.get_closest_marker("tk"):
        return

    def forbidden_root(*args, **kwargs):
        pytest.fail("Tk construction is forbidden outside tests marked `tk`")

    monkeypatch.setattr(tk.Tk, "__init__", forbidden_root)
