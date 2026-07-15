"""Tests for hoi4cm.core.lru.LRUCache — the bounded PhotoImage-cache backing."""

from hoi4cm.core.lru import LRUCache


def test_set_and_get_roundtrip():
    cache = LRUCache(maxsize=3)
    cache["a"] = 1
    assert "a" in cache
    assert cache["a"] == 1
    assert cache.get("a") == 1


def test_get_missing_returns_default():
    cache = LRUCache(maxsize=3)
    assert cache.get("missing") is None
    assert cache.get("missing", "fallback") == "fallback"
    assert "missing" not in cache


def test_eviction_drops_least_recently_used():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache["c"] = 3  # over capacity: "a" (oldest, never touched) is evicted
    assert "a" not in cache
    assert "b" in cache
    assert "c" in cache
    assert len(cache) == 2


def test_get_refreshes_recency_and_protects_from_eviction():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache.get("a")  # "a" is now more-recently-used than "b"
    cache["c"] = 3  # "b" is now the oldest untouched entry, not "a"
    assert "a" in cache
    assert "b" not in cache
    assert "c" in cache


def test_getitem_refreshes_recency_and_protects_from_eviction():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    _ = cache["a"]
    cache["c"] = 3
    assert "a" in cache
    assert "b" not in cache


def test_reassigning_a_key_refreshes_recency():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache["a"] = 10  # touch "a" again via overwrite
    cache["c"] = 3
    assert "a" in cache
    assert cache["a"] == 10
    assert "b" not in cache


def test_none_value_is_memoized_as_a_hit_not_a_miss():
    """None means 'already tried, don't retry' — must not look like cache-miss."""
    cache = LRUCache(maxsize=2)
    cache["failed"] = None
    assert "failed" in cache
    assert cache.get("failed", "sentinel") is None


def test_none_value_participates_in_eviction_normally():
    cache = LRUCache(maxsize=2)
    cache["failed"] = None
    cache["b"] = 2
    cache["c"] = 3  # "failed" is oldest untouched, evicted like any other entry
    assert "failed" not in cache
    assert "b" in cache
    assert "c" in cache


def test_clear_empties_the_cache():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache.clear()
    assert len(cache) == 0
    assert "a" not in cache
