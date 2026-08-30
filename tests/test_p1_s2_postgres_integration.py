"""Real PostgreSQL 16 integration checks for the isolated P1-S2 substrate."""

from __future__ import annotations

import asyncio
import hashlib
import multiprocessing
import os
import queue
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from api.main import ApiSettings, create_app
from api.postgres_idempotency import (
    DurableIdempotencyConflictError,
    FailedReservationError,
    PostgresIdempotencyStore,
    ReservationInProgressError,
    StaleReservationError,
    StateStoreUnavailableError,
    canonical_response_bytes,
)
from api.postgres_migrations import (
    DEFAULT_MIGRATION_DIRECTORY,
    MigrationError,
    MigrationIntegrityError,
    run_migrations,
)
from api.scale_config import PostgresScaleSettings, validate_test_dsn
from api.scale_response import (
    BoundedModelProvenance,
    BoundedPolicyProvenance,
    BoundedPredictionRepresentation,
    BoundedSchemaProvenance,
)
from api.service import ModelService
from src.preprocessing.feature_config import ALL_FEATURES

_SCHEMA_PREFIX = "secureswipe_s2_test_"
_SECRET = b"p1-s2-integration-hmac-secret-value"


def _dsn() -> str:
    value = os.getenv("SECURESWIPE_TEST_POSTGRES_DSN", "")
    if not value:
        pytest.skip("SECURESWIPE_TEST_POSTGRES_DSN is not configured")
    validate_test_dsn(value)
    return value


def _schema(label: str) -> str:
    return f"{_SCHEMA_PREFIX}{label}_{uuid.uuid4().hex[:12]}"


def _settings(dsn: str, schema: str, *, pool_max_size: int = 4) -> PostgresScaleSettings:
    return PostgresScaleSettings(
        dsn=dsn,
        schema=schema,
        hmac_secret=_SECRET,
        pool_min_size=1,
        pool_max_size=pool_max_size,
        connect_timeout_seconds=2.0,
    )


def _bounded_response() -> BoundedPredictionRepresentation:
    return BoundedPredictionRepresentation(
        decision="human_review",
        model=BoundedModelProvenance(
            model_version="synthetic-scale-test-1",
            bundle_format_version="3",
            model_artifact_sha256="a" * 64,
            training_data_fingerprint="b" * 64,
            evidence_category="synthetic_demo_inference",
            historical_taint=False,
            decision_eligible=False,
            historical_metrics_claimed=False,
            evaluation_performed=False,
        ),
        policy=BoundedPolicyProvenance(
            producer_policy="synthetic_api_smoke_v1",
            producer_policy_sha256="c" * 64,
            operating_threshold=0.53,
            threshold_source="synthetic_reference",
            threshold_model_linkage="reference_only",
            threshold_purpose="demo_review_routing",
            threshold_calibrated=False,
            threshold_cost_optimal=False,
            threshold_razorpay_approved=False,
            threshold_production_approved=False,
        ),
        schema=BoundedSchemaProvenance(feature_schema_sha256="d" * 64),
    )


async def _drop_schema(dsn: str, schema: str) -> None:
    if not schema.startswith(_SCHEMA_PREFIX):
        raise RuntimeError("Refusing to drop a schema not owned by this test module.")
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        await connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )
    finally:
        await connection.close()


def _process_reservation_worker(
    dsn: str,
    schema: str,
    shared_counter: Any,
    barrier: Any,
    results: Any,
) -> None:
    async def run() -> None:
        store = PostgresIdempotencyStore(
            _settings(dsn, schema),
            wait_timeout_seconds=10.0,
            poll_interval_seconds=0.01,
        )
        await store.open()
        try:
            await asyncio.to_thread(barrier.wait)

            async def one_attempt() -> bytes:
                async def score_once() -> BoundedPredictionRepresentation:
                    with shared_counter.get_lock():
                        shared_counter.value += 1
                    await asyncio.sleep(0.15)
                    return _bounded_response()

                response = await store.execute(
                    request_id="p1-s2-sixty-four-identical",
                    request_digest="e" * 64,
                    operation=score_once,
                )
                return canonical_response_bytes(response)

            completed = await asyncio.gather(*(one_attempt() for _ in range(16)))
            results.put(("ok", [hashlib.sha256(item).hexdigest() for item in completed]))
        except BaseException as exc:
            results.put(("error", type(exc).__name__, str(exc)))
        finally:
            await store.close()

    asyncio.run(run())


