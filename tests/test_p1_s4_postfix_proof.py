"""Focused tests for the P1-S4 closeout evidence-preservation repair.

A post-measurement gate used to raise a bare ``ScaleBenchmarkError`` that no
handler persisted, so a failed proof was discarded with no artifact. These tests
pin the versioned failure schema, its privacy, the machine-health criteria, and
the fact that none of it activates outside the benchmark path.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from scripts.run_p1_s4_postfix_proof import (
    CONCURRENCY,
    MAX_ONE_MINUTE_LOAD_AVERAGE,
    PROTOCOL_PATH,
    REPEAT,
    WORKERS,
    _disable_state_store_diagnostic,
    _evaluate_machine_health,
    _safe_write,
)
from scripts.run_p1_scale_benchmark import _run_repeat, _validate_harness_gates
from src.operations.p1_scale_benchmark import (
    HARNESS_GATE_FAILURE_SCHEMA,
    BenchmarkValidationError,
    ScaleBenchmarkError,
    safe_gate_failure_diagnostics,
    validate_safe_result,
)

from api.state_store_diagnostic import DIAGNOSTIC_FLAG, DIAGNOSTIC_OUTPUT_DIR


def _aggregates() -> dict:
    return {
        "attempted": 1000,
        "completed": 1000,
        "successful_2xx": 900,
        "expected_non_2xx": 100,
        "unexpected_non_2xx": 0,
        "timeouts": 0,
        "transport_errors": 0,
        "status_counts": {"200": 900, "422": 100},
        "all_completed_latency": {"p50_ms": 100.0, "p95_ms": 200.0, "p99_ms": 300.0},
    }


def _diagnostics(failure: str = "S4e scheduler queue p99 exceeds gate.") -> dict:
    return safe_gate_failure_diagnostics(
        workers=WORKERS,
        concurrency=CONCURRENCY,
        repeat=REPEAT,
        warmup_result=_aggregates(),
        measured_result=_aggregates(),
        audit={"warmup_growth": 70, "measured_growth": 700},
        failure=failure,
    )


def test_failed_gate_keeps_versioned_aggregate_only_evidence() -> None:
    diagnostics = _diagnostics()

    assert diagnostics["diagnostic_schema"] == HARNESS_GATE_FAILURE_SCHEMA
    assert diagnostics["failure_stage"] == "post_measurement_gate"
    assert diagnostics["workers"] == 4
    assert diagnostics["concurrency"] == 64
    assert diagnostics["measured"]["successful_2xx"] == 900
    assert diagnostics["audit"]["measured_growth"] == 700


def test_failure_evidence_carries_no_per_request_arrays_or_sensitive_fields() -> None:
    diagnostics = _diagnostics()

    validate_safe_result(diagnostics)
    encoded = json.dumps(diagnostics)
    for forbidden in ("request_id", "dsn", "password", "features", "raw_score"):
        assert forbidden not in encoded
    for value in diagnostics.values():
        assert not isinstance(value, list)


def test_new_schema_is_versioned_and_never_relabels_old_artifacts() -> None:
    assert HARNESS_GATE_FAILURE_SCHEMA.endswith("_v1")
    assert _diagnostics()["diagnostic_schema"] != "p1_scale_incremental_evidence"


def test_post_measurement_gate_raises_the_persistable_error_class() -> None:
    source = inspect.getsource(_run_repeat)
    guarded = source.split('record["harness_validation"]', 1)[1]

    assert "except ScaleBenchmarkError as exc:" in guarded
    assert "safe_gate_failure_diagnostics" in guarded
    assert "raise BenchmarkValidationError(" in guarded
    assert issubclass(BenchmarkValidationError, ScaleBenchmarkError)


def test_unchanged_scheduler_gate_still_fails_closed() -> None:
    """The repair preserves evidence; it must not soften the gate itself."""
    source = inspect.getsource(_validate_harness_gates)

    assert "queue_limit_ms = max(10.0, request_e2e_p50_ms * 0.05)" in source
    assert "if queue_p99_ms is None or queue_p99_ms > queue_limit_ms:" in source
    assert "reuse_rate < 0.95" in source


@pytest.mark.parametrize(
    ("load", "thermal", "sampler", "expected"),
    [
        (4.79, False, 0, []),
        (MAX_ONE_MINUTE_LOAD_AVERAGE, False, 0, []),
        (8.01, False, 0, ["M1_pre_run_load_average"]),
        (1.0, True, 0, ["M2_thermal_warning"]),
        (1.0, False, 1, ["M3_task_infrastructure"]),
    ],
)
def test_only_preregistered_conditions_invalidate_an_environment(
    load: float, thermal: bool, sampler: int, expected: list[str]
) -> None:
    health = _evaluate_machine_health(
        {"load_average_1m": load, "thermal_warning_recorded": thermal},
        {"load_average_1m": load, "thermal_warning_recorded": False},
        sampler_failures=sampler,
    )

    assert health["breaches"] == expected
    assert health["environment_valid"] is (not expected)


def test_a_failed_benchmark_gate_alone_is_never_an_environment_invalidation() -> None:
    health = _evaluate_machine_health(
        {"load_average_1m": 4.79, "thermal_warning_recorded": False},
        {"load_average_1m": 5.10, "thermal_warning_recorded": False},
        sampler_failures=0,
    )

    assert health["environment_valid"] is True
    assert health["breaches"] == []


def test_postfix_proof_disables_the_opt_in_state_store_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DIAGNOSTIC_FLAG, "1")
    monkeypatch.setenv(DIAGNOSTIC_OUTPUT_DIR, "/tmp/should-not-be-inherited")

    _disable_state_store_diagnostic()

    import os

    assert DIAGNOSTIC_FLAG not in os.environ
    assert DIAGNOSTIC_OUTPUT_DIR not in os.environ


def test_postfix_proof_binds_the_committed_closeout_protocol() -> None:
    assert PROTOCOL_PATH.exists()
    assert PROTOCOL_PATH.name == "P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md"


def test_written_proof_artifact_is_validated_before_replacement(tmp_path: Path) -> None:
    path = tmp_path / "proof.json"

    _safe_write({"proofs": [], "failure": _diagnostics()}, path)
    assert json.loads(path.read_text())["failure"]["workers"] == 4
    assert not list(tmp_path.glob(".*.tmp"))

    with pytest.raises(ScaleBenchmarkError):
        _safe_write({"request_id": "leaked"}, tmp_path / "unsafe.json")
