from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from api.main import ApiSettings, create_app
from api.postgres_idempotency import (
    DurableReservation,
    PostgresIdempotencyStore,
    ReservationInProgressError,
)
from api.scale_config import PostgresScaleSettings
from api.scale_lifecycle_timing import (
    LIFECYCLE_METRIC_NAMES,
    LIFECYCLE_TIMING_FLAG,
    LIFECYCLE_TIMING_OUTPUT_DIR,
    RESERVATION_OUTCOMES,
    EventLoopLagMonitor,
    LifecycleTimingAggregator,
    RequestLifecycleTimer,
    lifecycle_aggregator_from_environment,
    lifecycle_timing_enabled,
)
from api.scale_response import BoundedPredictionRepresentation
from api.service import ModelService

ROOT = Path(__file__).resolve().parents[1]


def _settings() -> PostgresScaleSettings:
    return PostgresScaleSettings(
        dsn="postgresql://user@127.0.0.1:55432/secureswipe_scale_test",
        schema="p1s4_lifecycle_timing",
        hmac_secret=b"z" * 32,
    )


def _timer(aggregator: LifecycleTimingAggregator) -> RequestLifecycleTimer:
    timer = RequestLifecycleTimer(aggregator)
    timer.mark_pre_reservation_complete()
    return timer


def test_lifecycle_diagnostic_requires_exact_opt_in(tmp_path: Path) -> None:
    assert lifecycle_timing_enabled({}) is False
    for value in ("", "0", "true", "TRUE", "yes", "on", "2", " ", " 1 ", "01"):
        assert lifecycle_timing_enabled({LIFECYCLE_TIMING_FLAG: value}) is False
    environment = {
        LIFECYCLE_TIMING_FLAG: "1",
        LIFECYCLE_TIMING_OUTPUT_DIR: str(tmp_path),
    }
    assert lifecycle_timing_enabled(environment) is True
    aggregator = lifecycle_aggregator_from_environment(environment)
    assert aggregator is not None and aggregator.output_dir == tmp_path


def test_local_default_app_never_constructs_lifecycle_timing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(LIFECYCLE_TIMING_FLAG, "1")
    monkeypatch.setenv(LIFECYCLE_TIMING_OUTPUT_DIR, str(tmp_path))
    application = create_app(
        service=ModelService(),
        settings=ApiSettings(
            artifact_root=tmp_path,
            bundle_manifest=None,
            cors_origins=(),
            state_backend="local-default",
        ),
    )
    with TestClient(application) as client:
        assert client.get("/health/live").status_code == 200
        assert application.state.postgres_idempotency_store is None
    assert not list(tmp_path.iterdir())


def test_required_spans_have_one_explicit_lifecycle_order() -> None:
    assert LIFECYCLE_METRIC_NAMES == (
        "pre_reservation_ms",
        "reservation_pool_checkout_ms",
        "reservation_transaction_ms",
        "reservation_outcome_handling_ms",
        "model_scoring_ms",
        "bounded_response_build_ms",
        "bounded_response_serialize_ms",
        "completion_pool_checkout_ms",
        "completion_transaction_ms",
        "total_handler_ms",
    )
    assert RESERVATION_OUTCOMES == (
        "owner",
        "completed_replay",
        "pending_fail_closed",
    )


def test_snapshot_contains_only_count_min_median_p95_p99_max(tmp_path: Path) -> None:
    aggregator = LifecycleTimingAggregator(tmp_path)
    for value in (1.0, 2.0, 3.0, 4.0, 5.0):
        aggregator.record_request({name: value for name in LIFECYCLE_METRIC_NAMES}, "owner")

    snapshot = aggregator.snapshot()
    metric = snapshot["metrics"]["model_scoring_ms"]
    assert metric == {
        "count": 5,
        "min_ms": 1.0,
        "median_ms": 3.0,
        "p95_ms": 5.0,
        "p99_ms": 5.0,
        "max_ms": 5.0,
    }
    assert "samples" not in json.dumps(snapshot).lower()


