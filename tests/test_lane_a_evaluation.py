"""Synthetic-only tests for Lane A selection, calibration and threshold logic."""

from __future__ import annotations

import numpy as np
import pytest

from src.lane_a.evaluation import (
    CALIBRATION_POSITIVE_FLOOR,
    MINIMUM_BRIER_IMPROVEMENT,
    MODEL_SIMPLICITY_ORDER,
    RECALL_TARGET,
    REVIEW_CAPACITY_PER_DAY,
    Interval,
    LaneAEvaluationError,
    confusion_counts,
    core_metrics,
    paired_ap_difference,
    paired_brier_improvement,
    select_champion,
    select_threshold,
)


def _labels_and_scores(n: int = 400, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = (rng.random(n) < 0.2).astype(int)
    scores = np.clip(labels * 0.5 + rng.normal(0.25, 0.15, n), 0.0, 1.0)
    return labels, scores


# ------------------------------------------------------------ selection


def test_champion_is_the_highest_average_precision() -> None:
    champion, reason = select_champion(
        {"dummy_majority": 0.05, "logistic_regression": 0.30, "xgboost": 0.42}
    )
    assert champion == "xgboost"
    assert "highest" in reason


def test_tie_breaks_toward_the_simpler_model() -> None:
    champion, reason = select_champion({"xgboost": 0.4, "logistic_regression": 0.4})
    assert champion == "logistic_regression"
    assert "simpler" in reason


def test_tie_break_order_is_dummy_lr_rf_xgb() -> None:
    assert MODEL_SIMPLICITY_ORDER == (
        "dummy_majority",
        "logistic_regression",
        "random_forest",
        "xgboost",
    )
    champion, _ = select_champion({name: 0.1 for name in MODEL_SIMPLICITY_ORDER})
    assert champion == "dummy_majority"


def test_empty_candidate_set_is_refused() -> None:
    with pytest.raises(LaneAEvaluationError):
        select_champion({})


# ------------------------------------------------------------ intervals


def test_interval_zero_semantics() -> None:
    assert Interval(0.05, 0.01, 0.09).excludes_zero_above()
    assert not Interval(0.05, -0.01, 0.09).excludes_zero_above()
    assert Interval(0.05, -0.01, 0.09).includes_zero()
    assert not Interval(0.05, 0.01, 0.09).includes_zero()


def test_identical_scores_give_a_difference_interval_containing_zero() -> None:
    labels, scores = _labels_and_scores()
    interval = paired_ap_difference(labels, scores, scores, n_resamples=200)
    assert interval.point == pytest.approx(0.0)
    assert interval.includes_zero()


def test_paired_bootstrap_is_deterministic_for_a_fixed_seed() -> None:
    labels, scores = _labels_and_scores()
    other = np.clip(scores + 0.05, 0.0, 1.0)
    first = paired_ap_difference(labels, scores, other, n_resamples=200, seed=42)
    second = paired_ap_difference(labels, scores, other, n_resamples=200, seed=42)
    assert (first.point, first.lower, first.upper) == (second.point, second.lower, second.upper)


def test_brier_improvement_is_positive_when_the_candidate_is_better() -> None:
    labels = np.array([0, 1] * 100)
    identity = np.full(200, 0.9)  # badly miscalibrated
    candidate = np.where(labels == 1, 0.6, 0.4)  # closer to the truth
    interval = paired_brier_improvement(labels, identity, candidate, n_resamples=200)
    assert interval.point > 0
    assert interval.excludes_zero_above()


def test_brier_improvement_sign_convention_matches_the_protocol() -> None:
    """improvement = Brier(identity) - Brier(candidate); negative means worse."""
    labels = np.array([0, 1] * 100)
    identity = np.where(labels == 1, 0.6, 0.4)
    worse = np.full(200, 0.9)
    interval = paired_brier_improvement(labels, identity, worse, n_resamples=200)
    assert interval.point < 0
    assert not interval.excludes_zero_above()


# ------------------------------------------------------------ thresholds


def test_threshold_reports_unsatisfiable_capacity_without_relaxing_it() -> None:
    labels = np.array([1] * 50 + [0] * 4950)
    scores = np.concatenate([np.full(50, 0.6), np.full(4950, 0.55)])
    decision = select_threshold(labels, scores, partition_days=1.0, review_capacity_per_day=10)
    assert decision["satisfiable"] is False
    assert decision["unsatisfiable_reason"] == "review_capacity"
    assert decision["selected"] is None
    assert "NOT relaxed" in str(decision["reason"])
    assert decision["best_meeting_recall_only"] is not None


def test_threshold_reports_unreachable_recall_target() -> None:
    """Recall is unreachable only when positives sit below every candidate threshold.

    Capacity is set generously so it cannot be the binding constraint: this test
    must fail for the recall reason specifically, not merely fail.
    """
    labels = np.array([1] * 10 + [0] * 990)
    # Eight positives score 0.0, below the lowest candidate threshold, so the
    # best achievable recall is 0.2 -- under the 0.80 target at every operating point.
    scores = np.concatenate([np.full(8, 0.0), np.full(2, 0.95), np.full(990, 0.10)])
    decision = select_threshold(
        labels, scores, partition_days=1.0, review_capacity_per_day=100_000
    )
    assert decision["satisfiable"] is False
    assert decision["unsatisfiable_reason"] == "recall_target"
    assert decision["selected"] is None


def test_threshold_selects_highest_precision_meeting_both_constraints() -> None:
    labels = np.array([1] * 100 + [0] * 900)
    scores = np.concatenate([np.full(100, 0.9), np.full(900, 0.1)])
    decision = select_threshold(
        labels, scores, partition_days=1.0, review_capacity_per_day=1000
    )
    assert decision["satisfiable"] is True
    selected = decision["selected"]
    assert selected["recall"] >= RECALL_TARGET
    assert selected["precision"] == pytest.approx(1.0)
    assert selected["within_capacity"] is True


def test_partition_days_must_be_positive() -> None:
    labels, scores = _labels_and_scores()
    with pytest.raises(LaneAEvaluationError):
        select_threshold(labels, scores, partition_days=0.0)


def test_protocol_constants_match_the_accepted_protocol() -> None:
    assert CALIBRATION_POSITIVE_FLOOR == 40
    assert MINIMUM_BRIER_IMPROVEMENT == 0.005
    assert RECALL_TARGET == 0.80
    assert REVIEW_CAPACITY_PER_DAY == 100


# ------------------------------------------------------------ metrics


def test_confusion_counts_sum_to_the_population() -> None:
    labels, scores = _labels_and_scores()
    counts = confusion_counts(labels, (scores >= 0.5).astype(int))
    assert sum(counts.values()) == len(labels)


def test_core_metrics_require_both_classes() -> None:
    with pytest.raises(LaneAEvaluationError):
        core_metrics(np.zeros(10, dtype=int), np.linspace(0, 1, 10))


def test_core_metrics_reject_misaligned_inputs() -> None:
    with pytest.raises(LaneAEvaluationError):
        core_metrics(np.array([0, 1, 1]), np.array([0.1, 0.2]))
