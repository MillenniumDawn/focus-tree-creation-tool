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
    config.cfg_save({"a": 1})
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


def test_cfg_save_failure_is_swallowed(tmp_path, monkeypatch):
    # Parent dir does not exist → open() raises; cfg_save must log, not crash.
    bad = tmp_path / "missing_dir" / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(bad))
    config.cfg_save({"a": 1})  # should not raise
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
    config.cfg_save({"a": 1})
    assert not os.path.exists(str(bad) + ".tmp")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_cfg_save_sets_owner_only_perms(tmp_path, monkeypatch):
    p = tmp_path / "cfg.json"
    monkeypatch.setattr(config, "CONFIG_PATH", str(p))
    config.cfg_save({"a": 1})
    assert (os.stat(str(p)).st_mode & 0o077) == 0
