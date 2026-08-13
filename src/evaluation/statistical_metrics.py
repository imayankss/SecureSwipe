"""Uncertainty utilities for rare-event binary classification development data."""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Sequence

import numpy as np
from sklearn.metrics import average_precision_score


def _binary_vector(values: Sequence[int] | np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array.")
    try:
        numeric = array.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not np.isfinite(numeric).all() or not set(np.unique(numeric)).issubset({0.0, 1.0}):
        raise ValueError(f"{name} must contain only finite binary values 0 and 1.")
    return numeric.astype(int)


def _bounded_scores(values: Sequence[float] | np.ndarray, expected_length: int) -> np.ndarray:
    try:
        scores = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("scores must be numeric.") from exc
    if scores.ndim != 1 or len(scores) != expected_length:
        raise ValueError("scores must be one-dimensional and match y_true length.")
    if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
        raise ValueError("scores must be finite and in [0, 1].")
    return scores


def wilson_interval(
    successes: int,
    total: int,
    confidence_level: float = 0.95,
) -> dict[str, float | int]:
    """Return a Wilson binomial interval without a fragile normal approximation."""
    if isinstance(successes, bool) or isinstance(total, bool):
        raise ValueError("successes and total must be integer counts.")
    if not isinstance(successes, (int, np.integer)) or not isinstance(total, (int, np.integer)):
        raise ValueError("successes and total must be integer counts.")
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("Require total > 0 and 0 <= successes <= total.")
    if not math.isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be finite and strictly between 0 and 1.")

    z = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return {
        "confidence_level": confidence_level,
        "lower": max(0.0, center - margin),
        "point": proportion,
        "successes": int(successes),
        "total": int(total),
        "upper": min(1.0, center + margin),
    }


def classification_wilson_intervals(
    y_true: Sequence[int] | np.ndarray,
    y_pred: Sequence[int] | np.ndarray,
    confidence_level: float = 0.95,
) -> dict[str, dict[str, float | int] | None]:
    """Compute precision, recall, and FPR intervals from one fixed operating point."""
    truth = _binary_vector(y_true, "y_true")
    predictions = _binary_vector(y_pred, "y_pred")
    if len(truth) != len(predictions):
        raise ValueError("y_true and y_pred lengths must match.")
    tp = int(np.logical_and(truth == 1, predictions == 1).sum())
    fp = int(np.logical_and(truth == 0, predictions == 1).sum())
    fn = int(np.logical_and(truth == 1, predictions == 0).sum())
    tn = int(np.logical_and(truth == 0, predictions == 0).sum())
    return {
        "precision": wilson_interval(tp, tp + fp, confidence_level) if tp + fp else None,
        "recall": wilson_interval(tp, tp + fn, confidence_level) if tp + fn else None,
        "false_positive_rate": (
            wilson_interval(fp, fp + tn, confidence_level) if fp + tn else None
        ),
    }


def paired_average_precision_difference(
    y_true: Sequence[int] | np.ndarray,
    simple_scores: Sequence[float] | np.ndarray,
    complex_scores: Sequence[float] | np.ndarray,
    *,
    confidence_level: float = 0.95,
    n_resamples: int = 2_000,
    random_seed: int = 42,
) -> dict[str, float | int | str]:
    """Stratified paired bootstrap CI for complex AP minus simple-model AP."""
    truth = _binary_vector(y_true, "y_true")
    if set(np.unique(truth)) != {0, 1}:
        raise ValueError("y_true must contain both classes for average precision.")
    simple = _bounded_scores(simple_scores, len(truth))
    complex_values = _bounded_scores(complex_scores, len(truth))
    if not isinstance(n_resamples, int) or n_resamples < 100:
        raise ValueError("n_resamples must be an integer >= 100.")
    if not math.isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be finite and strictly between 0 and 1.")

    positive_indices = np.flatnonzero(truth == 1)
    negative_indices = np.flatnonzero(truth == 0)
    rng = np.random.default_rng(random_seed)
    differences = np.empty(n_resamples, dtype=float)
    for index in range(n_resamples):
        sampled = np.concatenate(
            [
                rng.choice(negative_indices, size=len(negative_indices), replace=True),
                rng.choice(positive_indices, size=len(positive_indices), replace=True),
            ]
        )
        sampled_truth = truth[sampled]
        differences[index] = average_precision_score(
            sampled_truth, complex_values[sampled]
        ) - average_precision_score(sampled_truth, simple[sampled])

    alpha = 1.0 - confidence_level
    return {
        "confidence_level": confidence_level,
        "lower": float(np.quantile(differences, alpha / 2.0)),
        "metric": "average_precision_difference_complex_minus_simple",
        "n_resamples": n_resamples,
        "point": float(
            average_precision_score(truth, complex_values) - average_precision_score(truth, simple)
        ),
        "random_seed": random_seed,
        "upper": float(np.quantile(differences, 1.0 - alpha / 2.0)),
    }


def select_with_simplicity_margin(
    *,
    simple_model: str,
    simple_metric: float,
    complex_model: str,
    complex_metric: float,
    maximum_simple_degradation: float = 0.005,
) -> dict[str, float | str]:
    """Prefer the simpler model unless its metric loses more than the declared margin."""
    values = (simple_metric, complex_metric, maximum_simple_degradation)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Metrics and margin must be finite.")
    if not simple_model.strip() or not complex_model.strip():
        raise ValueError("Model names must not be empty.")
    if not 0.0 <= simple_metric <= 1.0 or not 0.0 <= complex_metric <= 1.0:
        raise ValueError("Metrics must be in [0, 1].")
    if not 0.0 <= maximum_simple_degradation <= 1.0:
        raise ValueError("maximum_simple_degradation must be in [0, 1].")
    difference = complex_metric - simple_metric
    selected = simple_model if difference <= maximum_simple_degradation else complex_model
    return {
        "complex_minus_simple": difference,
        "maximum_simple_degradation": maximum_simple_degradation,
        "metric": "average_precision",
        "selected_model": selected,
        "selection_reason": (
            "simpler_model_within_predeclared_margin"
            if selected == simple_model
            else "complex_model_exceeds_predeclared_margin"
        ),
    }
