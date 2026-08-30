"""PostgreSQL-backed score-free idempotency substrate for the future scale profile."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from api.postgres_audit import (
    AUDIT_CHAIN_ID,
    PostgresAuditIntegrityError,
    build_audit_event,
    verify_audit_chain,
)
from api.postgres_migrations import MigrationError, run_migrations
from api.scale_config import PostgresScaleSettings
from api.scale_response import (
    BoundedPredictionRepresentation,
    canonical_response_bytes,
    response_sha256,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_RESPONSE_KEYS = {
    "raw_score",
    "decision_score",
    "calibrated_probability",
    "score",
    "score_type",
    "request_id",
    "features",
    "payload",
}


class DurableIdempotencyError(RuntimeError):
    """Base class for fail-closed durable idempotency outcomes."""


class StateStoreUnavailableError(DurableIdempotencyError):
    """The configured PostgreSQL substrate could not be used safely."""


class DurableIdempotencyConflictError(DurableIdempotencyError):
    """An HMAC-key digest is already bound to different canonical input."""


class ReservationInProgressError(DurableIdempotencyError):
    """An identical owner remains active after the bounded wait."""


class StaleReservationError(DurableIdempotencyError):
    """An abandoned reservation requires operator-controlled recovery."""


class FailedReservationError(DurableIdempotencyError):
    """A prior owner recorded terminal failure for the idempotency key."""


class StoredResponseIntegrityError(DurableIdempotencyError):
    """A completed row does not contain its exact valid bounded response."""


ReservationKind = Literal["owner", "completed", "reserved", "stale", "failed"]


@dataclass(frozen=True)
class DurableReservation:
    kind: ReservationKind
    key_digest: str
    request_digest: str
    response: BoundedPredictionRepresentation | None = None
    response_hash: str | None = None
    audit_receipt_sha256: str | None = None


@dataclass(frozen=True)
class DurableExecutionResult:
    response: BoundedPredictionRepresentation
    audit_receipt_sha256: str
    replayed: bool


def idempotency_key_digest(secret: bytes, request_id: str) -> str:
    return hmac.new(secret, request_id.encode("utf-8"), hashlib.sha256).hexdigest()


def _validate_request_digest(value: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError("request_digest must be a lowercase SHA-256 digest.")


def _validate_response_keys(value: object) -> None:
    if isinstance(value, dict):
        forbidden = _FORBIDDEN_RESPONSE_KEYS.intersection(value)
        if forbidden:
            raise StoredResponseIntegrityError("Bounded response contains a forbidden field.")
        for item in value.values():
            _validate_response_keys(item)
    elif isinstance(value, list):
        for item in value:
            _validate_response_keys(item)


class PostgresIdempotencyStore:
    """Short-transaction durable reservations; scoring executes outside the database."""

    def __init__(
        self,
        settings: PostgresScaleSettings,
        *,
        reservation_ttl_seconds: float = 30.0,
        retention_seconds: float = 86_400.0,
        wait_timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.025,
    ) -> None:
        if reservation_ttl_seconds <= 0 or retention_seconds <= reservation_ttl_seconds:
            raise ValueError("Retention must be greater than the positive reservation TTL.")
        if wait_timeout_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("Wait and poll durations must be positive.")
        self.settings = settings
        self.reservation_ttl = timedelta(seconds=reservation_ttl_seconds)
        self.retention = timedelta(seconds=retention_seconds)
        self.wait_timeout_seconds = wait_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._pool: AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]] | None = None

    @property
    def table(self) -> sql.Composed:
        return sql.SQL("{}.secureswipe_idempotency").format(
            sql.Identifier(self.settings.schema)
        )

    async def open(self) -> None:
        if self._pool is not None:
            return
        try:
            await run_migrations(
                dsn=self.settings.dsn,
                schema=self.settings.schema,
                apply=False,
                connect_timeout_seconds=self.settings.connect_timeout_seconds,
            )
            pool = cast(
                AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]],
                AsyncConnectionPool(
                    conninfo=self.settings.dsn,
                    min_size=self.settings.pool_min_size,
                    max_size=self.settings.pool_max_size,
                    timeout=self.settings.connect_timeout_seconds,
                    kwargs={
                        "autocommit": False,
                        "connect_timeout": max(
                            1, math.ceil(self.settings.connect_timeout_seconds)
                        ),
                        "row_factory": dict_row,
                    },
                    open=False,
                ),
            )
            await pool.open(wait=True)
            self._pool = pool
            async with pool.connection() as connection:
                await verify_audit_chain(connection, schema=self.settings.schema)
        except (
            MigrationError,
            PostgresAuditIntegrityError,
            psycopg.Error,
            PoolTimeout,
            OSError,
        ):
            if self._pool is not None:
                await self.close()
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable or incompatible."
            ) from None

    async def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            await pool.close()

    def _require_pool(
        self,
    ) -> AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]]:
        if self._pool is None:
            raise StateStoreUnavailableError("The postgres-scale state store is not open.")
        return self._pool

    async def is_available(self) -> bool:
        """Check current connectivity and the bounded head row without a chain scan."""
        try:
            pool = self._require_pool()
            async with pool.connection() as connection:
                cursor = await connection.execute(
                    sql.SQL(
                        """
                        SELECT last_sequence, last_hash
                        FROM {}.audit_chain_heads
                        WHERE chain_id = %s
                        """
                    ).format(sql.Identifier(self.settings.schema)),
                    (AUDIT_CHAIN_ID,),
                )
                row = await cursor.fetchone()
            return bool(
                row is not None
                and int(row["last_sequence"]) >= 0
                and _SHA256_PATTERN.fullmatch(str(row["last_hash"]))
            )
        except (
            DurableIdempotencyError,
            psycopg.Error,
            PoolTimeout,
            OSError,
            TypeError,
            ValueError,
        ):
            return False

    def _from_row(self, row: dict[str, object], *, request_digest: str) -> DurableReservation:
        existing_digest = str(row["request_digest"])
        if not hmac.compare_digest(existing_digest, request_digest):
            raise DurableIdempotencyConflictError(
                "The request ID was already used for different canonical input."
            )
        state = str(row["state"])
        key_digest = str(row["key_digest"])
        if state == "reserved":
            kind: ReservationKind = "stale" if bool(row["is_stale"]) else "reserved"
            return DurableReservation(kind, key_digest, request_digest)
        if state == "failed":
            return DurableReservation("failed", key_digest, request_digest)
        if state != "completed":
            raise StoredResponseIntegrityError("Stored reservation has an invalid state.")
        document = row["response_document"]
        stored_hash = str(row["response_sha256"])
        if not isinstance(document, dict) or not _SHA256_PATTERN.fullmatch(stored_hash):
            raise StoredResponseIntegrityError("Stored bounded response is incomplete.")
        _validate_response_keys(document)
        try:
            response = BoundedPredictionRepresentation.model_validate(document)
        except ValueError as exc:
            raise StoredResponseIntegrityError("Stored bounded response is invalid.") from exc
        actual_hash = response_sha256(response)
        if not hmac.compare_digest(stored_hash, actual_hash):
            raise StoredResponseIntegrityError("Stored bounded response hash does not match.")
        receipt_value = row["audit_receipt_sha256"]
        receipt = None if receipt_value is None else str(receipt_value)
        if receipt is None or not _SHA256_PATTERN.fullmatch(receipt):
            raise StoredResponseIntegrityError("Stored audit receipt is invalid.")
        return DurableReservation(
            "completed",
            key_digest,
            request_digest,
            response=response,
            response_hash=stored_hash,
            audit_receipt_sha256=receipt,
        )

    async def reserve(self, *, request_id: str, request_digest: str) -> DurableReservation:
        _validate_request_digest(request_digest)
        key_digest = idempotency_key_digest(self.settings.hmac_secret, request_id)
        pool = self._require_pool()
        try:
            async with pool.connection() as connection:
                async with connection.transaction():
                    cursor = await connection.execute(
                        sql.SQL(
                            """
                            INSERT INTO {} (
                                key_digest, request_digest, state, created_at, updated_at,
                                reservation_expires_at, retention_until
                            )
                            VALUES (
                                %s, %s, 'reserved', clock_timestamp(), clock_timestamp(),
                                clock_timestamp() + %s, clock_timestamp() + %s
                            )
                            ON CONFLICT (key_digest) DO NOTHING
                            RETURNING key_digest
                            """
                        ).format(self.table),
                        (key_digest, request_digest, self.reservation_ttl, self.retention),
                    )
                    inserted = await cursor.fetchone()
                    if inserted is not None:
                        return DurableReservation("owner", key_digest, request_digest)
                    cursor = await connection.execute(
                        sql.SQL(
                            """
                            SELECT key_digest, request_digest, state,
                                   reservation_expires_at <= clock_timestamp() AS is_stale,
                                   response_document, response_sha256, audit_receipt_sha256
                            FROM {}
                            WHERE key_digest = %s
                            FOR SHARE
                            """
                        ).format(self.table),
                        (key_digest,),
                    )
                    row = await cursor.fetchone()
                    if row is None:
                        raise StateStoreUnavailableError(
                            "The durable reservation could not be observed safely."
                        )
                    return self._from_row(row, request_digest=request_digest)
        except DurableIdempotencyError:
            raise
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable "
                f"({type(exc).__name__})."
            ) from None

    async def _read(
        self, *, key_digest: str, request_digest: str
    ) -> DurableReservation:
        pool = self._require_pool()
        try:
            async with pool.connection() as connection:
                cursor = await connection.execute(
                    sql.SQL(
                        """
                        SELECT key_digest, request_digest, state,
                               reservation_expires_at <= clock_timestamp() AS is_stale,
                               response_document, response_sha256, audit_receipt_sha256
                        FROM {}
                        WHERE key_digest = %s
                        """
                    ).format(self.table),
                    (key_digest,),
                )
                row = await cursor.fetchone()
            if row is None:
                raise StateStoreUnavailableError("The durable reservation disappeared.")
            return self._from_row(row, request_digest=request_digest)
        except DurableIdempotencyError:
            raise
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable "
                f"({type(exc).__name__})."
            ) from None

    async def wait_for_resolution(
        self, reservation: DurableReservation
    ) -> BoundedPredictionRepresentation:
        completed = await self.wait_for_reservation(reservation)
        if completed.response is None:
            raise StoredResponseIntegrityError("Stored bounded response is missing.")
        return completed.response

    async def wait_for_reservation(
        self, reservation: DurableReservation
    ) -> DurableReservation:
        if reservation.kind == "completed" and reservation.response is not None:
            return reservation
        if reservation.kind == "stale":
            raise StaleReservationError("The durable reservation is stale; retry is refused.")
        if reservation.kind == "failed":
            raise FailedReservationError("The durable reservation previously failed.")
        if reservation.kind != "reserved":
            raise RuntimeError("Only observed reservations can be awaited.")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.wait_timeout_seconds
        while loop.time() < deadline:
            await asyncio.sleep(self.poll_interval_seconds)
            current = await self._read(
                key_digest=reservation.key_digest,
                request_digest=reservation.request_digest,
            )
            if current.kind == "completed" and current.response is not None:
                return current
            if current.kind == "stale":
                raise StaleReservationError(
                    "The durable reservation became stale; retry is refused."
                )
            if current.kind == "failed":
                raise FailedReservationError("The durable reservation failed.")
        raise ReservationInProgressError(
            "The durable reservation is still in progress after the bounded wait."
        )

    async def complete(
        self,
        reservation: DurableReservation,
        response: BoundedPredictionRepresentation,
        *,
        fault_hook: Callable[[str], None] | None = None,
    ) -> BoundedPredictionRepresentation:
        completed = await self.complete_reservation(
            reservation, response, fault_hook=fault_hook
        )
        if completed.response is None:
            raise StoredResponseIntegrityError("Committed bounded response is missing.")
        return completed.response

    async def complete_reservation(
        self,
        reservation: DurableReservation,
        response: BoundedPredictionRepresentation,
        *,
        fault_hook: Callable[[str], None] | None = None,
    ) -> DurableReservation:
        if reservation.kind != "owner":
            raise RuntimeError("Only the reservation owner can complete work.")
        document = response.model_dump(mode="json", by_alias=True)
        _validate_response_keys(document)
        digest = response_sha256(response)
        pool = self._require_pool()
        try:
            async with pool.connection() as connection:
                async with connection.transaction():
                    reservation_cursor = await connection.execute(
                        sql.SQL(
                            """
                            SELECT key_digest, request_digest, state,
                                   reservation_expires_at <= clock_timestamp() AS is_stale,
                                   response_document, response_sha256, audit_receipt_sha256
                            FROM {}
                            WHERE key_digest = %s
                            FOR UPDATE
                            """
                        ).format(self.table),
                        (reservation.key_digest,),
                    )
                    locked_reservation = await reservation_cursor.fetchone()
                    if locked_reservation is None:
                        raise StateStoreUnavailableError(
                            "The durable reservation disappeared before completion."
                        )
                    if not hmac.compare_digest(
                        str(locked_reservation["request_digest"]),
                        reservation.request_digest,
                    ):
                        raise DurableIdempotencyConflictError(
                            "The request ID was already used for different canonical input."
                        )
                    if str(locked_reservation["state"]) != "reserved" or bool(
                        locked_reservation["is_stale"]
                    ):
                        raise StaleReservationError(
                            "The reservation cannot complete after expiry or state change."
                        )

                    head_cursor = await connection.execute(
                        sql.SQL(
                            """
                            SELECT chain_id, last_sequence, last_hash
                            FROM {}.audit_chain_heads
                            WHERE chain_id = %s
                            FOR UPDATE
                            """
                        ).format(sql.Identifier(self.settings.schema)),
                        (AUDIT_CHAIN_ID,),
                    )
                    head = await head_cursor.fetchone()
                    if head is None:
                        raise PostgresAuditIntegrityError(
                            "The seeded audit chain head is missing."
                        )
                    event = build_audit_event(
                        chain_id=str(head["chain_id"]),
                        sequence=int(head["last_sequence"]) + 1,
                        previous_hash=str(head["last_hash"]),
                        key_digest=reservation.key_digest,
                        request_digest=reservation.request_digest,
                        response=response,
                        occurred_at=datetime.now(timezone.utc),
                    )
                    await connection.execute(
                        sql.SQL(
                            """
                            INSERT INTO {}.audit_events (
                                event_id, chain_id, sequence, previous_hash, event_hash,
                                key_digest, request_digest, decision, bounded_response,
                                response_sha256, occurred_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
                        ).format(sql.Identifier(self.settings.schema)),
                        (
                            event.event_id,
                            event.chain_id,
                            event.sequence,
                            event.previous_hash,
                            event.event_hash,
                            event.key_digest,
                            event.request_digest,
                            event.decision,
                            Jsonb(event.bounded_response),
                            event.response_sha256,
                            event.occurred_at,
                        ),
                    )
                    cursor = await connection.execute(
                        sql.SQL(
                            """
                            UPDATE {}
                            SET state = 'completed', updated_at = clock_timestamp(),
                                completed_at = clock_timestamp(), response_document = %s,
                                response_sha256 = %s, audit_receipt_sha256 = %s
                            WHERE key_digest = %s
                              AND request_digest = %s
                              AND state = 'reserved'
                            """
                        ).format(self.table),
                        (
                            Jsonb(document),
                            digest,
                            event.event_hash,
                            reservation.key_digest,
                            reservation.request_digest,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise StaleReservationError(
                            "The reservation cannot complete after expiry or state change."
                        )
                    head_update = await connection.execute(
                        sql.SQL(
                            """
                            UPDATE {}.audit_chain_heads
                            SET last_sequence = %s, last_hash = %s,
                                updated_at = clock_timestamp()
                            WHERE chain_id = %s
                              AND last_sequence = %s
                              AND last_hash = %s
                            """
                        ).format(sql.Identifier(self.settings.schema)),
                        (
                            event.sequence,
                            event.event_hash,
                            event.chain_id,
                            event.sequence - 1,
                            event.previous_hash,
                        ),
                    )
                    if head_update.rowcount != 1:
                        raise PostgresAuditIntegrityError(
                            "The audit chain head changed unexpectedly."
                        )
                    if fault_hook is not None:
                        fault_hook("before_commit")
            completed = DurableReservation(
                "completed",
                reservation.key_digest,
                reservation.request_digest,
                response=response,
                response_hash=digest,
                audit_receipt_sha256=event.event_hash,
            )
            if fault_hook is not None:
                fault_hook("after_commit")
            return completed
        except DurableIdempotencyError:
            raise
        except PostgresAuditIntegrityError as exc:
            raise StoredResponseIntegrityError(str(exc)) from exc
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable "
                f"({type(exc).__name__})."
            ) from None

    async def fail(self, reservation: DurableReservation) -> None:
        if reservation.kind != "owner":
            raise RuntimeError("Only the reservation owner can record failure.")
        pool = self._require_pool()
        try:
            async with pool.connection() as connection:
                async with connection.transaction():
                    await connection.execute(
                        sql.SQL(
                            """
                            UPDATE {}
                            SET state = 'failed', updated_at = clock_timestamp()
                            WHERE key_digest = %s
                              AND request_digest = %s
                              AND state = 'reserved'
                            """
                        ).format(self.table),
                        (reservation.key_digest, reservation.request_digest),
                    )
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable "
                f"({type(exc).__name__})."
            ) from None

    async def execute(
        self,
        *,
        request_id: str,
        request_digest: str,
        operation: Callable[[], Awaitable[BoundedPredictionRepresentation]],
    ) -> BoundedPredictionRepresentation:
        result = await self.execute_detailed(
            request_id=request_id,
            request_digest=request_digest,
            operation=operation,
        )
        return result.response

    async def execute_detailed(
        self,
        *,
        request_id: str,
        request_digest: str,
        operation: Callable[[], Awaitable[BoundedPredictionRepresentation]],
        fault_hook: Callable[[str], None] | None = None,
    ) -> DurableExecutionResult:
        reservation = await self.reserve(request_id=request_id, request_digest=request_digest)
        if reservation.kind == "completed" and reservation.response is not None:
            if reservation.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Stored audit receipt is missing.")
            return DurableExecutionResult(
                reservation.response, reservation.audit_receipt_sha256, True
            )
        if reservation.kind == "reserved":
            completed = await self.wait_for_reservation(reservation)
            if completed.response is None or completed.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Completed replay is incomplete.")
            return DurableExecutionResult(
                completed.response, completed.audit_receipt_sha256, True
            )
        if reservation.kind == "stale":
            raise StaleReservationError("The durable reservation is stale; retry is refused.")
        if reservation.kind == "failed":
            raise FailedReservationError("The durable reservation previously failed.")
        try:
            response = await operation()
            completed = await self.complete_reservation(
                reservation, response, fault_hook=fault_hook
            )
            if completed.response is None or completed.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Committed response is incomplete.")
            return DurableExecutionResult(
                completed.response, completed.audit_receipt_sha256, False
            )
        except BaseException:
            try:
                await self.fail(reservation)
            except DurableIdempotencyError:
                pass
            raise


__all__ = [
    "DurableIdempotencyConflictError",
    "DurableExecutionResult",
    "DurableReservation",
    "FailedReservationError",
    "PostgresIdempotencyStore",
    "ReservationInProgressError",
    "StaleReservationError",
    "StateStoreUnavailableError",
    "StoredResponseIntegrityError",
    "canonical_response_bytes",
    "idempotency_key_digest",
]
