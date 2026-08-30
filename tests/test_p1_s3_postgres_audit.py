"""P1-S3 correctness tests against the dedicated local PostgreSQL boundary."""

from __future__ import annotations

import asyncio
import hashlib
import multiprocessing
import os
import queue
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.rows import tuple_row

from api.main import ApiSettings, create_app
from api.postgres_audit import PostgresAuditIntegrityError, verify_audit_chain
from api.postgres_idempotency import (
    DurableIdempotencyConflictError,
    PostgresIdempotencyStore,
    ReservationInProgressError,
    canonical_response_bytes,
)
from api.postgres_migrations import MigrationIntegrityError, run_migrations
from api.scale_config import PostgresScaleSettings, validate_test_dsn
from api.scale_response import (
    BoundedModelProvenance,
    BoundedPolicyProvenance,
    BoundedPredictionRepresentation,
    BoundedSchemaProvenance,
)
from api.schemas import TransactionFeatures
from api.service import ModelService
from src.preprocessing.feature_config import ALL_FEATURES
from tests.synthetic_bundle import build_synthetic_serving_bundle

_SCHEMA_PREFIX = "secureswipe_s3_test_"
_ROLE_PREFIX = "secureswipe_s3_app_"
_SECRET = b"p1-s3-integration-hmac-secret-value"


def _admin_dsn() -> str:
    value = os.getenv("SECURESWIPE_TEST_POSTGRES_DSN", "")
    if not value:
        pytest.skip("SECURESWIPE_TEST_POSTGRES_DSN is not configured")
    validate_test_dsn(value)
    return value


def _schema(label: str) -> str:
    return f"{_SCHEMA_PREFIX}{label}_{uuid.uuid4().hex[:10]}"


def _settings(
    dsn: str, schema: str, *, pool_max_size: int = 16
) -> PostgresScaleSettings:
    return PostgresScaleSettings(
        dsn=dsn,
        schema=schema,
        hmac_secret=_SECRET,
        pool_min_size=1,
        pool_max_size=pool_max_size,
        connect_timeout_seconds=2.0,
    )


def _dsn_for_role(dsn: str, role: str) -> str:
    parsed = urlsplit(dsn)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, f"{role}@{host}", parsed.path, "", ""))


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
        raise RuntimeError("Refusing to drop a schema not owned by P1-S3 tests.")
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        await connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )
    finally:
        await connection.close()


async def _counts(dsn: str, schema: str) -> tuple[int, int, int, int]:
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        cursor = await connection.execute(
            sql.SQL(
                """
                SELECT
                    (SELECT count(*) FROM {}.secureswipe_idempotency
                     WHERE state = 'completed'),
                    (SELECT count(*) FROM {}.audit_events),
                    (SELECT last_sequence FROM {}.audit_chain_heads
                     WHERE chain_id = 'primary'),
                    (SELECT count(DISTINCT audit_receipt_sha256)
                     FROM {}.secureswipe_idempotency WHERE state = 'completed')
                """
            ).format(*[sql.Identifier(schema) for _ in range(4)])
        )
        row = await cursor.fetchone()
        assert row is not None
        return tuple(int(value) for value in row)  # type: ignore[return-value]
    finally:
        await connection.close()


def _identical_worker(
    dsn: str,
    schema: str,
    shared_counter: Any,
    barrier: Any,
    results: Any,
) -> None:
    async def run() -> None:
        store = PostgresIdempotencyStore(
            _settings(dsn, schema, pool_max_size=4),
            wait_timeout_seconds=15.0,
            poll_interval_seconds=0.01,
        )
        await store.open()
        try:
            await asyncio.to_thread(barrier.wait)

            async def attempt() -> tuple[str, str]:
                async def score_once() -> BoundedPredictionRepresentation:
                    with shared_counter.get_lock():
                        shared_counter.value += 1
                    await asyncio.sleep(0.15)
                    return _bounded_response()

                completed = await store.execute_detailed(
                    request_id="p1-s3-sixty-four-identical",
                    request_digest="e" * 64,
                    operation=score_once,
                )
                return (
                    hashlib.sha256(canonical_response_bytes(completed.response)).hexdigest(),
                    completed.audit_receipt_sha256,
                )

            results.put(("ok", await asyncio.gather(*(attempt() for _ in range(16)))))
        except BaseException as exc:
            results.put(("error", type(exc).__name__, str(exc)))
        finally:
            await store.close()

    asyncio.run(run())


