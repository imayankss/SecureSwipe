"""Deterministic, privacy-bounded primitives for the P1 scale benchmark.

This module constructs synthetic-only request schedules and validates aggregate
results. It deliberately has no database, process, or network side effects.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

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

# Structured API error codes the V2 surface can return, mapped to the fail-closed
# category each one proves. Diagnostics keep the code and the category only; the
# human-readable message is never retained because it is unbounded server text.
API_ERROR_CODE_CATEGORIES: dict[str, str] = {
    "validation_error": "request_validation",
    "request_too_large": "request_limits",
    "model_unavailable": "model_readiness",
    "not_ready": "model_readiness",
    "prediction_integrity_error": "prediction_integrity",
    "prediction_timeout": "prediction_timeout",
    "capacity_exceeded": "api_admission_capacity",
    "idempotency_conflict": "idempotency_conflict",
    "idempotency_in_progress": "idempotency_reservation",
    "idempotency_stale": "idempotency_reservation",
    "idempotency_failed": "idempotency_reservation",
    "state_integrity_failure": "state_integrity",
    "state_store_unavailable": "database_state_store",
    "state_store_failure": "database_state_store",
    "audit_unavailable": "audit_chain",
    "scale_profile_unavailable": "response_profile",
    "scale_profile_requires_v2": "response_profile",
    "http_error": "http_protocol",
    "internal_error": "unhandled_server_error",
}
ABSENT_API_ERROR_CODE = "absent_api_error_code"
UNRECOGNIZED_API_ERROR_CODE = "unrecognized_api_error_code"
UNPARSEABLE_API_ERROR_BODY = "unparseable_api_error_body"

# A structured code is server-controlled text, so only a bounded slug shape is
# ever retained; anything else is recorded as unrecognized without its value.
_API_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Header evidence is reduced to presence flags. Values are never retained because
# X-Request-ID echoes the plaintext request identifier.
_CLASSIFIED_HEADERS: tuple[tuple[str, str], ...] = (
    ("retry-after", "retry_after_present"),
    ("x-audit-event-hash", "audit_receipt_header_present"),
    ("x-idempotent-replay", "replay_header_present"),
    ("x-request-id", "correlation_header_present"),
)
_CLASSIFIED_CONTENT_TYPES = (
    "application/json",
    "application/problem+json",
    "text/plain",
    "text/html",
)

RequestKind = Literal["valid", "replay", "malformed"]
Phase = Literal["warmup", "measured", "smoke-warmup", "smoke-measured"]


class ScaleBenchmarkError(RuntimeError):
    """Raised when a frozen workload or result invariant is violated."""


class BenchmarkValidationError(ScaleBenchmarkError):
    """A fail-closed validation error with privacy-safe diagnostic context."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


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
    request_group_sha256: str | None = None
    server_replay: bool | None = None
    response_sha256: str | None = None
    audit_receipt_sha256: str | None = None
    response_schema_version: str | None = None
    response_profile: str | None = None
    model_artifact_sha256: str | None = None
    failure_reason: str | None = None
    api_error_code: str | None = None
    api_error_category: str | None = None
    header_classification: dict[str, Any] | None = None


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


def request_group_sha256(request_id: str) -> str:
    """Return an in-memory grouping token without retaining the plaintext ID."""
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def normalize_api_error_code(code: Any) -> str:
    """Reduce an untrusted structured error code to a bounded, safe slug."""
    if code is None:
        return ABSENT_API_ERROR_CODE
    if not isinstance(code, str) or not _API_ERROR_CODE_PATTERN.match(code):
        return UNRECOGNIZED_API_ERROR_CODE
    if code not in API_ERROR_CODE_CATEGORIES:
        return UNRECOGNIZED_API_ERROR_CODE
    return code


def classify_api_error_code(code: Any) -> str:
    """Map a structured error code to the fail-closed condition it proves."""
    normalized = normalize_api_error_code(code)
    if normalized == ABSENT_API_ERROR_CODE:
        return ABSENT_API_ERROR_CODE
    if normalized == UNRECOGNIZED_API_ERROR_CODE:
        return UNRECOGNIZED_API_ERROR_CODE
    return API_ERROR_CODE_CATEGORIES[normalized]


