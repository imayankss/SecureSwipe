"""Synthetic tests for the MT4 benchmark primitives.

No network, no real transaction data, no held-out role. These cover the corpus
contract, latency statistics, and the accounting rule that no request may ever
be silently dropped.
"""

from __future__ import annotations

import pytest

from src.operations.benchmark import (
    CONCURRENCY_LEVELS,
    FEATURE_ORDER,
    MIN_REPEATS,
    PROVENANCE_LABEL,
    BenchmarkError,
    RepeatResult,
    aggregate_repeats,
    median,
    percentile,
    synthetic_corpus,
)


def _repeat(concurrency: int = 1, *, latencies=None, **kwargs) -> RepeatResult:
    latencies = latencies if latencies is not None else [1.0, 2.0, 3.0, 4.0]
    defaults = dict(
        concurrency=concurrency,
        attempted=len(latencies),
        completed=len(latencies),
        timeouts=0,
        transport_errors=0,
        status_counts={200: len(latencies)},
        latencies_ms=list(latencies),
        wall_seconds=1.0,
    )
    defaults.update(kwargs)
    return RepeatResult(**defaults)


# -- protocol constants ---------------------------------------------------


def test_frozen_concurrency_levels_and_repeats():
    assert CONCURRENCY_LEVELS == (1, 2, 4, 8, 16)
    assert MIN_REPEATS == 3


def test_provenance_label_is_the_required_string():
    assert PROVENANCE_LABEL == "HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS"


# -- synthetic corpus -----------------------------------------------------


def test_corpus_is_deterministic_for_a_fixed_seed():
    assert synthetic_corpus(16) == synthetic_corpus(16)


def test_corpus_changes_with_the_seed():
    assert synthetic_corpus(8, seed=1) != synthetic_corpus(8, seed=2)


def test_corpus_covers_exactly_the_serving_feature_contract():
    row = synthetic_corpus(1)[0]
    assert tuple(row) == FEATURE_ORDER
    assert len(row) == 30


def test_corpus_carries_no_label_or_identifier_field():
    row = synthetic_corpus(4)[0]
    for forbidden in ("isFraud", "label", "TransactionID", "id", "email", "card"):
        assert forbidden not in row


def test_corpus_values_are_finite_and_bounded():
    for row in synthetic_corpus(64):
        for name, value in row.items():
            assert isinstance(value, float)
            if name not in ("Time", "Amount"):
                # Deterministic synthetic fillers in a small bounded band. They
                # are not scaled features and carry no distributional meaning.
                assert -1.0 <= value <= 1.01


def test_empty_corpus_is_refused():
    with pytest.raises(BenchmarkError):
        synthetic_corpus(0)


# -- latency statistics ---------------------------------------------------


def test_percentile_is_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 0.50) == 50
    assert percentile(values, 0.95) == 95
    assert percentile(values, 0.99) == 99
    assert percentile(values, 1.0) == 100


def test_percentile_rejects_empty_and_out_of_range():
    with pytest.raises(BenchmarkError):
        percentile([], 0.5)
    with pytest.raises(BenchmarkError):
        percentile([1.0], 0.0)
    with pytest.raises(BenchmarkError):
        percentile([1.0], 1.5)


def test_median_handles_even_and_odd_samples():
    assert median([3.0, 1.0, 2.0]) == 2.0
    assert median([4.0, 1.0, 3.0, 2.0]) == 2.5


# -- accounting rule ------------------------------------------------------


def test_every_request_must_be_accounted_for():
    with pytest.raises(BenchmarkError, match="does not reconcile"):
        RepeatResult(concurrency=1, attempted=10, completed=4, timeouts=1,
                     transport_errors=0, status_counts={200: 4},
                     latencies_ms=[1.0] * 4, wall_seconds=1.0)


