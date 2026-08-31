"""Exact-opt-in, aggregate-only PostgreSQL state-store diagnostics for P1-S4f."""

from __future__ import annotations

import atexit
import errno
import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from psycopg_pool import PoolClosed, PoolTimeout

DIAGNOSTIC_FLAG = "SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC"
DIAGNOSTIC_OUTPUT_DIR = "SECURESWIPE_P1_S4F_STATE_STORE_DIAGNOSTIC_OUTPUT_DIR"
DIAGNOSTIC_SCHEMA_VERSION = "p1-s4f-state-store-diagnostic-v1"

STAGES: tuple[str, ...] = (
    "initialize_open",
    "connection_checkout",
    "reserve",
    "complete_outcome",
    "commit",
    "rollback",
    "close",
)

FAILURE_CATEGORIES: tuple[str, ...] = (
    "pool_closed",
    "connection_closed",
    "checkout_timeout",
    "connection_refused",
    "postgres_operational_error",
    "postgres_interface_error",
    "transaction_error",
    "serialization_error",
    "resource_limit",
    "unknown_state_store_error",
)

POOL_COUNTERS: tuple[str, ...] = (
    "pool_min",
    "pool_max",
    "pool_size",
    "pool_available",
    "requests_waiting",
    "requests_num",
    "requests_queued",
    "requests_errors",
    "connections_num",
    "connections_errors",
    "connections_lost",
    "returns_bad",
)

_SQLSTATE = re.compile(r"^[0-9A-Z]{5}$")
_FLUSH_EVERY = 25


class PoolStatsProvider(Protocol):
    def get_stats(self) -> Mapping[str, int | float]: ...


def diagnostic_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source: Mapping[str, str] = os.environ if environment is None else environment
    return source.get(DIAGNOSTIC_FLAG, "") == "1"


def _nearest_rank(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * fraction)) - 1]


def _aggregate(values: Sequence[float]) -> dict[str, int | float | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "median": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": len(values),
        "min": round(min(values), 4),
        "median": round(_nearest_rank(values, 0.50), 4),
        "p95": round(_nearest_rank(values, 0.95), 4),
        "p99": round(_nearest_rank(values, 0.99), 4),
        "max": round(max(values), 4),
    }


def _sqlstate(exc: BaseException) -> str | None:
    value = getattr(exc, "sqlstate", None)
    if isinstance(value, str) and _SQLSTATE.fullmatch(value):
        return value
    return None


def sanitize_failure(exc: BaseException) -> tuple[str, str | None]:
    """Return only an allowlisted category and syntactically valid SQLSTATE."""
    state = _sqlstate(exc)
    if isinstance(exc, PoolClosed):
        category = "pool_closed"
    elif isinstance(exc, PoolTimeout):
        category = "checkout_timeout"
    elif isinstance(exc, OSError):
        if exc.errno == errno.ECONNREFUSED:
            category = "connection_refused"
        elif exc.errno in {errno.EMFILE, errno.ENFILE, errno.ENOMEM, errno.ENOBUFS}:
            category = "resource_limit"
        else:
            category = "unknown_state_store_error"
    elif state == "40001":
        category = "serialization_error"
    elif state is not None and state.startswith("53"):
        category = "resource_limit"
    elif isinstance(exc, psycopg.OperationalError):
        category = "connection_closed" if state is not None and state.startswith("08") else (
            "postgres_operational_error"
        )
    elif isinstance(exc, psycopg.InterfaceError):
        category = "postgres_interface_error"
    elif isinstance(exc, psycopg.DatabaseError):
        category = "transaction_error"
    else:
        category = "unknown_state_store_error"
    return category, state


def _pool_snapshot(pool: PoolStatsProvider | None) -> dict[str, float]:
    if pool is None:
        return {}
    try:
        values = pool.get_stats()
    except Exception:
        return {}
    snapshot: dict[str, float] = {}
    for name in POOL_COUNTERS:
        value = values.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number) and number >= 0:
                snapshot[name] = number
    return snapshot


