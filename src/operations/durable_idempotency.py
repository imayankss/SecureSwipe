"""Local SQLite idempotency prototype (optional; not the default backend).

MT6 demonstrated three crash/restart gaps in the in-memory registry. Their root
cause is that the audit event is durable while the idempotency record is not,
and the record is discarded on any failure. This store closes that gap for the
single-node case.

**Scope and non-claims.** This is *local single-node durability only*. It is not
immutable or WORM storage, not ACID across services, not a multi-writer scale
solution, not high availability, and not a cross-host failover mechanism.
Concurrent multi-process writing is explicitly unsupported and untested; MT4
already established that multi-worker serving is incompatible with current state
ownership.

**What is stored.** Only the hashed idempotency key, the canonical input digest,
a lifecycle state, bounded decision-level metadata, the audit event hash, and
timestamps. Never raw request JSON, feature values, per-record scores, labels,
secrets, or plaintext identifiers.

Protocol: docs/evidence/MT6_STATE_AND_CRASH_PROTOCOL.md
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Lifecycle states. ``UNRESOLVED`` is terminal and always fails closed.
State = Literal["PENDING", "COMPLETED", "FAILED", "UNRESOLVED"]

PENDING: State = "PENDING"
COMPLETED: State = "COMPLETED"
FAILED: State = "FAILED"
UNRESOLVED: State = "UNRESOLVED"

#: Decision labels the store will persist. Anything else is refused.
ALLOWED_DECISIONS = ("human_review", "below_review_threshold", "unavailable_fail_closed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency (
    key_sha256           TEXT PRIMARY KEY NOT NULL,
    input_digest_sha256  TEXT NOT NULL,
    state                TEXT NOT NULL,
    decision             TEXT,
    model_version        TEXT,
    audit_event_hash     TEXT,
    created_utc          TEXT NOT NULL,
    resolved_utc         TEXT
);
"""


class DurableIdempotencyError(RuntimeError):
    """Raised when the durable store refuses an operation."""


class IdempotencyConflict(DurableIdempotencyError):
    """Same key, different canonical body."""


class UnresolvedRequestError(DurableIdempotencyError):
    """A request whose outcome is unknown after a crash. Never rescored."""


@dataclass(frozen=True)
class Reservation:
    """Outcome of reserving a key."""

    key_sha256: str
    owner: bool
    state: State
    decision: str | None = None
    model_version: str | None = None
    audit_event_hash: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_digest(request_id: str) -> str:
    """Hash the request id. The plaintext id is never stored here."""
    return hashlib.sha256(request_id.encode("ascii")).hexdigest()


def _require_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise DurableIdempotencyError(f"{label} must be a lowercase hex SHA-256 digest.")
    return value


