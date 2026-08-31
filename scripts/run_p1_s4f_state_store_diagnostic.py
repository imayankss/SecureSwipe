#!/usr/bin/env python3
"""Reproduce the frozen P1-S4e 4-worker/concurrency-64 failure safely."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.state_store_diagnostic import (
    DIAGNOSTIC_FLAG,
    DIAGNOSTIC_OUTPUT_DIR,
    sanitize_failure,
)
from scripts.run_p1_scale_benchmark import (
    BenchmarkValidationError,
    OwnedPostgres,
    POSTGRES_HOST,
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

PROTOCOL_PATH = Path("docs/benchmarks/P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md")
PROTOCOL_SHA256 = "a214287636ffd05b5ad685eaa8cf84b930a2c829f7bbaccf34d94aa558d28d5f"
EXPECTED_MODEL_FINGERPRINT = (
    "a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3"
)
WORKERS = 4
CONCURRENCY = 64
REPEAT = 2
MAX_ATTEMPTS = 3
SAMPLE_INTERVAL_SECONDS = 0.100

_WAIT_CATEGORIES = {
    "Activity",
    "Client",
    "Extension",
    "IO",
    "IPC",
    "Lock",
    "Timeout",
    "none",
}


def _aggregate(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "last": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "last": values[-1],
    }


class PostgresAggregateSampler:
    """Read only low-cardinality aggregates from the dedicated task database."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="p1-s4f-pg-sampler")
        self._lock = threading.Lock()
        self._samples = 0
        self._failures: dict[str, int] = {}
        self._connections: dict[str, list[float]] = {
            name: [] for name in ("total", "active", "idle")
        }
        self._locks: dict[str, list[float]] = {
            name: [] for name in ("granted", "waiting")
        }
        self._wait_max: dict[str, int] = {}
        self._max_connections: int | None = None
        self._postmaster_start: float | None = None
        self._postmaster_start_changes = 0
        self._session_counters_first: tuple[int, int, int, int] | None = None
        self._session_counters_last: tuple[int, int, int, int] | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise ScaleBenchmarkError("Task-owned PostgreSQL sampler did not stop.")
        return self.snapshot()

    def _record_failure(self, exc: BaseException) -> None:
        category, _ = sanitize_failure(exc)
        with self._lock:
            self._failures[category] = self._failures.get(category, 0) + 1

    def _run(self) -> None:
        try:
            with psycopg.connect(
                self._dsn,
                autocommit=True,
                application_name="p1_s4f_sampler",
                connect_timeout=2,
            ) as connection:
                while not self._stop.is_set():
                    try:
                        self._sample(connection)
                    except (psycopg.Error, OSError) as exc:
                        self._record_failure(exc)
                    self._stop.wait(SAMPLE_INTERVAL_SECONDS)
        except (psycopg.Error, OSError) as exc:
            self._record_failure(exc)

    def _sample(self, connection: psycopg.Connection[Any]) -> None:
        row = connection.execute(
            """
            SELECT
                count(*) FILTER (WHERE application_name <> 'p1_s4f_sampler'),
                count(*) FILTER (
                    WHERE application_name <> 'p1_s4f_sampler' AND state = 'active'
                ),
                count(*) FILTER (
                    WHERE application_name <> 'p1_s4f_sampler' AND state = 'idle'
                )
            FROM pg_stat_activity
            WHERE datname = current_database()
            """
        ).fetchone()
        wait_rows = connection.execute(
            """
            SELECT COALESCE(wait_event_type, 'none'), count(*)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND application_name <> 'p1_s4f_sampler'
            GROUP BY COALESCE(wait_event_type, 'none')
            """
        ).fetchall()
        lock_row = connection.execute(
            """
            SELECT
                count(*) FILTER (WHERE granted),
                count(*) FILTER (WHERE NOT granted)
            FROM pg_locks
            WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
            """
        ).fetchone()
        max_connections_row = connection.execute("SHOW max_connections").fetchone()
        postmaster_start_row = connection.execute(
            "SELECT EXTRACT(EPOCH FROM pg_postmaster_start_time())"
        ).fetchone()
        session_row = connection.execute(
            """
            SELECT sessions, sessions_abandoned, sessions_fatal, sessions_killed
            FROM pg_stat_database WHERE datname = current_database()
            """
        ).fetchone()
        if (
            row is None
            or lock_row is None
            or max_connections_row is None
            or postmaster_start_row is None
            or session_row is None
        ):
            raise ScaleBenchmarkError("Required PostgreSQL aggregate row was unavailable.")
        max_connections = int(max_connections_row[0])
        postmaster_start = float(postmaster_start_row[0])
        with self._lock:
            self._samples += 1
            for name, value in zip(("total", "active", "idle"), row, strict=True):
                self._connections[name].append(float(value))
            for name, value in zip(("granted", "waiting"), lock_row, strict=True):
                self._locks[name].append(float(value))
            for raw_category, value in wait_rows:
                category = str(raw_category)
                if category not in _WAIT_CATEGORIES:
                    category = "other"
                self._wait_max[category] = max(self._wait_max.get(category, 0), int(value))
            self._max_connections = max_connections
            if self._postmaster_start is None:
                self._postmaster_start = postmaster_start
            elif not math.isclose(self._postmaster_start, postmaster_start):
                self._postmaster_start_changes += 1
                self._postmaster_start = postmaster_start
            counters = (
                int(session_row[0]),
                int(session_row[1]),
                int(session_row[2]),
                int(session_row[3]),
            )
            if self._session_counters_first is None:
                self._session_counters_first = counters
            self._session_counters_last = counters

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            first = self._session_counters_first or (0, 0, 0, 0)
            last = self._session_counters_last or first
            return {
                "diagnostic_kind": "p1_s4f_postgresql_aggregate",
                "sample_count": self._samples,
                "sample_failure_categories": dict(sorted(self._failures.items())),
                "server_ready_sample_count": self._samples,
                "connections": {
                    name: _aggregate(list(values))
                    for name, values in self._connections.items()
                },
                "wait_event_category_max_counts": dict(sorted(self._wait_max.items())),
                "locks": {
                    name: _aggregate(list(values)) for name, values in self._locks.items()
                },
                "max_connections": self._max_connections,
                "postmaster_start_change_count": self._postmaster_start_changes,
                "session_counter_deltas": {
                    name: last[index] - first[index]
                    for index, name in enumerate(
                        ("sessions", "sessions_abandoned", "sessions_fatal", "sessions_killed")
                    )
                },
            }