def _crash_worker(dsn: str, schema: str, boundary: str, counter: Any) -> None:
    async def run() -> None:
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()

        async def score_once() -> BoundedPredictionRepresentation:
            with counter.get_lock():
                counter.value += 1
            return _bounded_response()

        def crash_at(current: str) -> None:
            if current == boundary:
                os._exit(91)

        await store.execute_detailed(
            request_id=f"p1-s3-crash-{boundary}",
            request_digest="f" * 64,
            operation=score_once,
            fault_hook=crash_at,
        )

    asyncio.run(run())


def test_64_distinct_concurrent_completions_are_contiguous_and_valid() -> None:
    dsn = _admin_dsn()
    schema = _schema("distinct")

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()
        try:
            completed = await asyncio.gather(
                *(
                    store.execute_detailed(
                        request_id=f"distinct-{index:02d}",
                        request_digest=hashlib.sha256(
                            f"distinct-body-{index:02d}".encode()
                        ).hexdigest(),
                        operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                    )
                    for index in range(64)
                )
            )
            assert len({item.audit_receipt_sha256 for item in completed}) == 64
        finally:
            await store.close()
        assert await _counts(dsn, schema) == (64, 64, 64, 64)
        connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            verified = await verify_audit_chain(connection, schema=schema)
            assert verified.event_count == 64
        finally:
            await connection.close()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_64_identical_across_processes_score_and_append_once() -> None:
    dsn = _admin_dsn()
    schema = _schema("identical")
    asyncio.run(run_migrations(dsn=dsn, schema=schema, apply=True))
    context = multiprocessing.get_context("spawn")
    counter = context.Value("i", 0)
    barrier = context.Barrier(4)
    results = context.Queue()
    processes = [
        context.Process(
            target=_identical_worker,
            args=(dsn, schema, counter, barrier, results),
        )
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=45)
            assert not process.is_alive()
            assert process.exitcode == 0
        messages = []
        for _ in processes:
            try:
                messages.append(results.get(timeout=5))
            except queue.Empty as exc:
                raise AssertionError("A P1-S3 worker returned no result.") from exc
        assert all(message[0] == "ok" for message in messages), messages
        pairs = [pair for _, worker_pairs in messages for pair in worker_pairs]
        assert len(pairs) == 64
        assert len(set(pairs)) == 1
        assert counter.value == 1
        assert asyncio.run(_counts(dsn, schema)) == (1, 1, 1, 1)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        asyncio.run(_drop_schema(dsn, schema))


def test_conflict_restart_and_exact_original_receipt() -> None:
    dsn = _admin_dsn()
    schema = _schema("restart")

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        first = PostgresIdempotencyStore(_settings(dsn, schema))
        await first.open()
        try:
            completed = await first.execute_detailed(
                request_id="restart-key",
                request_digest="1" * 64,
                operation=lambda: asyncio.sleep(0, result=_bounded_response()),
            )
            with pytest.raises(DurableIdempotencyConflictError):
                await first.execute_detailed(
                    request_id="restart-key",
                    request_digest="2" * 64,
                    operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                )
        finally:
            await first.close()
        restarted = PostgresIdempotencyStore(_settings(dsn, schema))
        await restarted.open()
        replay_calls = 0
        try:
            async def must_not_score() -> BoundedPredictionRepresentation:
                nonlocal replay_calls
                replay_calls += 1
                return _bounded_response()

            replay = await restarted.execute_detailed(
                request_id="restart-key",
                request_digest="1" * 64,
                operation=must_not_score,
            )
        finally:
            await restarted.close()
        assert replay_calls == 0
        assert replay.replayed is True
        assert replay.audit_receipt_sha256 == completed.audit_receipt_sha256
        assert canonical_response_bytes(replay.response) == canonical_response_bytes(
            completed.response
        )
        assert await _counts(dsn, schema) == (1, 1, 1, 1)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


