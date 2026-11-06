"""Durable recovery eligibility, independent of destination filesystem calls.

There is one active lease for the per-user workspace recovery slot. A crash
leaves it eligible; an explicit invalidation revokes it. SQLite provides atomic
compare-and-delete across processes without retaining per-generation files.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from hoi4cm.core.paths import autosave_path

RECOVERY_KEY = "_hoi4cm_recovery"
_store_lock = threading.RLock()


class RecoveryEligibilityError(RuntimeError):
    """The local eligibility store could not complete an operation."""


class RevokedRecoveryError(ValueError):
    """Recovery belongs to an invalidated or superseded generation."""


def _store_path() -> str:
    return autosave_path("recovery-eligibility.sqlite3")


@contextmanager
def _connection(*, writable: bool) -> Iterator[sqlite3.Connection | None]:
    connection = None
    try:
        path = _store_path()
        if not writable and not Path(path).is_file():
            yield None
            return
        connection = sqlite3.connect(path, timeout=0)
        if writable:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS recovery "
                "(slot INTEGER PRIMARY KEY CHECK (slot = 1), "
                "token TEXT NOT NULL, paths TEXT NOT NULL, "
                "previous TEXT, previous_paths TEXT)"
            )
            connection.execute("BEGIN IMMEDIATE")
        with connection:
            yield connection
    except (OSError, sqlite3.Error) as error:
        raise RecoveryEligibilityError(
            f"Could not update or read local recovery eligibility: {error}"
        ) from error
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def _store(*, writable: bool) -> Iterator[sqlite3.Connection | None]:
    # This lock covers only local control transactions, never payload staging,
    # rename, or reads from a destination. External contention fails immediately.
    with _store_lock, _connection(writable=writable) as connection:
        yield connection


def new_recovery_token() -> str:
    return secrets.token_hex(16)


def _published_token(path: str) -> str | None:
    try:
        with open(path, "rb") as stream:
            prefix = stream.read(128)
    except FileNotFoundError:
        return None
    match = re.match(rb'\{"_hoi4cm_recovery":"([0-9a-f]{32})"', prefix)
    return match[1].decode("ascii") if match else None


def activate_recovery(token: str, paths: tuple[str, ...]) -> None:
    published = _published_token(paths[0])
    destinations = [os.path.normcase(os.path.abspath(path)) for path in paths]
    with _store(writable=True) as connection:
        assert connection is not None
        row = connection.execute(
            "SELECT token, paths, previous, previous_paths FROM recovery"
        ).fetchone()
        previous = previous_paths = None
        if row is not None:
            # Never turn a revoked token from a late rename back into an
            # eligible backup. Only retain an already eligible token.
            if published == row[0]:
                previous, previous_paths = row[:2]
            elif published is not None and published == row[2]:
                previous, previous_paths = row[2:]
            elif published is None:
                previous, previous_paths = row[2:] if row[2] else row[:2]
        connection.execute(
            "INSERT OR REPLACE INTO recovery VALUES (1, ?, ?, ?, ?)",
            (token, json.dumps(destinations), previous, previous_paths),
        )


def complete_recovery(token: str) -> None:
    with _store(writable=True) as connection:
        assert connection is not None
        connection.execute(
            "UPDATE recovery SET previous = NULL, previous_paths = NULL "
            "WHERE token = ?",
            (token,),
        )


def revoke_recovery(token: str) -> None:
    with _store(writable=True) as connection:
        assert connection is not None
        connection.execute("DELETE FROM recovery WHERE token = ?", (token,))
        connection.execute(
            "UPDATE recovery SET previous = NULL, previous_paths = NULL "
            "WHERE previous = ?",
            (token,),
        )


def revoke_recovery_path(path: str) -> None:
    """Revoke even when a destination has not reached its final rename yet."""
    if not Path(_store_path()).is_file():
        return
    destination = os.path.normcase(os.path.abspath(path))
    with _store(writable=True) as connection:
        assert connection is not None
        row = connection.execute(
            "SELECT token, paths, previous, previous_paths FROM recovery"
        ).fetchone()
        if row is not None and destination in json.loads(row[1]):
            connection.execute("DELETE FROM recovery WHERE token = ?", (row[0],))
        elif row is not None and row[3] and destination in json.loads(row[3]):
            connection.execute(
                "UPDATE recovery SET previous = NULL, previous_paths = NULL "
                "WHERE previous = ?",
                (row[2],),
            )


def recovery_is_eligible(token: str) -> bool:
    with _store(writable=False) as connection:
        row = (
            connection.execute(
                "SELECT 1 FROM recovery WHERE token = ? OR previous = ?", (token, token)
            ).fetchone()
            if connection is not None
            else None
        )
    return row is not None


def validate_recovery(data: Mapping[str, Any]) -> None:
    if RECOVERY_KEY not in data:
        return
    token = data[RECOVERY_KEY]
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None:
        raise RevokedRecoveryError("Invalid recovery eligibility token")
    if not recovery_is_eligible(token):
        raise RevokedRecoveryError(
            "This recovery was discarded or superseded; open the saved project instead"
        )


__all__ = [
    "RECOVERY_KEY",
    "RecoveryEligibilityError",
    "RevokedRecoveryError",
    "activate_recovery",
    "complete_recovery",
    "new_recovery_token",
    "recovery_is_eligible",
    "revoke_recovery",
    "revoke_recovery_path",
    "validate_recovery",
]
