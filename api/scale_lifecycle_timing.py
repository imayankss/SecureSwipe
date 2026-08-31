"""Opt-in, aggregate-only timing for the postgres-scale V2 request lifecycle.

The recorder is deliberately unable to accept request-derived values.  It
observes only allowlisted elapsed durations and one of three low-cardinality
reservation outcomes, then writes aggregate statistics atomically.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import math
import os
import tempfile
import threading
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence

LIFECYCLE_TIMING_FLAG = "SECURESWIPE_SCALE_LIFECYCLE_TIMING"
LIFECYCLE_TIMING_OUTPUT_DIR = "SECURESWIPE_SCALE_LIFECYCLE_TIMING_OUTPUT_DIR"
LIFECYCLE_TIMING_SCHEMA_VERSION = "postgres-scale-lifecycle-timing-v1"
DEFAULT_LIFECYCLE_TIMING_OUTPUT_DIR = Path("reports/benchmarks/p1-scale-results/lifecycle-timing")
EVENT_LOOP_LAG_INTERVAL_SECONDS = 0.100
FLUSH_EVERY_REQUESTS = 25

LIFECYCLE_METRIC_NAMES: tuple[str, ...] = (
    "pre_reservation_ms",
    "reservation_pool_checkout_ms",
    "reservation_transaction_ms",
    "reservation_outcome_handling_ms",
    "model_scoring_ms",
    "bounded_response_build_ms",
    "bounded_response_serialize_ms",
    "completion_pool_checkout_ms",
    "completion_transaction_ms",
    "total_handler_ms",
)

RESERVATION_OUTCOMES: tuple[str, ...] = (
    "owner",
    "completed_replay",
    "pending_fail_closed",
)


def lifecycle_timing_enabled(environment: Mapping[str, str] | None = None) -> bool:
    """Return true only for the exact explicit opt-in value."""
    source: Mapping[str, str] = os.environ if environment is None else environment
    return source.get(LIFECYCLE_TIMING_FLAG, "") == "1"


def _safe_duration(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    duration = float(value)
    return duration if math.isfinite(duration) and duration >= 0.0 else None


def _nearest_rank(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * fraction)) - 1]


def _aggregate(values: Sequence[float]) -> dict[str, int | float | None]:
    if not values:
        return {
            "count": 0,
            "min_ms": None,
            "median_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }
    return {
        "count": len(values),
        "min_ms": round(min(values), 4),
        "median_ms": round(_nearest_rank(values, 0.50), 4),
        "p95_ms": round(_nearest_rank(values, 0.95), 4),
        "p99_ms": round(_nearest_rank(values, 0.99), 4),
        "max_ms": round(max(values), 4),
    }


class LifecycleTimingAggregator:
    """Publish anonymous per-process lifecycle and event-loop aggregates."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._samples: dict[str, list[float]] = {name: [] for name in LIFECYCLE_METRIC_NAMES}
        self._event_loop_lag: list[float] = []
        self._outcomes = {name: 0 for name in RESERVATION_OUTCOMES}
        self._requests = 0
        atexit.register(self.flush)

    @property
    def requests(self) -> int:
        with self._lock:
            return self._requests

    def record_request(self, metrics: Mapping[str, object], outcome: str) -> None:
        """Accept allowlisted completed spans and one allowlisted outcome only."""
        if outcome not in RESERVATION_OUTCOMES:
            return
        with self._lock:
            for name in LIFECYCLE_METRIC_NAMES:
                value = _safe_duration(metrics.get(name))
                if value is not None:
                    self._samples[name].append(value)
            self._outcomes[outcome] += 1
            self._requests += 1
            due = self._requests % FLUSH_EVERY_REQUESTS == 0
        if due:
            self.flush()

    def record_event_loop_lag(self, duration_ms: object) -> None:
        value = _safe_duration(duration_ms)
        if value is None:
            return
        with self._lock:
            self._event_loop_lag.append(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            metrics = {
                name: _aggregate(tuple(self._samples[name])) for name in LIFECYCLE_METRIC_NAMES
            }
            lag = _aggregate(tuple(self._event_loop_lag))
            outcomes = dict(self._outcomes)
            requests = self._requests
        return {
            "diagnostic_kind": "postgres_scale_request_lifecycle_timing",
            "schema_version": LIFECYCLE_TIMING_SCHEMA_VERSION,
            "unit": "milliseconds",
            "process_id": os.getpid(),
            "requests": requests,
            "reservation_outcome_counts": outcomes,
            "metrics": metrics,
            "event_loop_lag": {
                "scope": "process",
                "sampling_method": "fixed_interval_monotonic_drift",
                "interval_ms": int(EVENT_LOOP_LAG_INTERVAL_SECONDS * 1000),
                **lag,
            },
        }

    def flush(self) -> Path | None:
        """Atomically replace this process's aggregate JSON artifact."""
        document = self.snapshot()
        if document["requests"] == 0 and document["event_loop_lag"]["count"] == 0:
            return None
        with self._flush_lock:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"scale-lifecycle-timing-{os.getpid()}.json"
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


class RequestLifecycleTimer:
    """Keep one request's durations in memory until a truthful outcome is known."""

    __slots__ = ("_aggregator", "_discarded", "_metrics", "_outcome", "_started")

    def __init__(self, aggregator: LifecycleTimingAggregator) -> None:
        self._aggregator = aggregator
        self._started = perf_counter()
        self._metrics: dict[str, float] = {}
        self._outcome: str | None = None
        self._discarded = False

    def started_at(self) -> float:
        return perf_counter()

    def observe_elapsed(self, metric: str, started: float) -> None:
        if metric not in LIFECYCLE_METRIC_NAMES or self._discarded:
            return
        value = _safe_duration((perf_counter() - started) * 1000.0)
        if value is not None:
            self._metrics[metric] = value

    def observe_duration(self, metric: str, duration_ms: object) -> None:
        if metric not in LIFECYCLE_METRIC_NAMES or self._discarded:
            return
        value = _safe_duration(duration_ms)
        if value is not None:
            self._metrics[metric] = value

    def mark_pre_reservation_complete(self) -> None:
        self.observe_elapsed("pre_reservation_ms", self._started)

    def classify(self, outcome: str) -> None:
        if outcome in RESERVATION_OUTCOMES and not self._discarded:
            self._outcome = outcome

    def discard(self) -> None:
        self._discarded = True

    def submit(self) -> None:
        if self._discarded or self._outcome is None:
            return
        self.observe_elapsed("total_handler_ms", self._started)
        self._aggregator.record_request(self._metrics, self._outcome)


class LifecycleTimer(Protocol):
    """Structural interface shared by the active and zero-effect timers."""

    def started_at(self) -> float: ...

    def observe_elapsed(self, metric: str, started: float) -> None: ...

    def observe_duration(self, metric: str, duration_ms: object) -> None: ...

    def mark_pre_reservation_complete(self) -> None: ...

    def classify(self, outcome: str) -> None: ...

    def discard(self) -> None: ...

    def submit(self) -> None: ...


class _NullRequestLifecycleTimer:
    __slots__ = ()

    def started_at(self) -> float:
        return 0.0

    def observe_elapsed(self, metric: str, started: float) -> None:
        return None

    def observe_duration(self, metric: str, duration_ms: object) -> None:
        return None

    def mark_pre_reservation_complete(self) -> None:
        return None

    def classify(self, outcome: str) -> None:
        return None

    def discard(self) -> None:
        return None

    def submit(self) -> None:
        return None


NULL_LIFECYCLE_TIMER = _NullRequestLifecycleTimer()


class EventLoopLagMonitor:
    """Sample process-level monotonic scheduling drift at a fixed low rate."""

    def __init__(
        self,
        aggregator: LifecycleTimingAggregator,
        *,
        interval_seconds: float = EVENT_LOOP_LAG_INTERVAL_SECONDS,
    ) -> None:
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("Event-loop lag interval must be positive and finite.")
        self._aggregator = aggregator
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._aggregator.flush()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            expected = loop.time() + self._interval
            await asyncio.sleep(self._interval)
            self._aggregator.record_event_loop_lag(max(0.0, (loop.time() - expected) * 1000.0))


def lifecycle_aggregator_from_environment(
    environment: Mapping[str, str] | None = None,
) -> LifecycleTimingAggregator | None:
    source: Mapping[str, str] = os.environ if environment is None else environment
    if not lifecycle_timing_enabled(source):
        return None
    configured = source.get(LIFECYCLE_TIMING_OUTPUT_DIR, "").strip()
    output_dir = Path(configured) if configured else DEFAULT_LIFECYCLE_TIMING_OUTPUT_DIR
    return LifecycleTimingAggregator(output_dir)


__all__ = [
    "DEFAULT_LIFECYCLE_TIMING_OUTPUT_DIR",
    "EVENT_LOOP_LAG_INTERVAL_SECONDS",
    "EventLoopLagMonitor",
    "LIFECYCLE_METRIC_NAMES",
    "LIFECYCLE_TIMING_FLAG",
    "LIFECYCLE_TIMING_OUTPUT_DIR",
    "LIFECYCLE_TIMING_SCHEMA_VERSION",
    "LifecycleTimer",
    "LifecycleTimingAggregator",
    "NULL_LIFECYCLE_TIMER",
    "RESERVATION_OUTCOMES",
    "RequestLifecycleTimer",
    "lifecycle_aggregator_from_environment",
    "lifecycle_timing_enabled",
]
