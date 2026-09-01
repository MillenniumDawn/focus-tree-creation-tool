"""Shared fixtures.

Two things need to be shared: every widget test needs a Tk root, and the
"no display" skip has to be loud in CI (which runs under Xvfb) instead of
quietly dropping every widget test from the run. The rest of this module
keeps those windows off the screen on a machine that has a real desktop.
"""

import gc
import os
import types

import pytest

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
