"""Synthetic tests for the Lane A final-evaluation metric module.

Every fixture is generated in-process. No IEEE-CIS file, no model artifact, and
no ``final_test`` row is opened.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.lane_a.capacity import MerchantCapacityConfig
from src.lane_a.final_evaluation import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CAPACITY_TIERS,
    CONFIDENCE_LEVEL,
    ECE_BINS,
    PREDECLARED_METRICS,
    PROHIBITED_ON_FINAL,
    REQUIRED_TERMS,
    SELECTED_VARIANT,
    FinalEvaluationError,
    aggregate_metrics,
    assert_metrics_predeclared,
    assert_public_export_safe,
    assert_required_terminology,
    assert_tiers_frozen,
    assert_variant_selected,
    capacity_table,
    evaluation_period_days,
    expected_calibration_error,
    recall_80_workload,
)


@pytest.fixture
def synthetic():
    rng = np.random.default_rng(7)
    n = 4_000
    labels = (rng.random(n) < 0.05).astype(int)
    scores = np.clip(rng.beta(2, 20, n) + labels * 0.25, 0.0, 1.0)
    return labels, scores


# -- frozen choices ------------------------------------------------------


def test_frozen_constants_match_the_protocol():
    assert SELECTED_VARIANT == "E"
    assert CAPACITY_TIERS == (100, 250, 500, 1_000, 2_000)
    assert (BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, CONFIDENCE_LEVEL) == (2_000, 42, 0.95)
    assert ECE_BINS == 15


@pytest.mark.parametrize("variant", PROHIBITED_ON_FINAL)
def test_variants_a_to_d_are_refused_on_final_data(variant):
    with pytest.raises(FinalEvaluationError, match="never be evaluated on final data"):
        assert_variant_selected(variant)


def test_only_variant_e_is_authorised():
    assert assert_variant_selected("E") == "E"
    with pytest.raises(FinalEvaluationError, match="Unknown variant"):
        assert_variant_selected("Z")


@pytest.mark.parametrize(
    "tiers",
    [
        (100, 250, 500, 1_000),
        (100, 250, 500, 1_000, 2_000, 5_000),
        (50, 250, 500, 1_000, 2_000),
        (2_000, 1_000, 500, 250, 100),
    ],
)
def test_altered_capacity_tiers_are_refused(tiers):
    with pytest.raises(FinalEvaluationError, match="frozen"):
        assert_tiers_frozen(tiers)


def test_frozen_tiers_are_accepted():
    assert assert_tiers_frozen(CAPACITY_TIERS) == CAPACITY_TIERS


def test_undeclared_metrics_are_refused():
    with pytest.raises(FinalEvaluationError, match="not predeclared"):
        assert_metrics_predeclared({"average_precision", "f1_score"})


def test_predeclared_metrics_are_accepted():
    assert assert_metrics_predeclared(PREDECLARED_METRICS) == PREDECLARED_METRICS


# -- evaluation period ---------------------------------------------------


def test_evaluation_period_is_span_over_86400():
    dt = np.array([0.0, 86_400.0 * 3])
    assert evaluation_period_days(dt) == pytest.approx(3.0)


@pytest.mark.parametrize("bad", [np.array([]), np.array([5.0, 5.0]), np.array([np.nan, 1.0])])
def test_evaluation_period_fails_closed_on_bad_input(bad):
    with pytest.raises(FinalEvaluationError):
        evaluation_period_days(bad)


# -- calibration ---------------------------------------------------------


def test_ece_bin_count_is_frozen(synthetic):
    labels, scores = synthetic
    with pytest.raises(FinalEvaluationError, match="frozen at 15"):
        expected_calibration_error(labels, scores, bins=10)


def test_calibration_table_reconciles_with_row_count(synthetic):
    labels, scores = synthetic
    result = expected_calibration_error(labels, scores)
    assert len(result["calibration_table"]) == ECE_BINS
    assert sum(row["count"] for row in result["calibration_table"]) == labels.size
    assert 0.0 <= result["expected_calibration_error"] <= 1.0


def test_calibration_table_reports_the_three_declared_fields(synthetic):
    labels, scores = synthetic
    for row in expected_calibration_error(labels, scores)["calibration_table"]:
        assert {"count", "mean_predicted", "observed_positive_rate"} <= set(row)


def test_perfectly_calibrated_scores_have_near_zero_ece():
    rng = np.random.default_rng(3)
    scores = rng.uniform(0.0, 1.0, 60_000)
    labels = (rng.random(60_000) < scores).astype(int)
    result = expected_calibration_error(labels, scores)
    assert result["expected_calibration_error"] < 0.01


def test_scores_outside_the_unit_interval_are_refused(synthetic):
    labels, _ = synthetic
    with pytest.raises(FinalEvaluationError, match=r"\[0, 1\]"):
        expected_calibration_error(labels, np.full(labels.shape, 1.5))


def test_score_of_exactly_one_is_counted_in_the_final_bin():
    labels = np.array([0, 1, 0, 1])
    scores = np.array([0.0, 1.0, 1.0, 0.0])
    table = expected_calibration_error(labels, scores)["calibration_table"]
    assert table[-1]["count"] == 2
    assert sum(row["count"] for row in table) == 4


# -- aggregate metrics ---------------------------------------------------


def test_aggregate_metrics_are_exactly_the_predeclared_set(synthetic):
    labels, scores = synthetic
    result = aggregate_metrics(labels, scores)
    for name in ("row_count", "positive_count", "negative_count", "prevalence"):
        assert name in result
    for name in ("average_precision", "roc_auc", "brier_score", "log_loss"):
        assert set(result[name]) >= {"point", "ci_lower", "ci_upper"}
        assert result[name]["resamples"] == BOOTSTRAP_RESAMPLES
        assert result[name]["seed"] == BOOTSTRAP_SEED
    assert result["ece_bins"] == ECE_BINS
    assert result["score_terminology"] == "Platt-calibrated benchmark output"


def test_counts_reconcile(synthetic):
    labels, scores = synthetic
    result = aggregate_metrics(labels, scores)
    assert result["positive_count"] + result["negative_count"] == result["row_count"]
    assert result["prevalence"] == pytest.approx(result["positive_count"] / result["row_count"])


def test_bootstrap_is_deterministic_for_the_frozen_seed(synthetic):
    labels, scores = synthetic
    first = aggregate_metrics(labels, scores)
    second = aggregate_metrics(labels, scores)
    for name in ("average_precision", "roc_auc", "brier_score", "log_loss"):
        assert first[name] == second[name]


def test_confidence_interval_brackets_the_point_estimate(synthetic):
    labels, scores = synthetic
    result = aggregate_metrics(labels, scores)
    for name in ("average_precision", "roc_auc"):
        assert result[name]["ci_lower"] <= result[name]["point"] <= result[name]["ci_upper"]


def test_single_class_input_is_refused():
    labels = np.zeros(50, dtype=int)
    with pytest.raises(FinalEvaluationError, match="Both classes"):
        aggregate_metrics(labels, np.full(50, 0.1))


# -- capacity ------------------------------------------------------------


def test_capacity_table_covers_exactly_the_five_frozen_tiers(synthetic):
    labels, scores = synthetic
    rows = capacity_table(labels, scores, evaluation_period_days=10.0)
    assert [row["daily_review_capacity"] for row in rows] == list(CAPACITY_TIERS)


def test_capacity_rows_reconcile_exactly(synthetic):
    labels, scores = synthetic
    total, positives = labels.size, int(labels.sum())
    negatives = total - positives
    for row in capacity_table(labels, scores, evaluation_period_days=10.0):
        assert row["tp"] + row["fp"] == row["alerts_selected"]
        assert row["tp"] + row["fn"] == positives
        assert row["tn"] + row["fp"] == negatives
        assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == total
        assert row["alerts_selected"] <= row["review_budget"]


def test_capacity_rates_reproduce_from_counts(synthetic):
    labels, scores = synthetic
    for row in capacity_table(labels, scores, evaluation_period_days=10.0):
        reviews = row["tp"] + row["fp"]
        if reviews:
            assert row["precision"] == pytest.approx(row["tp"] / reviews)
        assert row["recall"] == pytest.approx(row["tp"] / (row["tp"] + row["fn"]))
        assert row["alert_rate"] == pytest.approx(reviews / labels.size)


def test_wilson_intervals_are_present_and_bracket_the_point(synthetic):
    labels, scores = synthetic
    for row in capacity_table(labels, scores, evaluation_period_days=10.0):
        for key, point in (("precision_wilson", "precision"), ("recall_wilson", "recall")):
            interval = row[key]
            assert interval is not None
            # Wilson bounds are computed in floating point; allow a rounding epsilon
            # at the degenerate ends (precision or recall of exactly 0.0 or 1.0).
            assert interval["lower"] <= row[point] + 1e-12
            assert row[point] <= interval["upper"] + 1e-12


def test_capacity_table_refuses_altered_tiers(synthetic):
    labels, scores = synthetic
    with pytest.raises(FinalEvaluationError, match="frozen"):
        capacity_table(labels, scores, evaluation_period_days=10.0, tiers=(100, 200))


def test_budget_is_floor_of_capacity_times_period():
    config = MerchantCapacityConfig(daily_review_capacity=250, evaluation_period_days=10.7)
    assert config.review_budget == 2_675


def test_recall_80_workload_is_marked_a_retrospective_diagnostic(synthetic):
    labels, scores = synthetic
    result = recall_80_workload(labels, scores, evaluation_period_days=10.0)
    assert result["diagnostic_class"] == "retrospective benchmark diagnostic"
    assert result["not_a_recommendation"] is True


# -- deterministic ranking and tie handling ------------------------------


def test_ties_are_broken_by_ascending_source_position():
    # Every score is identical, so only position can decide the selection.
    labels = np.array([0, 0, 1, 1, 0, 0])
    scores = np.full(6, 0.5)
    rows = capacity_table(
        labels, scores, evaluation_period_days=1.0, tiers=CAPACITY_TIERS
    )
    # Budget far exceeds the population, so everything is selected.
    assert rows[0]["alerts_selected"] == 6


def test_ranking_is_deterministic_across_repeated_calls():
    rng = np.random.default_rng(11)
    labels = (rng.random(500) < 0.1).astype(int)
    scores = np.round(rng.random(500), 2)  # deliberately many ties
    first = capacity_table(labels, scores, evaluation_period_days=5.0)
    second = capacity_table(labels, scores, evaluation_period_days=5.0)
    assert [dict(r) for r in first] == [dict(r) for r in second]


def test_tie_selection_prefers_the_earlier_source_position():
    scores = np.array([0.5, 0.5, 0.5, 0.5])
    config = MerchantCapacityConfig(daily_review_capacity=1, evaluation_period_days=1.0)
    from src.lane_a.capacity import allocate_reviews

    allocation = allocate_reviews(scores, config)
    assert list(allocation["selected_mask"]) == [True, False, False, False]


# -- public export safety ------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"note": "/Users/example/example-private-root"},
        {"note": "~/example-private-root/data.csv"},
        {"domain": "gmail.com"},
        {"device": "SM-G950F"},
        {"ids": "TransactionID"},
        {"contact": "person@example.org"},
        {"path": "C:\\\\Users\\\\data"},
    ],
)
def test_public_export_rejects_private_or_row_level_content(payload):
    with pytest.raises(FinalEvaluationError, match="Public export rejected"):
        assert_public_export_safe(payload)


@pytest.mark.parametrize(
    "claim",
    [
        "this was a human-blind evaluation",
        "externally blind holdout",
        "guaranteed savings for merchants",
        "delivers ROI in month one",
        "a universal operating threshold",
    ],
)
def test_public_export_rejects_prohibited_claims(claim):
    with pytest.raises(FinalEvaluationError, match="prohibited claim"):
        assert_public_export_safe({"summary": claim})


def test_public_export_accepts_clean_aggregates():
    assert_public_export_safe(
        {
            "evaluation": "IEEE-CIS Lane A final evaluation",
            "row_count": 1234,
            "average_precision": {"point": 0.21, "ci_lower": 0.19, "ci_upper": 0.23},
            "limitations": ["not a production SLO", "not directly comparable with Lane B"],
        }
    )


def test_required_terminology_is_enforced():
    document = " ".join(REQUIRED_TERMS)
    assert_required_terminology(document)
    with pytest.raises(FinalEvaluationError, match="missing required terminology"):
        assert_required_terminology("a document with none of the required phrases")
