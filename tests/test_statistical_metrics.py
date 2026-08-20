"""Deterministic uncertainty and simplicity-policy tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.evaluation.statistical_metrics import (
    classification_wilson_intervals,
    paired_average_precision_difference,
    select_with_simplicity_margin,
    wilson_interval,
)


def test_wilson_interval_contains_observed_proportion() -> None:
    interval = wilson_interval(62, 74)
    assert interval["point"] == pytest.approx(62 / 74)
    assert interval["lower"] == pytest.approx(0.738, abs=0.001)
    assert interval["upper"] == pytest.approx(0.905, abs=0.001)


@pytest.mark.parametrize(
    ("successes", "total"),
    [(-1, 10), (11, 10), (0, 0), (True, 1), (1.5, 2)],
)
def test_wilson_interval_rejects_invalid_counts(successes: object, total: object) -> None:
    with pytest.raises(ValueError):
        wilson_interval(successes, total)  # type: ignore[arg-type]


def test_classification_intervals_use_correct_denominators() -> None:
    intervals = classification_wilson_intervals(
        [0, 0, 0, 1, 1, 1],
        [0, 1, 0, 1, 0, 1],
    )
    assert intervals["precision"]["successes"] == 2  # type: ignore[index]
    assert intervals["precision"]["total"] == 3  # type: ignore[index]
    assert intervals["recall"]["successes"] == 2  # type: ignore[index]
    assert intervals["recall"]["total"] == 3  # type: ignore[index]
    assert intervals["false_positive_rate"]["successes"] == 1  # type: ignore[index]


def test_paired_bootstrap_is_reproducible_and_preserves_pairing() -> None:
    labels = np.array([0] * 40 + [1] * 10)
    simple = np.linspace(0.01, 0.95, 50)
    complex_scores = simple.copy()
    first = paired_average_precision_difference(
        labels, simple, complex_scores, n_resamples=200, random_seed=7
    )
    second = paired_average_precision_difference(
        labels, simple, complex_scores, n_resamples=200, random_seed=7
    )
    assert first == second
    assert first["point"] == pytest.approx(0.0)
    assert first["lower"] == pytest.approx(0.0)
    assert first["upper"] == pytest.approx(0.0)


def test_simplicity_margin_prefers_simple_model_when_comparable() -> None:
    decision = select_with_simplicity_margin(
        simple_model="random_forest",
        simple_metric=0.8125,
        complex_model="xgboost",
        complex_metric=0.8129,
        maximum_simple_degradation=0.005,
    )
    assert decision["selected_model"] == "random_forest"
    assert decision["selection_reason"] == "simpler_model_within_predeclared_margin"


def test_simplicity_margin_selects_complex_model_for_material_gain() -> None:
    decision = select_with_simplicity_margin(
        simple_model="simple",
        simple_metric=0.70,
        complex_model="complex",
        complex_metric=0.80,
        maximum_simple_degradation=0.01,
    )
    assert decision["selected_model"] == "complex"