class StageObservation:
    __slots__ = ("_aggregator", "_finished", "_pool", "_stage", "_started")

    def __init__(
        self,
        aggregator: StateStoreDiagnosticAggregator,
        stage: str,
        pool: PoolStatsProvider | None,
    ) -> None:
        self._aggregator = aggregator
        self._stage = stage
        self._pool = pool
        self._started = perf_counter()
        self._finished = False

    def success(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._aggregator.record(
            stage=self._stage,
            duration_ms=(perf_counter() - self._started) * 1000.0,
            succeeded=True,
            failure=None,
            pool=_pool_snapshot(self._pool),
        )

    def failure(self, exc: BaseException) -> None:
        if self._finished:
            return
        self._finished = True
        self._aggregator.record(
            stage=self._stage,
            duration_ms=(perf_counter() - self._started) * 1000.0,
            succeeded=False,
            failure=sanitize_failure(exc),
            pool=_pool_snapshot(self._pool),
        )


class StateStoreDiagnosticAggregator:
    """Persist per-process counts and distributions, never request-level records."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._attempts = 0
        self._stages: dict[str, dict[str, Any]] = {
            stage: {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "durations": [],
                "failure_categories": {},
                "sqlstates": {},
                "pool": {name: [] for name in POOL_COUNTERS},
            }
            for stage in STAGES
        }
        atexit.register(self.flush)

    def start(
        self, stage: str, pool: PoolStatsProvider | None = None
    ) -> StageObservation:
        if stage not in STAGES:
            raise ValueError("State-store diagnostic stage is not allowlisted.")
        return StageObservation(self, stage, pool)

    def record(
        self,
        *,
        stage: str,
        duration_ms: float,
        succeeded: bool,
        failure: tuple[str, str | None] | None,
        pool: Mapping[str, float],
    ) -> None:
        if stage not in STAGES or not math.isfinite(duration_ms) or duration_ms < 0:
            return
        with self._lock:
            record = self._stages[stage]
            record["attempts"] += 1
            record["successes" if succeeded else "failures"] += 1
            record["durations"].append(duration_ms)
            if failure is not None:
                category, state = failure
                if category not in FAILURE_CATEGORIES:
                    category = "unknown_state_store_error"
                categories = record["failure_categories"]
                categories[category] = categories.get(category, 0) + 1
                if state is not None:
                    states = record["sqlstates"]
                    states[state] = states.get(state, 0) + 1
            for name, value in pool.items():
                if name in POOL_COUNTERS:
                    record["pool"][name].append(value)
            self._attempts += 1
            due = self._attempts % _FLUSH_EVERY == 0 or not succeeded
        if due:
            self.flush()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stages: dict[str, Any] = {}
            for name in STAGES:
                record = self._stages[name]
                stages[name] = {
                    "attempt_count": record["attempts"],
                    "success_count": record["successes"],
                    "failure_count": record["failures"],
                    "duration_ms": _aggregate(tuple(record["durations"])),
                    "failure_categories": dict(sorted(record["failure_categories"].items())),
                    "sqlstate_counts": dict(sorted(record["sqlstates"].items())),
                    "pool_counters": {
                        key: _aggregate(tuple(values))
                        for key, values in record["pool"].items()
                        if values
                    },
                }
        return {
            "diagnostic_kind": "p1_s4f_state_store_process_aggregate",
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "process_id": os.getpid(),
            "unit": "milliseconds",
            "stages": stages,
        }

    def flush(self) -> Path | None:
        document = self.snapshot()
        if not any(item["attempt_count"] for item in document["stages"].values()):
            return None
        with self._flush_lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"state-store-{os.getpid()}.json"
            temporary_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.output_dir,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_name = temporary.name
                    json.dump(document, temporary, indent=2, sort_keys=True, allow_nan=False)
                    temporary.write("\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, path)
            finally:
                if temporary_name is not None:
                    Path(temporary_name).unlink(missing_ok=True)
            return path


def aggregator_from_environment(
    environment: Mapping[str, str] | None = None,
) -> StateStoreDiagnosticAggregator | None:
    source: Mapping[str, str] = os.environ if environment is None else environment
    if not diagnostic_enabled(source):
        return None
    configured = source.get(DIAGNOSTIC_OUTPUT_DIR, "").strip()
    output_dir = Path(configured) if configured else Path(
        "reports/benchmarks/p1-scale-results/state-store-diagnostic"
    )
    return StateStoreDiagnosticAggregator(output_dir)


__all__ = [
    "DIAGNOSTIC_FLAG",
    "DIAGNOSTIC_OUTPUT_DIR",
    "DIAGNOSTIC_SCHEMA_VERSION",
    "FAILURE_CATEGORIES",
    "POOL_COUNTERS",
    "STAGES",
    "StageObservation",
    "StateStoreDiagnosticAggregator",
    "aggregator_from_environment",
    "diagnostic_enabled",
    "sanitize_failure",
]
