"""SQLite-backed per-file cache for ``ModContext`` scans.

A warm mod reload still walks the directory tree, but only re-parses files
whose ``(mtime, size)`` changed since the last scan. Everything unchanged is
served from a small SQLite database under ``~/.hoi4cm/scan_cache/``, named by a
hash of the mod root path.

The cache stores, per ``(domain, file path)``, a JSON blob of that file's
extracted contribution. Domains are scanner names ("focus", "events", …). All
DB access is best-effort: a corrupt or locked database degrades to "no cache"
and never raises into the scanner.
"""

import hashlib
import json
import os
import sqlite3

from hoi4cm.core.logger import get_logger

_log = get_logger("scan_cache")

# Overridable so tests can point the cache away from the real ~/.hoi4cm.
STATE_DIR = os.path.join(os.path.expanduser("~"), ".hoi4cm")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_cache (
    domain TEXT    NOT NULL,
    path   TEXT    NOT NULL,
    mtime  REAL    NOT NULL,
    size   INTEGER NOT NULL,
    data   TEXT    NOT NULL,
    PRIMARY KEY (domain, path)
);
"""


def database_path(mod_root: str) -> str:
    h = hashlib.sha1(os.path.abspath(mod_root).encode("utf-8")).hexdigest()[:16]
    return os.path.join(STATE_DIR, "scan_cache", f"{h}.db")


_db_path = database_path


class ScanCache:
    """Per-file scan cache for one mod root. Never raises on DB errors."""

    def __init__(self, mod_root):
        self._conn = None
        conn = None
        try:
            path = database_path(mod_root)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            conn = sqlite3.connect(path)
            conn.execute(_SCHEMA)
            conn.commit()
            self._conn = conn
        except (  # pragma: no cover - depends on FS/db state
            OSError,
            sqlite3.Error,
            ValueError,
            RuntimeError,
        ) as exc:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error, OSError:
                    pass
            _log.warning("scan cache disabled (open failed): %s", exc)
            self._conn = None

    @property
    def enabled(self):
        return self._conn is not None

    def get(self, domain, path, mtime, size):
        """Return the cached contribution for *path* if its sig matches, else None."""
        if not self._conn:
            return None
        try:
            row = self._conn.execute(
                "SELECT mtime, size, data FROM file_cache WHERE domain=? AND path=?",
                (domain, path),
            ).fetchone()
            if not row:
                return None
            c_mtime, c_size, data = row
            if c_size != size or abs(c_mtime - mtime) > 1e-6:
                return None
            return json.loads(data)
        except sqlite3.Error, json.JSONDecodeError, ValueError, OSError, TypeError:
            return None

    def get_many(self, domain, sigs):
        """Return cached contributions for *sigs* ({path: (mtime, size)}).

        One SELECT per domain instead of one per path. Only paths whose sig
        matches the cache are returned.
        """
        if not self._conn or not sigs:
            return {}
        try:
            rows = self._conn.execute(
                "SELECT path, mtime, size, data FROM file_cache WHERE domain=?",
                (domain,),
            ).fetchall()
            hits = {}
            for path, c_mtime, c_size, data in rows:
                sig = sigs.get(path)
                if sig is None:
                    continue
                mtime, size = sig
                if c_size != size or abs(c_mtime - mtime) > 1e-6:
                    continue
                try:
                    value = json.loads(data)
                except json.JSONDecodeError, ValueError, TypeError:
                    continue
                if value is None:
                    continue
                hits[path] = value
            return hits
        except sqlite3.Error, OSError, ValueError, RuntimeError:
            return {}

    def put(self, domain, path, mtime, size, data):
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO file_cache "
                "(domain, path, mtime, size, data) VALUES (?, ?, ?, ?, ?)",
                (domain, path, mtime, size, json.dumps(data, ensure_ascii=False)),
            )
        except sqlite3.Error, OSError, ValueError, TypeError:
            pass

    def put_many(self, domain, items):
        """Insert/replace several (path, mtime, size, data) rows in one statement."""
        if not self._conn or not items:
            return
        try:
            self._conn.executemany(
                "INSERT OR REPLACE INTO file_cache "
                "(domain, path, mtime, size, data) VALUES (?, ?, ?, ?, ?)",
                [
                    (domain, path, mtime, size, json.dumps(data, ensure_ascii=False))
                    for path, mtime, size, data in items
                ],
            )
        except sqlite3.Error, OSError, ValueError, TypeError:
            pass

    def prune(self, domain, keep_paths):
        """Drop rows in *domain* whose path is absent from *keep_paths*."""
        if not self._conn:
            return
        try:
            keep = set(keep_paths)
            rows = self._conn.execute(
                "SELECT path FROM file_cache WHERE domain=?", (domain,)
            ).fetchall()
            stale = [(domain, r[0]) for r in rows if r[0] not in keep]
            if stale:
                self._conn.executemany(
                    "DELETE FROM file_cache WHERE domain=? AND path=?", stale
                )
        except sqlite3.Error, OSError, ValueError:
            pass

    def commit(self):
        if not self._conn:
            return
        try:
            self._conn.commit()
        except sqlite3.Error, OSError:
            pass

    def close(self):
        if not self._conn:
            return
        try:
            try:
                self._conn.commit()
            except (sqlite3.Error, OSError) as exc:
                _log.warning("scan cache commit failed: %s", exc)
            try:
                self._conn.close()
            except sqlite3.Error, OSError:
                pass
        finally:
            self._conn = None


__all__ = ["ScanCache", "STATE_DIR", "database_path"]
