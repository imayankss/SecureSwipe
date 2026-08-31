#!/usr/bin/env python3
"""Run the frozen P1-S4 postfix proofs with S4f diagnostics disabled.

The postfix proof re-measures the exact cell that failed in P1-S4e (four API
workers, concurrency 64, repeat 2) against the committed state-store repair. It
uses the unchanged P1-S4e harness and its unchanged gates; only the opt-in S4f
state-store diagnostic and the S4f PostgreSQL sampler are left off, because a
performance proof must not carry classification instrumentation on the
measured path.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.state_store_diagnostic import DIAGNOSTIC_FLAG, DIAGNOSTIC_OUTPUT_DIR
from scripts.run_p1_scale_benchmark import (
    BenchmarkValidationError,
    OwnedPostgres,
    POSTGRES_HOST,
    POSTGRES_IMAGE,
    POSTGRES_PORT,
    RESULT_DIRECTORY,
    _git_value,
    _machine_record,
    _run,
    _run_repeat,
    _sha256_file,
    create_synthetic_bundle,
)
from src.operations.p1_scale_benchmark import ScaleBenchmarkError, validate_safe_result
from src.operations.p1_scale_client_timing import CLIENT_TIMING_FLAG

PROTOCOL_PATH = Path("docs/benchmarks/P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md")
BENCHMARK_VERSION = "p1-s4-terminal-closeout-v1"
EXPECTED_MODEL_FINGERPRINT = (
    "a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3"
)
REPAIR_COMMIT = "f4d38c249045796f05815aac6c244d6432cf703a"
WORKERS = 4
CONCURRENCY = 64
REPEAT = 2
PROOF_COUNT = 3

# Pre-registered independent machine-health gate M1: one load-average unit per
# logical CPU. Recorded closeout baseline was 4.79 on eight logical CPUs.
MAX_ONE_MINUTE_LOAD_AVERAGE = 8.00


def _load_average() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except OSError:
        return None


def _thermal_warning() -> bool:
    result = _run(("pmset", "-g", "therm"), timeout=10)
    if result.returncode != 0:
        return False
    text = result.stdout.lower()
    return "warning level" in text and "no thermal warning level" not in text


def _free_memory_percent() -> float | None:
    result = _run(("memory_pressure", "-Q"), timeout=10)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "free percentage" in line.lower():
            token = line.rsplit(":", 1)[-1].strip().rstrip("%")
            try:
                return float(token)
            except ValueError:
                return None
    return None


def _machine_health(stage: str) -> dict[str, Any]:
    """Sample host health outside the request and scheduler hot path."""
    load = _load_average()
    return {
        "stage": stage,
        "load_average_1m": round(load[0], 2) if load else None,
        "load_average_5m": round(load[1], 2) if load else None,
        "load_average_15m": round(load[2], 2) if load else None,
        "free_memory_percent": _free_memory_percent(),
        "thermal_warning_recorded": _thermal_warning(),
    }


def _port_is_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((POSTGRES_HOST, port)) == 0


def _evaluate_machine_health(
    before: dict[str, Any], after: dict[str, Any], *, sampler_failures: int
) -> dict[str, Any]:
    """Apply the pre-registered M1-M3 criteria. A failed gate is never M1-M3."""
    breaches: list[str] = []
    load_before = before.get("load_average_1m")
    if load_before is not None and load_before > MAX_ONE_MINUTE_LOAD_AVERAGE:
        breaches.append("M1_pre_run_load_average")
    if before.get("thermal_warning_recorded") or after.get("thermal_warning_recorded"):
        breaches.append("M2_thermal_warning")
    if sampler_failures:
        breaches.append("M3_task_infrastructure")
    return {
        "criteria": {
            "M1_max_one_minute_load_average": MAX_ONE_MINUTE_LOAD_AVERAGE,
            "M2_thermal_warning": False,
            "M3_task_infrastructure_failures": 0,
        },
        "before": before,
        "after": after,
        "breaches": breaches,
        "environment_valid": not breaches,
    }


def _safe_write(document: dict[str, Any], path: Path) -> Path:
    validate_safe_result(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)
    return path


def _disable_state_store_diagnostic() -> None:
    """Child API workers inherit os.environ, so clear rather than merely unset."""
    os.environ.pop(DIAGNOSTIC_FLAG, None)
    os.environ.pop(DIAGNOSTIC_OUTPUT_DIR, None)


def run(*, proofs: int, output_dir: Path) -> tuple[dict[str, Any], Path]:
    if not 1 <= proofs <= PROOF_COUNT:
        raise ScaleBenchmarkError("P1-S4 closeout permits one to three postfix proofs.")
    if not PROTOCOL_PATH.exists():
        raise ScaleBenchmarkError("The P1-S4 terminal closeout protocol is missing.")
    if _run(("git", "diff", "--quiet")).returncode != 0 or _run(
        ("git", "diff", "--cached", "--quiet")
    ).returncode != 0:
        raise ScaleBenchmarkError("P1-S4 postfix proofs require a clean tracked tree.")
    if _port_is_open(POSTGRES_PORT):
        raise ScaleBenchmarkError("M3: port 55432 is occupied before setup.")

    source_sha = _git_value("rev-parse", "HEAD")
    run_id = f"p1-s4-postfix-{int(time.time())}"
    report: dict[str, Any] = {
        "diagnostic_kind": "p1_s4_postfix_proof",
        "benchmark_version": BENCHMARK_VERSION,
        "publishable": False,
        "run_id": run_id,
        "source_commit_sha": source_sha,
        "repair_commit_sha": REPAIR_COMMIT,
        "protocol": {
            "path": str(PROTOCOL_PATH),
            "sha256": _sha256_file(PROTOCOL_PATH),
        },
        "frozen_cell": {"workers": WORKERS, "concurrency": CONCURRENCY, "repeat": REPEAT},
        "model_artifact_sha256": EXPECTED_MODEL_FINGERPRINT,
        "instrumentation": {
            "state_store_diagnostic": "disabled",
            "s4f_postgres_sampler": "not_started",
            "client_timing": "enabled",
            "s4e_resource_sampler": "unchanged_enabled",
        },
        "runtime": _machine_record(),
        "postgresql": {"image": POSTGRES_IMAGE, "endpoint": f"{POSTGRES_HOST}:{POSTGRES_PORT}"},
        "proofs": [],
    }
    result_path = output_dir / f"{run_id}.json"

    previous_client_timing = os.environ.get(CLIENT_TIMING_FLAG)
    previous_flag = os.environ.get(DIAGNOSTIC_FLAG)
    previous_output = os.environ.get(DIAGNOSTIC_OUTPUT_DIR)
    try:
        for proof in range(1, proofs + 1):
            health_before = _machine_health("before_run")
            with tempfile.TemporaryDirectory(
                prefix=f"secureswipe-p1-s4-postfix-{proof}-"
            ) as raw:
                temp_root = Path(raw).resolve(strict=True)
                artifact_root = temp_root / "synthetic-bundle"
                manifest = create_synthetic_bundle(artifact_root)
                record: dict[str, Any] | None = None
                failure: dict[str, Any] | None = None
                infrastructure_failures = 0
                _disable_state_store_diagnostic()
                os.environ[CLIENT_TIMING_FLAG] = "1"
                try:
                    with OwnedPostgres() as postgres:
                        try:
                            record = _run_repeat(
                                postgres=postgres,
                                workers=WORKERS,
                                concurrency=CONCURRENCY,
                                repeat=REPEAT,
                                smoke=False,
                                manifest=manifest,
                                artifact_root=artifact_root,
                                temp_root=temp_root,
                            )
                        except BenchmarkValidationError as exc:
                            failure = dict(exc.diagnostics)
                except (ScaleBenchmarkError, OSError) as exc:
                    infrastructure_failures = 1
                    failure = {
                        "diagnostic_schema": "p1_s4_postfix_infrastructure_failure_v1",
                        "failure_stage": "task_infrastructure",
                        "failure_type": type(exc).__name__,
                    }
                health_after = _machine_health("after_run")
                health = _evaluate_machine_health(
                    health_before, health_after, sampler_failures=infrastructure_failures
                )
                passed = record is not None and failure is None
                report["proofs"].append(
                    {
                        "proof": proof,
                        "bundle_manifest_sha256": _sha256_file(manifest),
                        "result": "passed" if passed else "failed",
                        "machine_health": health,
                        "correctness": (
                            {
                                "warmup": record["warmup"]["result"],
                                "measured": record["measured"]["result"],
                                "model": record["model"],
                                "audit": record["audit"],
                                "harness_validation": record["harness_validation"],
                                "resources": record["resources"],
                            }
                            if record is not None
                            else None
                        ),
                        "failure": failure,
                        "raw_log_policy": "removed_after_aggregate_capture",
                    }
                )
                _safe_write(report, result_path)
                if not passed:
                    break
    finally:
        if previous_client_timing is None:
            os.environ.pop(CLIENT_TIMING_FLAG, None)
        else:
            os.environ[CLIENT_TIMING_FLAG] = previous_client_timing
        if previous_flag is not None:
            os.environ[DIAGNOSTIC_FLAG] = previous_flag
        if previous_output is not None:
            os.environ[DIAGNOSTIC_OUTPUT_DIR] = previous_output

    passed_count = sum(item["result"] == "passed" for item in report["proofs"])
    invalid = [
        item
        for item in report["proofs"]
        if not item["machine_health"]["environment_valid"]
    ]
    if invalid:
        decision = "ENVIRONMENT_INVALID_REPLACEMENT_AUTHORIZED"
    elif passed_count == proofs == PROOF_COUNT:
        decision = "POSTFIX_PROOFS_PASSED_MATRIX_AUTHORIZED"
    else:
        decision = "POSTFIX_PROOF_FAILED_NO_SCALE_CLAIM"
    report["decision"] = decision
    report["passed_proof_count"] = passed_count
    report["cleanup"] = {
        "port_55432_closed": not _port_is_open(POSTGRES_PORT),
        "port_5432_touched": False,
        "raw_task_logs_removed": True,
    }
    _safe_write(report, result_path)
    return report, result_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proofs", type=int, default=PROOF_COUNT)
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report, path = run(proofs=args.proofs, output_dir=args.output_dir.resolve())
    except (ScaleBenchmarkError, OSError) as exc:
        print(f"P1-S4 postfix proof failed closed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "passed_proof_count": report["passed_proof_count"],
                "proofs": len(report["proofs"]),
                "result_path": str(path),
                "cleanup": report["cleanup"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