def test_unsafe_values_and_unknown_fields_cannot_reach_artifact(tmp_path: Path) -> None:
    aggregator = LifecycleTimingAggregator(tmp_path)
    aggregator.record_request(
        {
            "model_scoring_ms": 12.5,
            "completion_transaction_ms": float("nan"),
            "total_handler_ms": -1.0,
            "request_id": "private-id-sentinel",
            "payload": "private-payload-sentinel",
            "raw_score": 0.99,
            "dsn": "postgresql://private-dsn-sentinel",
            "exception": "private-error-sentinel",
        },
        "owner",
    )
    aggregator.record_event_loop_lag(float("inf"))
    path = aggregator.flush()

    assert path is not None
    document = json.loads(path.read_text(encoding="utf-8"))
    encoded = json.dumps(document)
    assert document["metrics"]["model_scoring_ms"]["count"] == 1
    assert document["metrics"]["completion_transaction_ms"]["count"] == 0
    assert document["metrics"]["total_handler_ms"]["count"] == 0
    for sentinel in (
        "private-id-sentinel",
        "private-payload-sentinel",
        "private-dsn-sentinel",
        "private-error-sentinel",
        "0.99",
    ):
        assert sentinel not in encoded


def test_outcome_counts_are_separated_and_invalid_outcomes_are_rejected(
    tmp_path: Path,
) -> None:
    aggregator = LifecycleTimingAggregator(tmp_path)
    for outcome in RESERVATION_OUTCOMES:
        timer = _timer(aggregator)
        timer.classify(outcome)
        timer.submit()
    aggregator.record_request({"total_handler_ms": 1.0}, "unexpected")

    snapshot = aggregator.snapshot()
    assert snapshot["requests"] == 3
    assert snapshot["reservation_outcome_counts"] == {
        "owner": 1,
        "completed_replay": 1,
        "pending_fail_closed": 1,
    }


def test_incomplete_and_discarded_requests_emit_no_misleading_record(tmp_path: Path) -> None:
    aggregator = LifecycleTimingAggregator(tmp_path)
    incomplete = _timer(aggregator)
    incomplete.submit()
    discarded = _timer(aggregator)
    discarded.classify("owner")
    discarded.discard()
    discarded.submit()

    assert aggregator.requests == 0
    assert aggregator.flush() is None


def test_flush_uses_atomic_replace_and_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    aggregator = LifecycleTimingAggregator(tmp_path)
    aggregator.record_request({"total_handler_ms": 3.0}, "owner")
    replacements: list[tuple[str, str]] = []
    real_replace = __import__("os").replace

    def observed_replace(source: str, destination: str) -> None:
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr("api.scale_lifecycle_timing.os.replace", observed_replace)
    path = aggregator.flush()

    assert path is not None and len(replacements) == 1
    assert replacements[0][0] != replacements[0][1]
    assert str(replacements[0][1]) == str(path)
    assert not list(tmp_path.glob("*.tmp"))


def test_event_loop_monitor_starts_stops_and_emits_process_aggregate(tmp_path: Path) -> None:
    async def exercise() -> tuple[LifecycleTimingAggregator, EventLoopLagMonitor]:
        aggregator = LifecycleTimingAggregator(tmp_path)
        monitor = EventLoopLagMonitor(aggregator, interval_seconds=0.001)
        monitor.start()
        assert monitor.running is True
        await asyncio.sleep(0.01)
        await monitor.stop()
        return aggregator, monitor

    aggregator, monitor = asyncio.run(exercise())

    assert monitor.running is False
    snapshot = aggregator.snapshot()
    assert snapshot["event_loop_lag"]["scope"] == "process"
    assert snapshot["event_loop_lag"]["sampling_method"] == ("fixed_interval_monotonic_drift")
    assert snapshot["event_loop_lag"]["count"] > 0
    assert list(tmp_path.glob("scale-lifecycle-timing-*.json"))


