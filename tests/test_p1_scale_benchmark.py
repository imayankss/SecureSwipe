from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from scripts.run_p1_scale_benchmark import _bounded_contract, _write_partial_diagnostic

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
    safe_outcome_diagnostics,
    summarize_outcomes,
    validate_safe_result,
    validate_response_groups,
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


def test_measured_status_mix_remains_exactly_900_success_and_100_validation() -> None:
    workload = build_workload(workers=4, concurrency=64, repeat=3, phase="measured")
    outcomes = [
        RequestOutcome(item.kind, 422 if item.kind == "malformed" else 200, 1.0)
        for item in workload.requests
    ]

    result = summarize_outcomes(workload, outcomes, wall_seconds=1.0)

    assert result["successful_2xx"] == 900
    assert result["expected_non_2xx"] == 100
    assert result["status_counts"] == {"200": 900, "422": 100}


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


def _successful_group_outcome(
    *, group: str, replay: bool, receipt: str = "a" * 64, response: str = "b" * 64
) -> RequestOutcome:
    return RequestOutcome(
        "replay" if replay else "valid",
        200,
        1.0,
        request_group_sha256=group,
        server_replay=replay,
        response_sha256=response,
        audit_receipt_sha256=receipt,
        response_schema_version="2.0",
        response_profile="postgres-scale-bounded-v1",
        model_artifact_sha256="c" * 64,
    )


def test_out_of_order_completion_uses_server_replay_evidence() -> None:
    outcomes = [
        _successful_group_outcome(group="group-a", replay=True),
        _successful_group_outcome(group="group-a", replay=False),
    ]

    summary = validate_response_groups(outcomes)

    assert summary == {
        "successful_request_groups": 1,
        "same_id_replay_groups": 1,
        "server_original_responses": 1,
        "server_replay_responses": 1,
    }


def test_identical_replay_group_requires_one_original_and_shared_evidence() -> None:
    outcomes = [_successful_group_outcome(group="group-a", replay=False)] + [
        _successful_group_outcome(group="group-a", replay=True) for _ in range(10)
    ]

    summary = validate_response_groups(outcomes)

    assert summary["successful_request_groups"] == 1
    assert summary["server_original_responses"] == 1
    assert summary["server_replay_responses"] == 10


def test_duplicate_event_or_changed_receipt_is_rejected() -> None:
    outcomes = [
        _successful_group_outcome(group="group-a", replay=False, receipt="a" * 64),
        _successful_group_outcome(group="group-a", replay=True, receipt="d" * 64),
    ]

    with pytest.raises(ScaleBenchmarkError, match="audit_receipt_mismatch"):
        validate_response_groups(outcomes)

    reused_across_groups = [
        _successful_group_outcome(group="group-a", replay=False, receipt="a" * 64),
        _successful_group_outcome(group="group-b", replay=False, receipt="a" * 64),
    ]
    with pytest.raises(ScaleBenchmarkError, match="audit_receipt_reused_across_groups"):
        validate_response_groups(reused_across_groups)


def test_original_two_invalid_contract_scenario_is_valid_by_server_outcome() -> None:
    outcomes = [
        # Group A completes opposite to client task ordering.
        _successful_group_outcome(group="group-a", replay=True),
        _successful_group_outcome(group="group-a", replay=False),
        # Group B completes in client task ordering.
        _successful_group_outcome(group="group-b", replay=False, receipt="e" * 64),
        _successful_group_outcome(group="group-b", replay=True, receipt="e" * 64),
    ]

    summary = validate_response_groups(outcomes)

    assert summary["successful_request_groups"] == 2
    assert summary["same_id_replay_groups"] == 2
    assert summary["server_original_responses"] == 2
    assert summary["server_replay_responses"] == 2


def test_changed_bounded_response_and_bad_replay_cardinality_are_rejected() -> None:
    changed = [
        _successful_group_outcome(group="group-a", replay=False, response="a" * 64),
        _successful_group_outcome(group="group-a", replay=True, response="b" * 64),
    ]
    with pytest.raises(ScaleBenchmarkError, match="bounded_response_mismatch"):
        validate_response_groups(changed)

    duplicate_originals = [
        _successful_group_outcome(group="group-a", replay=False),
        _successful_group_outcome(group="group-a", replay=False),
    ]
    with pytest.raises(ScaleBenchmarkError, match="server_replay_cardinality_mismatch"):
        validate_response_groups(duplicate_originals)


