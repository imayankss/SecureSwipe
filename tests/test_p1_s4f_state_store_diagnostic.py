"""Focused privacy, opt-in, and classification checks for P1-S4f."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from api.postgres_idempotency import PostgresIdempotencyStore
from api.scale_config import PostgresScaleSettings
from api.state_store_diagnostic import (
    DIAGNOSTIC_FLAG,
    DIAGNOSTIC_OUTPUT_DIR,
    StateStoreDiagnosticAggregator,
    diagnostic_enabled,
    sanitize_failure,
)
from scripts.run_p1_s4f_state_store_diagnostic import (
    CONCURRENCY,
    EXPECTED_MODEL_FINGERPRINT,
    PROTOCOL_PATH,
    PROTOCOL_SHA256,
    REPEAT,
    WORKERS,
    _root_cause,
)
from scripts.run_p1_scale_benchmark import _sha256_file
from src.operations.p1_scale_benchmark import validate_safe_result


class _PoolStats:
    def get_stats(self) -> dict[str, int]:
        return {
            "pool_min": 1,
            "pool_max": 4,
            "pool_size": 4,
            "pool_available": 0,
            "requests_waiting": 17,
            "not_allowlisted": 999,
        }


@pytest.mark.parametrize("value", [None, "", "0", "true", "TRUE", "yes", " 1 "])
def test_state_store_diagnostic_requires_exact_opt_in(value: str | None) -> None:
    environment = {} if value is None else {DIAGNOSTIC_FLAG: value}
    assert diagnostic_enabled(environment) is False


def test_state_store_diagnostic_exact_opt_in() -> None:
    assert diagnostic_enabled({DIAGNOSTIC_FLAG: "1"}) is True


def test_aggregate_contains_only_allowlisted_failure_evidence(tmp_path: Path) -> None:
    aggregator = StateStoreDiagnosticAggregator(tmp_path)
    observation = aggregator.start("connection_checkout", _PoolStats())
    observation.failure(PoolTimeout("contains-dsn-and-secret-sentinel"))

    snapshot = aggregator.snapshot()
    encoded = json.dumps(snapshot)

    assert snapshot["stages"]["connection_checkout"]["failure_count"] == 1
    assert snapshot["stages"]["connection_checkout"]["failure_categories"] == {
        "checkout_timeout": 1
    }
    assert "not_allowlisted" not in encoded
    assert "sentinel" not in encoded
    assert "PoolTimeout" not in encoded
    validate_safe_result(snapshot)


def test_success_path_does_not_write_until_explicit_flush(tmp_path: Path) -> None:
    aggregator = StateStoreDiagnosticAggregator(tmp_path)
    for _ in range(30):
        observation = aggregator.start("reserve", _PoolStats())
        observation.success()

    assert list(tmp_path.glob("*.json")) == []
    path = aggregator.flush()
    assert path is not None
    reserve = json.loads(path.read_text())["stages"]["reserve"]
    assert reserve["success_count"] == 30
    assert reserve["pool_counters"] == {}


def test_pool_counters_are_captured_only_at_failure_boundary(tmp_path: Path) -> None:
    aggregator = StateStoreDiagnosticAggregator(tmp_path)
    observation = aggregator.start("connection_checkout", _PoolStats())
    observation.failure(PoolTimeout("private"))

    pool = aggregator.snapshot()["stages"]["connection_checkout"]["pool_counters"]
    assert pool["pool_size"]["max"] == 4.0
    assert pool["pool_available"]["max"] == 0.0
    assert pool["requests_waiting"]["max"] == 17.0


def test_failure_sanitizer_never_retains_exception_text() -> None:
    assert sanitize_failure(PoolTimeout("private")) == ("checkout_timeout", None)
    assert sanitize_failure(PoolClosed("private")) == ("pool_closed", None)
    assert sanitize_failure(OSError(24, "private")) == ("resource_limit", None)


def test_store_diagnostic_is_absent_for_non_exact_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = PostgresScaleSettings(
        dsn="postgresql://local@127.0.0.1/secureswipe_test",
        schema="p1s4f_test",
        hmac_secret=b"p1-s4f-test-secret-that-is-long-enough",
    )
    monkeypatch.setenv(DIAGNOSTIC_OUTPUT_DIR, str(tmp_path))
    for value in ("", "0", "true"):
        monkeypatch.setenv(DIAGNOSTIC_FLAG, value)
        assert PostgresIdempotencyStore(settings).state_store_diagnostic is None


def test_store_diagnostic_is_created_only_for_exact_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DIAGNOSTIC_FLAG, "1")
    monkeypatch.setenv(DIAGNOSTIC_OUTPUT_DIR, str(tmp_path))
    settings = PostgresScaleSettings(
        dsn="postgresql://local@127.0.0.1/secureswipe_test",
        schema="p1s4f_test",
        hmac_secret=b"p1-s4f-test-secret-that-is-long-enough",
    )
    assert PostgresIdempotencyStore(settings).state_store_diagnostic is not None


def test_checkout_timeout_is_supported_only_with_reproduced_api_failure() -> None:
    process = {
        "stages": {
            "connection_checkout": {
                "failure_categories": {"checkout_timeout": 3},
                "sqlstate_counts": {},
            }
        }
    }
    reproduced = _root_cause(
        {"api_error_code_counts": {"state_store_unavailable": 3}}, [process]
    )
    passed = _root_cause(None, [process])

    assert reproduced == {
        "state_store_unavailable_reproduced": True,
        "supported_root_cause": True,
        "classification": "connection_checkout_timeout",
        "earliest_failing_stage": "connection_checkout",
        "stage_failure_category_counts": {
            "connection_checkout": {"checkout_timeout": 3}
        },
        "sqlstate_counts": {},
    }
    assert passed["supported_root_cause"] is False
    assert passed["classification"] == "not_reproduced"


def test_frozen_reproduction_identity_and_protocol_hash() -> None:
    assert (WORKERS, CONCURRENCY, REPEAT) == (4, 64, 2)
    assert EXPECTED_MODEL_FINGERPRINT == (
        "a044d90fcd49359e37705bb1b61fb34c3e1ebc380931753f5db8928c307168c3"
    )
    assert _sha256_file(PROTOCOL_PATH) == PROTOCOL_SHA256


def test_completion_waits_before_connection_checkout() -> None:
    settings = PostgresScaleSettings(
        dsn="postgresql://local@127.0.0.1/secureswipe_test",
        schema="p1s4f_test",
        hmac_secret=b"p1-s4f-test-secret-that-is-long-enough",
    )
    store = PostgresIdempotencyStore(settings)
    active = 0
    maximum_active = 0

    @asynccontextmanager
    async def observed_checkout(pool: Any) -> Any:
        nonlocal active, maximum_active
        del pool
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            await asyncio.sleep(0.002)
            yield object()
        finally:
            active -= 1

    store._connection = observed_checkout  # type: ignore[method-assign]

    async def exercise() -> None:
        async def one_completion() -> None:
            async with store._completion_connection(object()):  # type: ignore[arg-type]
                await asyncio.sleep(0.002)

        await asyncio.gather(*(one_completion() for _ in range(32)))

    asyncio.run(exercise())
    assert maximum_active == 1
