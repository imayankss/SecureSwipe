from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from scripts.run_p1_s4d_client_diagnostic import CELLS, _verify_cell
from src.operations.p1_scale_client_timing import (
    CLIENT_TIMING_FLAG,
    ClientRequestTimer,
    ClientTimingAggregator,
    HttpTraceRecorder,
    client_timing_enabled,
)


def _clock(values: list[float]) -> Iterator[float]:
    return iter(values)


def test_client_timing_requires_exact_opt_in() -> None:
    assert client_timing_enabled({CLIENT_TIMING_FLAG: "1"}) is True
    for value in (None, "", "0", "true", " 1", "1 ", "TRUE"):
        environment = {} if value is None else {CLIENT_TIMING_FLAG: value}
        assert client_timing_enabled(environment) is False


def test_executor_queue_and_client_boundaries_use_one_monotonic_clock() -> None:
    ticks = _clock([1.125, 1.250, 2.250, 2.300, 2.325])
    timer = ClientRequestTimer(submitted_at=1.0, clock=lambda: next(ticks))
    for boundary in (
        "task_started",
        "request_started",
        "headers_received",
        "body_completed",
        "client_completed",
    ):
        timer.mark(boundary)

    assert timer.durations() == {
        "executor_queue_wait_ms": 125.0,
        "client_setup_ms": 125.0,
        "request_to_response_headers_ms": 1000.0,
        "response_body_read_ms": pytest.approx(50.0),
        "client_teardown_ms": pytest.approx(25.0),
        "client_e2e_ms": pytest.approx(1200.0),
        "scheduled_total_ms": pytest.approx(1325.0),
    }


def test_aggregate_statistics_and_same_request_ratios_are_nearest_rank() -> None:
    timing = ClientTimingAggregator(timeout_seconds=10.0)
    for value in (1.0, 2.0, 3.0, 4.0, 100.0):
        timing.record(
            {
                "executor_queue_wait_ms": value,
                "scheduled_total_ms": 200.0,
                "client_e2e_ms": 100.0,
                "request_to_response_headers_ms": value,
            },
            {},
            connection_kind="unknown",
        )

    snapshot = timing.snapshot()
    aggregate = snapshot["duration_aggregates"]["executor_queue_wait_ms"]
    assert aggregate == {
        "count": 5,
        "min_ms": 1.0,
        "median_ms": 3.0,
        "p95_ms": 100.0,
        "p99_ms": 100.0,
        "max_ms": 100.0,
    }
    share = snapshot["same_request_ratio_aggregates"][
        "request_to_response_headers_share_of_e2e_percent"
    ]
    assert share["count"] == 5
    assert share["median_percent"] == 3.0


def test_supported_trace_events_measure_spans_and_classify_connections() -> None:
    ticks = _clock([1.0, 1.010, 2.0, 2.020, 3.0, 3.030, 4.0, 4.400])
    trace = HttpTraceRecorder(clock=lambda: next(ticks))
    for event in (
        "connection.connect_tcp.started",
        "connection.connect_tcp.complete",
        "http11.send_request_headers.started",
        "http11.send_request_headers.complete",
        "http11.send_request_body.started",
        "http11.send_request_body.complete",
        "http11.receive_response_headers.started",
        "http11.receive_response_headers.complete",
    ):
        trace(event, {"unsafe_payload": "ignored"})

    assert trace.durations() == {
        "tcp_connect_ms": pytest.approx(10.0),
        "request_headers_send_ms": pytest.approx(20.0),
        "request_body_send_ms": pytest.approx(30.0),
        "response_headers_wait_ms": pytest.approx(400.0),
        "request_transmission_ms": pytest.approx(50.0),
    }
    assert trace.connection_kind(request_completed=True) == "new"

    reused = HttpTraceRecorder(clock=lambda: 1.0)
    reused("http11.send_request_headers.started", {})
    reused("http11.send_request_headers.complete", {})
    assert reused.connection_kind(request_completed=True) == "reused"
    assert HttpTraceRecorder().connection_kind(request_completed=False) == "unknown"


