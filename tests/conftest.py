"""Shared fixtures.

Only one thing needs to be shared: every widget test needs a Tk root, and
the "no display" skip has to be loud in CI (which runs under Xvfb) instead
of quietly dropping every widget test from the run.
"""

import os
import tkinter as tk

import pytest


@pytest.fixture
def tk_root():
    """A live Tk root, destroyed after the test.

    Skips when no display is reachable, so the suite still runs on a
    headless box. `HOI4CM_REQUIRE_TK=1` (set by the CI test job) turns that
    skip into a failure, so a broken Xvfb shows up as a red build rather
    than a green one with every Tk test silently skipped.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("HOI4CM_REQUIRE_TK") == "1":
            pytest.fail(f"HOI4CM_REQUIRE_TK=1 but Tk is unavailable: {exc}")
        pytest.skip("Tk display is unavailable")
    try:
        yield root
    finally:
        root.destroy()