def safe_header_classification(headers: Mapping[str, str]) -> dict[str, Any]:
    """Classify response headers by presence only; never retain their values."""
    lowered = {str(name).lower() for name in headers}
    raw_content_type = str(headers.get("content-type", headers.get("Content-Type", "")))
    media_type = raw_content_type.split(";", 1)[0].strip().lower()
    if not media_type:
        content_type = "absent"
    elif media_type in _CLASSIFIED_CONTENT_TYPES:
        content_type = media_type
    else:
        content_type = "other"
    classification: dict[str, Any] = {
        "content_type": content_type,
        "header_count": len(lowered),
    }
    for header_name, flag in _CLASSIFIED_HEADERS:
        classification[flag] = header_name in lowered
    return classification


def safe_api_error_evidence(
    headers: Mapping[str, str], body: Any, *, parsed: bool
) -> dict[str, Any]:
    """Extract the structured code, category, and header shape of a failure."""
    if not parsed:
        code: Any = None
        normalized = UNPARSEABLE_API_ERROR_BODY
        category = UNPARSEABLE_API_ERROR_BODY
    else:
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        normalized = normalize_api_error_code(code)
        category = classify_api_error_code(code)
    return {
        "api_error_code": normalized,
        "api_error_category": category,
        "header_classification": safe_header_classification(headers),
    }


def safe_outcome_diagnostics(
    workload: Workload, outcomes: Sequence[RequestOutcome], *, failure: str
) -> dict[str, Any]:
    """Summarize response evidence without IDs, inputs, features, or scores."""
    grouped: dict[str, list[RequestOutcome]] = {}
    for outcome in outcomes:
        token = outcome.request_group_sha256
        if token is not None:
            grouped.setdefault(token, []).append(outcome)
    labels = {token: f"group_{index + 1:04d}" for index, token in enumerate(sorted(grouped))}
    group_summaries: list[dict[str, Any]] = []
    for token, items in grouped.items():
        successful = [item for item in items if item.status_code == 200]
        repeated = len(successful) > 1
        problematic = any(not item.contract_valid for item in items)
        if not repeated and not problematic:
            continue
        receipts = {
            item.audit_receipt_sha256
            for item in successful
            if item.audit_receipt_sha256 is not None
        }
        bodies = {
            item.response_sha256 for item in successful if item.response_sha256 is not None
        }
        group_summaries.append(
            {
                "anonymous_group": labels[token],
                "request_group_classification": (
                    "same_id_replay_group" if repeated else "single_request_group"
                ),
                "responses": len(items),
                "status_counts": {
                    str(status): sum(item.status_code == status for item in items)
                    for status in sorted(
                        {item.status_code for item in items if item.status_code is not None}
                    )
                },
                "server_original_count": sum(
                    item.server_replay is False for item in successful
                ),
                "server_replay_count": sum(item.server_replay is True for item in successful),
                "distinct_response_hashes": len(bodies),
                "distinct_audit_receipts": len(receipts),
                "failure_reasons": sorted(
                    {
                        item.failure_reason
                        for item in items
                        if item.failure_reason is not None
                    }
                ),
            }
        )
    response_failures = [
        {
            "anonymous_group": labels.get(outcome.request_group_sha256 or "", "unclassified"),
            "request_group_classification": (
                "malformed_unique_group"
                if outcome.request_kind == "malformed"
                else "valid_or_replay_group"
            ),
            "phase": workload.phase,
            "workers": workload.workers,
            "concurrency": workload.concurrency,
            "repeat": workload.repeat,
            "status_code": outcome.status_code,
            "api_error_code": outcome.api_error_code,
            "api_error_category": outcome.api_error_category,
            "header_classification": outcome.header_classification,
            "latency_ms": round(outcome.latency_ms, 3),
            "server_replay_header": outcome.server_replay,
            "response_schema_version": outcome.response_schema_version,
            "response_profile": outcome.response_profile,
            "failure_reason": outcome.failure_reason,
        }
        for outcome in outcomes
        if not outcome.contract_valid
    ]
    unexpected = [
        outcome
        for outcome in outcomes
        if outcome.status_code is not None
        and outcome.status_code != (422 if outcome.request_kind == "malformed" else 200)
    ]
    unexpected_statuses = sorted(
        {outcome.status_code for outcome in unexpected if outcome.status_code is not None}
    )
    fingerprints = sorted(
        {
            outcome.model_artifact_sha256
            for outcome in outcomes
            if outcome.model_artifact_sha256 is not None
        }
    )
    return {
        "phase": workload.phase,
        "workers": workload.workers,
        "concurrency": workload.concurrency,
        "repeat": workload.repeat,
        "failure": failure,
        "attempted": len(outcomes),
        "status_counts": {
            str(status): sum(outcome.status_code == status for outcome in outcomes)
            for status in sorted(
                {outcome.status_code for outcome in outcomes if outcome.status_code is not None}
            )
        },
        "unexpected_status_counts": {
            str(status): sum(outcome.status_code == status for outcome in unexpected)
            for status in unexpected_statuses
        },
        "api_error_code_counts": dict(
            sorted(
                Counter(
                    outcome.api_error_code
                    for outcome in unexpected
                    if outcome.api_error_code is not None
                ).items()
            )
        ),
        "api_error_category_counts": dict(
            sorted(
                Counter(
                    outcome.api_error_category
                    for outcome in unexpected
                    if outcome.api_error_category is not None
                ).items()
            )
        ),
        "unexpected_latency_ms": (
            {
                "min": round(min(outcome.latency_ms for outcome in unexpected), 3),
                "p50": round(nearest_rank([o.latency_ms for o in unexpected], 0.50), 3),
                "max": round(max(outcome.latency_ms for outcome in unexpected), 3),
            }
            if unexpected
            else None
        ),
        "timeouts": sum(outcome.timeout for outcome in outcomes),
        "transport_errors": sum(outcome.transport_error for outcome in outcomes),
        "model_fingerprints": fingerprints,
        "response_failures": response_failures,
        "replay_groups": sorted(group_summaries, key=lambda item: item["anonymous_group"]),
    }