def test_failure_diagnostic_is_anonymous_and_privacy_safe() -> None:
    workload = build_workload(
        workers=1, concurrency=8, repeat=1, phase="smoke-measured"
    )
    outcome = RequestOutcome(
        "valid",
        200,
        1.0,
        contract_valid=False,
        request_group_sha256="f" * 64,
        server_replay=True,
        response_schema_version="2.0",
        response_profile="postgres-scale-bounded-v1",
        model_artifact_sha256="c" * 64,
        failure_reason="audit_receipt_mismatch",
    )

    diagnostic = safe_outcome_diagnostics(workload, [outcome], failure="probe")

    assert diagnostic["response_failures"] == [
        {
            "anonymous_group": "group_0001",
            "request_group_classification": "valid_or_replay_group",
            "status_code": 200,
            "server_replay_header": True,
            "response_schema_version": "2.0",
            "response_profile": "postgres-scale-bounded-v1",
            "failure_reason": "audit_receipt_mismatch",
        }
    ]
    encoded = str(diagnostic).lower()
    assert "request_id" not in encoded
    assert "payload" not in encoded
    assert "raw_score" not in encoded
    validate_safe_result(diagnostic)


def _bounded_body() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "response_profile": "postgres-scale-bounded-v1",
        "status": "completed",
        "decision": "human_review",
        "model": {
            "model_version": "synthetic-smoke-1",
            "bundle_format_version": "3",
            "model_artifact_sha256": "a" * 64,
            "training_data_fingerprint": "b" * 64,
            "evidence_category": "synthetic_demo_inference",
            "historical_taint": True,
            "decision_eligible": False,
            "historical_metrics_claimed": False,
            "evaluation_performed": False,
        },
        "policy": {
            "producer_policy": "synthetic_api_smoke_v1",
            "producer_policy_sha256": "c" * 64,
            "operating_threshold": 0.53,
            "threshold_source": "synthetic_reference",
            "threshold_model_linkage": "unverified",
            "threshold_purpose": "reference_demo",
            "threshold_calibrated": False,
            "threshold_cost_optimal": False,
            "threshold_razorpay_approved": False,
            "threshold_production_approved": False,
        },
        "schema": {"api_schema_version": "2.0", "feature_schema_sha256": "d" * 64},
    }


def test_bounded_contract_uses_actual_server_replay_header() -> None:
    original = httpx.Response(
        200,
        json=_bounded_body(),
        headers={"X-Audit-Event-Hash": "e" * 64},
    )
    replay = httpx.Response(
        200,
        json=_bounded_body(),
        headers={"X-Audit-Event-Hash": "e" * 64, "X-Idempotent-Replay": "true"},
    )

    original_valid, _, original_evidence = _bounded_contract(original)
    replay_valid, _, replay_evidence = _bounded_contract(replay)

    assert original_valid is True
    assert original_evidence["server_replay"] is False
    assert replay_valid is True
    assert replay_evidence["server_replay"] is True
    assert original_evidence["response_sha256"] == replay_evidence["response_sha256"]


@pytest.mark.parametrize(
    ("headers", "body_change", "reason"),
    [
        ({}, None, "missing_audit_receipt"),
        (
            {"X-Audit-Event-Hash": "e" * 64, "X-Idempotent-Replay": "false"},
            None,
            "invalid_replay_header",
        ),
        (
            {"X-Audit-Event-Hash": "e" * 64},
            ("response_profile", "wrong-profile"),
            "invalid_bounded_schema_or_profile",
        ),
        (
            {"X-Audit-Event-Hash": "e" * 64},
            ("raw_score", 0.9),
            "invalid_bounded_schema_or_profile",
        ),
    ],
)
def test_bounded_contract_keeps_genuine_violations_invalid(
    headers: dict[str, str], body_change: tuple[str, object] | None, reason: str
) -> None:
    body = _bounded_body()
    if body_change is not None:
        body[body_change[0]] = body_change[1]
    response = httpx.Response(200, json=body, headers=headers)

    valid, _, evidence = _bounded_contract(response)

    assert valid is False
    assert evidence["failure_reason"] == reason


def test_partial_diagnostic_writer_preserves_only_safe_summary(tmp_path: Path) -> None:
    report = {
        "run_id": "p1-scale-test",
        "source_commit_sha": "a" * 40,
        "workers": 1,
        "concurrency": 8,
        "repeat": 1,
        "runtime": {"python": "3.12"},
        "model_artifact_sha256": "b" * 64,
        "failure": {
            "request_group_classification": "same_id_replay_group",
            "status_code": 200,
            "server_replay_header": True,
            "response_schema_version": "2.0",
            "failure_reason": "audit_receipt_mismatch",
        },
    }

    path = _write_partial_diagnostic(report, tmp_path)

    assert path.name == "p1-scale-test-partial.json"
    persisted = path.read_text()
    assert "same_id_replay_group" in persisted
    assert "request_id" not in persisted
    assert "payload" not in persisted
    assert "raw_score" not in persisted
