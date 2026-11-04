"""Tests for hoi4cm.core.config — persistent user config."""

import json
import os
import sys

import pytest

from hoi4cm.core import config


def test_cfg_load_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "nope.json"))
    assert config.cfg_load() == {}


def test_cfg_load_invalid_json_returns_empty(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    p.write_text("{ not valid json")
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    assert config.cfg_load() == {}


def test_cfg_save_writes_and_roundtrips(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    assert config.cfg_save({"a": 1}) is True
    assert json.loads(p.read_text()) == {"a": 1}
    assert config.cfg_load() == {"a": 1}


def test_cfg_save_merges_existing_keys(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    config.cfg_save({"a": 1})
    config.cfg_save({"b": 2})
    assert config.cfg_load() == {"a": 1, "b": 2}


def test_cfg_save_overwrites_existing_key(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    config.cfg_save({"a": 1})
    config.cfg_save({"a": 99})
    assert config.cfg_load()["a"] == 99


def test_cfg_save_failure_reports_false_without_raising(tmp_path, monkeypatch):
    # Parent dir does not exist → open() raises; cfg_save must report failure,
    # not crash the caller.
    bad = tmp_path / "missing_dir" / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(bad))
    assert config.cfg_save({"a": 1}) is False
    assert config.cfg_load() == {}


def test_cfg_save_is_atomic_no_leftover_tmp(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    config.cfg_save({"a": 1})
    config.cfg_save({"b": 2})
    assert config.cfg_load() == {"a": 1, "b": 2}
    assert not os.path.exists(str(p) + ".tmp")  # temp file cleaned up


def test_cfg_save_failure_leaves_no_tmp(tmp_path, monkeypatch):
    bad = tmp_path / "missing_dir" / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(bad))
    assert config.cfg_save({"a": 1}) is False
    assert not os.path.exists(str(bad) + ".tmp")


def test_app_config_save_propagates_failure(monkeypatch):
    from hoi4cm.core.app_config import AppConfig

    monkeypatch.setattr("hoi4cm.core.app_config.cfg_save", lambda data: False)
    assert AppConfig().save() is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_cfg_save_sets_owner_only_perms(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    config.cfg_save({"a": 1})
    assert (os.stat(str(p)).st_mode & 0o077) == 0


def test_sidebar_refresh_skip_flag_registered_and_honored(monkeypatch):
    from hoi4cm.core.app_config import AppConfig

    monkeypatch.setattr("hoi4cm.core.app_config.cfg_load", lambda: {})
    assert AppConfig.load().sidebar_refresh_skip is True
    monkeypatch.setattr(
        "hoi4cm.core.app_config.cfg_load", lambda: {"sidebar_refresh_skip": False}
    )
    assert AppConfig.load().sidebar_refresh_skip is False


def test_sidebar_refresh_skip_roundtrips_through_save_config(monkeypatch):
    """Saving persists the flag and a fresh config reloads it."""
    from hoi4cm.core.app_config import AppConfig

    saved = {}
    monkeypatch.setattr(
        "hoi4cm.core.app_config.cfg_save", lambda data: (saved.update(data), True)[1]
    )
    monkeypatch.setattr("hoi4cm.core.app_config.cfg_load", lambda: dict(saved))

    settings = AppConfig()
    settings.sidebar_refresh_skip = False
    assert settings.save() is True
    assert saved["sidebar_refresh_skip"] is False
    assert AppConfig.load().sidebar_refresh_skip is False


def test_loc_language_defaults_persists_and_normalizes(monkeypatch):
    from hoi4cm.core.app_config import AppConfig

    saved = {}
    monkeypatch.setattr(
        "hoi4cm.core.app_config.cfg_save", lambda data: (saved.update(data), True)[1]
    )
    monkeypatch.setattr("hoi4cm.core.app_config.cfg_load", lambda: dict(saved))

    settings = AppConfig()
    assert settings.loc_language == "english"
    settings.loc_language = "french"
    assert settings.save() is True
    assert saved["loc_language"] == "french"
    assert AppConfig.load().loc_language == "french"

    saved["loc_language"] = "invalid"
    assert AppConfig.load().loc_language == "english"
