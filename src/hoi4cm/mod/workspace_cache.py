from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path

from hoi4cm.core.logger import get_logger

_log = get_logger("workspace_cache")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graphics_snapshot (
    config_fingerprint TEXT PRIMARY KEY,
    schema_version     INTEGER NOT NULL,
    root_identity      TEXT    NOT NULL,
    data               TEXT    NOT NULL
);
"""


class WorkspaceCache:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def load_graphics(
        self,
        *,
        schema_version: int,
        root_identity: str,
        config_fingerprint: str,
    ) -> dict[str, object] | None:
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT schema_version, root_identity, data "
                    "FROM graphics_snapshot WHERE config_fingerprint = ?",
                    (config_fingerprint,),
                ).fetchone()
        except (OSError, sqlite3.Error) as error:
            _log.debug("graphics cache read failed: %s", error)
            return None

        if row is None or row[0] != schema_version or row[1] != root_identity:
            return None
        try:
            data = json.loads(row[2])
        except TypeError, ValueError:
            return None
        return data if isinstance(data, dict) else None

    def store_graphics(
        self,
        data: Mapping[str, object],
        *,
        schema_version: int,
        root_identity: str,
        config_fingerprint: str,
    ) -> bool:
        try:
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            with self._connection() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO graphics_snapshot "
                    "(config_fingerprint, schema_version, root_identity, data) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        config_fingerprint,
                        schema_version,
                        root_identity,
                        encoded,
                    ),
                )
        except (OSError, TypeError, ValueError, sqlite3.Error) as error:
            _log.debug("graphics cache write failed: %s", error)
            return False
        return True

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.execute(_SCHEMA)
        return connection


__all__ = ["WorkspaceCache"]
