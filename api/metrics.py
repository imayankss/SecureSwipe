"""Small Prometheus text-format metrics with bounded label sets."""

from __future__ import annotations

import threading
from collections import Counter, defaultdict

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
SCORE_BUCKETS = (0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


class ApiMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._latency: Counter[tuple[str, float]] = Counter()
        self._latency_sum: dict[str, float] = defaultdict(float)
        self._latency_count: Counter[str] = Counter()
        self._scores: Counter[float] = Counter()
        self._score_count = 0

    def observe_request(self, method: str, route: str, status: int, latency: float) -> None:
        normalized_route = (
            route
            if route
            in {
                "/health/live",
                "/health/ready",
                "/v1/model-info",
                "/v1/predict",
                "/v1/predict/batch",
                "/metrics",
            }
            else "unmatched"
        )
        with self._lock:
            self._requests[(method, normalized_route, status)] += 1
            self._latency_sum[normalized_route] += latency
            self._latency_count[normalized_route] += 1
            for bucket in LATENCY_BUCKETS:
                if latency <= bucket:
                    self._latency[(normalized_route, bucket)] += 1

    def observe_scores(self, scores: list[float]) -> None:
        with self._lock:
            for score in scores:
                self._score_count += 1
                for bucket in SCORE_BUCKETS:
                    if score <= bucket:
                        self._scores[bucket] += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP secureswipe_http_requests_total HTTP requests by bounded route and status.",
                "# TYPE secureswipe_http_requests_total counter",
            ]
            for (method, route, status), value in sorted(self._requests.items()):
                lines.append(
                    f'secureswipe_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {value}'
                )
            lines.extend(
                [
                    "# HELP secureswipe_http_request_duration_seconds Request latency.",
                    "# TYPE secureswipe_http_request_duration_seconds histogram",
                ]
            )
            for route in sorted(self._latency_count):
                for bucket in LATENCY_BUCKETS:
                    count = self._latency[(route, bucket)]
                    lines.append(
                        f'secureswipe_http_request_duration_seconds_bucket{{route="{route}",le="{bucket}"}} {count}'
                    )
                count = self._latency_count[route]
                lines.append(
                    f'secureswipe_http_request_duration_seconds_bucket{{route="{route}",le="+Inf"}} {count}'
                )
                lines.append(
                    f'secureswipe_http_request_duration_seconds_sum{{route="{route}"}} {self._latency_sum[route]:.9f}'
                )
                lines.append(
                    f'secureswipe_http_request_duration_seconds_count{{route="{route}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP secureswipe_prediction_decision_score Prediction decision-score distribution.",
                    "# TYPE secureswipe_prediction_decision_score histogram",
                ]
            )
            for bucket in SCORE_BUCKETS:
                lines.append(
                    f'secureswipe_prediction_decision_score_bucket{{le="{bucket}"}} {self._scores[bucket]}'
                )
            lines.append(
                f'secureswipe_prediction_decision_score_bucket{{le="+Inf"}} {self._score_count}'
            )
            lines.append(f"secureswipe_prediction_decision_score_count {self._score_count}")
            return "\n".join(lines) + "\n"
