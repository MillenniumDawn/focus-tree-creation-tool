"""Import-time user-home isolation and a headless default for every test."""

import atexit
import logging
import os
import sys
import tempfile
import tkinter as tk
from collections.abc import Iterator
from typing import Any

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


def _capture_mutable_state(value: Any) -> Any:
    """Capture built-in mutable containers without copying opaque UI objects."""
    if isinstance(value, dict):
        contents = [(key, _capture_mutable_state(item)) for key, item in value.items()]
        return ("dict", value, contents)
    if isinstance(value, list):
        return ("list", value, [_capture_mutable_state(item) for item in value])
    if isinstance(value, set):
        return ("set", value, set(value))
    return ("value", value)


def _restore_mutable_state(state: Any) -> Any:
    kind, original, *contents = state
    if kind == "dict":
        original.clear()
        original.update(
            (key, _restore_mutable_state(item)) for key, item in contents[0]
        )
    elif kind == "list":
        original[:] = [_restore_mutable_state(item) for item in contents[0]]
    elif kind == "set":
        original.clear()
        original.update(contents[0])
    return original


def _capture_mod_state(mod: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Snapshot MOD's attributes and mutable state while retaining live objects."""
    from hoi4cm.core.lru import LRUCache
    from hoi4cm.mod.graphics_catalog import GraphicsCatalog

    attrs = dict(mod.__dict__)
    states = {name: _capture_mutable_state(value) for name, value in attrs.items()}
    catalog = attrs.get("graphics_catalog")
    if isinstance(catalog, GraphicsCatalog):
        states["graphics_catalog"] = (
            "object",
            catalog,
            {
                name: _capture_mutable_state(value)
                for name, value in catalog.__dict__.items()
            },
            catalog.last_metrics,
            dict(catalog.last_metrics.__dict__),
        )
    cache = attrs.get("sprite_imgs")
    if isinstance(cache, LRUCache):
        states["sprite_imgs"] = (
            "lru",
            cache,
            cache.maxsize,
            _capture_mutable_state(cache._data),
        )
    return attrs, states


def _restore_mod_state(
    mod: Any, snapshot: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    attrs, states = snapshot
    mod.__dict__.clear()
    mod.__dict__.update(attrs)
    for name, state in states.items():
        if state[0] == "object":
            obj, fields, metrics, metric_fields = state[1:]
            obj.__dict__.clear()
            obj.__dict__.update(
                {key: _restore_mutable_state(value) for key, value in fields.items()}
            )
            metrics.__dict__.clear()
            metrics.__dict__.update(metric_fields)
            mod.__dict__[name] = obj
        elif state[0] == "lru":
            cache, maxsize, data = state[1:]
            cache.maxsize = maxsize
            _restore_mutable_state(data)
            mod.__dict__[name] = cache
        else:
            mod.__dict__[name] = _restore_mutable_state(state)


@pytest.fixture
def mod_state_isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Opt-in MOD singleton isolation, preserving catalog and live image identity."""
    from hoi4cm.mod import MOD

    snapshot = _capture_mod_state(MOD)
    yield
    # The shared fixture is ordered outside scenario fixtures. Undo their and
    # the test's patches before restoring the pre-test singleton snapshot.
    monkeypatch.undo()
    _restore_mod_state(MOD, snapshot)


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
