from __future__ import annotations

import csv
import inspect
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from scripts.run_p1_scale_benchmark import (
    IncrementalEvidenceLog,
    _api_error_evidence,
    _bounded_contract,
    _median_matrix_and_gates,
    _published_timing_reconciles,
    _run_bounded_requests,
    _run_repeat,
    _run_workload,
    _validate_harness_gates,
    _write_partial_diagnostic,
)

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
    RequestSpec,
    ScaleBenchmarkError,
    assert_safe_target,
    build_workload,
    classify_api_error_code,
    normalize_api_error_code,
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


def test_s4e_has_no_per_request_client_construction() -> None:
    workload_source = inspect.getsource(_run_workload)
    repeat_source = inspect.getsource(_run_repeat)
    assert "httpx.Client(" not in workload_source
    assert repeat_source.count("httpx.Client(") == 1
    assert repeat_source.index("httpx.Client(") < repeat_source.index(
        "_run_workload("
    )


def test_bounded_scheduler_never_exceeds_concurrency_or_builds_backlog() -> None:
    requests = tuple(
        RequestSpec("valid", f"transient-{index}", {"Time": float(index)})
        for index in range(40)
    )
    active = 0
    peak = 0
    lock = threading.Lock()

    def issue(spec: RequestSpec, timer: object) -> RequestOutcome:
        nonlocal active, peak
        del timer
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.002)
        with lock:
            active -= 1
        return RequestOutcome(spec.kind, 200, 1.0)

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes, max_outstanding = _run_bounded_requests(
            requests,
            concurrency=8,
            executor=executor,
            issue=issue,
            timing_enabled=False,
        )

    assert len(outcomes) == 40
    assert max_outstanding == 8
    assert peak <= 8


def test_flat_validated_matrix_closes_p1_s4_without_s4f() -> None:
    runs = []
    for workers in WORKER_COUNTS:
        for concurrency in CONCURRENCY_LEVELS:
            for repeat in REPEAT_NUMBERS:
                runs.append(
                    {
                        "workers": workers,
                        "concurrency": concurrency,
                        "repeat": repeat,
                        "measured": {
                            "result": {
                                "successful_rps": 100.0 + workers,
                                "all_completed_latency": {
                                    "p50_ms": 10.0,
                                    "p95_ms": 20.0,
                                    "p99_ms": 30.0,
                                },
                            }
                        },
                        "resources": {
                            "api_process_group_cpu_percent": {"mean": 50.0},
                            "api_process_group_rss": {"median_mib": 100.0},
                        },
                    }
                )

    evaluation = _median_matrix_and_gates(runs)

    assert evaluation["scaling_demonstrated"] is False
    assert evaluation["p1_s4_status"] == "complete"
    assert evaluation["s4f_required"] is False
    assert evaluation["allowed_conclusion"] == (
        "validated_local_loopback_harness_did_not_demonstrate_horizontal_scaling"
    )


def _harness_gate_record(*, reuse: int = 10, queue_p99_ms: float = 1.0) -> dict:
    def timing(*, new: int, reused: int) -> dict:
        return {
            "diagnostic_recording_failures": 0,
            "connection_counts": {"new": new, "reused": reused, "unknown": 0},
            "duration_aggregates": {
                "scheduler_queue_wait_ms": {"p99_ms": queue_p99_ms},
                "client_setup_ms": {"count": 10, "max_ms": 0.0},
            },
        }

    return {
        "concurrency": 8,
        "client_harness": {
            "created_before_warmup": True,
            "per_request_client_construction": False,
            "limits": {"max_connections": 8, "max_keepalive_connections": 8},
        },
        "warmup": {
            "result": {"attempted": 10, "client_timing": timing(new=8, reused=2)}
        },
        "measured": {
            "result": {
                "attempted": 10,
                "all_completed_latency": {"p50_ms": 100.0},
                "client_timing": timing(new=10 - reuse, reused=reuse),
                "harness": {
                    "max_outstanding_observed": 8,
                    "outstanding_work_limit": 8,
                },
            }
        },
    }


def test_s4e_harness_gates_enforce_queue_setup_reuse_and_warmup() -> None:
    passed = _validate_harness_gates(_harness_gate_record())
    assert passed["status"] == "passed"
    assert passed["measured_connection_reuse_rate"] == 1.0
    assert passed["per_request_client_setup_max_ms"] == 0.0

    with pytest.raises(ScaleBenchmarkError, match="reuse was below"):
        _validate_harness_gates(_harness_gate_record(reuse=9))
    with pytest.raises(ScaleBenchmarkError, match="queue p99"):
        _validate_harness_gates(_harness_gate_record(queue_p99_ms=10.1))


def test_e2e_reconciliation_allows_only_publication_rounding_delta() -> None:
    assert _published_timing_reconciles(4.2345, 4.234)
    assert _published_timing_reconciles(4.2345, 4.235)
    assert not _published_timing_reconciles(4.2345, 4.236)


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
            "phase": "smoke-measured",
            "workers": 1,
            "concurrency": 8,
            "repeat": 1,
            "status_code": 200,
            "api_error_code": None,
            "api_error_category": None,
            "header_classification": None,
            "latency_ms": 1.0,
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


