#!/usr/bin/env python3
"""Run the four-cell P1-S4d client transport diagnostic, and nothing else."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.scale_lifecycle_timing import (  # noqa: E402
    LIFECYCLE_TIMING_FLAG,
    LIFECYCLE_TIMING_OUTPUT_DIR,
)
from scripts.run_p1_scale_benchmark import (  # noqa: E402
    RESULT_DIRECTORY,
    TIMEOUT_SECONDS,
    OwnedPostgres,
    ScaleBenchmarkError,
    _git_value,
    _machine_record,
    _run_repeat,
    _sha256_file,
    _write_safe_json,
)
from scripts.create_synthetic_bundle import create_synthetic_bundle  # noqa: E402
from src.operations.p1_scale_benchmark import (  # noqa: E402
    POSTGRES_HOST,
    POSTGRES_IMAGE,
    POSTGRES_PORT,
    POSTGRES_VERSION,
    PREDICTION_ROUTE,
    STATE_BACKEND,
    validate_safe_result,
)
from src.operations.p1_scale_client_timing import CLIENT_TIMING_FLAG  # noqa: E402

PROTOCOL_PATH = Path("docs/benchmarks/P1_S4D_CLIENT_TRANSPORT_PROTOCOL.md")
PROTOCOL_SHA256 = "d8fde6108af5e7cf0b1771c77f9ace71778b155102ed1071d38e379742253f6e"
PARENT_ARTIFACT_PATH = Path(
    "reports/benchmarks/p1-scale-results/p1-s4c-lifecycle-1788130435.json"
)
PARENT_ARTIFACT_SHA256 = (
    "403dc5907c5c71838f9a7d118c68d088685178cc68f20ab44a22aacb5725d73f"
)
EXPECTED_MODEL_FINGERPRINT = (
    "a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3"
)
CELLS = ((1, 8, 1), (4, 32, 1), (4, 64, 1), (4, 64, 2))
INSTRUMENTATION_PATHS = (
    Path("scripts/run_p1_scale_benchmark.py"),
    Path("scripts/run_p1_s4d_client_diagnostic.py"),
    Path("src/operations/p1_scale_client_timing.py"),
)


def _instrumentation_sha256(paths: tuple[Path, ...] = INSTRUMENTATION_PATHS) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update((PROJECT_ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _verify_input(path: Path, expected_sha256: str) -> None:
    absolute = PROJECT_ROOT / path
    if not absolute.is_file() or _sha256_file(absolute) != expected_sha256:
        raise ScaleBenchmarkError(f"Required diagnostic input failed verification: {path}.")


@contextmanager
def _diagnostic_environment(output_dir: Path) -> Iterator[None]:
    updates = {
        CLIENT_TIMING_FLAG: "1",
        LIFECYCLE_TIMING_FLAG: "1",
        LIFECYCLE_TIMING_OUTPUT_DIR: str(output_dir),
    }
    original = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _safe_lifecycle_records(output_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    outcomes = {"owner": 0, "completed_replay": 0, "pending_fail_closed": 0}
    total_requests = 0
    for index, path in enumerate(sorted(output_dir.glob("scale-lifecycle-timing-*.json")), 1):
        document = json.loads(path.read_text(encoding="utf-8"))
        outcome_counts = document.get("reservation_outcome_counts", {})
        for name in outcomes:
            outcomes[name] += int(outcome_counts.get(name, 0))
        requests = int(document.get("requests", 0))
        total_requests += requests
        records.append(
            {
                "anonymous_process": f"worker_process_{index:02d}",
                "schema_version": document.get("schema_version"),
                "requests": requests,
                "reservation_outcome_counts": {
                    name: int(outcome_counts.get(name, 0)) for name in outcomes
                },
                "metrics": document.get("metrics", {}),
                "event_loop_lag": document.get("event_loop_lag", {}),
            }
        )
    if not records:
        raise ScaleBenchmarkError("Server lifecycle timing artifacts were not produced.")
    return {
        "process_aggregates": records,
        "combined_request_count": total_requests,
        "combined_reservation_outcome_counts": outcomes,
    }


def _verify_cell(record: Mapping[str, Any]) -> None:
    warmup = record["warmup"]["result"]
    measured = record["measured"]["result"]
    for result, successes, malformed in ((warmup, 90, 10), (measured, 900, 100)):
        if (
            result["successful_2xx"] != successes
            or result["expected_non_2xx"] != malformed
            or result["unexpected_non_2xx"] != 0
            or result["timeouts"] != 0
            or result["transport_errors"] != 0
        ):
            raise ScaleBenchmarkError("P1-S4d request/status correctness failed closed.")
        timing = result.get("client_timing")
        if not isinstance(timing, dict):
            raise ScaleBenchmarkError("P1-S4d client timing was not captured.")
        if timing.get("diagnostic_recording_failures") != 0:
            raise ScaleBenchmarkError("P1-S4d client timing recording failed.")
        attempted = int(result["attempted"])
        connection_total = sum(timing["connection_counts"].values())
        if connection_total != attempted:
            raise ScaleBenchmarkError("Connection classification count did not reconcile.")
    lifecycle = record["server_lifecycle"]
    expected_outcomes = {
        "owner": 770,
        "completed_replay": 220,
        "pending_fail_closed": 0,
    }
    if lifecycle["combined_request_count"] != 990:
        raise ScaleBenchmarkError("Lifecycle request count did not reconcile.")
    if lifecycle["combined_reservation_outcome_counts"] != expected_outcomes:
        raise ScaleBenchmarkError("Lifecycle reservation outcomes did not reconcile.")
    audit = record["audit"]
    if (
        audit["warmup_growth"] != 70
        or audit["measured_growth"] != 700
        or audit["full_verifier_status"] != "verified"
    ):
        raise ScaleBenchmarkError("Audit growth or full-chain verification failed.")
    if record["model"]["model_artifact_sha256"] != EXPECTED_MODEL_FINGERPRINT:
        raise ScaleBenchmarkError("Model fingerprint did not match the frozen protocol.")


def _port_closed() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((POSTGRES_HOST, POSTGRES_PORT)) != 0


def run_diagnostic(*, output_dir: Path) -> dict[str, Any]:
    _verify_input(PROTOCOL_PATH, PROTOCOL_SHA256)
    _verify_input(PARENT_ARTIFACT_PATH, PARENT_ARTIFACT_SHA256)
    source_commit = _git_value("rev-parse", "HEAD")
    run_id = f"p1-s4d-client-transport-{int(time.time())}"
    artifact = output_dir / f"{run_id}.json"
    instrumentation_sha256 = _instrumentation_sha256()
    completed: list[dict[str, Any]] = []
    base: dict[str, Any] = {
        "schema_version": "p1-s4d-client-transport-result-v1",
        "purpose": "attribute_client_transport_and_combined_response_header_wait",
        "non_claim": "diagnostic_only_no_scalability_capacity_or_slo_claim",
        "run_id": run_id,
        "measurement_source_commit": source_commit,
        "instrumentation_files_sha256": instrumentation_sha256,
        "protocol": {"path": str(PROTOCOL_PATH), "sha256": PROTOCOL_SHA256},
        "parent_diagnostic": {
            "path": str(PARENT_ARTIFACT_PATH),
            "sha256": PARENT_ARTIFACT_SHA256,
        },
        "runtime": _machine_record(),
        "target": {
            "state_backend": STATE_BACKEND,
            "prediction_route": PREDICTION_ROUTE,
            "postgresql_host": POSTGRES_HOST,
            "postgresql_port": POSTGRES_PORT,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "cells": completed,
        "limitations": [
            "connection_pool_acquisition_is_not_observable_with_supported_hooks",
            "response_header_wait_combines_transport_ingress_dispatch_handler_and_header_send",
            "server_process_aggregate_percentiles_are_not_merged_across_processes",
            "diagnostic_results_do_not_change_p1_s1_gates_or_authorize_scalability_claims",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="secureswipe-p1-s4d-") as temporary:
            temp_root = Path(temporary).resolve(strict=True)
            artifact_root = temp_root / "synthetic-bundle"
            manifest = create_synthetic_bundle(artifact_root)
            base["bundle_manifest_sha256"] = _sha256_file(manifest)
            with OwnedPostgres() as postgres:
                base["postgresql"] = {
                    "version": postgres.server_version(),
                    "image": POSTGRES_IMAGE,
                    "image_digest": postgres.image_digest(),
                    "expected_version": POSTGRES_VERSION,
                    "settings": postgres.database_settings(),
                }
                for workers, concurrency, repeat in CELLS:
                    lifecycle_dir = temp_root / (
                        f"lifecycle-w{workers}-c{concurrency}-r{repeat}"
                    )
                    with _diagnostic_environment(lifecycle_dir):
                        record = _run_repeat(
                            postgres=postgres,
                            workers=workers,
                            concurrency=concurrency,
                            repeat=repeat,
                            smoke=False,
                            manifest=manifest,
                            artifact_root=artifact_root,
                            temp_root=temp_root,
                        )
                    record["server_lifecycle"] = _safe_lifecycle_records(lifecycle_dir)
                    _verify_cell(record)
                    completed.append(record)
                    _write_safe_json(
                        {
                            **base,
                            "evidence_status": "in_progress",
                            "cleanup": "pending",
                        },
                        artifact,
                    )
        cleanup = {
            "task_owned_api_processes": "stopped",
            "task_owned_postgresql_container": "removed",
            "task_owned_postgresql_volume": "removed",
            "temporary_logs_and_timing_files": "removed_after_aggregate_capture",
            "postgresql_port_55432_closed": _port_closed(),
        }
        if not cleanup["postgresql_port_55432_closed"]:
            raise ScaleBenchmarkError("Task-owned PostgreSQL port remained open after cleanup.")
        report = {**base, "evidence_status": "completed", "cleanup": cleanup}
        validate_safe_result(report)
        _write_safe_json(report, artifact)
        report["result_artifact"] = {
            "path": str(artifact.relative_to(PROJECT_ROOT)),
            "sha256": _sha256_file(artifact),
        }
        return report
    except BaseException as exc:
        partial = {
            **base,
            "evidence_status": "failed_closed",
            "failure_type": type(exc).__name__,
            "cleanup": {
                "postgresql_port_55432_closed_after_failure": _port_closed()
            },
        }
        _write_safe_json(partial, artifact)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-four-cells", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_four_cells:
        print("P1-S4d diagnostic failed closed: --confirm-four-cells is required.")
        return 1
    try:
        report = run_diagnostic(output_dir=args.output_dir.resolve())
    except BaseException as exc:
        print(f"P1-S4d diagnostic failed closed: {type(exc).__name__}")
        return 1
    print(
        json.dumps(
            {
                "run_id": report["run_id"],
                "completed_cells": len(report["cells"]),
                "result_artifact": report["result_artifact"],
                "cleanup": report["cleanup"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
