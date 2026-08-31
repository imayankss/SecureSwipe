"""Privacy-safe opt-in client timing for the P1 scale benchmark."""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal

import httpcore
import httpx

CLIENT_TIMING_FLAG = "SECURESWIPE_SCALE_CLIENT_TIMING"
CLIENT_TIMING_SCHEMA_VERSION = "p1-s4d-client-timing-v1"

PhaseStatus = Literal["observed", "not_observable", "unsupported"]
ConnectionKind = Literal["new", "reused", "unknown"]

DURATION_METRICS: tuple[str, ...] = (
    "executor_queue_wait_ms",
    "client_setup_ms",
    "tcp_connect_ms",
    "request_headers_send_ms",
    "request_body_send_ms",
    "request_transmission_ms",
    "response_headers_wait_ms",
    "request_to_response_headers_ms",
    "response_body_read_ms",
    "client_teardown_ms",
    "client_e2e_ms",
    "scheduled_total_ms",
)

RATIO_METRICS: tuple[str, ...] = (
    "executor_queue_share_of_scheduled_percent",
    "client_setup_share_of_e2e_percent",
    "tcp_connect_share_of_e2e_percent",
    "request_transmission_share_of_e2e_percent",
    "response_headers_wait_share_of_e2e_percent",
    "request_to_response_headers_share_of_e2e_percent",
    "response_body_read_share_of_e2e_percent",
    "client_teardown_share_of_e2e_percent",
)

PHASE_AVAILABILITY: dict[str, dict[str, str]] = {
    "executor_task_queue": {"status": "observed"},
    "connection_pool_acquisition": {
        "status": "not_observable",
        "reason": "no_supported_httpx_httpcore_trace_event",
    },
    "tcp_connection": {"status": "observed"},
    "request_transmission": {"status": "observed"},
    "response_headers": {
        "status": "observed",
        "scope": "combined_transport_ingress_server_wait",
    },
    "response_body_read": {"status": "observed"},
    "client_e2e": {"status": "observed"},
}

TRACE_SPANS: dict[str, str] = {
    "connection.connect_tcp": "tcp_connect_ms",
    "http11.send_request_headers": "request_headers_send_ms",
    "http11.send_request_body": "request_body_send_ms",
    "http11.receive_response_headers": "response_headers_wait_ms",
}


def client_timing_enabled(environment: Mapping[str, str] | None = None) -> bool:
    """Enable only for the exact explicit value ``1``."""
    source: Mapping[str, str] = os.environ if environment is None else environment
    return source.get(CLIENT_TIMING_FLAG, "") == "1"


def _safe_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def _nearest_rank(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * fraction)) - 1]


def _aggregate(
    values: Sequence[float], *, unit_suffix: str
) -> dict[str, int | float | None]:
    if not values:
        return {
            "count": 0,
            f"min_{unit_suffix}": None,
            f"median_{unit_suffix}": None,
            f"p95_{unit_suffix}": None,
            f"p99_{unit_suffix}": None,
            f"max_{unit_suffix}": None,
        }
    return {
        "count": len(values),
        f"min_{unit_suffix}": round(min(values), 4),
        f"median_{unit_suffix}": round(_nearest_rank(values, 0.50), 4),
        f"p95_{unit_suffix}": round(_nearest_rank(values, 0.95), 4),
        f"p99_{unit_suffix}": round(_nearest_rank(values, 0.99), 4),
        f"max_{unit_suffix}": round(max(values), 4),
    }


@dataclass
class ClientRequestTimer:
    """Transient monotonic boundaries for one request; never serialized."""

    submitted_at: float
    clock: Callable[[], float] = field(default=perf_counter, repr=False)
    _marks: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def submitted_now(cls) -> "ClientRequestTimer":
        return cls(perf_counter())

    def mark(self, boundary: str) -> None:
        if boundary not in {
            "task_started",
            "request_started",
            "headers_received",
            "body_completed",
            "client_completed",
        }:
            return
        self._marks.setdefault(boundary, self.clock())

    def durations(self) -> dict[str, float]:
        marks = self._marks
        spans = {
            "executor_queue_wait_ms": (marks.get("task_started"), self.submitted_at),
            "client_setup_ms": (marks.get("request_started"), marks.get("task_started")),
            "request_to_response_headers_ms": (
                marks.get("headers_received"),
                marks.get("request_started"),
            ),
            "response_body_read_ms": (
                marks.get("body_completed"),
                marks.get("headers_received"),
            ),
            "client_teardown_ms": (
                marks.get("client_completed"),
                marks.get("body_completed"),
            ),
            "client_e2e_ms": (marks.get("client_completed"), marks.get("task_started")),
            "scheduled_total_ms": (marks.get("client_completed"), self.submitted_at),
        }
        durations: dict[str, float] = {}
        for name, (later, earlier) in spans.items():
            if later is None or earlier is None or later < earlier:
                continue
            durations[name] = (later - earlier) * 1000.0
        return durations