def _error_body(code: object) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "request_id": "p1sf-v1-w4-c64-r2-valid-0123",
        "error": {"code": code, "message": "Pool timeout waiting for a connection."},
    }


def test_unexpected_response_keeps_structured_code_category_and_header_shape() -> None:
    response = httpx.Response(
        503,
        json=_error_body("state_store_unavailable"),
        headers={
            "Content-Type": "application/json",
            "Retry-After": "1",
            "X-Request-ID": "p1sf-v1-w4-c64-r2-valid-0123",
        },
    )

    evidence = _api_error_evidence(response)

    assert evidence["api_error_code"] == "state_store_unavailable"
    assert evidence["api_error_category"] == "database_state_store"
    assert evidence["header_classification"] == {
        "content_type": "application/json",
        "header_count": 4,
        "retry_after_present": True,
        "audit_receipt_header_present": False,
        "replay_header_present": False,
        "correlation_header_present": True,
    }
    encoded = json.dumps(evidence)
    assert "p1sf-v1" not in encoded
    assert "Pool timeout" not in encoded
    validate_safe_result(evidence)


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("capacity_exceeded", "api_admission_capacity"),
        ("audit_unavailable", "audit_chain"),
        ("idempotency_in_progress", "idempotency_reservation"),
        ("state_store_failure", "database_state_store"),
        ("model_unavailable", "model_readiness"),
        ("scale_profile_unavailable", "response_profile"),
    ],
)
def test_every_fail_closed_503_code_maps_to_an_explicit_category(
    code: str, category: str
) -> None:
    assert classify_api_error_code(code) == category
    assert normalize_api_error_code(code) == code


@pytest.mark.parametrize(
    "code",
    ["State_Store_Unavailable", "not a code", "x" * 80, "", 17, None, {"code": "x"}],
)
def test_untrusted_error_code_shapes_are_never_retained_verbatim(code: object) -> None:
    normalized = normalize_api_error_code(code)

    assert normalized in {"unrecognized_api_error_code", "absent_api_error_code"}
    assert normalized != code


def test_unparseable_error_body_is_recorded_without_the_raw_body() -> None:
    response = httpx.Response(503, content=b"<html>upstream failure</html>")

    evidence = _api_error_evidence(response)

    assert evidence["api_error_code"] == "unparseable_api_error_body"
    assert evidence["api_error_category"] == "unparseable_api_error_body"
    assert "upstream failure" not in json.dumps(evidence)


def test_diagnostics_aggregate_unexpected_status_codes_and_dimensions() -> None:
    workload = build_workload(workers=4, concurrency=64, repeat=2, phase="measured")
    outcomes = [
        RequestOutcome(item.kind, 422 if item.kind == "malformed" else 200, 1.0)
        for item in workload.requests
    ]
    outcomes[0] = RequestOutcome(
        "valid",
        503,
        41.5,
        contract_valid=False,
        request_group_sha256="a" * 64,
        failure_reason="unexpected_http_status",
        api_error_code="state_store_unavailable",
        api_error_category="database_state_store",
        header_classification={"content_type": "application/json"},
    )

    diagnostic = safe_outcome_diagnostics(workload, outcomes, failure="probe")

    assert diagnostic["workers"] == 4
    assert diagnostic["concurrency"] == 64
    assert diagnostic["repeat"] == 2
    assert diagnostic["unexpected_status_counts"] == {"503": 1}
    assert diagnostic["api_error_code_counts"] == {"state_store_unavailable": 1}
    assert diagnostic["api_error_category_counts"] == {"database_state_store": 1}
    assert diagnostic["unexpected_latency_ms"] == {"min": 41.5, "p50": 41.5, "max": 41.5}
    assert diagnostic["response_failures"][0]["api_error_code"] == "state_store_unavailable"
    assert diagnostic["response_failures"][0]["latency_ms"] == 41.5
    validate_safe_result(diagnostic)


def _repeat_record(*, workers: int, concurrency: int, repeat: int) -> dict[str, object]:
    phase = {
        "manifest": {"phase": "measured", "attempts": 1000},
        "result": {
            "attempted": 1000,
            "successful_2xx": 900,
            "expected_non_2xx": 100,
            "unexpected_non_2xx": 0,
            "timeouts": 0,
            "transport_errors": 0,
            "wall_seconds": 9.5,
            "successful_rps": 94.7,
            "all_completed_latency": {"p50_ms": 12.0, "p95_ms": 40.0, "p99_ms": 80.0},
            "successful_latency": {"p50_ms": 12.0, "p95_ms": 40.0, "p99_ms": 80.0},
        },
    }
    return {
        "workers": workers,
        "concurrency": concurrency,
        "repeat": repeat,
        "warmup": phase,
        "measured": phase,
        "model": {"model_artifact_sha256": "c" * 64, "model_version": "synthetic-1"},
        "audit": {
            "warmup_growth": 70,
            "measured_growth": 700,
            "full_verifier_status": "verified",
        },
        "resources": {
            "api_process_group_cpu_percent": {"mean": 210.0, "peak": 380.0, "samples": 90},
            "api_process_group_rss": {"median_mib": 460.0, "peak_mib": 520.0, "samples": 90},
        },
    }