def test_pool_wait_is_honestly_not_observable_and_samples_are_not_persisted() -> None:
    timing = ClientTimingAggregator(timeout_seconds=10.0)
    timing.record(
        {"client_e2e_ms": 10.0, "request_to_response_headers_ms": 8.0},
        {},
        connection_kind="new",
    )

    snapshot = timing.snapshot()
    assert snapshot["phase_availability"]["connection_pool_acquisition"] == {
        "status": "not_observable",
        "reason": "no_supported_httpx_httpcore_trace_event",
    }
    assert snapshot["connection_counts"] == {"new": 1, "reused": 0, "unknown": 0}
    assert "samples" not in json.dumps(snapshot).lower()


def test_unsafe_values_and_recording_failure_are_inert() -> None:
    timing = ClientTimingAggregator(timeout_seconds=10.0)
    timing.record(
        {
            "client_e2e_ms": 2.0,
            "request_id": "must-not-persist",
            "raw_score": 0.99,
            "payload": {"PAN": "must-not-persist"},
        },
        {"tcp_connect_ms": float("nan"), "secret": "must-not-persist"},
        connection_kind="unknown",
    )

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            raise RuntimeError("diagnostic failure")

    decision = "human_review"
    timing.record(ExplodingMapping(), {}, connection_kind="unknown")
    encoded = json.dumps(timing.snapshot()).lower()

    assert decision == "human_review"
    assert timing.snapshot()["diagnostic_recording_failures"] == 1
    for forbidden in (
        "must-not-persist",
        "request_id",
        "raw_score",
        "payload",
        "pan",
        "cvv",
        "secret",
    ):
        assert forbidden not in encoded


def test_unknown_trace_events_and_payloads_are_ignored() -> None:
    trace = HttpTraceRecorder(clock=lambda: 1.0)
    trace("connection.pool_wait.started", {"request_id": "private"})
    trace("http11.receive_response_body.started", {"score": 0.5})
    trace("http11.receive_response_body.complete", {"score": 0.5})

    assert trace.durations() == {}
    assert trace.connection_kind(request_completed=False) == "unknown"


def _verified_cell() -> dict[str, object]:
    def result(*, attempted: int, successes: int, malformed: int) -> dict[str, object]:
        return {
            "attempted": attempted,
            "successful_2xx": successes,
            "expected_non_2xx": malformed,
            "unexpected_non_2xx": 0,
            "timeouts": 0,
            "transport_errors": 0,
            "client_timing": {
                "diagnostic_recording_failures": 0,
                "connection_counts": {"new": attempted, "reused": 0, "unknown": 0},
            },
        }

    return {
        "warmup": {"result": result(attempted=100, successes=90, malformed=10)},
        "measured": {
            "result": result(attempted=1_000, successes=900, malformed=100)
        },
        "server_lifecycle": {
            "combined_request_count": 990,
            "combined_reservation_outcome_counts": {
                "owner": 770,
                "completed_replay": 220,
                "pending_fail_closed": 0,
            },
        },
        "audit": {
            "warmup_growth": 70,
            "measured_growth": 700,
            "full_verifier_status": "verified",
        },
        "model": {
            "model_artifact_sha256": (
                "a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3"
            )
        },
    }


def test_diagnostic_matrix_and_correctness_reconciliation_are_frozen() -> None:
    assert CELLS == ((1, 8, 1), (4, 32, 1), (4, 64, 1), (4, 64, 2))
    _verify_cell(_verified_cell())

    malformed_created_audit = _verified_cell()
    malformed_created_audit["audit"]["measured_growth"] = 701  # type: ignore[index]
    with pytest.raises(Exception, match="Audit growth"):
        _verify_cell(malformed_created_audit)
