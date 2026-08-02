"""A tiny bounded LRU mapping.

Backs the two in-memory ``PhotoImage`` caches (``mod.context.ModContext.
sprite_imgs`` and the GFX browser's ``img_cache``) that used to grow without
limit for a process's whole lifetime. Both also memoize ``None`` on a failed
load so a bad path isn't retried every frame; that still counts as a cache
hit here; a ``None`` value is not treated specially.
"""

from collections import OrderedDict


class LRUCache:
    """Bounded ``dict``-like mapping with least-recently-used eviction.

    Both reads and writes count as a "use" and move the key to the
    most-recently-used end. Once more than ``maxsize`` keys are held, the
    least-recently-used one is dropped. Supports the small dict subset the
    call sites need: ``in``, ``[]``, ``.get``, ``.clear``.
    """

    def __init__(self, maxsize=512):
        self.maxsize = maxsize
        self._data = OrderedDict()

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        value = self._data[key]
        self._data.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def clear(self):
        self._data.clear()

    def evict(self, predicate):
        """Drop every key for which *predicate* returns True."""
        stale = [key for key in self._data if predicate(key)]
        for key in stale:
            del self._data[key]


__all__ = ["LRUCache"]
