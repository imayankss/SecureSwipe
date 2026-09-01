"""Opt-in, duration-only timing diagnostics for the postgres-scale completion path.

The P1-S4 benchmark proved that additional uvicorn workers do not raise
throughput, but aggregate throughput alone cannot separate *waiting* for the
single ``primary`` audit-chain-head row lock from *work performed while holding
it*. This module records that split.

It is inert unless ``SECURESWIPE_SCALE_TIMING_DIAGNOSTIC=1`` is set locally, and
it never observes anything but elapsed durations: no request identifiers,
payloads, features, decisions, scores, model output, headers, DSNs,
credentials, SQL text, or exception text ever reaches it.
"""

from __future__ import annotations

import atexit
import json
import math
import os
import threading
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

TIMING_FLAG = "SECURESWIPE_SCALE_TIMING_DIAGNOSTIC"
TIMING_OUTPUT_DIR = "SECURESWIPE_SCALE_TIMING_OUTPUT_DIR"
TIMING_SCHEMA_VERSION = "postgres-scale-completion-timing-v1"

FLUSH_EVERY_COMPLETIONS = 25

# Checkpoints taken inside one completion transaction, in the order they occur.
CHECKPOINT_NAMES: tuple[str, ...] = (
    "transaction_open",
    "idempotency_locked",
    "head_lock_requested",
    "head_locked",
    "event_built",
    "event_inserted",
    "idempotency_updated",
    "head_updated",
    "committed",
)

# Derived durations, each expressed as (later checkpoint, earlier checkpoint).
METRIC_SPANS: tuple[tuple[str, str, str], ...] = (
    ("idempotency_lock_wait_ms", "idempotency_locked", "transaction_open"),
    ("head_lock_wait_ms", "head_locked", "head_lock_requested"),
    ("head_lock_hold_ms", "committed", "head_locked"),
    ("event_build_ms", "event_built", "head_locked"),
    ("event_insert_ms", "event_inserted", "event_built"),
    ("idempotency_update_ms", "idempotency_updated", "event_inserted"),
    ("head_update_ms", "head_updated", "idempotency_updated"),
    ("commit_ms", "committed", "head_updated"),
    ("total_completion_ms", "committed", "transaction_open"),
)
METRIC_NAMES: tuple[str, ...] = tuple(span[0] for span in METRIC_SPANS)


def timing_enabled(environment: Mapping[str, str] | None = None) -> bool:
    """Return True only for the explicit local opt-in value."""
    source: Mapping[str, str] = os.environ if environment is None else environment
    return source.get(TIMING_FLAG, "").strip() == "1"


def nearest_rank(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * fraction)) - 1]


class TimingAggregator:
    """Accumulate completion durations and publish anonymous aggregates only."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._samples: dict[str, list[float]] = {name: [] for name in METRIC_NAMES}
        self._completions = 0
        if output_dir is not None:
            atexit.register(self.flush)

    @property
    def completions(self) -> int:
        with self._lock:
            return self._completions

    def record(self, durations: dict[str, float]) -> None:
        """Record one completion. Only known metric names carrying floats persist."""
        with self._lock:
            for name in METRIC_NAMES:
                value = durations.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self._samples[name].append(float(value))
            self._completions += 1
            due = self._completions % FLUSH_EVERY_COMPLETIONS == 0
        if due:
            self.flush()

    def snapshot(self) -> dict[str, Any]:
        """Return counts and percentiles only; individual samples never leave."""
        with self._lock:
            metrics: dict[str, Any] = {}
            for name in METRIC_NAMES:
                values = self._samples[name]
                metrics[name] = (
                    {
                        "count": len(values),
                        "median_ms": round(nearest_rank(values, 0.50), 4),
                        "p95_ms": round(nearest_rank(values, 0.95), 4),
                        "p99_ms": round(nearest_rank(values, 0.99), 4),
                    }
                    if values
                    else {"count": 0, "median_ms": None, "p95_ms": None, "p99_ms": None}
                )
            completions = self._completions
        return {
            "diagnostic_kind": "postgres_scale_completion_timing",
            "schema_version": TIMING_SCHEMA_VERSION,
            "unit": "milliseconds",
            "process_id": os.getpid(),
            "completions": completions,
            "metrics": metrics,
        }

    def flush(self) -> Path | None:
        """Atomically replace this process's aggregate file, if a directory is set."""
        if self.output_dir is None:
            return None
        document = self.snapshot()
        if document["completions"] == 0:
            return None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"scale-timing-{os.getpid()}.json"
        temporary = path.with_name(f"{path.name}.tmp")
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
        return path


class CompletionTimer:
    """Checkpoint recorder for one completion transaction."""

    __slots__ = ("_aggregator", "_checkpoints", "_completion_observer")

    def __init__(
        self,
        aggregator: TimingAggregator | None,
        *,
        completion_observer: Callable[[float], None] | None = None,
    ) -> None:
        self._aggregator = aggregator
        self._completion_observer = completion_observer
        self._checkpoints: dict[str, float] = {}

    def at(self, checkpoint: str) -> None:
        if checkpoint not in CHECKPOINT_NAMES:
            raise ValueError(f"Unknown completion checkpoint: {checkpoint}")
        self._checkpoints[checkpoint] = perf_counter()

    def durations(self) -> dict[str, float]:
        marks = self._checkpoints
        return {
            name: (marks[later] - marks[earlier]) * 1000.0
            for name, later, earlier in METRIC_SPANS
            if later in marks and earlier in marks
        }

    def submit(self) -> None:
        """Publish this completion only when every checkpoint was reached."""
        durations = self.durations()
        if len(durations) != len(METRIC_SPANS):
            return
        if self._aggregator is not None:
            self._aggregator.record(durations)
        if self._completion_observer is not None:
            self._completion_observer(durations["total_completion_ms"])


class _NullTimer:
    """Zero-effect stand-in used whenever the diagnostic is disabled."""

    __slots__ = ()

    def at(self, checkpoint: str) -> None:
        return None

    def durations(self) -> dict[str, float]:
        return {}

    def submit(self) -> None:
        return None


NULL_TIMER = _NullTimer()


def aggregator_from_environment(
    environment: Mapping[str, str] | None = None,
) -> TimingAggregator | None:
    """Build an aggregator only when the explicit local opt-in flag is set."""
    source: Mapping[str, str] = os.environ if environment is None else environment
    if not timing_enabled(source):
        return None
    directory = source.get(TIMING_OUTPUT_DIR, "").strip()
    return TimingAggregator(Path(directory) if directory else None)


def merge_snapshots(snapshots: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Combine per-process aggregates into one anonymous per-cell summary."""
    per_process = [
        {
            "completions": int(snapshot["completions"]),
            "metrics": snapshot["metrics"],
        }
        for snapshot in snapshots
    ]
    return {
        "diagnostic_kind": "postgres_scale_completion_timing_merged",
        "schema_version": TIMING_SCHEMA_VERSION,
        "unit": "milliseconds",
        "processes": len(per_process),
        "completions": sum(item["completions"] for item in per_process),
        "per_process": per_process,
    }


__all__ = [
    "CHECKPOINT_NAMES",
    "CompletionTimer",
    "METRIC_NAMES",
    "METRIC_SPANS",
    "NULL_TIMER",
    "TIMING_FLAG",
    "TIMING_OUTPUT_DIR",
    "TIMING_SCHEMA_VERSION",
    "TimingAggregator",
    "aggregator_from_environment",
    "merge_snapshots",
    "nearest_rank",
    "timing_enabled",
]