def test_migrations_are_forward_only_idempotent_checksum_verified_and_locked(
    tmp_path: Path,
) -> None:
    dsn = _dsn()
    schema = _schema("migration")

    async def exercise() -> None:
        try:
            first, second = await asyncio.gather(
                run_migrations(dsn=dsn, schema=schema, apply=True),
                run_migrations(dsn=dsn, schema=schema, apply=True),
            )
            assert sorted((first, second), key=len) == [(), (1, 2)]
            assert await run_migrations(dsn=dsn, schema=schema, apply=False) == ()

            altered = tmp_path / "altered"
            altered.mkdir()
            original = DEFAULT_MIGRATION_DIRECTORY / "0001_durable_idempotency.sql"
            (altered / original.name).write_bytes(original.read_bytes() + b"\n-- changed\n")
            second_migration = (
                DEFAULT_MIGRATION_DIRECTORY / "0002_transactional_audit_chain.sql"
            )
            (altered / second_migration.name).write_bytes(second_migration.read_bytes())
            with pytest.raises(MigrationIntegrityError, match="checksum mismatch"):
                await run_migrations(
                    dsn=dsn,
                    schema=schema,
                    apply=False,
                    migration_directory=altered,
                )
        finally:
            await _drop_schema(dsn, schema)

    asyncio.run(exercise())


def test_migration_failure_rolls_back_only_the_failed_version(tmp_path: Path) -> None:
    dsn = _dsn()
    schema = _schema("rollback")

    async def exercise() -> None:
        migrations = tmp_path / "rollback"
        migrations.mkdir()
        original = DEFAULT_MIGRATION_DIRECTORY / "0001_durable_idempotency.sql"
        (migrations / original.name).write_bytes(original.read_bytes())
        (migrations / "0002_injected_failure.sql").write_text(
            "CREATE TABLE must_rollback (id integer); SELECT definitely_invalid_syntax;\n",
            encoding="utf-8",
        )
        try:
            with pytest.raises(MigrationError, match="operation failed"):
                await run_migrations(
                    dsn=dsn,
                    schema=schema,
                    apply=True,
                    migration_directory=migrations,
                )
            connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
            try:
                cursor = await connection.execute(
                    sql.SQL(
                        "SELECT version FROM {}.secureswipe_schema_migrations WHERE version = 2"
                    ).format(sql.Identifier(schema))
                )
                assert await cursor.fetchone() is None
                cursor = await connection.execute(
                    "SELECT to_regclass(%s)", (f"{schema}.must_rollback",)
                )
                assert (await cursor.fetchone())[0] is None
            finally:
                await connection.close()
        finally:
            await _drop_schema(dsn, schema)

    asyncio.run(exercise())