@pytest.mark.parametrize("boundary", ["before_commit", "after_commit"])
def test_process_crash_boundaries_are_fail_closed_and_replayable(boundary: str) -> None:
    dsn = _admin_dsn()
    schema = _schema(f"crash_{boundary}")
    asyncio.run(run_migrations(dsn=dsn, schema=schema, apply=True))
    context = multiprocessing.get_context("spawn")
    counter = context.Value("i", 0)
    process = context.Process(target=_crash_worker, args=(dsn, schema, boundary, counter))
    try:
        process.start()
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 91
        assert counter.value == 1
        counts = asyncio.run(_counts(dsn, schema))
        if boundary == "before_commit":
            assert counts == (0, 0, 0, 0)

            async def assert_no_false_replay() -> None:
                store = PostgresIdempotencyStore(
                    _settings(dsn, schema), wait_timeout_seconds=0.05
                )
                await store.open()
                try:
                    with pytest.raises(ReservationInProgressError):
                        await store.execute_detailed(
                            request_id="p1-s3-crash-before_commit",
                            request_digest="f" * 64,
                            operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                        )
                finally:
                    await store.close()

            asyncio.run(assert_no_false_replay())
        else:
            assert counts == (1, 1, 1, 1)

            async def assert_exact_replay() -> None:
                store = PostgresIdempotencyStore(_settings(dsn, schema))
                await store.open()
                calls = 0
                try:
                    async def must_not_score() -> BoundedPredictionRepresentation:
                        nonlocal calls
                        calls += 1
                        return _bounded_response()

                    replay = await store.execute_detailed(
                        request_id="p1-s3-crash-after_commit",
                        request_digest="f" * 64,
                        operation=must_not_score,
                    )
                    assert replay.replayed is True
                    assert len(replay.audit_receipt_sha256) == 64
                    assert calls == 0
                finally:
                    await store.close()

            asyncio.run(assert_exact_replay())
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        asyncio.run(_drop_schema(dsn, schema))


@pytest.mark.parametrize("corruption", ["mutation", "deletion", "reordering"])
def test_explicit_verifier_rejects_event_corruption(corruption: str) -> None:
    dsn = _admin_dsn()
    schema = _schema(corruption)

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()
        try:
            for index in range(3):
                await store.execute_detailed(
                    request_id=f"tamper-{index}",
                    request_digest=hashlib.sha256(f"tamper-{index}".encode()).hexdigest(),
                    operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                )
        finally:
            await store.close()
        connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            assert (await verify_audit_chain(connection, schema=schema)).event_count == 3
            if corruption == "mutation":
                await connection.execute(
                    sql.SQL(
                        "UPDATE {}.audit_events SET decision = 'below_review_threshold' "
                        "WHERE sequence = 2"
                    ).format(sql.Identifier(schema))
                )
            elif corruption == "deletion":
                await connection.execute(
                    sql.SQL(
                        "ALTER TABLE {}.secureswipe_idempotency "
                        "DROP CONSTRAINT secureswipe_completion_event_fk"
                    ).format(sql.Identifier(schema))
                )
                await connection.execute(
                    sql.SQL("DELETE FROM {}.audit_events WHERE sequence = 2").format(
                        sql.Identifier(schema)
                    )
                )
            else:
                table = sql.Identifier(schema, "audit_events")
                await connection.execute(
                    sql.SQL("UPDATE {} SET sequence = 101 WHERE sequence = 1").format(table)
                )
                await connection.execute(
                    sql.SQL("UPDATE {} SET sequence = 102 WHERE sequence = 2").format(table)
                )
                await connection.execute(
                    sql.SQL("UPDATE {} SET sequence = 2 WHERE sequence = 101").format(table)
                )
                await connection.execute(
                    sql.SQL("UPDATE {} SET sequence = 1 WHERE sequence = 102").format(table)
                )
            with pytest.raises(PostgresAuditIntegrityError):
                await verify_audit_chain(connection, schema=schema)
        finally:
            await connection.close()

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_append_path_never_calls_full_chain_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dsn = _admin_dsn()
    schema = _schema("bounded_append")

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()

        async def forbidden_verifier(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise AssertionError("Normal append invoked the full-chain verifier.")

        monkeypatch.setattr(
            "api.postgres_idempotency.verify_audit_chain", forbidden_verifier
        )
        try:
            await store.execute_detailed(
                request_id="bounded-append",
                request_digest="3" * 64,
                operation=lambda: asyncio.sleep(0, result=_bounded_response()),
            )
        finally:
            await store.close()
        assert await _counts(dsn, schema) == (1, 1, 1, 1)

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_application_role_has_append_only_event_privileges() -> None:
    admin_dsn = _admin_dsn()
    schema = _schema("privileges")
    role = f"{_ROLE_PREFIX}{uuid.uuid4().hex[:10]}"

    async def exercise() -> None:
        admin = await psycopg.AsyncConnection.connect(admin_dsn, autocommit=True)
        try:
            await admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(role)
                )
            )
        finally:
            await admin.close()
        app_dsn = _dsn_for_role(admin_dsn, role)
        try:
            await run_migrations(
                dsn=admin_dsn,
                schema=schema,
                apply=True,
                application_role=role,
            )
            await run_migrations(dsn=app_dsn, schema=schema, apply=False)
            store = PostgresIdempotencyStore(_settings(app_dsn, schema))
            await store.open()
            try:
                await store.execute_detailed(
                    request_id="app-role-append",
                    request_digest="4" * 64,
                    operation=lambda: asyncio.sleep(0, result=_bounded_response()),
                )
            finally:
                await store.close()
            app = await psycopg.AsyncConnection.connect(app_dsn, autocommit=True)
            try:
                cursor = await app.execute(
                    """
                    SELECT
                        has_table_privilege(current_user, %s, 'INSERT'),
                        has_table_privilege(current_user, %s, 'UPDATE'),
                        has_table_privilege(current_user, %s, 'DELETE')
                    """,
                    tuple(f"{schema}.audit_events" for _ in range(3)),
                )
                assert await cursor.fetchone() == (True, False, False)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    await app.execute(
                        sql.SQL("DELETE FROM {}.audit_events").format(
                            sql.Identifier(schema)
                        )
                    )
            finally:
                await app.close()
        finally:
            await _drop_schema(admin_dsn, schema)
            admin = await psycopg.AsyncConnection.connect(admin_dsn, autocommit=True)
            try:
                await admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
            finally:
                await admin.close()

    asyncio.run(exercise())