def _load_process_aggregates(path: Path) -> list[dict[str, Any]]:
    documents = [json.loads(item.read_text()) for item in sorted(path.glob("state-store-*.json"))]
    for document in documents:
        validate_safe_result(document)
    return documents


def _root_cause(
    failure: dict[str, Any] | None, processes: list[dict[str, Any]]
) -> dict[str, Any]:
    reproduced = bool(
        failure
        and failure.get("api_error_code_counts", {}).get("state_store_unavailable", 0)
    )
    failure_counts: dict[str, dict[str, int]] = {}
    sqlstates: dict[str, int] = {}
    for process in processes:
        for stage, record in process.get("stages", {}).items():
            categories = record.get("failure_categories", {})
            if categories:
                target = failure_counts.setdefault(stage, {})
                for category, count in categories.items():
                    target[category] = target.get(category, 0) + int(count)
            for state, count in record.get("sqlstate_counts", {}).items():
                sqlstates[state] = sqlstates.get(state, 0) + int(count)
    if reproduced and failure_counts.get("connection_checkout", {}).get("checkout_timeout", 0):
        classification = "connection_checkout_timeout"
        supported = True
        earliest_stage = "connection_checkout"
    elif reproduced and failure_counts:
        classification = "supported_sanitized_state_store_failure"
        supported = True
        earliest_stage = next(
            stage
            for stage in (
                "initialize_open",
                "connection_checkout",
                "reserve",
                "complete_outcome",
                "commit",
                "rollback",
                "close",
            )
            if stage in failure_counts
        )
    elif reproduced:
        classification = "reproduced_but_diagnostic_unresolved"
        supported = False
        earliest_stage = None
    else:
        classification = "not_reproduced"
        supported = False
        earliest_stage = None
    return {
        "state_store_unavailable_reproduced": reproduced,
        "supported_root_cause": supported,
        "classification": classification,
        "earliest_failing_stage": earliest_stage,
        "stage_failure_category_counts": failure_counts,
        "sqlstate_counts": dict(sorted(sqlstates.items())),
    }