def test_database_newer_than_code_is_rejected() -> None:
    dsn = _dsn()
    schema = _schema("newer")

    async def exercise() -> None:
        try:
            await run_migrations(dsn=dsn, schema=schema, apply=True)
            connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
            try:
                await connection.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}.secureswipe_schema_migrations
                            (version, name, checksum_sha256)
                        VALUES (3, 'future', %s)
                        """
                    ).format(sql.Identifier(schema)),
                    ("f" * 64,),
                )
            finally:
                await connection.close()
            with pytest.raises(MigrationIntegrityError, match="newer"):
                await run_migrations(dsn=dsn, schema=schema, apply=False)
        finally:
            await _drop_schema(dsn, schema)

    asyncio.run(exercise())


def test_64_identical_concurrent_reservations_across_processes_complete_once() -> None:
    dsn = _dsn()
    schema = _schema("multiprocess")

    async def prepare() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)

    asyncio.run(prepare())
    context = multiprocessing.get_context("spawn")
    counter = context.Value("i", 0)
    barrier = context.Barrier(4)
    results = context.Queue()
    processes = [
        context.Process(
            target=_process_reservation_worker,
            args=(dsn, schema, counter, barrier, results),
        )
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert not process.is_alive()
            assert process.exitcode == 0
        messages = []
        for _ in processes:
            try:
                messages.append(results.get(timeout=5))
            except queue.Empty as exc:
                raise AssertionError("A reservation worker returned no result.") from exc
        assert all(message[0] == "ok" for message in messages), messages
        hashes = [item for _, process_hashes in messages for item in process_hashes]
        assert len(hashes) == 64
        assert len(set(hashes)) == 1
        assert counter.value == 1

        async def verify_row() -> None:
            connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
            try:
                cursor = await connection.execute(
                    sql.SQL(
                        "SELECT state, count(*) OVER () FROM {}.secureswipe_idempotency"
                    ).format(sql.Identifier(schema))
                )
                assert await cursor.fetchall() == [("completed", 1)]
            finally:
                await connection.close()

        asyncio.run(verify_row())
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        asyncio.run(_drop_schema(dsn, schema))


def test_conflict_restart_replay_and_exact_response() -> None:
    dsn = _dsn()
    schema = _schema("replay")

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        first_store = PostgresIdempotencyStore(_settings(dsn, schema))
        await first_store.open()
        try:
            owner = await first_store.reserve(
                request_id="restart-replay", request_digest="1" * 64
            )
            assert owner.kind == "owner"
            expected = await first_store.complete(owner, _bounded_response())
            with pytest.raises(DurableIdempotencyConflictError):
                await first_store.reserve(
                    request_id="restart-replay", request_digest="2" * 64
                )
        finally:
            await first_store.close()

        restarted = PostgresIdempotencyStore(_settings(dsn, schema))
        await restarted.open()
        try:
            replay = await restarted.reserve(
                request_id="restart-replay", request_digest="1" * 64
            )
            assert replay.kind == "completed"
            assert replay.response is not None
            assert canonical_response_bytes(replay.response) == canonical_response_bytes(expected)
        finally:
            await restarted.close()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_reserved_stale_and_failed_states_remain_fail_closed() -> None:
    dsn = _dsn()
    schema = _schema("states")

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(
            _settings(dsn, schema),
            reservation_ttl_seconds=0.1,
            retention_seconds=10,
            wait_timeout_seconds=0.03,
            poll_interval_seconds=0.005,
        )
        await store.open()
        try:
            owner = await store.reserve(request_id="in-progress", request_digest="3" * 64)
            observed = await store.reserve(
                request_id="in-progress", request_digest="3" * 64
            )
            assert owner.kind == "owner" and observed.kind == "reserved"
            with pytest.raises(ReservationInProgressError):
                await store.wait_for_resolution(observed)
            await asyncio.sleep(0.11)
            stale = await store.reserve(request_id="in-progress", request_digest="3" * 64)
            assert stale.kind == "stale"
            with pytest.raises(StaleReservationError):
                await store.execute(
                    request_id="in-progress",
                    request_digest="3" * 64,
                    operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                )

            failed_owner = await store.reserve(request_id="failed", request_digest="4" * 64)
            await store.fail(failed_owner)
            failed = await store.reserve(request_id="failed", request_digest="4" * 64)
            assert failed.kind == "failed"
            with pytest.raises(FailedReservationError):
                await store.execute(
                    request_id="failed",
                    request_digest="4" * 64,
                    operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                )
        finally:
            await store.close()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_unavailable_store_fails_closed_without_secret_disclosure() -> None:
    settings = PostgresScaleSettings(
        dsn="postgresql://user:private-value@127.0.0.1:1/secureswipe_p1_scale_test",  # trufflehog:ignore — intentionally invalid unreachable test fixture; no real credential
        schema=_schema("unavailable"),
        hmac_secret=_SECRET,
        connect_timeout_seconds=0.1,
    )

    async def exercise() -> None:
        store = PostgresIdempotencyStore(settings)
        with pytest.raises(StateStoreUnavailableError) as caught:
            await store.open()
        assert "private-value" not in str(caught.value)

    asyncio.run(exercise())


def test_real_postgres_profile_keeps_v1_prediction_entry_points_unavailable(
    tmp_path: Path,
) -> None:
    dsn = _dsn()
    schema = _schema("api_gate")

    async def prepare() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)

    asyncio.run(prepare())
    settings = ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
        state_backend="postgres-scale",
        postgres_scale=_settings(dsn, schema),
    )
    payload = {feature: 0.0 for feature in ALL_FEATURES}
    try:
        with TestClient(create_app(service=ModelService(), settings=settings)) as client:
            ready = client.get("/health/ready")
            single = client.post(
                "/v1/predict",
                json=payload,
                headers={"X-Request-ID": "scale-api-gate-single"},
            )
            batch = client.post(
                "/v1/predict/batch",
                json={"transactions": [payload]},
                headers={"X-Request-ID": "scale-api-gate-batch"},
            )
            assert client.app.state.idempotency_registry is None
        assert ready.status_code == 503 and ready.json()["status"] == "not_ready"
        for response in (single, batch):
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "scale_profile_requires_v2"
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_table_and_rows_contain_only_allowlisted_score_free_state() -> None:
    dsn = _dsn()
    schema = _schema("privacy")
    plaintext_request_id = "plaintext-id-must-not-persist"
    payload_sentinel = "raw-payload-sentinel-987654321"

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()
        try:
            owner = await store.reserve(
                request_id=plaintext_request_id,
                request_digest=hashlib.sha256(payload_sentinel.encode()).hexdigest(),
            )
            await store.complete(owner, _bounded_response())
        finally:
            await store.close()

        connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            cursor = await connection.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'secureswipe_idempotency'
                ORDER BY ordinal_position
                """,
                (schema,),
            )
            columns = [str(row[0]) for row in await cursor.fetchall()]
            assert columns == [
                "key_digest",
                "request_digest",
                "state",
                "created_at",
                "updated_at",
                "reservation_expires_at",
                "retention_until",
                "completed_at",
                "response_document",
                "response_sha256",
                "audit_receipt_sha256",
            ]
            cursor = await connection.execute(
                sql.SQL("SELECT row_to_json(value)::text FROM {} AS value").format(
                    sql.Identifier(schema, "secureswipe_idempotency")
                )
            )
            encoded = "\n".join(str(row[0]) for row in await cursor.fetchall())
        finally:
            await connection.close()

        for forbidden in (
            plaintext_request_id,
            payload_sentinel,
            "raw_score",
            "decision_score",
            "calibrated_probability",
            '"score"',
            '"score_type"',
            '"features"',
            '"payload"',
            "0.731",
        ):
            assert forbidden not in encoded

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))
