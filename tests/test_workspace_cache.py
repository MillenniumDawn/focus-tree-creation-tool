"""Tests for hoi4cm.mod.workspace_cache — the SQLite graphics snapshot cache.

Pure sqlite, no Tk: each test points the database at a tmp_path file so
nothing touches user state.
"""

import pytest

from hoi4cm.mod.workspace_cache import WorkspaceCache


@pytest.fixture
def cache(tmp_path):
    return WorkspaceCache(tmp_path / "state" / "cache.db")


def test_store_load_roundtrip(cache):
    cache.store_graphics(
        {"a": 1, "b": ["x", "y"]},
        schema_version=1,
        root_identity="root-1",
        config_fingerprint="fp-1",
    )
    assert cache.load_graphics(
        schema_version=1,
        root_identity="root-1",
        config_fingerprint="fp-1",
    ) == {"a": 1, "b": ["x", "y"]}


def test_load_miss_returns_none(cache):
    assert (
        cache.load_graphics(
            schema_version=1, root_identity="root-1", config_fingerprint="nope"
        )
        is None
    )


def test_store_overwrites_same_fingerprint(cache):
    cache.store_graphics(
        {"a": 1}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    cache.store_graphics(
        {"a": 2}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    assert cache.load_graphics(
        schema_version=1, root_identity="root-1", config_fingerprint="fp"
    ) == {"a": 2}


def test_schema_version_mismatch_is_a_miss(cache):
    cache.store_graphics(
        {"a": 1}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    assert (
        cache.load_graphics(
            schema_version=2, root_identity="root-1", config_fingerprint="fp"
        )
        is None
    )


def test_root_identity_mismatch_is_a_miss(cache):
    cache.store_graphics(
        {"a": 1}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    assert (
        cache.load_graphics(
            schema_version=1, root_identity="root-2", config_fingerprint="fp"
        )
        is None
    )


def test_corrupt_json_degrades_to_none(tmp_path):
    cache = WorkspaceCache(tmp_path / "state" / "cache.db")
    cache.store_graphics(
        {"a": 1}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    # Corrupt the stored JSON directly in the db.
    import sqlite3

    conn = sqlite3.connect(tmp_path / "state" / "cache.db")
    with conn:
        conn.execute("UPDATE graphics_snapshot SET data = 'not-json'")
    conn.close()
    assert (
        cache.load_graphics(
            schema_version=1, root_identity="root-1", config_fingerprint="fp"
        )
        is None
    )


def test_unreadable_database_degrades_to_none(tmp_path, monkeypatch):
    cache = WorkspaceCache(tmp_path / "state" / "cache.db")
    monkeypatch.setattr(cache, "_connect", lambda: (_ for _ in ()).throw(OSError("x")))
    assert (
        cache.load_graphics(
            schema_version=1, root_identity="root-1", config_fingerprint="fp"
        )
        is None
    )


def test_store_non_jsonable_degrades_without_raising(tmp_path, monkeypatch):
    cache = WorkspaceCache(tmp_path / "state" / "cache.db")
    cache.store_graphics(
        {"bad": object()},
        schema_version=1,
        root_identity="root-1",
        config_fingerprint="fp",
    )
    # A non-serializable value must not raise; the write is skipped.
    assert (
        cache.load_graphics(
            schema_version=1, root_identity="root-1", config_fingerprint="fp"
        )
        is None
    )


def test_store_load_does_not_leak_connection(cache):
    import gc
    import warnings

    cache.store_graphics(
        {"a": 1}, schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    cache.load_graphics(
        schema_version=1, root_identity="root-1", config_fingerprint="fp"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        gc.collect()
