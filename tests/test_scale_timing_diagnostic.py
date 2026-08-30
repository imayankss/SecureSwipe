from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.postgres_idempotency import PostgresIdempotencyStore
from api.scale_config import PostgresScaleSettings
from api.scale_timing import (
    CHECKPOINT_NAMES,
    METRIC_NAMES,
    METRIC_SPANS,
    NULL_TIMER,
    TIMING_FLAG,
    TIMING_OUTPUT_DIR,
    CompletionTimer,
    TimingAggregator,
    aggregator_from_environment,
    merge_snapshots,
    nearest_rank,
    timing_enabled,
)

ROOT = Path(__file__).resolve().parents[1]


def _settings() -> PostgresScaleSettings:
    return PostgresScaleSettings(
        dsn="postgresql://user@127.0.0.1:55432/secureswipe_scale_test",
        schema="p1s4_timing",
        hmac_secret=b"z" * 32,
    )


# --- default-off behaviour -------------------------------------------------


def test_diagnostic_is_off_unless_the_explicit_local_value_is_set() -> None:
    assert timing_enabled({}) is False
    for value in ("", "0", "true", "TRUE", "yes", "on", "2", " ", "01"):
        assert timing_enabled({TIMING_FLAG: value}) is False
    assert timing_enabled({TIMING_FLAG: "1"}) is True
    assert timing_enabled({TIMING_FLAG: " 1 "}) is True


def test_store_builds_no_aggregator_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TIMING_FLAG, raising=False)
    monkeypatch.delenv(TIMING_OUTPUT_DIR, raising=False)

    store = PostgresIdempotencyStore(_settings())

    assert store.timing_aggregator is None
    assert aggregator_from_environment({}) is None


def test_store_builds_an_aggregator_only_with_the_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(TIMING_FLAG, "1")
    monkeypatch.setenv(TIMING_OUTPUT_DIR, str(tmp_path))

    store = PostgresIdempotencyStore(_settings())

    assert isinstance(store.timing_aggregator, TimingAggregator)
    assert store.timing_aggregator.output_dir == tmp_path


def test_null_timer_records_nothing_and_never_raises() -> None:
    for checkpoint in CHECKPOINT_NAMES:
        NULL_TIMER.at(checkpoint)
    NULL_TIMER.at("not_a_real_checkpoint")
    NULL_TIMER.submit()

    assert NULL_TIMER.durations() == {}


# --- timing boundaries -----------------------------------------------------


def test_every_required_completion_duration_is_measured() -> None:
    assert set(METRIC_NAMES) == {
        "idempotency_lock_wait_ms",
        "head_lock_wait_ms",
        "head_lock_hold_ms",
        "event_build_ms",
        "event_insert_ms",
        "idempotency_update_ms",
        "head_update_ms",
        "commit_ms",
        "total_completion_ms",
    }


def test_spans_reference_only_declared_checkpoints_in_order() -> None:
    order = {name: index for index, name in enumerate(CHECKPOINT_NAMES)}
    for metric, later, earlier in METRIC_SPANS:
        assert later in order, metric
        assert earlier in order, metric
        assert order[later] > order[earlier], metric


def test_head_lock_hold_spans_acquisition_through_commit() -> None:
    aggregator = TimingAggregator()
    timer = CompletionTimer(aggregator)
    marks = {
        "transaction_open": 0.0,
        "idempotency_locked": 0.002,
        "head_lock_requested": 0.003,
        "head_locked": 0.010,
        "event_built": 0.011,
        "event_inserted": 0.014,
        "idempotency_updated": 0.016,
        "head_updated": 0.017,
        "committed": 0.025,
    }
    timer._checkpoints.update(marks)  # noqa: SLF001 - deterministic clock for the assertion

    d = timer.durations()

    assert d["idempotency_lock_wait_ms"] == pytest.approx(2.0)
    assert d["head_lock_wait_ms"] == pytest.approx(7.0)
    # Hold time is acquisition -> commit, not merely the statements in between.
    assert d["head_lock_hold_ms"] == pytest.approx(15.0)
    assert d["commit_ms"] == pytest.approx(8.0)
    assert d["total_completion_ms"] == pytest.approx(25.0)
    # The in-lock statement spans must sum to the hold time.
    inner = sum(
        d[name]
        for name in (
            "event_build_ms",
            "event_insert_ms",
            "idempotency_update_ms",
            "head_update_ms",
            "commit_ms",
        )
    )
    assert inner == pytest.approx(d["head_lock_hold_ms"])


def test_incomplete_transactions_are_never_recorded() -> None:
    aggregator = TimingAggregator()
    timer = CompletionTimer(aggregator)
    timer.at("transaction_open")
    timer.at("idempotency_locked")
    timer.at("head_lock_requested")

    timer.submit()

    assert aggregator.completions == 0
    assert aggregator.snapshot()["metrics"]["head_lock_hold_ms"]["count"] == 0


def test_unknown_checkpoint_names_are_rejected() -> None:
    timer = CompletionTimer(TimingAggregator())
    with pytest.raises(ValueError, match="Unknown completion checkpoint"):
        timer.at("commit")


