"""Deterministic, privacy-bounded primitives for the P1 scale benchmark.

This module constructs synthetic-only request schedules and validates aggregate
results. It deliberately has no database, process, or network side effects.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from src.operations.benchmark import synthetic_corpus

PROTOCOL_VERSION = "p1-scale-protocol-v1"
FIXTURE_VERSION = "p1-scale-fixture-v1"
PREDICTION_ROUTE = "/v2/predict"
STATE_BACKEND = "postgres-scale"
POSTGRES_HOST = "127.0.0.1"
POSTGRES_PORT = 55432
POSTGRES_VERSION = "16.10"
POSTGRES_IMAGE = "postgres:16-alpine"
POSTGRES_IMAGE_DIGEST = (
    "postgres@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297"
)

WORKER_COUNTS = (1, 2, 4)
CONCURRENCY_LEVELS = (1, 8, 32, 64)
REPEAT_NUMBERS = (1, 2, 3)

RequestKind = Literal["valid", "replay", "malformed"]
Phase = Literal["warmup", "measured", "smoke-warmup", "smoke-measured"]


class ScaleBenchmarkError(RuntimeError):
    """Raised when a frozen workload or result invariant is violated."""


@dataclass(frozen=True)
class RequestSpec:
    """One in-memory synthetic request; never serialize this object to results."""

    kind: RequestKind
    request_id: str
    body: dict[str, float]


@dataclass(frozen=True)
class Workload:
    phase: Phase
    workers: int
    concurrency: int
    repeat: int
    seed: int
    requests: tuple[RequestSpec, ...]

    @property
    def counts(self) -> dict[str, int]:
        counts = Counter(item.kind for item in self.requests)
        return {
            "valid": counts["valid"],
            "replay": counts["replay"],
            "malformed": counts["malformed"],
        }

    @property
    def manifest_sha256(self) -> str:
        """Hash the complete schedule without exposing it in a saved report."""
        manifest = [
            {
                "kind": item.kind,
                "request_id": item.request_id,
                "body": item.body,
            }
            for item in self.requests
        ]
        encoded = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def safe_manifest(self) -> dict[str, Any]:
        return {
            "fixture_version": FIXTURE_VERSION,
            "phase": self.phase,
            "seed": self.seed,
            "attempts": len(self.requests),
            "counts": self.counts,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class RequestOutcome:
    request_kind: RequestKind
    status_code: int | None
    latency_ms: float
    timeout: bool = False
    transport_error: bool = False
    contract_valid: bool = True


def _validate_dimensions(workers: int, concurrency: int, repeat: int) -> None:
    if workers not in WORKER_COUNTS:
        raise ScaleBenchmarkError(f"workers must be one of {WORKER_COUNTS}.")
    if concurrency not in CONCURRENCY_LEVELS:
        raise ScaleBenchmarkError(f"concurrency must be one of {CONCURRENCY_LEVELS}.")
    if repeat not in REPEAT_NUMBERS:
        raise ScaleBenchmarkError(f"repeat must be one of {REPEAT_NUMBERS}.")


def build_workload(
    *, workers: int, concurrency: int, repeat: int, phase: Phase
) -> Workload:
    """Build the frozen full or deliberately small non-publishable smoke mix."""
    _validate_dimensions(workers, concurrency, repeat)
    if phase in {"warmup", "measured"}:
        valid_count = 70 if phase == "warmup" else 700
        malformed_count = 10 if phase == "warmup" else 100
        replay_sources = 2 if phase == "warmup" else 20
        replays_per_source = 10
        phase_token = "warmup" if phase == "warmup" else f"r{repeat}"
        seed = 20260830 + workers * 10000 + concurrency * 100 + repeat
        if phase == "warmup":
            seed += 1_000_000
    else:
        valid_count = 7
        malformed_count = 1
        replay_sources = 2
        replays_per_source = 1
        phase_token = phase
        seed = 20260830 + workers * 10000 + concurrency * 100 + repeat + 2_000_000

    corpus = synthetic_corpus(valid_count, seed=42)
    prefix = f"p1sf-v1-w{workers}-c{concurrency}-{phase_token}"
    valid = [
        RequestSpec("valid", f"{prefix}-valid-{index:04d}", corpus[index])
        for index in range(valid_count)
    ]
    replays = [
        RequestSpec("replay", valid[index].request_id, valid[index].body)
        for index in range(replay_sources)
        for _ in range(replays_per_source)
    ]
    malformed = [
        RequestSpec(
            "malformed",
            f"{prefix}-invalid-{index:04d}",
            {"Time": float(index)},
        )
        for index in range(malformed_count)
    ]
    requests = [*valid, *replays, *malformed]
    random.Random(seed).shuffle(requests)
    return Workload(phase, workers, concurrency, repeat, seed, tuple(requests))


def nearest_rank(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ScaleBenchmarkError("Cannot calculate a percentile without samples.")
    if not 0 < fraction <= 1:
        raise ScaleBenchmarkError("Percentile fraction must be in (0, 1].")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * fraction)) - 1]


def summarize_outcomes(
    workload: Workload, outcomes: Sequence[RequestOutcome], wall_seconds: float
) -> dict[str, Any]:
    """Reconcile every attempt and fail closed on a wrong status/contract mix."""
    if len(outcomes) != len(workload.requests):
        raise ScaleBenchmarkError(
            f"Outcome count {len(outcomes)} != attempt count {len(workload.requests)}."
        )
    if wall_seconds <= 0:
        raise ScaleBenchmarkError("Measured wall time must be positive.")

    status_counts: Counter[int] = Counter()
    expected_status_counts: Counter[int] = Counter()
    unexpected_status_counts: Counter[int] = Counter()
    timeouts = transport_errors = invalid_contracts = 0
    completed_latencies: list[float] = []
    successful_latencies: list[float] = []

    for outcome in outcomes:
        if outcome.timeout:
            timeouts += 1
            continue
        if outcome.transport_error:
            transport_errors += 1
            continue
        if outcome.status_code is None:
            raise ScaleBenchmarkError("Completed outcome is missing a status code.")
        status_counts[outcome.status_code] += 1
        completed_latencies.append(outcome.latency_ms)
        expected = 422 if outcome.request_kind == "malformed" else 200
        if outcome.status_code == expected:
            expected_status_counts[expected] += 1
        else:
            unexpected_status_counts[outcome.status_code] += 1
        if not outcome.contract_valid:
            invalid_contracts += 1
        if 200 <= outcome.status_code < 300:
            successful_latencies.append(outcome.latency_ms)

    if timeouts or transport_errors or unexpected_status_counts or invalid_contracts:
        raise ScaleBenchmarkError(
            "Result validation failed: "
            f"timeouts={timeouts}, transport_errors={transport_errors}, "
            f"unexpected_statuses={dict(unexpected_status_counts)}, "
            f"invalid_contracts={invalid_contracts}."
        )
    expected_successes = workload.counts["valid"] + workload.counts["replay"]
    if status_counts[200] != expected_successes or status_counts[422] != workload.counts["malformed"]:
        raise ScaleBenchmarkError("Expected 2xx/422 outcome mix did not reconcile.")

    def percentiles(values: Sequence[float]) -> dict[str, float]:
        return {
            "p50_ms": round(nearest_rank(values, 0.50), 3),
            "p95_ms": round(nearest_rank(values, 0.95), 3),
            "p99_ms": round(nearest_rank(values, 0.99), 3),
        }

    return {
        "attempted": len(outcomes),
        "completed": len(completed_latencies),
        "successful_2xx": status_counts[200],
        "expected_non_2xx": status_counts[422],
        "unexpected_non_2xx": sum(unexpected_status_counts.values()),
        "timeouts": timeouts,
        "transport_errors": transport_errors,
        "status_counts": {str(key): value for key, value in sorted(status_counts.items())},
        "expected_status_counts": {
            str(key): value for key, value in sorted(expected_status_counts.items())
        },
        "wall_seconds": round(wall_seconds, 6),
        "successful_rps": round(status_counts[200] / wall_seconds, 3),
        "all_completed_latency": percentiles(completed_latencies),
        "successful_latency": percentiles(successful_latencies),
    }


_FORBIDDEN_RESULT_KEYS = {
    "dsn",
    "secret",
    "password",
    "payload",
    "features",
    "raw_score",
    "decision_score",
    "calibrated_probability",
    "request_id",
}


def validate_safe_result(value: Any, *, path: str = "result") -> None:
    """Reject secret-, input-, ID-, and score-shaped fields before persistence."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _FORBIDDEN_RESULT_KEYS or normalized.endswith("_dsn"):
                raise ScaleBenchmarkError(f"Forbidden saved-result field at {path}.{key}.")
            validate_safe_result(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_safe_result(item, path=f"{path}[{index}]")


def assert_safe_target(*, host: str, port: int, route: str, backend: str) -> None:
    if host != POSTGRES_HOST or port != POSTGRES_PORT:
        raise ScaleBenchmarkError("Benchmark PostgreSQL target must be 127.0.0.1:55432.")
    if route != PREDICTION_ROUTE or backend != STATE_BACKEND:
        raise ScaleBenchmarkError("Benchmark traffic must use postgres-scale POST /v2/predict.")