def _evidence_header() -> dict[str, object]:
    return {
        "mode": "full",
        "source_commit_sha": "5137ef69c6218a6a12c90dc3313f623843c41629",
        "bundle_manifest_sha256": "b" * 64,
        "runtime": {"python": "3.12.10", "logical_cpu_count": 8},
    }


def test_every_completed_repeat_is_persisted_before_the_next_one_starts(
    tmp_path: Path,
) -> None:
    log = IncrementalEvidenceLog(
        run_id="p1-scale-incremental", output_dir=tmp_path, header=_evidence_header()
    )

    assert log.json_path.exists()
    assert json.loads(log.json_path.read_text())["completed_repeat_count"] == 0

    log.record_repeat(_repeat_record(workers=4, concurrency=32, repeat=3))
    after_first = json.loads(log.json_path.read_text())
    log.record_repeat(_repeat_record(workers=4, concurrency=64, repeat=1))
    after_second = json.loads(log.json_path.read_text())

    assert after_first["completed_repeat_count"] == 1
    assert after_second["completed_repeat_count"] == 2
    assert after_first["source_commit_sha"] == "5137ef69c6218a6a12c90dc3313f623843c41629"
    assert after_first["runtime"]["python"] == "3.12.10"
    assert after_first["publishable"] is False

    persisted = after_second["completed_runs"][0]["measured"]["result"]
    assert persisted["successful_rps"] == 94.7
    assert persisted["all_completed_latency"] == {
        "p50_ms": 12.0,
        "p95_ms": 40.0,
        "p99_ms": 80.0,
    }
    assert after_second["completed_runs"][0]["resources"]["api_process_group_rss"][
        "median_mib"
    ] == 460.0
    assert after_second["completed_runs"][0]["audit"]["measured_growth"] == 700
    assert after_second["completed_runs"][0]["model"]["model_artifact_sha256"] == "c" * 64

    rows = list(csv.DictReader(log.csv_path.read_text().splitlines()))
    assert len(rows) == 4
    assert rows[0]["p99_ms"] == "80.0"
    assert rows[0]["api_rss_median_mib"] == "460.0"


def test_completed_cells_survive_a_later_cell_failing_closed(tmp_path: Path) -> None:
    log = IncrementalEvidenceLog(
        run_id="p1-scale-failure", output_dir=tmp_path, header=_evidence_header()
    )
    log.record_repeat(_repeat_record(workers=4, concurrency=32, repeat=3))
    log.record_repeat(_repeat_record(workers=4, concurrency=64, repeat=1))

    log.record_failure(
        {
            "workers": 4,
            "concurrency": 64,
            "repeat": 2,
            "status_counts": {"200": 891, "422": 100, "503": 9},
            "api_error_code_counts": {"state_store_unavailable": 9},
        }
    )

    persisted = json.loads(log.json_path.read_text())
    assert persisted["evidence_status"] == "failed_after_completed_repeats"
    assert persisted["completed_repeat_count"] == 2
    assert [run["concurrency"] for run in persisted["completed_runs"]] == [32, 64]
    assert persisted["completed_runs"][1]["measured"]["result"]["successful_rps"] == 94.7
    assert persisted["failure"]["api_error_code_counts"] == {"state_store_unavailable": 9}
    assert len(list(csv.DictReader(log.csv_path.read_text().splitlines()))) == 4


def test_incremental_evidence_refuses_unsafe_repeat_records(tmp_path: Path) -> None:
    log = IncrementalEvidenceLog(
        run_id="p1-scale-privacy", output_dir=tmp_path, header=_evidence_header()
    )
    log.record_repeat(_repeat_record(workers=1, concurrency=1, repeat=1))

    for forbidden in ("request_id", "payload", "features", "raw_score", "secret", "dsn"):
        record = _repeat_record(workers=1, concurrency=8, repeat=1)
        record[forbidden] = "sentinel"
        with pytest.raises(ScaleBenchmarkError, match="Forbidden saved-result field"):
            log.record_repeat(record)

    persisted = json.loads(log.json_path.read_text())
    assert persisted["completed_repeat_count"] == 1
    assert "sentinel" not in log.json_path.read_text()


def test_incremental_evidence_is_replaced_atomically(tmp_path: Path) -> None:
    log = IncrementalEvidenceLog(
        run_id="p1-scale-atomic", output_dir=tmp_path, header=_evidence_header()
    )
    log.record_repeat(_repeat_record(workers=2, concurrency=8, repeat=1))
    log.record_completion()

    assert json.loads(log.json_path.read_text())["evidence_status"] == "completed"
    assert not list(tmp_path.glob("*.tmp"))
