"""Validation-only threshold tuning utilities for fraud detection.

This module evaluates a fraud model's bounded decision scores across a
range of classification thresholds and selects business-relevant
operating points (best F1, recall-target, precision-target).

This module does not train models, plot anything, or use test data.
Only development-validation labels and bounded scores should be passed in.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

ArrayLike = Union[pd.Series, np.ndarray, Sequence[float]]

DEFAULT_THRESHOLDS: np.ndarray = np.round(np.arange(0.01, 1.00, 0.01), 2)


def validate_binary_inputs(y_true: ArrayLike, y_proba: ArrayLike) -> None:
    """Validate that y_true and y_proba are well-formed for threshold tuning.

    Args:
        y_true: Ground-truth binary labels (must contain only 0 and 1).
        y_proba: Predicted probabilities for the positive class.

    Raises:
        ValueError: If either input is empty, lengths mismatch, y_true
            contains values outside {0, 1}, or y_proba contains values
            outside the [0, 1] range.
    """
    y_true_arr = np.asarray(y_true)
    try:
        y_true_numeric = y_true_arr.astype(float)
        y_proba_arr = np.asarray(y_proba, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("y_true and y_proba must contain numeric values.") from exc

    if y_true_arr.size == 0 or y_proba_arr.size == 0:
        raise ValueError(
            "y_true and y_proba must not be empty. "
            f"Got y_true size={y_true_arr.size}, y_proba size={y_proba_arr.size}."
        )

    if y_true_arr.shape[0] != y_proba_arr.shape[0]:
        raise ValueError(
            "y_true and y_proba must have the same length. "
            f"Got y_true length={y_true_arr.shape[0]}, "
            f"y_proba length={y_proba_arr.shape[0]}."
        )

    if not np.isfinite(y_true_numeric).all():
        raise ValueError("y_true must not contain NaN or infinity.")

    unique_labels = set(np.unique(y_true_numeric).tolist())
    if not unique_labels.issubset({0, 1}):
        raise ValueError(
            "y_true must contain only 0 and 1 (legitimate=0, fraud=1). "
            f"Found unexpected values: {sorted(unique_labels - {0, 1})}."
        )

    if not np.isfinite(y_proba_arr).all():
        raise ValueError("y_proba must not contain NaN or infinity.")

    if (y_proba_arr < 0).any() or (y_proba_arr > 1).any():
        raise ValueError(
            "y_proba must contain values between 0 and 1 inclusive. "
            f"Found min={float(np.min(y_proba_arr))}, max={float(np.max(y_proba_arr))}."
        )


def _validate_threshold(threshold: float) -> None:
    """Validate that a single threshold value is within [0, 1].

    Args:
        threshold: Classification threshold to validate.

    Raises:
        ValueError: If threshold is not between 0 and 1 inclusive.
    """
    if not np.isfinite(float(threshold)) or not (0.0 <= float(threshold) <= 1.0):
        raise ValueError(f"threshold must be between 0 and 1. Got {threshold}.")


def calculate_threshold_metrics(
    y_true: ArrayLike,
    y_proba: ArrayLike,
    threshold: float,
) -> Dict[str, Any]:
    """Calculate fraud-aware classification metrics at a single threshold.

    Args:
        y_true: Ground-truth binary labels (0=legitimate, 1=fraud).
        y_proba: Predicted probabilities for the positive (fraud) class.
        threshold: Probability cutoff used to convert probabilities into
            binary predictions (prediction = 1 if y_proba >= threshold).

    Returns:
        Dictionary containing threshold, precision, recall, f1, tp, fp,
        fn, tn, fraud_caught, fraud_missed, false_alerts,
        predicted_frauds, and predicted_legitimate.
    """
    validate_binary_inputs(y_true, y_proba)
    _validate_threshold(threshold)

    y_true_arr = np.asarray(y_true).astype(int)
    y_proba_arr = np.asarray(y_proba).astype(float)

    y_pred = (y_proba_arr >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true_arr, y_pred, labels=[0, 1]).ravel()

    precision = precision_score(y_true_arr, y_pred, zero_division=0)
    recall = recall_score(y_true_arr, y_pred, zero_division=0)
    f1 = f1_score(y_true_arr, y_pred, zero_division=0)

    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "fraud_caught": int(tp),
        "fraud_missed": int(fn),
        "false_alerts": int(fp),
        "predicted_frauds": int(tp + fp),
        "predicted_legitimate": int(tn + fn),
    }


def build_threshold_metrics_table(
    y_true: ArrayLike,
    y_proba: ArrayLike,
    thresholds: Optional[Sequence[float]] = None,
) -> pd.DataFrame:
    """Build a metrics table across a range of classification thresholds.

    Args:
        y_true: Ground-truth binary labels (0=legitimate, 1=fraud).
        y_proba: Predicted probabilities for the positive (fraud) class.
        thresholds: Sequence of thresholds to evaluate. Defaults to
            0.01 through 0.99 in steps of 0.01.

    Returns:
        DataFrame with one row per threshold, sorted by threshold
        ascending, containing the columns produced by
        calculate_threshold_metrics.
    """
    validate_binary_inputs(y_true, y_proba)

    thresholds_to_use = (
        DEFAULT_THRESHOLDS if thresholds is None else np.asarray(list(thresholds))
    )

    if thresholds_to_use.size == 0:
        raise ValueError("thresholds must not be empty.")

    rows: List[Dict[str, Any]] = [
        calculate_threshold_metrics(y_true, y_proba, threshold)
        for threshold in thresholds_to_use
    ]

    threshold_table = pd.DataFrame(rows).sort_values("threshold").reset_index(drop=True)
    return threshold_table


def _validate_threshold_table(threshold_table: pd.DataFrame) -> None:
    """Validate that a threshold metrics table is non-empty and well-formed.

    Args:
        threshold_table: DataFrame produced by build_threshold_metrics_table.

    Raises:
        ValueError: If the table is empty or missing required columns.
    """
    if threshold_table is None or threshold_table.empty:
        raise ValueError("threshold_table must not be empty.")

    required_columns = {"threshold", "precision", "recall", "f1"}
    missing = required_columns - set(threshold_table.columns)
    if missing:
        raise ValueError(f"threshold_table is missing required columns: {sorted(missing)}.")
    try:
        values = threshold_table[list(required_columns)].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold_table metrics must be numeric.") from exc
    if not np.isfinite(values).all() or np.logical_or(values < 0.0, values > 1.0).any():
        raise ValueError("threshold_table metrics must be finite and in [0, 1].")
    if threshold_table["threshold"].duplicated().any():
        raise ValueError("threshold_table thresholds must be unique.")


def select_best_f1_threshold(threshold_table: pd.DataFrame) -> Dict[str, Any]:
    """Select the threshold row with the highest F1-score.

    Args:
        threshold_table: DataFrame produced by build_threshold_metrics_table.

    Returns:
        Dictionary representing the row with the maximum F1-score. If
        multiple thresholds tie for the highest F1, the smallest
        threshold among them is returned.
    """
    _validate_threshold_table(threshold_table)

    max_f1 = threshold_table["f1"].max()
    candidates = threshold_table[threshold_table["f1"] == max_f1]
    best_row = candidates.sort_values("threshold").iloc[0]
    return best_row.to_dict()


def select_recall_target_threshold(
    threshold_table: pd.DataFrame,
    min_recall: float = 0.80,
) -> Dict[str, Any]:
    """Select the highest-precision threshold that meets a recall target.

    Args:
        threshold_table: DataFrame produced by build_threshold_metrics_table.
        min_recall: Minimum acceptable recall. Defaults to 0.80.

    Returns:
        Dictionary representing the threshold row with the highest
        precision among rows whose recall is greater than or equal to
        min_recall.

    Raises:
        ValueError: If no threshold achieves the requested minimum recall.
    """
    _validate_threshold_table(threshold_table)
    if not np.isfinite(min_recall) or not 0.0 <= min_recall <= 1.0:
        raise ValueError("min_recall must be finite and in [0, 1].")

    eligible = threshold_table[threshold_table["recall"] >= min_recall]
    if eligible.empty:
        raise ValueError(
            f"No threshold achieves recall >= {min_recall}. "
            f"Maximum recall available is {threshold_table['recall'].max()}."
        )

    max_precision = eligible["precision"].max()
    candidates = eligible[eligible["precision"] == max_precision]
    best_row = candidates.sort_values("threshold").iloc[0]
    return best_row.to_dict()


def select_precision_target_threshold(
    threshold_table: pd.DataFrame,
    min_precision: float = 0.80,
) -> Dict[str, Any]:
    """Select the highest-recall threshold that meets a precision target.

    Args:
        threshold_table: DataFrame produced by build_threshold_metrics_table.
        min_precision: Minimum acceptable precision. Defaults to 0.80.

    Returns:
        Dictionary representing the threshold row with the highest
        recall among rows whose precision is greater than or equal to
        min_precision.

    Raises:
        ValueError: If no threshold achieves the requested minimum precision.
    """
    _validate_threshold_table(threshold_table)
    if not np.isfinite(min_precision) or not 0.0 <= min_precision <= 1.0:
        raise ValueError("min_precision must be finite and in [0, 1].")

    eligible = threshold_table[threshold_table["precision"] >= min_precision]
    if eligible.empty:
        raise ValueError(
            f"No threshold achieves precision >= {min_precision}. "
            f"Maximum precision available is {threshold_table['precision'].max()}."
        )

    max_recall = eligible["recall"].max()
    candidates = eligible[eligible["recall"] == max_recall]
    best_row = candidates.sort_values("threshold").iloc[0]
    return best_row.to_dict()


def select_false_positive_rate_target_threshold(
    threshold_table: pd.DataFrame,
    max_false_positive_rate: float,
) -> Dict[str, Any]:
    """Select the highest-recall threshold satisfying an explicit FPR cap."""
    _validate_threshold_table(threshold_table)
    if not np.isfinite(max_false_positive_rate) or not 0.0 <= max_false_positive_rate <= 1.0:
        raise ValueError("max_false_positive_rate must be finite and in [0, 1].")
    if "false_positive_rate" not in threshold_table:
        raise ValueError("threshold_table is missing required column: false_positive_rate.")

    eligible = threshold_table[threshold_table["false_positive_rate"] <= max_false_positive_rate]
    if eligible.empty:
        raise ValueError(f"No threshold achieves false_positive_rate <= {max_false_positive_rate}.")
    max_recall = eligible["recall"].max()
    candidates = eligible[eligible["recall"] == max_recall]
    # When recall ties, minimize false positives and then choose the largest
    # threshold so the policy is deterministic and operationally conservative.
    return (
        candidates.sort_values(["false_positive_rate", "threshold"], ascending=[True, False])
        .iloc[0]
        .to_dict()
    )


def _to_native_type(value: Any) -> Any:
    """Convert numpy scalar types to native Python types for JSON output.

    Args:
        value: Value that may be a numpy scalar type.

    Returns:
        The value converted to a native Python type where applicable.
    """
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def save_threshold_outputs(
    threshold_table: pd.DataFrame,
    selected_thresholds: Dict[str, Dict[str, Any]],
    output_dir: Union[str, Path],
) -> Dict[str, Path]:
    """Save the threshold metrics table and selected thresholds to disk.

    Args:
        threshold_table: DataFrame produced by build_threshold_metrics_table.
        selected_thresholds: Mapping of threshold name (e.g. "default",
            "best_f1", "recall_target") to its metrics dictionary.
        output_dir: Directory in which to save the output files. Created
            if it does not already exist.

    Returns:
        Dictionary mapping output names ("threshold_metrics_csv" and
        "selected_thresholds_json") to their saved Path objects.
    """
    _validate_threshold_table(threshold_table)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    csv_path = output_path / "threshold_metrics.csv"
    threshold_table.to_csv(csv_path, index=False)

    clean_selected_thresholds = {
        name: {key: _to_native_type(value) for key, value in metrics.items()}
        for name, metrics in selected_thresholds.items()
    }

    json_path = output_path / "selected_thresholds.json"
    with open(json_path, "w", encoding="utf-8") as json_file:
        json.dump(clean_selected_thresholds, json_file, indent=2)

    return {
        "threshold_metrics_csv": csv_path,
        "selected_thresholds_json": json_path,
    }


if __name__ == "__main__":
    print(
        "This module is intended to be used by "
        "scripts/run_day6_threshold_tuning.py"
    )
