"""Tests for hoi4cm.mod.scan_cache — the SQLite per-file scan cache.

Each test points ``STATE_DIR`` at a tmp dir so nothing touches the real
~/.hoi4cm, then exercises get/put/prune and the degrade-on-error contract.
"""

import os

import pytest

from hoi4cm.mod import scan_cache as sc


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "state"))
    c = sc.ScanCache(str(tmp_path / "mod"))
    yield c
    c.close()


def test_put_get_roundtrip(cache):
    assert cache.enabled
    cache.put("focus", "/x/a.txt", 100.0, 5, {"ids": ["A", "B"]})
    cache.commit()
    assert cache.get("focus", "/x/a.txt", 100.0, 5) == {"ids": ["A", "B"]}


def test_get_miss_returns_none(cache):
    assert cache.get("focus", "/x/nope.txt", 1.0, 1) is None


def test_get_stale_on_size_change(cache):
    cache.put("d", "/a", 100.0, 5, [1, 2])
    assert cache.get("d", "/a", 100.0, 6) is None


def test_get_stale_on_mtime_change(cache):
    cache.put("d", "/a", 100.0, 5, [1, 2])
    assert cache.get("d", "/a", 200.0, 5) is None


def test_domains_are_independent(cache):
    cache.put("focus", "/a", 1.0, 1, ["F"])
    cache.put("events", "/a", 1.0, 1, ["E"])
    assert cache.get("focus", "/a", 1.0, 1) == ["F"]
    assert cache.get("events", "/a", 1.0, 1) == ["E"]


def test_prune_removes_missing_paths(cache):
    cache.put("d", "/a", 1.0, 1, {})
    cache.put("d", "/b", 1.0, 1, {})
    cache.put("other", "/b", 1.0, 1, {})
    cache.prune("d", ["/a"])
    cache.commit()
    assert cache.get("d", "/a", 1.0, 1) == {}
    assert cache.get("d", "/b", 1.0, 1) is None
    # prune is scoped to its domain
    assert cache.get("other", "/b", 1.0, 1) == {}


def test_disabled_cache_never_raises(tmp_path, monkeypatch):
    """A corrupt DB file degrades to a no-op cache rather than raising."""
    monkeypatch.setattr(sc, "STATE_DIR", str(tmp_path / "state"))
    db = sc._db_path(str(tmp_path / "mod"))
    os.makedirs(os.path.dirname(db), exist_ok=True)
    with open(db, "wb") as f:
        f.write(b"this is not a sqlite database")
    c = sc.ScanCache(str(tmp_path / "mod"))
    assert not c.enabled
    c.put("d", "/a", 1.0, 1, {"x": 1})  # no-op, no raise
    assert c.get("d", "/a", 1.0, 1) is None
    c.prune("d", [])
    c.close()
