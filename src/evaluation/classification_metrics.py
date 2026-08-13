"""Fraud-aware classification metrics for baseline model validation.

This module calculates and persists evaluation metrics for the Credit
Card Fraud Detection & Risk Scoring System. Because the fraud class is
extremely rare, accuracy alone is misleading: this module emphasizes
precision, recall, F1-score, ROC-AUC, average precision, and confusion matrix
breakdowns instead.

No threshold tuning, curve plotting, or test-set evaluation is performed
in this module.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

POSITIVE_LABEL: int = 1
NEGATIVE_LABEL: int = 0
DEFAULT_METRICS_DIR: Path = Path("reports/metrics")


def validate_evaluation_inputs(
    y_true: Union[pd.Series, np.ndarray],
    y_pred: Union[pd.Series, np.ndarray],
    y_proba: Optional[Union[pd.Series, np.ndarray]] = None,
) -> None:
    """Validate inputs before calculating classification metrics.

    Args:
        y_true: Ground truth binary labels (0 or 1).
        y_pred: Predicted binary labels (0 or 1).
        y_proba: Optional predicted scores/probabilities for the positive
            class.

    Raises:
        ValueError: If any validation check fails.
    """
    y_true_array = np.asarray(y_true)
    y_pred_array = np.asarray(y_pred)

    if y_true_array.ndim != 1 or y_pred_array.ndim != 1:
        raise ValueError("y_true and y_pred must be one-dimensional.")
    try:
        y_true_numeric = y_true_array.astype(float)
        y_pred_numeric = y_pred_array.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("y_true and y_pred must contain numeric values.") from exc
    if not np.isfinite(y_true_numeric).all() or not np.isfinite(y_pred_numeric).all():
        raise ValueError("y_true and y_pred must not contain NaN or infinity.")

    if y_true_array.size == 0:
        raise ValueError("y_true is empty. Cannot evaluate with no data.")

    if y_pred_array.size == 0:
        raise ValueError("y_pred is empty. Cannot evaluate with no data.")

    if len(y_true_array) != len(y_pred_array):
        raise ValueError(
            f"y_true has {len(y_true_array)} values but y_pred has "
            f"{len(y_pred_array)} values. They must match."
        )

    true_labels = set(np.unique(y_true_array).tolist())
    if not true_labels.issubset({NEGATIVE_LABEL, POSITIVE_LABEL}):
        raise ValueError(
            f"y_true must contain only {NEGATIVE_LABEL} and {POSITIVE_LABEL}, "
            f"but found: {true_labels}"
        )

    pred_labels = set(np.unique(y_pred_array).tolist())
    if not pred_labels.issubset({NEGATIVE_LABEL, POSITIVE_LABEL}):
        raise ValueError(
            f"y_pred must contain only {NEGATIVE_LABEL} and {POSITIVE_LABEL}, "
            f"but found: {pred_labels}"
        )

    if len(true_labels) < 2:
        raise ValueError(
            "y_true must contain both classes "
            f"({NEGATIVE_LABEL} and {POSITIVE_LABEL}), but only found: "
            f"{true_labels}"
        )

    if y_proba is not None:
        try:
            y_proba_array = np.asarray(y_proba, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("y_proba must contain numeric values.") from exc

        if len(y_proba_array) != len(y_true_array):
            raise ValueError(
                f"y_proba has {len(y_proba_array)} values but y_true has "
                f"{len(y_true_array)} values. They must match."
            )

        if y_proba_array.ndim != 1:
            raise ValueError("y_proba must be one-dimensional.")
        if not np.isfinite(y_proba_array).all():
            raise ValueError("y_proba must not contain NaN or infinity.")


def get_positive_class_scores(model: Any, X: pd.DataFrame) -> np.ndarray:
    """Extract scores for the positive (fraud) class from a fitted model.

    Prefers predicted probabilities when available, falls back to
    decision function scores, and falls back to predicted labels as a
    last resort.

    Args:
        model: A fitted scikit-learn-compatible classifier.
        X: Feature matrix to score.

    Returns:
        A 1D numpy array of scores for the positive class.
    """
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(X)
        positive_class_index = 1 if probabilities.shape[1] > 1 else 0
        scores = probabilities[:, positive_class_index]
    elif hasattr(model, "decision_function"):
        scores = model.decision_function(X)
    else:
        scores = model.predict(X)

    return np.asarray(scores).reshape(-1)


def calculate_binary_classification_metrics(
    y_true: Union[pd.Series, np.ndarray],
    y_pred: Union[pd.Series, np.ndarray],
    y_proba: Optional[Union[pd.Series, np.ndarray]] = None,
) -> Dict[str, Any]:
    """Calculate fraud-aware binary classification metrics.

    Args:
        y_true: Ground truth binary labels (0 or 1).
        y_pred: Predicted binary labels (0 or 1).
        y_proba: Optional predicted scores/probabilities for the positive
            class, used to calculate ROC-AUC and PR-AUC.

    Returns:
        A dictionary containing:
        - accuracy
        - precision
        - recall
        - f1_score
        - roc_auc
        - average_precision (with legacy pr_auc compatibility alias)
        - confusion_matrix
        - true_negatives
        - false_positives
        - false_negatives
        - true_positives
        - fraud_detection_note
    """
    validate_evaluation_inputs(y_true, y_pred, y_proba)

    y_true_array = np.asarray(y_true)
    y_pred_array = np.asarray(y_pred)

    accuracy = accuracy_score(y_true_array, y_pred_array)
    precision = precision_score(y_true_array, y_pred_array, zero_division=0)
    recall = recall_score(y_true_array, y_pred_array, zero_division=0)
    f1 = f1_score(y_true_array, y_pred_array, zero_division=0)

    roc_auc: Optional[float] = None
    average_precision: Optional[float] = None
    if y_proba is not None:
        y_proba_array = np.asarray(y_proba)
        try:
            roc_auc = roc_auc_score(y_true_array, y_proba_array)
        except ValueError:
            roc_auc = None
        try:
            average_precision = average_precision_score(y_true_array, y_proba_array)
        except ValueError:
            average_precision = None

    cm = confusion_matrix(
        y_true_array, y_pred_array, labels=[NEGATIVE_LABEL, POSITIVE_LABEL]
    )
    true_negatives, false_positives, false_negatives, true_positives = cm.ravel()

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1_score": float(f1),
        "roc_auc": float(roc_auc) if roc_auc is not None else None,
        "average_precision": (
            float(average_precision) if average_precision is not None else None
        ),
        # Compatibility alias for historical artifacts. The value has always
        # been sklearn average_precision_score, not trapezoidal PR-curve area.
        "pr_auc": float(average_precision) if average_precision is not None else None,
        "confusion_matrix": cm.tolist(),
        "true_negatives": int(true_negatives),
        "false_positives": int(false_positives),
        "false_negatives": int(false_negatives),
        "true_positives": int(true_positives),
        "fraud_detection_note": (
            "Accuracy can look high even when fraud detection is poor "
            "because legitimate transactions vastly outnumber fraud. "
            "Prioritize average precision, recall, and precision over accuracy when "
            "judging fraud detection performance."
        ),
    }


def evaluate_model(model: Any, X_val: pd.DataFrame, y_val: pd.Series) -> Dict[str, Any]:
    """Evaluate a single fitted model on the validation set.

    Args:
        model: A fitted scikit-learn-compatible classifier.
        X_val: Validation feature matrix.
        y_val: Validation target vector.

    Returns:
        A dictionary of classification metrics for this model.
    """
    y_pred = model.predict(X_val)
    y_proba = get_positive_class_scores(model, X_val)
    return calculate_binary_classification_metrics(y_val, y_pred, y_proba)


def evaluate_models(
    models: Dict[str, Any],
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> Dict[str, Dict[str, Any]]:
    """Evaluate multiple fitted models on the validation set.

    Args:
        models: A dictionary mapping model names to fitted model instances.
        X_val: Validation feature matrix.
        y_val: Validation target vector.

    Returns:
        A dictionary mapping each model name to its metrics dictionary.
    """
    all_metrics: Dict[str, Dict[str, Any]] = {}
    for model_name, model in models.items():
        all_metrics[model_name] = evaluate_model(model, X_val, y_val)
    return all_metrics


def metrics_to_dataframe(all_metrics: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    """Convert a dictionary of model metrics into a comparison DataFrame.

    Args:
        all_metrics: A dictionary mapping model names to metrics dictionaries.

    Returns:
        A pandas DataFrame with one row per model and columns:
        model_name, accuracy, precision, recall, f1_score, roc_auc,
        pr_auc, true_negatives, false_positives, false_negatives,
        true_positives.
    """
    rows = []
    for model_name, metrics in all_metrics.items():
        rows.append(
            {
                "model_name": model_name,
                "accuracy": metrics.get("accuracy"),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "f1_score": metrics.get("f1_score"),
                "roc_auc": metrics.get("roc_auc"),
                "pr_auc": metrics.get("pr_auc"),
                "true_negatives": metrics.get("true_negatives"),
                "false_positives": metrics.get("false_positives"),
                "false_negatives": metrics.get("false_negatives"),
                "true_positives": metrics.get("true_positives"),
            }
        )

    columns = [
        "model_name",
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
        "pr_auc",
        "true_negatives",
        "false_positives",
        "false_negatives",
        "true_positives",
    ]
    return pd.DataFrame(rows, columns=columns)


def _convert_to_native_types(value: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON output.

    Args:
        value: Any value that may contain numpy types.

    Returns:
        The value converted to native Python types where applicable.
    """
    if isinstance(value, dict):
        return {key: _convert_to_native_types(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert_to_native_types(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def save_metrics_json(
    all_metrics: Dict[str, Dict[str, Any]],
    output_path: Union[str, Path] = DEFAULT_METRICS_DIR / "day4_baseline_metrics.json",
) -> Path:
    """Save all model metrics to a JSON file.

    Args:
        all_metrics: A dictionary mapping model names to metrics dictionaries.
        output_path: Destination path for the JSON file.

    Returns:
        The path where the metrics were saved.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    native_metrics = _convert_to_native_types(all_metrics)

    with open(output_path, "w", encoding="utf-8") as json_file:
        json.dump(native_metrics, json_file, indent=2)

    return output_path


def save_metrics_csv(
    all_metrics: Dict[str, Dict[str, Any]],
    output_path: Union[str, Path] = DEFAULT_METRICS_DIR / "day4_baseline_metrics.csv",
) -> Path:
    """Save a model comparison table of metrics to a CSV file.

    Args:
        all_metrics: A dictionary mapping model names to metrics dictionaries.
        output_path: Destination path for the CSV file.

    Returns:
        The path where the metrics were saved.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics_df = metrics_to_dataframe(all_metrics)
    metrics_df.to_csv(output_path, index=False)

    return output_path


def find_best_model_by_pr_auc(all_metrics: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Find the model with the highest PR-AUC score.

    Args:
        all_metrics: A dictionary mapping model names to metrics dictionaries.

    Returns:
        The name of the model with the highest valid PR-AUC, or None if no
        model has a valid (non-None) PR-AUC value.
    """
    best_model_name: Optional[str] = None
    best_pr_auc: Optional[float] = None

    for model_name, metrics in all_metrics.items():
        pr_auc = metrics.get("pr_auc")
        if pr_auc is None:
            continue
        if best_pr_auc is None or pr_auc > best_pr_auc:
            best_pr_auc = pr_auc
            best_model_name = model_name

    return best_model_name