def validate_response_groups(outcomes: Sequence[RequestOutcome]) -> dict[str, int]:
    """Validate same-ID responses using only server-provided replay evidence."""
    grouped: dict[str, list[RequestOutcome]] = {}
    for outcome in outcomes:
        if outcome.status_code != 200:
            continue
        if outcome.request_group_sha256 is None:
            raise ScaleBenchmarkError("Successful response is missing an anonymous group token.")
        grouped.setdefault(outcome.request_group_sha256, []).append(outcome)

    failures: list[str] = []
    same_id_groups = server_originals = server_replays = 0
    group_receipts: list[str] = []
    for items in grouped.values():
        if len(items) > 1:
            same_id_groups += 1
        invalid = [item.failure_reason or "invalid_response_contract" for item in items if not item.contract_valid]
        failures.extend(invalid)
        original_count = sum(item.server_replay is False for item in items)
        replay_count = sum(item.server_replay is True for item in items)
        server_originals += original_count
        server_replays += replay_count
        if original_count != 1 or replay_count != len(items) - 1:
            failures.append("server_replay_cardinality_mismatch")
        receipts = {item.audit_receipt_sha256 for item in items}
        if None in receipts or len(receipts) != 1:
            failures.append("audit_receipt_mismatch")
        else:
            group_receipts.append(next(receipt for receipt in receipts if receipt is not None))
        responses = {item.response_sha256 for item in items}
        if None in responses or len(responses) != 1:
            failures.append("bounded_response_mismatch")

    if len(set(group_receipts)) != len(group_receipts):
        failures.append("audit_receipt_reused_across_groups")

    if failures:
        counts = Counter(failures)
        raise ScaleBenchmarkError(
            "Server-evidence response-group validation failed: "
            + ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
            + "."
        )
    return {
        "successful_request_groups": len(grouped),
        "same_id_replay_groups": same_id_groups,
        "server_original_responses": server_originals,
        "server_replay_responses": server_replays,
    }


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
