"""Leakage-aware calibration diagnostics for bounded development scores."""

from __future__ import annotations

import math
from typing import Any, Literal, Sequence

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

CalibrationMethod = Literal["identity", "platt", "isotonic"]


def _validated_inputs(
    y_true: Sequence[int] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
    *,
    require_both_classes: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    labels = np.asarray(y_true)
    try:
        labels_numeric = labels.astype(float)
        values = np.asarray(probabilities, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Labels and scores must be numeric.") from exc
    if labels_numeric.ndim != 1 or values.ndim != 1 or len(labels_numeric) != len(values):
        raise ValueError("Labels and scores must be one-dimensional with equal length.")
    if len(labels_numeric) == 0:
        raise ValueError("Labels and scores must not be empty.")
    if not np.isfinite(labels_numeric).all() or not set(np.unique(labels_numeric)).issubset(
        {0.0, 1.0}
    ):
        raise ValueError("Labels must contain only finite binary values 0 and 1.")
    if require_both_classes and set(np.unique(labels_numeric)) != {0.0, 1.0}:
        raise ValueError("Both classes are required for calibration analysis.")
    if not np.isfinite(values).all() or np.logical_or(values < 0.0, values > 1.0).any():
        raise ValueError("Scores must be finite and in [0, 1].")
    return labels_numeric.astype(int), values


def reliability_table(
    y_true: Sequence[int] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
    *,
    n_bins: int = 10,
    strategy: Literal["uniform", "quantile"] = "quantile",
) -> pd.DataFrame:
    """Return non-empty reliability bins with counts and calibration gaps."""
    labels, values = _validated_inputs(y_true, probabilities)
    if not isinstance(n_bins, int) or not 2 <= n_bins <= min(100, len(values)):
        raise ValueError("n_bins must be an integer between 2 and min(100, sample size).")
    if strategy not in {"uniform", "quantile"}:
        raise ValueError("strategy must be 'uniform' or 'quantile'.")

    if strategy == "uniform":
        assignments = np.minimum((values * n_bins).astype(int), n_bins - 1)
        groups = [np.flatnonzero(assignments == index) for index in range(n_bins)]
    else:
        edges = np.unique(np.quantile(values, np.linspace(0.0, 1.0, n_bins + 1)))
        if len(edges) == 1:
            groups = [np.arange(len(values))]
        else:
            assignments = np.searchsorted(edges[1:-1], values, side="right")
            groups = [
                np.flatnonzero(assignments == index) for index in range(len(edges) - 1)
            ]

    rows: list[dict[str, float | int]] = []
    for bin_index, indices in enumerate(groups):
        if len(indices) == 0:
            continue
        mean_score = float(values[indices].mean())
        observed_rate = float(labels[indices].mean())
        rows.append(
            {
                "bin": bin_index,
                "count": int(len(indices)),
                "max_score": float(values[indices].max()),
                "mean_score": mean_score,
                "min_score": float(values[indices].min()),
                "observed_rate": observed_rate,
                "absolute_gap": abs(mean_score - observed_rate),
            }
        )
    return pd.DataFrame(rows)


def evaluate_calibration(
    y_true: Sequence[int] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
    *,
    n_bins: int = 10,
    strategy: Literal["uniform", "quantile"] = "quantile",
) -> dict[str, Any]:
    """Compute Brier score, weighted ECE, MCE, and reliability records."""
    labels, values = _validated_inputs(y_true, probabilities)
    table = reliability_table(labels, values, n_bins=n_bins, strategy=strategy)
    weights = table["count"].to_numpy(dtype=float) / len(labels)
    gaps = table["absolute_gap"].to_numpy(dtype=float)
    return {
        "brier_score": float(brier_score_loss(labels, values)),
        "expected_calibration_error": float(np.sum(weights * gaps)),
        "maximum_calibration_error": float(np.max(gaps)),
        "n_bins": int(len(table)),
        "requested_bins": n_bins,
        "strategy": strategy,
        "reliability": table.to_dict(orient="records"),
    }


def fit_calibrator(
    calibration_train_scores: Sequence[float] | np.ndarray,
    calibration_train_labels: Sequence[int] | np.ndarray,
    method: Literal["platt", "isotonic"],
) -> object:
    """Fit only on a dedicated development calibration-training partition."""
    labels, values = _validated_inputs(calibration_train_labels, calibration_train_scores)
    if method == "platt":
        return LogisticRegression(random_state=42, max_iter=1_000).fit(
            values.reshape(-1, 1), labels
        )
    if method == "isotonic":
        return IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(values, labels)
    raise ValueError("method must be 'platt' or 'isotonic'.")


def apply_calibrator(calibrator: object, scores: Sequence[float] | np.ndarray) -> np.ndarray:
    """Apply a fitted supported calibrator and fail closed on invalid output."""
    values = np.asarray(scores, dtype=float)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("scores must be a non-empty finite one-dimensional array.")
    if np.logical_or(values < 0.0, values > 1.0).any():
        raise ValueError("scores must be in [0, 1].")
    if hasattr(calibrator, "predict_proba"):
        output = np.asarray(calibrator.predict_proba(values.reshape(-1, 1)), dtype=float)
        calibrated = output[:, 1]
    elif hasattr(calibrator, "predict"):
        calibrated = np.asarray(calibrator.predict(values), dtype=float).reshape(-1)
    else:
        raise ValueError("Unsupported calibrator object.")
    if calibrated.shape != values.shape or not np.isfinite(calibrated).all():
        raise ValueError("Calibrator produced malformed output.")
    if np.logical_or(calibrated < 0.0, calibrated > 1.0).any():
        raise ValueError("Calibrator output must be in [0, 1].")
    return calibrated


def compare_calibrators(
    calibration_train_scores: Sequence[float] | np.ndarray,
    calibration_train_labels: Sequence[int] | np.ndarray,
    evaluation_scores: Sequence[float] | np.ndarray,
    evaluation_labels: Sequence[int] | np.ndarray,
    *,
    calibration_train_row_ids: Sequence[str | int],
    evaluation_row_ids: Sequence[str | int],
    n_bins: int = 10,
    minimum_brier_improvement: float = 0.0,
) -> tuple[pd.DataFrame, object | None, CalibrationMethod]:
    """Fit on one development partition and compare on a distinct caller-supplied one.

    The historical held-out test must never be supplied to this function. Identity
    wins ties; calibration is selected only when it clears the declared Brier margin.
    """
    train_labels, train_scores = _validated_inputs(
        calibration_train_labels, calibration_train_scores
    )
    eval_labels, eval_scores = _validated_inputs(evaluation_labels, evaluation_scores)
    train_ids = list(calibration_train_row_ids)
    eval_ids = list(evaluation_row_ids)
    if len(train_ids) != len(train_labels) or len(eval_ids) != len(eval_labels):
        raise ValueError("Row IDs must match their calibration partition lengths.")
    if len(set(train_ids)) != len(train_ids) or len(set(eval_ids)) != len(eval_ids):
        raise ValueError("Row IDs must be unique within each calibration partition.")
    overlap = set(train_ids).intersection(eval_ids)
    if overlap:
        raise ValueError("Calibration training and evaluation row IDs must be disjoint.")
    if not math.isfinite(minimum_brier_improvement) or minimum_brier_improvement < 0.0:
        raise ValueError("minimum_brier_improvement must be finite and non-negative.")

    candidates: list[tuple[CalibrationMethod, object | None, np.ndarray]] = [
        ("identity", None, eval_scores)
    ]
    for method in ("platt", "isotonic"):
        calibrator = fit_calibrator(train_scores, train_labels, method)
        candidates.append((method, calibrator, apply_calibrator(calibrator, eval_scores)))

    rows: list[dict[str, float | int | str]] = []
    fitted: dict[CalibrationMethod, object | None] = {}
    for method, calibrator, values in candidates:
        metrics = evaluate_calibration(eval_labels, values, n_bins=n_bins)
        rows.append(
            {
                "method": method,
                "brier_score": metrics["brier_score"],
                "expected_calibration_error": metrics["expected_calibration_error"],
                "maximum_calibration_error": metrics["maximum_calibration_error"],
                "evaluation_rows": len(eval_labels),
            }
        )
        fitted[method] = calibrator
    comparison = pd.DataFrame(rows)
    preference = {"identity": 0, "platt": 1, "isotonic": 2}
    ranked = comparison.assign(preference=comparison["method"].map(preference)).sort_values(
        ["brier_score", "expected_calibration_error", "preference"],
        kind="mergesort",
    )
    best_method = ranked.iloc[0]["method"]
    identity_brier = float(
        comparison.loc[comparison["method"] == "identity", "brier_score"].iloc[0]
    )
    best_brier = float(ranked.iloc[0]["brier_score"])
    selected: CalibrationMethod = (
        best_method
        if best_method != "identity" and identity_brier - best_brier >= minimum_brier_improvement
        else "identity"
    )
    comparison["selected"] = comparison["method"] == selected
    return comparison, fitted[selected], selected
