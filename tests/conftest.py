"""Shared Tk fixtures with import-time user-home isolation."""

import atexit
import gc
import logging
import os
import sys
import tempfile
import types

import pytest

# Isolate import-time app state before pytest collects test modules.
_HOME_ENV_NAMES = ("HOME", "USERPROFILE", "XAUTHORITY")
_ORIGINAL_HOME_ENV = {
    name: os.environ[name] for name in _HOME_ENV_NAMES if name in os.environ
}
_ORIGINAL_USER_HOME = os.path.abspath(os.path.expanduser("~"))
if "XAUTHORITY" not in os.environ:
    xauthority = os.path.join(_ORIGINAL_USER_HOME, ".Xauthority")
    if os.path.exists(xauthority):
        os.environ["XAUTHORITY"] = xauthority


def _new_isolated_home() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="hoi4cm-pytest-home-")


_ISOLATED_HOME_DIR = _new_isolated_home()
_ISOLATED_HOME_ROOT = _ISOLATED_HOME_DIR.name
_ISOLATED_HOME: str | None = _ISOLATED_HOME_ROOT
os.environ["HOME"] = _ISOLATED_HOME_ROOT
if sys.platform == "win32":
    os.environ["USERPROFILE"] = _ISOLATED_HOME_ROOT


def _cleanup_isolated_home() -> None:
    """Restore the home environment and release the temporary directory."""
    global _ISOLATED_HOME
    home_dir = _ISOLATED_HOME_DIR
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
        home_dir.cleanup()
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


tk: types.ModuleType | None
try:
    import tkinter as tk
except ImportError:
    tk = None

TclError = tk.TclError if tk is not None else RuntimeError


def _hidden() -> bool:
    return os.environ.get("HOI4CM_SHOW_TK") != "1"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "visible_tk: test needs its windows mapped (real geometry, real events)",
    )


@pytest.fixture(autouse=True)
def hide_tk_windows(request, monkeypatch):
    """Withdraw every Toplevel the test creates.

    The widget tests need a display, but almost none of them need the windows
    drawn; left alone the suite maps a thousand roots and dialogs over
    whatever else is on screen. `grab_set` refuses to run on a window that is
    not viewable, so it becomes a no-op while the windows are hidden. Tests
    that measure geometry or generate real pointer events opt out with
    `@pytest.mark.visible_tk`, and `HOI4CM_SHOW_TK=1` opts the whole run out.
    """
    if tk is None or not _hidden() or request.node.get_closest_marker("visible_tk"):
        return

    toplevel_init = tk.Toplevel.__init__
    grab_set = tk.Misc.grab_set

    def hidden_init(self, *args, **kwargs):
        toplevel_init(self, *args, **kwargs)
        self.withdraw()

    def optional_grab_set(self):
        try:
            grab_set(self)
        except TclError:
            pass

    monkeypatch.setattr(tk.Toplevel, "__init__", hidden_init)
    monkeypatch.setattr(tk.Misc, "grab_set", optional_grab_set)


@pytest.fixture
def tk_root(request):
    """A live Tk root, destroyed after the test.

    Skips when no display is reachable (or tkinter itself is missing), so the
    suite still runs on a headless box. `HOI4CM_REQUIRE_TK=1` (set by the CI
    test job) turns that skip into a failure, so a broken Xvfb or missing
    python3-tk shows up as a red build rather than a green one with every Tk
    test silently skipped.
    """
    if tk is None:
        if os.environ.get("HOI4CM_REQUIRE_TK") == "1":
            pytest.fail("HOI4CM_REQUIRE_TK=1 but tkinter is unavailable")
        pytest.skip("tkinter is unavailable")
    try:
        root = tk.Tk()
    except TclError as exc:
        if os.environ.get("HOI4CM_REQUIRE_TK") == "1":
            pytest.fail(f"HOI4CM_REQUIRE_TK=1 but Tk is unavailable: {exc}")
        pytest.skip("Tk display is unavailable")
    if _hidden() and not request.node.get_closest_marker("visible_tk"):
        root.withdraw()
    try:
        yield root
    finally:
        root.destroy()
        gc.collect()
