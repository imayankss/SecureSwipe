"""MT4 loopback concurrency benchmark primitives.

Serving-plumbing measurement only. This module never trains, tunes, calibrates
or evaluates a model, never reads a held-out role, and never records a request
body, feature value, identifier, or score tied to a record.

Every quantity produced here is a low-cardinality aggregate.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping, Sequence

#: Concurrency levels fixed by the MT4 protocol.
CONCURRENCY_LEVELS: tuple[int, ...] = (1, 2, 4, 8, 16)

#: Minimum measured repeats per configuration and level, fixed by the protocol.
MIN_REPEATS = 3

#: The published PCA feature names the serving contract expects.
PCA_FEATURES: tuple[str, ...] = tuple(f"V{i}" for i in range(1, 29))
FEATURE_ORDER: tuple[str, ...] = ("Time", *PCA_FEATURES, "Amount")

#: Label every MT4 result must carry.
PROVENANCE_LABEL = "HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS"


class BenchmarkError(RuntimeError):
    """Raised when a benchmark invariant is violated."""


def synthetic_corpus(size: int, *, seed: int = 42) -> list[dict[str, float]]:
    """Deterministic synthetic requests.

    Values are arithmetic functions of the row index and the seed. No real
    transaction, label, identifier, card value, email domain, device string or
    private value is involved, and no ground truth exists for these rows.
    """
    if size < 1:
        raise BenchmarkError("Corpus size must be at least 1.")
    corpus: list[dict[str, float]] = []
    for index in range(size):
        row: dict[str, float] = {}
        for position, name in enumerate(FEATURE_ORDER):
            if name == "Time":
                row[name] = float((index * 7 + seed) % 86_400)
            elif name == "Amount":
                row[name] = round(1.0 + ((index * 13 + seed) % 50_000) / 100.0, 2)
            else:
                raw = ((index * 37 + position * 13 + seed) % 2_003) / 1_000.0 - 1.0
                row[name] = round(raw, 6)
        corpus.append(row)
    return corpus


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile over already-collected latencies."""
    if not values:
        raise BenchmarkError("Cannot take a percentile of an empty sample.")
    if not 0.0 < fraction <= 1.0:
        raise BenchmarkError("fraction must be in (0, 1].")
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