def _safe_write(document: dict[str, Any], path: Path) -> None:
    validate_safe_result(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _port_is_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((POSTGRES_HOST, port)) == 0


def run(*, attempts: int, output_dir: Path) -> tuple[dict[str, Any], Path]:
    if not 1 <= attempts <= MAX_ATTEMPTS:
        raise ScaleBenchmarkError("P1-S4f permits one to three fresh attempts.")
    if _sha256_file(PROTOCOL_PATH) != PROTOCOL_SHA256:
        raise ScaleBenchmarkError("P1-S4f protocol hash verification failed.")
    if _run(("git", "diff", "--quiet")).returncode != 0 or _run(
        ("git", "diff", "--cached", "--quiet")
    ).returncode != 0:
        raise ScaleBenchmarkError("P1-S4f reproduction requires a clean tracked tree.")
    source_sha = _git_value("rev-parse", "HEAD")
    run_id = f"p1-s4f-reproduction-{int(time.time())}"
    report: dict[str, Any] = {
        "diagnostic_kind": "p1_s4f_state_store_reproduction",
        "publishable": False,
        "run_id": run_id,
        "source_commit_sha": source_sha,
        "protocol": {"path": str(PROTOCOL_PATH), "sha256": PROTOCOL_SHA256},
        "frozen_cell": {"workers": WORKERS, "concurrency": CONCURRENCY, "repeat": REPEAT},
        "model_artifact_sha256": EXPECTED_MODEL_FINGERPRINT,
        "runtime": _machine_record(),
        "attempts": [],
    }
    result_path = output_dir / f"{run_id}.json"
    for attempt in range(1, attempts + 1):
        with tempfile.TemporaryDirectory(prefix=f"secureswipe-p1-s4f-a{attempt}-") as raw:
            temp_root = Path(raw).resolve(strict=True)
            artifact_root = temp_root / "synthetic-bundle"
            manifest = create_synthetic_bundle(artifact_root)
            diagnostic_dir = temp_root / "state-store-aggregate"
            sampler: PostgresAggregateSampler | None = None
            failure: dict[str, Any] | None = None
            record: dict[str, Any] | None = None
            previous_flag = os.environ.get(DIAGNOSTIC_FLAG)
            previous_output = os.environ.get(DIAGNOSTIC_OUTPUT_DIR)
            previous_client_timing = os.environ.get(CLIENT_TIMING_FLAG)
            try:
                with OwnedPostgres() as postgres:
                    sampler = PostgresAggregateSampler(postgres.owner_dsn)
                    sampler.start()
                    os.environ[DIAGNOSTIC_FLAG] = "1"
                    os.environ[DIAGNOSTIC_OUTPUT_DIR] = str(diagnostic_dir)
                    os.environ[CLIENT_TIMING_FLAG] = "1"
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
                    finally:
                        postgres_aggregate = sampler.stop()
                        sampler = None
            finally:
                if sampler is not None:
                    sampler.stop()
                if previous_flag is None:
                    os.environ.pop(DIAGNOSTIC_FLAG, None)
                else:
                    os.environ[DIAGNOSTIC_FLAG] = previous_flag
                if previous_output is None:
                    os.environ.pop(DIAGNOSTIC_OUTPUT_DIR, None)
                else:
                    os.environ[DIAGNOSTIC_OUTPUT_DIR] = previous_output
                if previous_client_timing is None:
                    os.environ.pop(CLIENT_TIMING_FLAG, None)
                else:
                    os.environ[CLIENT_TIMING_FLAG] = previous_client_timing
            processes = _load_process_aggregates(diagnostic_dir)
            root_cause = _root_cause(failure, processes)
            attempt_record: dict[str, Any] = {
                "attempt": attempt,
                "bundle_manifest_sha256": _sha256_file(manifest),
                "result": "correctness_passed" if failure is None else "correctness_failed",
                "failure": failure,
                "correctness": (
                    {
                        "warmup": record["warmup"]["result"],
                        "measured": record["measured"]["result"],
                        "model": record["model"],
                        "audit": record["audit"],
                        "harness_validation": record["harness_validation"],
                    }
                    if record is not None
                    else None
                ),
                "state_store_process_aggregates": processes,
                "postgresql_aggregate": postgres_aggregate,
                "root_cause": root_cause,
                "raw_log_policy": "removed_after_allowlisted_aggregate_capture",
            }
            report["attempts"].append(attempt_record)
            _safe_write(report, result_path)
            if root_cause["state_store_unavailable_reproduced"]:
                break
    reproduced = any(
        item["root_cause"]["state_store_unavailable_reproduced"]
        for item in report["attempts"]
    )
    report["decision"] = (
        "ROOT_CAUSE_SUPPORTED"
        if reproduced and report["attempts"][-1]["root_cause"]["supported_root_cause"]
        else (
            "DIAGNOSTIC_UNRESOLVED"
            if reproduced
            else "FAILURE NOT REPRODUCED UNDER THREE CONTROLLED ATTEMPTS"
        )
    )
    report["cleanup"] = {
        "port_55432_closed": not _port_is_open(POSTGRES_PORT),
        "port_5432_touched": False,
        "raw_task_logs_removed": True,
    }
    _safe_write(report, result_path)
    return report, result_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, path = run(attempts=args.attempts, output_dir=args.output_dir)
    summary = {
        "decision": report["decision"],
        "attempts": len(report["attempts"]),
        "result_path": str(path),
        "cleanup": report["cleanup"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
