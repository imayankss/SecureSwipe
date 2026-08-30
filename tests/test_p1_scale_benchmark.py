from __future__ import annotations

from pathlib import Path

import pytest

from src.operations.p1_scale_benchmark import (
    CONCURRENCY_LEVELS,
    POSTGRES_HOST,
    POSTGRES_IMAGE_DIGEST,
    POSTGRES_PORT,
    PREDICTION_ROUTE,
    REPEAT_NUMBERS,
    STATE_BACKEND,
    WORKER_COUNTS,
    RequestOutcome,
    ScaleBenchmarkError,
    assert_safe_target,
    build_workload,
    summarize_outcomes,
    validate_safe_result,
)

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_measured_mix_is_deterministic_and_exact() -> None:
    first = build_workload(workers=4, concurrency=64, repeat=3, phase="measured")
    second = build_workload(workers=4, concurrency=64, repeat=3, phase="measured")

    assert first.counts == {"valid": 700, "replay": 200, "malformed": 100}
    assert len(first.requests) == 1_000
    assert first.seed == 20260830 + 4 * 10000 + 64 * 100 + 3
    assert first.manifest_sha256 == second.manifest_sha256
    assert [item.request_id for item in first.requests] == [
        item.request_id for item in second.requests
    ]
    assert {frozenset(item.body) for item in first.requests if item.kind == "malformed"} == {
        frozenset({"Time"})
    }


def test_frozen_warmup_and_smoke_are_separate() -> None:
    warmup = build_workload(workers=1, concurrency=1, repeat=1, phase="warmup")
    smoke_warmup = build_workload(
        workers=1, concurrency=1, repeat=1, phase="smoke-warmup"
    )
    smoke_measured = build_workload(
        workers=1, concurrency=1, repeat=1, phase="smoke-measured"
    )

    assert warmup.counts == {"valid": 70, "replay": 20, "malformed": 10}
    assert smoke_warmup.counts == {"valid": 7, "replay": 2, "malformed": 1}
    assert smoke_measured.counts == {"valid": 7, "replay": 2, "malformed": 1}
    assert warmup.manifest_sha256 != smoke_warmup.manifest_sha256
    assert smoke_warmup.manifest_sha256 != smoke_measured.manifest_sha256


def test_matrix_is_frozen_to_36_measured_configurations() -> None:
    assert WORKER_COUNTS == (1, 2, 4)
    assert CONCURRENCY_LEVELS == (1, 8, 32, 64)
    assert REPEAT_NUMBERS == (1, 2, 3)
    assert len(WORKER_COUNTS) * len(CONCURRENCY_LEVELS) * len(REPEAT_NUMBERS) == 36


def test_result_validation_counts_malformed_422_as_expected_not_success() -> None:
    workload = build_workload(
        workers=1, concurrency=1, repeat=1, phase="smoke-measured"
    )
    outcomes = [
        RequestOutcome(
            item.kind,
            422 if item.kind == "malformed" else 200,
            latency_ms=float(index + 1),
        )
        for index, item in enumerate(workload.requests)
    ]

    result = summarize_outcomes(workload, outcomes, wall_seconds=2.0)

    assert result["successful_2xx"] == 9
    assert result["expected_non_2xx"] == 1
    assert result["unexpected_non_2xx"] == 0
    assert result["status_counts"] == {"200": 9, "422": 1}


@pytest.mark.parametrize("status", [201, 400, 409, 500])
def test_result_validation_fails_closed_on_wrong_malformed_status(status: int) -> None:
    workload = build_workload(
        workers=1, concurrency=1, repeat=1, phase="smoke-measured"
    )
    outcomes = [
        RequestOutcome(item.kind, status if item.kind == "malformed" else 200, 1.0)
        for item in workload.requests
    ]
    with pytest.raises(ScaleBenchmarkError, match="validation failed"):
        summarize_outcomes(workload, outcomes, wall_seconds=1.0)


def test_saved_results_reject_inputs_ids_scores_and_secrets() -> None:
    validate_safe_result({"aggregate": {"successful_rps": 1.0, "status_counts": {"200": 9}}})
    for key in ("dsn", "secret", "payload", "features", "raw_score", "request_id"):
        with pytest.raises(ScaleBenchmarkError, match="Forbidden saved-result field"):
            validate_safe_result({"nested": {key: "sentinel"}})


def test_connection_and_prediction_targets_are_fixed_and_loopback_only() -> None:
    assert_safe_target(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        route=PREDICTION_ROUTE,
        backend=STATE_BACKEND,
    )
    assert (POSTGRES_HOST, POSTGRES_PORT) == ("127.0.0.1", 55432)
    assert POSTGRES_IMAGE_DIGEST.startswith("postgres@sha256:")
    assert PREDICTION_ROUTE == "/v2/predict"
    assert STATE_BACKEND == "postgres-scale"
    for invalid in (
        {"host": "localhost", "port": 5432, "route": PREDICTION_ROUTE, "backend": STATE_BACKEND},
        {"host": POSTGRES_HOST, "port": POSTGRES_PORT, "route": "/v1/predict", "backend": STATE_BACKEND},
        {"host": POSTGRES_HOST, "port": POSTGRES_PORT, "route": "/v2/predict/batch", "backend": STATE_BACKEND},
        {"host": POSTGRES_HOST, "port": POSTGRES_PORT, "route": PREDICTION_ROUTE, "backend": "local-default"},
    ):
        with pytest.raises(ScaleBenchmarkError):
            assert_safe_target(**invalid)  # type: ignore[arg-type]


def test_runner_contains_no_v1_or_batch_prediction_target() -> None:
    runner = (ROOT / "scripts" / "run_p1_scale_benchmark.py").read_text()
    assert '"/v1/' not in runner
    assert '"/v2/predict/batch"' not in runner
    assert '"local-default"' not in runner
    assert "127.0.0.1:5432" not in runner


def test_generated_result_directory_is_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text()
    assert "reports/benchmarks/p1-scale-results/" in ignore