class SqliteIdempotencyStore:
    """Durable, single-node idempotency records backed by ``sqlite3``."""

    def __init__(self, database_path: str | Path, *, allow_inside_repo: bool = False) -> None:
        path = Path(database_path).expanduser()
        if not path.is_absolute():
            raise DurableIdempotencyError("Database path must be absolute.")
        if path.is_symlink():
            raise DurableIdempotencyError("Database path must not be a symlink.")
        resolved_parent = path.parent.resolve()
        if not resolved_parent.is_dir():
            raise DurableIdempotencyError("Database parent directory must already exist.")
        if not allow_inside_repo and (
            resolved_parent == PROJECT_ROOT or PROJECT_ROOT in resolved_parent.parents
        ):
            raise DurableIdempotencyError("Database must live outside the repository.")

        self.path = path
        self._connection = sqlite3.connect(str(path), isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA)
        self.recovered_unresolved = self._recover()

    # -- lifecycle -------------------------------------------------------

    def _recover(self) -> int:
        """Any request left ``PENDING`` by a crash becomes ``UNRESOLVED``.

        It is never rescored and never approved. A later retry fails closed.
        """
        cursor = self._connection.execute(
            "UPDATE idempotency SET state = ?, resolved_utc = ? WHERE state = ?",
            (UNRESOLVED, _utc_now(), PENDING),
        )
        return int(cursor.rowcount or 0)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SqliteIdempotencyStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- operations ------------------------------------------------------

    def reserve(self, *, request_id: str, input_digest_sha256: str) -> Reservation:
        """Claim a key, or describe the durable outcome that already exists."""
        _require_sha256(input_digest_sha256, label="input_digest_sha256")
        key = key_digest(request_id)
        row = self._connection.execute(
            "SELECT * FROM idempotency WHERE key_sha256 = ?", (key,)
        ).fetchone()

        if row is None:
            self._connection.execute(
                "INSERT INTO idempotency (key_sha256, input_digest_sha256, state, created_utc)"
                " VALUES (?, ?, ?, ?)",
                (key, input_digest_sha256, PENDING, _utc_now()),
            )
            return Reservation(key_sha256=key, owner=True, state=PENDING)

        if row["input_digest_sha256"] != input_digest_sha256:
            raise IdempotencyConflict(
                "The request ID was already used for different canonical input."
            )
        if row["state"] == UNRESOLVED:
            raise UnresolvedRequestError(
                "A previous attempt for this request ID did not resolve. It will not be "
                "rescored; inspect the audit evidence before retrying."
            )
        if row["state"] == PENDING:
            raise UnresolvedRequestError(
                "This request ID is already in flight in this process."
            )
        if row["state"] == FAILED:
            # The earlier attempt released no durable decision, so a retry is honest.
            self._connection.execute(
                "UPDATE idempotency SET state = ?, resolved_utc = NULL WHERE key_sha256 = ?",
                (PENDING, key),
            )
            return Reservation(key_sha256=key, owner=True, state=PENDING)

        return Reservation(
            key_sha256=key,
            owner=False,
            state=COMPLETED,
            decision=row["decision"],
            model_version=row["model_version"],
            audit_event_hash=row["audit_event_hash"],
        )

    def complete(
        self,
        reservation: Reservation,
        *,
        decision: str,
        model_version: str,
        audit_event_hash: str,
    ) -> None:
        """Commit the decision record and its audit binding together."""
        if not reservation.owner:
            raise DurableIdempotencyError("Only an owner reservation can be completed.")
        if decision not in ALLOWED_DECISIONS:
            raise DurableIdempotencyError(f"Decision {decision!r} is not on the allowlist.")
        _require_sha256(audit_event_hash, label="audit_event_hash")

        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "UPDATE idempotency SET state = ?, decision = ?, model_version = ?,"
                " audit_event_hash = ?, resolved_utc = ? WHERE key_sha256 = ? AND state = ?",
                (COMPLETED, decision, model_version, audit_event_hash, _utc_now(),
                 reservation.key_sha256, PENDING),
            )
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def fail(self, reservation: Reservation, *, audit_event_durable: bool) -> None:
        """Record a failed attempt.

        If the audit event was already durable the outcome is **unknown**, so the
        key becomes ``UNRESOLVED`` and can never be silently rescored. Only a
        failure with no durable audit event is marked retryable.
        """
        if not reservation.owner:
            raise DurableIdempotencyError("Only an owner reservation can fail.")
        state = UNRESOLVED if audit_event_durable else FAILED
        self._connection.execute(
            "UPDATE idempotency SET state = ?, resolved_utc = ? WHERE key_sha256 = ?",
            (state, _utc_now(), reservation.key_sha256),
        )

    # -- inspection ------------------------------------------------------

    def state_of(self, request_id: str) -> State | None:
        row = self._connection.execute(
            "SELECT state FROM idempotency WHERE key_sha256 = ?", (key_digest(request_id),)
        ).fetchone()
        return None if row is None else row["state"]

    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM idempotency").fetchone()
        return int(row["n"])