def test_execute_classifies_owner_replay_and_pending_from_server_outcomes(
    tmp_path: Path,
) -> None:
    async def exercise() -> LifecycleTimingAggregator:
        aggregator = LifecycleTimingAggregator(tmp_path)
        store = PostgresIdempotencyStore(_settings(), lifecycle_timing_aggregator=aggregator)
        bounded = BoundedPredictionRepresentation.model_construct()
        owner = DurableReservation("owner", "a" * 64, "b" * 64)
        completed = DurableReservation(
            "completed",
            "a" * 64,
            "b" * 64,
            response=bounded,
            response_hash="c" * 64,
            audit_receipt_sha256="d" * 64,
        )
        store.reserve = AsyncMock(return_value=owner)  # type: ignore[method-assign]
        store.complete_reservation = AsyncMock(  # type: ignore[method-assign]
            return_value=completed
        )
        owner_timer = _timer(aggregator)
        await store.execute_detailed(
            request_id="not-persisted",
            request_digest="b" * 64,
            operation=AsyncMock(return_value=bounded),
            lifecycle_timer=owner_timer,
        )
        owner_timer.submit()

        store.reserve = AsyncMock(return_value=completed)  # type: ignore[method-assign]
        replay_timer = _timer(aggregator)
        await store.execute_detailed(
            request_id="not-persisted",
            request_digest="b" * 64,
            operation=AsyncMock(return_value=bounded),
            lifecycle_timer=replay_timer,
        )
        replay_timer.submit()

        reserved = DurableReservation("reserved", "a" * 64, "b" * 64)
        store.reserve = AsyncMock(return_value=reserved)  # type: ignore[method-assign]
        store.wait_for_reservation = AsyncMock(  # type: ignore[method-assign]
            side_effect=ReservationInProgressError("safe fail closed")
        )
        pending_timer = _timer(aggregator)
        with pytest.raises(ReservationInProgressError):
            await store.execute_detailed(
                request_id="not-persisted",
                request_digest="b" * 64,
                operation=AsyncMock(return_value=bounded),
                lifecycle_timer=pending_timer,
            )
        pending_timer.submit()
        return aggregator

    aggregator = asyncio.run(exercise())

    assert aggregator.snapshot()["reservation_outcome_counts"] == {
        "owner": 1,
        "completed_replay": 1,
        "pending_fail_closed": 1,
    }


def test_owner_operation_failure_discards_partial_timing(tmp_path: Path) -> None:
    async def exercise() -> LifecycleTimingAggregator:
        aggregator = LifecycleTimingAggregator(tmp_path)
        store = PostgresIdempotencyStore(_settings(), lifecycle_timing_aggregator=aggregator)
        store.reserve = AsyncMock(  # type: ignore[method-assign]
            return_value=DurableReservation("owner", "a" * 64, "b" * 64)
        )
        store.fail = AsyncMock()  # type: ignore[method-assign]
        timer = _timer(aggregator)
        with pytest.raises(RuntimeError, match="synthetic operation failure"):
            await store.execute_detailed(
                request_id="not-persisted",
                request_digest="b" * 64,
                operation=AsyncMock(side_effect=RuntimeError("synthetic operation failure")),
                lifecycle_timer=timer,
            )
        timer.submit()
        return aggregator

    aggregator = asyncio.run(exercise())

    assert aggregator.requests == 0


def test_lifecycle_instrumentation_adds_no_public_or_audit_surface() -> None:
    source = (ROOT / "api" / "scale_lifecycle_timing.py").read_text(encoding="utf-8")
    for forbidden in (
        "APIRouter",
        "@application",
        "add_route",
        "headers[",
        "audit_events",
        "response_body",
        "postgresql://",
    ):
        assert forbidden not in source
    assert "SECURESWIPE_SCALE_LIFECYCLE_TIMING" not in (
        ROOT / "api" / "postgres_audit.py"
    ).read_text(encoding="utf-8")