def test_migration_refuses_owner_as_application_role() -> None:
    dsn = _admin_dsn()
    schema = _schema("role_separation")

    async def exercise() -> None:
        connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            cursor = await connection.execute("SELECT current_user")
            row = await cursor.fetchone()
            assert row is not None
            current_role = str(row[0])
        finally:
            await connection.close()
        with pytest.raises(MigrationIntegrityError, match="must be separate"):
            await run_migrations(
                dsn=dsn,
                schema=schema,
                apply=True,
                application_role=current_role,
            )

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_database_privacy_and_transactional_consistency() -> None:
    dsn = _admin_dsn()
    schema = _schema("privacy")
    plaintext_id = "plaintext-request-id-must-not-persist"
    payload_sentinel = "raw-payload-sentinel-987654321"

    async def exercise() -> None:
        await run_migrations(dsn=dsn, schema=schema, apply=True)
        store = PostgresIdempotencyStore(_settings(dsn, schema))
        await store.open()
        try:
            await store.execute_detailed(
                request_id=plaintext_id,
                request_digest=hashlib.sha256(payload_sentinel.encode()).hexdigest(),
                operation=lambda: asyncio.sleep(0, result=_bounded_response()),
            )
        finally:
            await store.close()
        connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
        try:
            assert (await verify_audit_chain(connection, schema=schema)).event_count == 1
            connection.row_factory = tuple_row
            cursor = await connection.execute(
                sql.SQL(
                    """
                    SELECT row_to_json(value)::text
                    FROM (
                        SELECT * FROM {}.secureswipe_idempotency
                        UNION ALL
                        SELECT key_digest, request_digest, 'completed', occurred_at,
                               occurred_at, occurred_at, occurred_at, occurred_at,
                               bounded_response, response_sha256, event_hash
                        FROM {}.audit_events
                    ) AS value
                    """
                ).format(sql.Identifier(schema), sql.Identifier(schema))
            )
            encoded = "\n".join(str(row[0]) for row in await cursor.fetchall())
            columns_cursor = await connection.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (schema,),
            )
            schema_text = "\n".join(
                ":".join(map(str, row)) for row in await columns_cursor.fetchall()
            )
        finally:
            await connection.close()
        for forbidden in (
            plaintext_id,
            payload_sentinel,
            "raw_score",
            "decision_score",
            "calibrated_probability",
            '"score"',
            '"score_type"',
            '"features"',
            '"payload"',
        ):
            assert forbidden not in encoded
            assert forbidden not in schema_text

    try:
        asyncio.run(exercise())
    finally:
        asyncio.run(_drop_schema(dsn, schema))


