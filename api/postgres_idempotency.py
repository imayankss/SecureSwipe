"""PostgreSQL-backed score-free idempotency substrate for the future scale profile."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
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
from api.scale_lifecycle_timing import (
    NULL_LIFECYCLE_TIMER,
    EventLoopLagMonitor,
    LifecycleTimer,
    LifecycleTimingAggregator,
    lifecycle_aggregator_from_environment,
)
from api.scale_timing import (
    NULL_TIMER,
    CompletionTimer,
    TimingAggregator,
    aggregator_from_environment,
)
from api.state_store_diagnostic import (
    StageObservation,
    StateStoreDiagnosticAggregator,
    aggregator_from_environment as state_store_diagnostic_from_environment,
)
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
        timing_aggregator: TimingAggregator | None = None,
        lifecycle_timing_aggregator: LifecycleTimingAggregator | None = None,
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
        # Opt-in duration-only diagnostic; None keeps the completion path unchanged.
        self._timing = (
            aggregator_from_environment() if timing_aggregator is None else timing_aggregator
        )
        self._lifecycle_timing = (
            lifecycle_aggregator_from_environment()
            if lifecycle_timing_aggregator is None
            else lifecycle_timing_aggregator
        )
        self._event_loop_monitor = (
            EventLoopLagMonitor(self._lifecycle_timing)
            if self._lifecycle_timing is not None
            else None
        )
        self._state_store_diagnostic = state_store_diagnostic_from_environment()

    @property
    def timing_aggregator(self) -> TimingAggregator | None:
        return self._timing

    @property
    def lifecycle_timing_aggregator(self) -> LifecycleTimingAggregator | None:
        return self._lifecycle_timing

    @property
    def state_store_diagnostic(self) -> StateStoreDiagnosticAggregator | None:
        return self._state_store_diagnostic

    @property
    def table(self) -> sql.Composed:
        return sql.SQL("{}.secureswipe_idempotency").format(sql.Identifier(self.settings.schema))

    def _observe(
        self,
        stage: str,
        pool: AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]] | None = None,
    ) -> StageObservation | None:
        if self._state_store_diagnostic is None:
            return None
        return self._state_store_diagnostic.start(stage, pool)

    @staticmethod
    def _observation_success(observation: StageObservation | None) -> None:
        if observation is not None:
            observation.success()

    @staticmethod
    def _observation_failure(
        observation: StageObservation | None, exc: BaseException
    ) -> None:
        if observation is not None:
            observation.failure(exc)

    @asynccontextmanager
    async def _connection(
        self,
        pool: AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]],
    ) -> AsyncIterator[psycopg.AsyncConnection[dict[str, Any]]]:
        """Observe only acquisition; preserve the pool context manager semantics."""
        if self._state_store_diagnostic is None:
            async with pool.connection() as connection:
                yield connection
            return

        context = pool.connection()
        observation = self._observe("connection_checkout", pool)
        try:
            connection = await context.__aenter__()
        except BaseException as exc:
            self._observation_failure(observation, exc)
            raise
        else:
            self._observation_success(observation)
        try:
            yield connection
        except BaseException as exc:
            suppressed = await context.__aexit__(type(exc), exc, exc.__traceback__)
            if not suppressed:
                raise
        else:
            await context.__aexit__(None, None, None)

    @asynccontextmanager
    async def _transaction(
        self,
        connection: psycopg.AsyncConnection[dict[str, Any]],
        pool: AsyncConnectionPool[psycopg.AsyncConnection[dict[str, Any]]],
    ) -> AsyncIterator[None]:
        """Separate commit/rollback observations only in exact diagnostic mode."""
        if self._state_store_diagnostic is None:
            async with connection.transaction():
                yield
            return

        context = connection.transaction()
        await context.__aenter__()
        try:
            yield
        except BaseException as exc:
            observation = self._observe("rollback", pool)
            try:
                suppressed = await context.__aexit__(type(exc), exc, exc.__traceback__)
            except BaseException as rollback_exc:
                self._observation_failure(observation, rollback_exc)
                raise
            else:
                self._observation_success(observation)
            if not suppressed:
                raise
        else:
            observation = self._observe("commit", pool)
            try:
                await context.__aexit__(None, None, None)
            except BaseException as commit_exc:
                self._observation_failure(observation, commit_exc)
                raise
            else:
                self._observation_success(observation)

    async def open(self) -> None:
        if self._pool is not None:
            return
        observation = self._observe("initialize_open")
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
                        "connect_timeout": max(1, math.ceil(self.settings.connect_timeout_seconds)),
                        "row_factory": dict_row,
                    },
                    open=False,
                ),
            )
            await pool.open(wait=True)
            self._pool = pool
            async with self._connection(pool) as connection:
                await verify_audit_chain(connection, schema=self.settings.schema)
            if self._event_loop_monitor is not None:
                self._event_loop_monitor.start()
            self._observation_success(observation)
        except (
            MigrationError,
            PostgresAuditIntegrityError,
            psycopg.Error,
            PoolTimeout,
            OSError,
        ) as exc:
            self._observation_failure(observation, exc)
            if self._pool is not None:
                await self.close()
            raise StateStoreUnavailableError(
                "The postgres-scale state store is unavailable or incompatible."
            ) from None

    async def close(self) -> None:
        observation = self._observe("close", self._pool)
        if self._event_loop_monitor is not None:
            await self._event_loop_monitor.stop()
        pool, self._pool = self._pool, None
        try:
            if pool is not None:
                await pool.close()
        except BaseException as exc:
            self._observation_failure(observation, exc)
            raise
        else:
            self._observation_success(observation)
        finally:
            if self._state_store_diagnostic is not None:
                self._state_store_diagnostic.flush()

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
            async with self._connection(pool) as connection:
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

    async def reserve(
        self,
        *,
        request_id: str,
        request_digest: str,
        lifecycle_timer: LifecycleTimer = NULL_LIFECYCLE_TIMER,
    ) -> DurableReservation:
        _validate_request_digest(request_digest)
        key_digest = idempotency_key_digest(self.settings.hmac_secret, request_id)
        pool = self._require_pool()
        observation = self._observe("reserve", pool)
        try:
            checkout_started = lifecycle_timer.started_at()
            async with self._connection(pool) as connection:
                lifecycle_timer.observe_elapsed("reservation_pool_checkout_ms", checkout_started)
                transaction_started = lifecycle_timer.started_at()
                async with self._transaction(connection, pool):
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
                        result = DurableReservation("owner", key_digest, request_digest)
                    else:
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
                        result = self._from_row(row, request_digest=request_digest)
                lifecycle_timer.observe_elapsed("reservation_transaction_ms", transaction_started)
                self._observation_success(observation)
                return result
        except DurableIdempotencyError as exc:
            self._observation_failure(observation, exc)
            raise
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            self._observation_failure(observation, exc)
            raise StateStoreUnavailableError(
                f"The postgres-scale state store is unavailable ({type(exc).__name__})."
            ) from None

    async def _read(self, *, key_digest: str, request_digest: str) -> DurableReservation:
        pool = self._require_pool()
        observation = self._observe("complete_outcome", pool)
        try:
            async with self._connection(pool) as connection:
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
            result = self._from_row(row, request_digest=request_digest)
            self._observation_success(observation)
            return result
        except DurableIdempotencyError as exc:
            self._observation_failure(observation, exc)
            raise
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            self._observation_failure(observation, exc)
            raise StateStoreUnavailableError(
                f"The postgres-scale state store is unavailable ({type(exc).__name__})."
            ) from None

    async def wait_for_resolution(
        self, reservation: DurableReservation
    ) -> BoundedPredictionRepresentation:
        completed = await self.wait_for_reservation(reservation)
        if completed.response is None:
            raise StoredResponseIntegrityError("Stored bounded response is missing.")
        return completed.response

    async def wait_for_reservation(self, reservation: DurableReservation) -> DurableReservation:
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
        completed = await self.complete_reservation(reservation, response, fault_hook=fault_hook)
        if completed.response is None:
            raise StoredResponseIntegrityError("Committed bounded response is missing.")
        return completed.response

    async def complete_reservation(
        self,
        reservation: DurableReservation,
        response: BoundedPredictionRepresentation,
        *,
        fault_hook: Callable[[str], None] | None = None,
        lifecycle_timer: LifecycleTimer = NULL_LIFECYCLE_TIMER,
    ) -> DurableReservation:
        if reservation.kind != "owner":
            raise RuntimeError("Only the reservation owner can complete work.")
        serialization_started = lifecycle_timer.started_at()
        document = response.model_dump(mode="json", by_alias=True)
        _validate_response_keys(document)
        digest = response_sha256(response)
        lifecycle_timer.observe_elapsed("bounded_response_serialize_ms", serialization_started)
        pool = self._require_pool()

        def lifecycle_observer(duration: float) -> None:
            lifecycle_timer.observe_duration("completion_transaction_ms", duration)

        timer = (
            CompletionTimer(self._timing, completion_observer=lifecycle_observer)
            if self._timing is not None or lifecycle_timer is not NULL_LIFECYCLE_TIMER
            else NULL_TIMER
        )
        try:
            observation = self._observe("complete_outcome", pool)
            checkout_started = lifecycle_timer.started_at()
            async with self._connection(pool) as connection:
                lifecycle_timer.observe_elapsed("completion_pool_checkout_ms", checkout_started)
                async with self._transaction(connection, pool):
                    timer.at("transaction_open")
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
                    timer.at("idempotency_locked")
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

                    timer.at("head_lock_requested")
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
                    timer.at("head_locked")
                    if head is None:
                        raise PostgresAuditIntegrityError("The seeded audit chain head is missing.")
                    event = build_audit_event(
                        chain_id=str(head["chain_id"]),
                        sequence=int(head["last_sequence"]) + 1,
                        previous_hash=str(head["last_hash"]),
                        key_digest=reservation.key_digest,
                        request_digest=reservation.request_digest,
                        response=response,
                        occurred_at=datetime.now(timezone.utc),
                    )
                    timer.at("event_built")
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
                    timer.at("event_inserted")
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
                    timer.at("idempotency_updated")
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
                    timer.at("head_updated")
                    if head_update.rowcount != 1:
                        raise PostgresAuditIntegrityError(
                            "The audit chain head changed unexpectedly."
                        )
                    if fault_hook is not None:
                        fault_hook("before_commit")
                # The transaction context manager commits on exit, so the commit
                # cost is only observable once this block has closed.
                timer.at("committed")
                timer.submit()
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
            self._observation_success(observation)
            return completed
        except DurableIdempotencyError as exc:
            self._observation_failure(observation, exc)
            raise
        except PostgresAuditIntegrityError as exc:
            self._observation_failure(observation, exc)
            raise StoredResponseIntegrityError(str(exc)) from exc
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            self._observation_failure(observation, exc)
            raise StateStoreUnavailableError(
                f"The postgres-scale state store is unavailable ({type(exc).__name__})."
            ) from None

    async def fail(self, reservation: DurableReservation) -> None:
        if reservation.kind != "owner":
            raise RuntimeError("Only the reservation owner can record failure.")
        pool = self._require_pool()
        observation = self._observe("complete_outcome", pool)
        try:
            async with self._connection(pool) as connection:
                async with self._transaction(connection, pool):
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
            self._observation_success(observation)
        except (psycopg.Error, PoolTimeout, OSError) as exc:
            self._observation_failure(observation, exc)
            raise StateStoreUnavailableError(
                f"The postgres-scale state store is unavailable ({type(exc).__name__})."
            ) from None

    async def execute(
        self,
        *,
        request_id: str,
        request_digest: str,
        operation: Callable[[], Awaitable[BoundedPredictionRepresentation]],
        lifecycle_timer: LifecycleTimer = NULL_LIFECYCLE_TIMER,
    ) -> BoundedPredictionRepresentation:
        result = await self.execute_detailed(
            request_id=request_id,
            request_digest=request_digest,
            operation=operation,
            lifecycle_timer=lifecycle_timer,
        )
        return result.response

    async def execute_detailed(
        self,
        *,
        request_id: str,
        request_digest: str,
        operation: Callable[[], Awaitable[BoundedPredictionRepresentation]],
        fault_hook: Callable[[str], None] | None = None,
        lifecycle_timer: LifecycleTimer = NULL_LIFECYCLE_TIMER,
    ) -> DurableExecutionResult:
        try:
            reservation = await self.reserve(
                request_id=request_id,
                request_digest=request_digest,
                lifecycle_timer=lifecycle_timer,
            )
        except DurableIdempotencyError:
            lifecycle_timer.classify("pending_fail_closed")
            raise
        outcome_started = lifecycle_timer.started_at()
        if reservation.kind == "completed" and reservation.response is not None:
            if reservation.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Stored audit receipt is missing.")
            lifecycle_timer.classify("completed_replay")
            lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
            return DurableExecutionResult(
                reservation.response, reservation.audit_receipt_sha256, True
            )
        if reservation.kind == "reserved":
            try:
                completed = await self.wait_for_reservation(reservation)
            except DurableIdempotencyError:
                lifecycle_timer.classify("pending_fail_closed")
                lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
                raise
            if completed.response is None or completed.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Completed replay is incomplete.")
            lifecycle_timer.classify("completed_replay")
            lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
            return DurableExecutionResult(completed.response, completed.audit_receipt_sha256, True)
        if reservation.kind == "stale":
            lifecycle_timer.classify("pending_fail_closed")
            lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
            raise StaleReservationError("The durable reservation is stale; retry is refused.")
        if reservation.kind == "failed":
            lifecycle_timer.classify("pending_fail_closed")
            lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
            raise FailedReservationError("The durable reservation previously failed.")
        lifecycle_timer.classify("owner")
        lifecycle_timer.observe_elapsed("reservation_outcome_handling_ms", outcome_started)
        try:
            response = await operation()
            completed = await self.complete_reservation(
                reservation,
                response,
                fault_hook=fault_hook,
                lifecycle_timer=lifecycle_timer,
            )
            if completed.response is None or completed.audit_receipt_sha256 is None:
                raise StoredResponseIntegrityError("Committed response is incomplete.")
            return DurableExecutionResult(completed.response, completed.audit_receipt_sha256, False)
        except BaseException:
            lifecycle_timer.discard()
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
