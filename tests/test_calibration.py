"""Calibration diagnostics and leakage-safe fit/compare tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.evaluation.calibration import (
    apply_calibrator,
    compare_calibrators,
    evaluate_calibration,
    fit_calibrator,
    reliability_table,
)


def test_perfect_scores_have_zero_brier_and_calibration_error() -> None:
    result = evaluate_calibration([0, 0, 1, 1], [0.0, 0.0, 1.0, 1.0], n_bins=2)
    assert result["brier_score"] == pytest.approx(0.0)
    assert result["expected_calibration_error"] == pytest.approx(0.0)
    assert result["maximum_calibration_error"] == pytest.approx(0.0)
    assert sum(row["count"] for row in result["reliability"]) == 4


def test_uniform_reliability_omits_empty_bins_but_preserves_rows() -> None:
    table = reliability_table([0, 0, 1, 1], [0.01, 0.02, 0.98, 0.99], n_bins=4, strategy="uniform")
    assert len(table) == 2
    assert table["count"].sum() == 4


def test_quantile_reliability_never_splits_equal_scores() -> None:
    table = reliability_table(
        [0, 1, 0, 1, 0, 1], [0.2, 0.2, 0.2, 0.8, 0.8, 0.8], n_bins=4
    )
    assert len(table) == 2
    assert sorted(table["count"].tolist()) == [3, 3]


@pytest.mark.parametrize("invalid", [[0.2, float("nan")], [0.2, float("inf")], [0.2, 1.1]])
def test_calibration_rejects_invalid_scores(invalid: list[float]) -> None:
    with pytest.raises(ValueError):
        evaluate_calibration([0, 1], invalid, n_bins=2)


def test_platt_calibrator_outputs_finite_bounded_values() -> None:
    labels = np.array([0] * 20 + [1] * 20)
    scores = np.array([0.4] * 20 + [0.6] * 20)
    calibrator = fit_calibrator(scores, labels, "platt")
    output = apply_calibrator(calibrator, np.array([0.0, 0.5, 1.0]))
    assert output.shape == (3,)
    assert np.isfinite(output).all()
    assert np.logical_and(output >= 0.0, output <= 1.0).all()


def test_comparison_fits_on_train_and_evaluates_on_separate_values() -> None:
    train_labels = np.array([0] * 30 + [1] * 30)
    train_scores = np.array([0.4] * 30 + [0.6] * 30)
    evaluation_labels = np.array([0] * 20 + [1] * 20)
    evaluation_scores = np.array([0.4] * 20 + [0.6] * 20)

    comparison, calibrator, selected = compare_calibrators(
        train_scores,
        train_labels,
        evaluation_scores,
        evaluation_labels,
        calibration_train_row_ids=[f"train-{index}" for index in range(60)],
        evaluation_row_ids=[f"eval-{index}" for index in range(40)],
        n_bins=4,
        minimum_brier_improvement=0.01,
    )
    assert set(comparison["method"]) == {"identity", "platt", "isotonic"}
    assert comparison["selected"].sum() == 1
    assert selected == "isotonic"
    assert calibrator is not None
    identity_brier = comparison.loc[comparison["method"] == "identity", "brier_score"].iloc[0]
    selected_brier = comparison.loc[comparison["selected"], "brier_score"].iloc[0]
    assert selected_brier < identity_brier


def test_large_improvement_margin_keeps_uncalibrated_identity() -> None:
    labels = np.array([0] * 20 + [1] * 20)
    scores = np.array([0.4] * 20 + [0.6] * 20)
    comparison, calibrator, selected = compare_calibrators(
        scores,
        labels,
        scores,
        labels,
        calibration_train_row_ids=[f"train-{index}" for index in range(40)],
        evaluation_row_ids=[f"eval-{index}" for index in range(40)],
        n_bins=4,
        minimum_brier_improvement=2.0,
    )
    assert selected == "identity"
    assert calibrator is None
    assert comparison.loc[comparison["selected"], "method"].item() == "identity"


def test_comparison_rejects_cross_partition_row_overlap() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        compare_calibrators(
            [0.2, 0.8],
            [0, 1],
            [0.3, 0.7],
            [0, 1],
            calibration_train_row_ids=["a", "b"],
            evaluation_row_ids=["b", "c"],
            n_bins=2,
        )