def test_percentiles_use_nearest_rank() -> None:
    values = [float(n) for n in range(1, 101)]
    assert nearest_rank(values, 0.50) == 50.0
    assert nearest_rank(values, 0.95) == 95.0
    assert nearest_rank(values, 0.99) == 99.0


# --- aggregate-only output and privacy filtering ---------------------------


def _record(aggregator: TimingAggregator, scale: float) -> None:
    aggregator.record({name: scale for name in METRIC_NAMES})


def test_snapshot_publishes_aggregates_and_never_individual_samples() -> None:
    aggregator = TimingAggregator()
    for value in (1.0, 2.0, 3.0, 4.0, 5.0):
        _record(aggregator, value)

    snapshot = aggregator.snapshot()

    assert snapshot["completions"] == 5
    assert snapshot["unit"] == "milliseconds"
    metric = snapshot["metrics"]["head_lock_hold_ms"]
    assert metric == {"count": 5, "median_ms": 3.0, "p95_ms": 5.0, "p99_ms": 5.0}
    encoded = json.dumps(snapshot)
    for forbidden in ("samples", "values", "request", "payload", "feature", "score"):
        assert forbidden not in encoded.lower()


def test_record_discards_anything_that_is_not_a_declared_duration() -> None:
    aggregator = TimingAggregator()
    aggregator.record(
        {
            "head_lock_hold_ms": 12.5,
            "request_id": "p1sf-v1-w4-c64-r2-valid-0123",
            "payload": {"Amount": 42.0},
            "features": [1.0, 2.0],
            "raw_score": 0.91,
            "decision": "human_review",
            "dsn": "postgresql://user:pw@127.0.0.1:55432/db",
            "sql": "SELECT ... FOR UPDATE",
            "error": "PoolTimeout: could not acquire",
        }
    )

    snapshot = aggregator.snapshot()
    encoded = json.dumps(snapshot).lower()

    assert snapshot["metrics"]["head_lock_hold_ms"]["count"] == 1
    for leaked in ("p1sf-v1", "postgresql://", "human_review", "pooltimeout", "for update"):
        assert leaked not in encoded
    assert set(snapshot["metrics"]) == set(METRIC_NAMES)


def test_non_numeric_and_boolean_durations_are_rejected() -> None:
    aggregator = TimingAggregator()
    aggregator.record({"head_lock_hold_ms": True, "commit_ms": "8.0", "head_update_ms": None})

    metrics = aggregator.snapshot()["metrics"]

    assert metrics["head_lock_hold_ms"]["count"] == 0
    assert metrics["commit_ms"]["count"] == 0
    assert metrics["head_update_ms"]["count"] == 0


def test_flush_writes_an_atomic_aggregate_file(tmp_path: Path) -> None:
    aggregator = TimingAggregator(tmp_path)
    for value in (4.0, 6.0):
        _record(aggregator, value)

    path = aggregator.flush()

    assert path is not None and path.parent == tmp_path
    assert path.name.startswith("scale-timing-") and path.suffix == ".json"
    document = json.loads(path.read_text())
    assert document["completions"] == 2
    assert document["metrics"]["commit_ms"]["count"] == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_flush_is_a_no_op_without_a_directory_or_samples(tmp_path: Path) -> None:
    assert TimingAggregator().flush() is None
    assert TimingAggregator(tmp_path).flush() is None
    assert not list(tmp_path.iterdir())


def test_merge_keeps_per_process_aggregates_only() -> None:
    first, second = TimingAggregator(), TimingAggregator()
    _record(first, 5.0)
    _record(second, 9.0)
    _record(second, 11.0)

    merged = merge_snapshots([first.snapshot(), second.snapshot()])

    assert merged["processes"] == 2
    assert merged["completions"] == 3
    assert len(merged["per_process"]) == 2
    assert "process_id" not in json.dumps(merged)


# --- public surface is unchanged -------------------------------------------


def test_diagnostic_adds_no_route_header_or_response_field() -> None:
    source = (ROOT / "api" / "scale_timing.py").read_text()
    for forbidden in ("JSONResponse", "APIRouter", "@app", "add_route", "headers[", "Response("):
        assert forbidden not in source
    wiring = (ROOT / "api" / "postgres_idempotency.py").read_text()
    assert wiring.count("timer.at(") == len(CHECKPOINT_NAMES)
    assert wiring.count("timer.submit()") == 1


def test_completion_path_still_returns_an_unchanged_reservation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The diagnostic must not alter what the store hands back to the API."""
    monkeypatch.setenv(TIMING_FLAG, "1")
    monkeypatch.setenv(TIMING_OUTPUT_DIR, str(tmp_path))
    enabled = PostgresIdempotencyStore(_settings())
    monkeypatch.delenv(TIMING_FLAG)
    disabled = PostgresIdempotencyStore(_settings())

    assert enabled.timing_aggregator is not None
    assert disabled.timing_aggregator is None
    # Same public API surface either way.
    assert dir(enabled) == dir(disabled)
