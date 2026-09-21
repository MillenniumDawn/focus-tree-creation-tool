"""Regression coverage for pytest's import-time HOME isolation."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

_CHILD_FLAG = "HOI4CM_HOME_ISOLATION_CHILD"
_SENTINEL_ENV = "HOI4CM_HOME_ISOLATION_SENTINEL"
_EXPECTED_XAUTHORITY = "HOI4CM_HOME_ISOLATION_EXPECTED_XAUTHORITY"
_EXPECTED_DISPLAY = "HOI4CM_HOME_ISOLATION_EXPECTED_DISPLAY"


def _assert_child_imports_are_isolated(sentinel_home: Path) -> None:
    """Check child environment before importing side-effectful modules."""
    isolated_home = Path(os.path.expanduser("~")).resolve()
    assert isolated_home != sentinel_home
    assert Path(os.environ["HOME"]).resolve() == isolated_home
    if sys.platform == "win32":
        assert Path(os.environ["USERPROFILE"]).resolve() == isolated_home
    assert os.environ.get("XAUTHORITY") == os.environ[_EXPECTED_XAUTHORITY]
    expected_display = os.environ.get(_EXPECTED_DISPLAY)
    if expected_display is None:
        assert "DISPLAY" not in os.environ
    else:
        assert os.environ.get("DISPLAY") == expected_display

    import hoi4cm.core.config as config
    import hoi4cm.core.logger as logger
    import hoi4cm.mod as mod
    import hoi4cm.mod.scan_cache as scan_cache
    from hoi4cm.core.paths import autosave_path

    def assert_under_home(path: str | os.PathLike[str]) -> None:
        resolved = Path(path).resolve()
        assert resolved.is_relative_to(isolated_home), (resolved, isolated_home)

    assert_under_home(config.CONFIG_PATH)
    assert_under_home(logger._LOG_DIR)
    assert_under_home(logger._LOG_FILE)
    assert_under_home(scan_cache.STATE_DIR)
    assert_under_home(scan_cache.database_path(str(sentinel_home / "mod")))
    autosave = Path(autosave_path("probe.json"))
    assert_under_home(autosave)
    assert autosave.parent.is_dir()
    assert Path(logger._LOG_FILE).is_file()

    file_handlers = [
        handler
        for handler in logger.log.handlers
        if isinstance(handler, logging.FileHandler)
    ]
    assert file_handlers
    for handler in file_handlers:
        assert_under_home(handler.baseFilename)

    # Importing MOD before conftest isolation would load the sentinel config.
    assert mod.MOD.custom_mod_path == ""
    assert config.cfg_load() == {}


@pytest.mark.parametrize("auth_mode", ("implicit", "explicit"), ids=str)
def test_import_time_paths_stay_out_of_real_home(tmp_path, auth_mode):
    """A fresh pytest process isolates HOME without breaking X11 auth."""
    if os.environ.get(_CHILD_FLAG) == "1":
        _assert_child_imports_are_isolated(Path(os.environ[_SENTINEL_ENV]).resolve())
        return

    real_home = (tmp_path / "real-home").resolve()
    implicit_auth = real_home / ".Xauthority"
    explicit_auth = real_home / "explicit.Xauthority"
    sentinel_files = {
        real_home
        / ".hoi4_focus_maker.json": json.dumps(
            {"custom_mod_path": "sentinel-real-home-value"}
        ).encode(),
        real_home / ".hoi4cm" / "app.log": b"sentinel log\n",
        real_home / ".hoi4cm" / "scan_cache" / "sentinel.db": b"sentinel cache\n",
        real_home / ".hoi4cm" / "autosave" / "sentinel.json": b"sentinel autosave\n",
        implicit_auth: b"sentinel implicit auth\n",
        explicit_auth: b"sentinel explicit auth\n",
    }
    for path, content in sentinel_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    expected_xauthority = explicit_auth if auth_mode == "explicit" else implicit_auth
    env = os.environ.copy()
    env["HOME"] = str(real_home)
    if sys.platform == "win32":
        env["USERPROFILE"] = str(real_home)
    if auth_mode == "explicit":
        env["XAUTHORITY"] = str(explicit_auth)
    else:
        env.pop("XAUTHORITY", None)
    env[_CHILD_FLAG] = "1"
    env[_SENTINEL_ENV] = str(real_home)
    env[_EXPECTED_XAUTHORITY] = str(expected_xauthority)
    if "DISPLAY" in env:
        env[_EXPECTED_DISPLAY] = env["DISPLAY"]
    else:
        env.pop(_EXPECTED_DISPLAY, None)
    nodeid = (
        f"{Path(__file__)}::test_import_time_paths_stay_out_of_real_home[{auth_mode}]"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", nodeid],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    failures = []
    if result.returncode != 0:
        failures.append(f"child pytest failed:\n{result.stdout}\n{result.stderr}")
    for path, expected in sentinel_files.items():
        actual = path.read_bytes() if path.exists() else None
        if actual != expected:
            failures.append(f"real-home sentinel changed: {path}")
    assert not failures, "\n".join(failures)