class HttpTraceRecorder:
    """Observe allowlisted public trace-event names and ignore event payloads."""

    def __init__(self, *, clock: Callable[[], float] = perf_counter) -> None:
        self._clock = clock
        self._started: dict[str, float] = {}
        self._durations: dict[str, float] = {}
        self._failed: set[str] = set()
        self._saw_http11 = False

    def __call__(self, event_name: str, event_info: Mapping[str, object]) -> None:
        del event_info
        try:
            base, separator, state = event_name.rpartition(".")
            if not separator or base not in TRACE_SPANS:
                return
            if base.startswith("http11."):
                self._saw_http11 = True
            if state == "started":
                self._started.setdefault(base, self._clock())
            elif state == "complete":
                started = self._started.get(base)
                completed = self._clock()
                if started is not None and completed >= started:
                    self._durations[TRACE_SPANS[base]] = (completed - started) * 1000.0
            elif state == "failed":
                self._failed.add(base)
        except BaseException:
            # Diagnostics must never alter transport behavior.
            return

    def durations(self) -> dict[str, float]:
        values = {
            name: value
            for name, value in self._durations.items()
            if name in DURATION_METRICS and _safe_number(value) is not None
        }
        header = values.get("request_headers_send_ms")
        body = values.get("request_body_send_ms")
        if header is not None and body is not None:
            values["request_transmission_ms"] = header + body
        return values

    def connection_kind(self, *, request_completed: bool) -> ConnectionKind:
        if "connection.connect_tcp" in self._failed:
            return "unknown"
        if "tcp_connect_ms" in self._durations:
            return "new"
        if request_completed and self._saw_http11:
            return "reused"
        return "unknown"


class ClientTimingAggregator:
    """Reduce transient client observations to anonymous aggregates only."""

    def __init__(self, *, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self._durations: dict[str, list[float]] = {name: [] for name in DURATION_METRICS}
        self._ratios: dict[str, list[float]] = {name: [] for name in RATIO_METRICS}
        self._connections = {"new": 0, "reused": 0, "unknown": 0}
        self._recording_failures = 0
        self._lock = threading.Lock()

    def record(
        self,
        request_durations: Mapping[str, object],
        trace_durations: Mapping[str, object],
        *,
        connection_kind: ConnectionKind,
    ) -> None:
        try:
            combined: dict[str, float] = {}
            for source in (request_durations, trace_durations):
                for name in DURATION_METRICS:
                    value = _safe_number(source.get(name))
                    if value is not None:
                        combined[name] = value
            with self._lock:
                for name, value in combined.items():
                    self._durations[name].append(value)
                if connection_kind in self._connections:
                    self._connections[connection_kind] += 1
                else:
                    self._connections["unknown"] += 1
                self._record_ratios(combined)
        except BaseException:
            try:
                with self._lock:
                    self._recording_failures += 1
            except BaseException:
                return

    def _record_ratios(self, values: Mapping[str, float]) -> None:
        scheduled = values.get("scheduled_total_ms")
        e2e = values.get("client_e2e_ms")
        if scheduled is not None and scheduled > 0:
            queue = values.get("executor_queue_wait_ms")
            if queue is not None:
                self._ratios["executor_queue_share_of_scheduled_percent"].append(
                    queue / scheduled * 100.0
                )
        if e2e is None or e2e <= 0:
            return
        ratio_sources = {
            "client_setup_share_of_e2e_percent": "client_setup_ms",
            "tcp_connect_share_of_e2e_percent": "tcp_connect_ms",
            "request_transmission_share_of_e2e_percent": "request_transmission_ms",
            "response_headers_wait_share_of_e2e_percent": "response_headers_wait_ms",
            "request_to_response_headers_share_of_e2e_percent": (
                "request_to_response_headers_ms"
            ),
            "response_body_read_share_of_e2e_percent": "response_body_read_ms",
            "client_teardown_share_of_e2e_percent": "client_teardown_ms",
        }
        for ratio_name, duration_name in ratio_sources.items():
            duration = values.get(duration_name)
            if duration is not None:
                self._ratios[ratio_name].append(duration / e2e * 100.0)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = {
                name: _aggregate(tuple(self._durations[name]), unit_suffix="ms")
                for name in DURATION_METRICS
            }
            ratios = {
                name: _aggregate(tuple(self._ratios[name]), unit_suffix="percent")
                for name in RATIO_METRICS
            }
            connections = dict(self._connections)
            recording_failures = self._recording_failures
        return {
            "schema_version": CLIENT_TIMING_SCHEMA_VERSION,
            "purpose": "diagnose_client_transport_and_combined_response_header_wait",
            "non_claim": "diagnostic_only_no_scalability_or_capacity_claim",
            "phase_availability": PHASE_AVAILABILITY,
            "client_configuration": {
                "library": "httpx",
                "httpx_version": httpx.__version__,
                "httpcore_version": httpcore.__version__,
                "interface": "synchronous",
                "protocol": "http1",
                "http2": False,
                "follow_redirects": False,
                "trust_env": True,
                "timeout_seconds": self.timeout_seconds,
                "client_scope": "one_new_client_per_request",
                "max_connections_per_client": 100,
                "max_keepalive_connections_per_client": 20,
                "keepalive_expiry_seconds": 5.0,
                "trace_interface": "request_extensions_trace",
            },
            "duration_aggregates": durations,
            "same_request_ratio_aggregates": ratios,
            "connection_counts": connections,
            "diagnostic_recording_failures": recording_failures,
        }


__all__ = [
    "CLIENT_TIMING_FLAG",
    "CLIENT_TIMING_SCHEMA_VERSION",
    "ClientRequestTimer",
    "ClientTimingAggregator",
    "DURATION_METRICS",
    "HttpTraceRecorder",
    "PHASE_AVAILABILITY",
    "RATIO_METRICS",
    "client_timing_enabled",
]