def test_postgres_scale_ready_serves_only_single_bounded_v2_contract(
    tmp_path: Path,
) -> None:
    admin_dsn = _admin_dsn()
    schema = _schema("api")
    role = f"{_ROLE_PREFIX}{uuid.uuid4().hex[:10]}"
    payload = {feature: float(index) for index, feature in enumerate(ALL_FEATURES)}
    conflicting_payload = {**payload, "Amount": payload["Amount"] + 1.0}
    bundle = build_synthetic_serving_bundle()
    calls = 0

    class CountingService(ModelService):
        def predict_one(self, value: TransactionFeatures):
            nonlocal calls
            calls += 1
            return super().predict_one(value)

    async def prepare() -> str:
        connection = await psycopg.AsyncConnection.connect(admin_dsn, autocommit=True)
        try:
            await connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(role)
                )
            )
        finally:
            await connection.close()
        await run_migrations(
            dsn=admin_dsn,
            schema=schema,
            apply=True,
            application_role=role,
        )
        return _dsn_for_role(admin_dsn, role)

    app_dsn = asyncio.run(prepare())
    settings = ApiSettings(
        artifact_root=tmp_path,
        bundle_manifest=None,
        cors_origins=(),
        state_backend="postgres-scale",
        postgres_scale=_settings(app_dsn, schema),
    )
    try:
        with TestClient(
            create_app(service=CountingService(bundle), settings=settings)
        ) as client:
            ready = client.get("/health/ready")
            first = client.post(
                "/v2/predict",
                json=payload,
                headers={"X-Request-ID": "bounded-v2-api"},
            )
            replay = client.post(
                "/v2/predict",
                json=payload,
                headers={"X-Request-ID": "bounded-v2-api"},
            )
            conflict = client.post(
                "/v2/predict",
                json=conflicting_payload,
                headers={"X-Request-ID": "bounded-v2-api"},
            )
            v1 = client.post(
                "/v1/predict",
                json=payload,
                headers={"X-Request-ID": "v1-remains-disabled"},
            )
            v1_batch = client.post(
                "/v1/predict/batch",
                json={"transactions": [payload]},
                headers={"X-Request-ID": "v1-batch-remains-disabled"},
            )
            v2_batch = client.post(
                "/v2/predict/batch",
                json={"transactions": [payload]},
                headers={"X-Request-ID": "v2-batch-unavailable"},
            )
        assert ready.status_code == 200 and ready.json()["status"] == "ready"
        assert first.status_code == 200 and replay.status_code == 200
        assert first.content == replay.content
        assert first.headers["X-Audit-Event-Hash"] == replay.headers[
            "X-Audit-Event-Hash"
        ]
        assert "X-Idempotent-Replay" not in first.headers
        assert replay.headers["X-Idempotent-Replay"] == "true"
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"
        assert calls == 1
        encoded = first.text
        for forbidden in (
            "request_id",
            "raw_score",
            "decision_score",
            "calibrated_probability",
            '"score"',
        ):
            assert forbidden not in encoded
        assert first.json()["model"]["decision_eligible"] is False
        assert first.json()["model"]["historical_metrics_claimed"] is False
        assert v1.status_code == 503
        assert v1_batch.status_code == 503
        assert v2_batch.status_code == 404
        assert asyncio.run(_counts(admin_dsn, schema)) == (1, 1, 1, 1)
    finally:
        asyncio.run(_drop_schema(admin_dsn, schema))
        connection = psycopg.connect(admin_dsn, autocommit=True)
        try:
            connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        finally:
            connection.close()