@dataclass
class RepeatResult:
    """One measured repeat. Every attempted request is accounted for."""

    concurrency: int
    attempted: int
    completed: int
    timeouts: int
    transport_errors: int
    status_counts: dict[int, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)
    wall_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.reconcile()

    def reconcile(self) -> None:
        """Nothing may be silently dropped."""
        accounted = self.completed + self.timeouts + self.transport_errors
        if accounted != self.attempted:
            raise BenchmarkError(
                f"Request accounting does not reconcile: {accounted} != {self.attempted}."
            )
        if sum(self.status_counts.values()) != self.completed:
            raise BenchmarkError("Status counts do not reconcile with completed requests.")

    @property
    def successes(self) -> int:
        return sum(count for status, count in self.status_counts.items() if 200 <= status < 300)

    @property
    def non_2xx(self) -> int:
        return self.completed - self.successes

    @property
    def successful_rps(self) -> float:
        return self.successes / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        latency: dict[str, float | None] = {
            "p50_ms": round(percentile(self.latencies_ms, 0.50), 3),
            "p95_ms": round(percentile(self.latencies_ms, 0.95), 3),
            "p99_ms": round(percentile(self.latencies_ms, 0.99), 3),
            "max_ms": round(max(self.latencies_ms), 3),
        } if self.latencies_ms else {"p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
        return {
            "concurrency": self.concurrency,
            "attempted": self.attempted,
            "completed": self.completed,
            "successes": self.successes,
            "non_2xx": self.non_2xx,
            "timeouts": self.timeouts,
            "transport_errors": self.transport_errors,
            "status_counts": {str(k): v for k, v in sorted(self.status_counts.items())},
            "wall_seconds": round(self.wall_seconds, 4),
            "successful_rps": round(self.successful_rps, 2),
            **latency,
        }


def run_repeat(
    client: Any,
    url: str,
    corpus: Sequence[Mapping[str, float]],
    *,
    concurrency: int,
    request_count: int,
    timeout_seconds: float,
    request_id_prefix: str,
) -> RepeatResult:
    """Drive ``request_count`` requests at ``concurrency`` over loopback.

    Each request carries a unique request id so idempotent replay never
    masquerades as throughput.
    """
    import httpx

    if concurrency < 1:
        raise BenchmarkError("Concurrency must be at least 1.")
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    timeouts = 0
    transport_errors = 0

    def issue(index: int) -> tuple[str, int | None, float]:
        body = corpus[index % len(corpus)]
        headers = {"X-Request-ID": f"{request_id_prefix}-{index}"}
        started = perf_counter()
        try:
            response = client.post(url, json=body, headers=headers, timeout=timeout_seconds)
            return ("http", response.status_code, (perf_counter() - started) * 1000.0)
        except httpx.TimeoutException:
            return ("timeout", None, (perf_counter() - started) * 1000.0)
        except httpx.HTTPError:
            return ("transport", None, (perf_counter() - started) * 1000.0)

    wall_started = perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes = list(pool.map(issue, range(request_count)))
    wall = perf_counter() - wall_started

    for kind, status, elapsed_ms in outcomes:
        if kind == "http" and status is not None:
            statuses[status] = statuses.get(status, 0) + 1
            latencies.append(elapsed_ms)
        elif kind == "timeout":
            timeouts += 1
        else:
            transport_errors += 1

    return RepeatResult(
        concurrency=concurrency,
        attempted=request_count,
        completed=sum(statuses.values()),
        timeouts=timeouts,
        transport_errors=transport_errors,
        status_counts=statuses,
        latencies_ms=latencies,
        wall_seconds=wall,
    )


def median(values: Sequence[float]) -> float:
    if not values:
        raise BenchmarkError("Cannot take a median of an empty sample.")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def aggregate_repeats(repeats: Sequence[RepeatResult]) -> dict[str, Any]:
    """Median across repeats plus every per-repeat value. No cherry-picking."""
    if len(repeats) < MIN_REPEATS:
        raise BenchmarkError(f"At least {MIN_REPEATS} repeats are required by the protocol.")
    per_repeat = [r.summary() for r in repeats]
    return {
        "concurrency": repeats[0].concurrency,
        "repeats": len(repeats),
        "median_successful_rps": round(median([r.successful_rps for r in repeats]), 2),
        "median_p50_ms": round(median([s["p50_ms"] for s in per_repeat]), 3),
        "median_p95_ms": round(median([s["p95_ms"] for s in per_repeat]), 3),
        "median_p99_ms": round(median([s["p99_ms"] for s in per_repeat]), 3),
        "median_max_ms": round(median([s["max_ms"] for s in per_repeat]), 3),
        "total_attempted": sum(r.attempted for r in repeats),
        "total_successes": sum(r.successes for r in repeats),
        "total_non_2xx": sum(r.non_2xx for r in repeats),
        "total_timeouts": sum(r.timeouts for r in repeats),
        "total_transport_errors": sum(r.transport_errors for r in repeats),
        "per_repeat": per_repeat,
    }


def measure_audit_append_growth(
    audit_log_path: Any,
    *,
    events: int = 400,
    sample_points: Sequence[int] = (1, 25, 50, 100, 200, 400),
) -> dict[str, Any]:
    """Measure how audit-append latency scales with existing log length.

    The audit writer re-verifies the whole hash chain before every append, which
    is a deliberate tamper-evidence property. This measures what that costs as
    the log grows. Synthetic events only; no request data is involved.
    """
    from api.audit import AuditDecision, AuditLog

    log = AuditLog(audit_log_path)
    decision = AuditDecision(
        score=0.1,
        threshold=0.53,
        decision="below_review_threshold",
        model_version="synthetic-benchmark",
        model_fingerprint_sha256="a" * 64,
    )
    samples: list[float] = []
    points: dict[str, float] = {}
    for index in range(1, events + 1):
        started = perf_counter()
        log.append_inference(
            request_id=f"audit-growth-{index}",
            api_schema_version="1.0",
            input_digest_sha256="b" * 64,
            latency_ms=1.0,
            decisions=[decision],
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        samples.append(elapsed_ms)
        if index in sample_points:
            points[str(index)] = round(elapsed_ms, 3)

    window = max(1, min(50, len(samples) // 4))
    first = sum(samples[:window]) / window
    last = sum(samples[-window:]) / window
    return {
        "events_appended": events,
        "append_ms_at_event": points,
        "mean_first_window_ms": round(first, 3),
        "mean_last_window_ms": round(last, 3),
        "growth_factor": round(last / first, 2) if first > 0 else None,
        "total_seconds": round(sum(samples) / 1000.0, 3),
        "window_size": window,
        "interpretation": (
            "Append cost grows with log length because the writer re-verifies the "
            "entire hash chain before each append. This is a tamper-evidence "
            "property, not a defect, but it makes sustained append throughput "
            "degrade as the log grows."
        ),
    }