def test_status_counts_must_reconcile_with_completed():
    with pytest.raises(BenchmarkError, match="Status counts"):
        RepeatResult(concurrency=1, attempted=5, completed=5, timeouts=0,
                     transport_errors=0, status_counts={200: 3},
                     latencies_ms=[1.0] * 5, wall_seconds=1.0)


def test_timeouts_and_transport_errors_are_counted_not_dropped():
    result = RepeatResult(concurrency=4, attempted=10, completed=6, timeouts=3,
                          transport_errors=1, status_counts={200: 5, 503: 1},
                          latencies_ms=[1.0] * 6, wall_seconds=2.0)
    assert result.timeouts == 3
    assert result.transport_errors == 1
    summary = result.summary()
    assert summary["attempted"] == 10
    assert summary["completed"] + summary["timeouts"] + summary["transport_errors"] == 10


def test_non_2xx_is_separated_from_successes():
    result = RepeatResult(concurrency=2, attempted=4, completed=4, timeouts=0,
                          transport_errors=0, status_counts={200: 2, 429: 2},
                          latencies_ms=[1.0] * 4, wall_seconds=1.0)
    assert result.successes == 2
    assert result.non_2xx == 2


def test_rejections_count_toward_completed_not_success():
    result = RepeatResult(concurrency=8, attempted=3, completed=3, timeouts=0,
                          transport_errors=0, status_counts={429: 3},
                          latencies_ms=[1.0] * 3, wall_seconds=1.0)
    assert result.successes == 0
    assert result.successful_rps == 0.0


# -- aggregation ----------------------------------------------------------


def test_aggregation_requires_the_declared_repeat_count():
    with pytest.raises(BenchmarkError, match="[Aa]t least 3 repeats"):
        aggregate_repeats([_repeat(), _repeat()])


def test_aggregation_reports_median_and_every_per_repeat_value():
    repeats = [_repeat(latencies=[float(x)] * 4) for x in (1, 5, 3)]
    out = aggregate_repeats(repeats)
    assert out["repeats"] == 3
    assert len(out["per_repeat"]) == 3
    assert out["median_p50_ms"] == 3.0  # median of 1, 5, 3 — not the best run


def test_aggregation_totals_every_outcome_class():
    repeats = [
        RepeatResult(concurrency=4, attempted=5, completed=4, timeouts=1, transport_errors=0,
                     status_counts={200: 3, 429: 1}, latencies_ms=[1.0] * 4, wall_seconds=1.0)
        for _ in range(3)
    ]
    out = aggregate_repeats(repeats)
    assert out["total_attempted"] == 15
    assert out["total_successes"] == 9
    assert out["total_non_2xx"] == 3
    assert out["total_timeouts"] == 3


# -- audit append growth --------------------------------------------------


def test_audit_append_growth_is_measured_and_reported(tmp_path):
    """The audit writer re-verifies the chain per append; that cost must be visible."""
    from src.operations.benchmark import measure_audit_append_growth

    result = measure_audit_append_growth(
        tmp_path / "growth.ndjson", events=120, sample_points=(1, 60, 120)
    )
    assert result["events_appended"] == 120
    assert set(result["append_ms_at_event"]) == {"1", "60", "120"}
    assert result["mean_first_window_ms"] > 0
    assert result["mean_last_window_ms"] > 0
    # Cost per append rises with log length rather than staying flat.
    assert result["growth_factor"] > 1.0
    assert "tamper-evidence" in result["interpretation"]


def test_audit_growth_measurement_writes_only_synthetic_events(tmp_path):
    import json as _json

    from src.operations.benchmark import measure_audit_append_growth

    log = tmp_path / "growth2.ndjson"
    measure_audit_append_growth(log, events=5, sample_points=(1, 5))
    events = [_json.loads(line) for line in log.read_text().splitlines() if line]
    assert len(events) == 5
    for event in events:
        assert event["request_id"].startswith("audit-growth-")
        assert event["model_version"] == "synthetic-benchmark"
