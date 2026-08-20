"""
src/evaluation/final_evaluation.py
====================================
Final locked-model evaluation for the Credit Card Fraud Detection &
Risk Scoring System.

Day 7 scope only.

This module evaluates the champion model at a fixed threshold that was
selected during Day 6 validation.  NO tuning, NO model training, and NO
threshold search happen here.  The evaluation is run exactly once on the
historical random holdout. The result is already observed and is not reused for
development decisions.

The executable runner is permanently locked. These functions remain available
for synthetic unit tests and newly named development scopes only; callers must
not overwrite the recorded historical outputs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default output paths
# ---------------------------------------------------------------------------
DEFAULT_FINAL_DIR = Path("reports/final")
DEFAULT_EVALUATION_JSON = DEFAULT_FINAL_DIR / "final_model_evaluation.json"
DEFAULT_EVALUATION_REPORT = DEFAULT_FINAL_DIR / "final_evaluation_report.md"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _to_array(x: pd.Series | np.ndarray) -> np.ndarray:
    """Convert a Series or ndarray to a plain 1-D numpy array."""
    return np.asarray(x).ravel()


def _validate_inputs(
    y_true: pd.Series | np.ndarray,
    y_proba: pd.Series | np.ndarray,
    threshold: float,
) -> None:
    """
    Validate inputs before running evaluation.

    Raises
    ------
    ValueError
        If any of the following is true:
        - Either array is empty.
        - Arrays have different lengths.
        - ``y_true`` contains values outside {0, 1}.
        - ``y_true`` does not contain both classes.
        - Any ``y_proba`` value is outside [0, 1].
        - ``threshold`` is outside [0, 1].
    TypeError
        If ``y_true`` or ``y_proba`` cannot be converted to a numeric array.
    """
    try:
        y_true_arr = _to_array(y_true)
        y_proba_arr = _to_array(y_proba).astype(float)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Could not convert inputs to numeric arrays: {exc}") from exc

    if y_true_arr.size == 0 or y_proba_arr.size == 0:
        raise ValueError("y_true and y_proba must not be empty.")

    if y_true_arr.size != y_proba_arr.size:
        raise ValueError(
            f"Length mismatch: y_true has {y_true_arr.size} elements, "
            f"y_proba has {y_proba_arr.size} elements."
        )

    unique_labels = set(y_true_arr.tolist())
    if not unique_labels.issubset({0, 1}):
        raise ValueError(
            f"y_true must contain only 0 (legitimate) and 1 (fraud). "
            f"Found labels: {sorted(unique_labels)}"
        )

    if not ({0, 1} <= unique_labels):
        raise ValueError(
            "y_true must contain both class 0 (legitimate) and class 1 (fraud). "
            f"Only found: {sorted(unique_labels)}"
        )

    if not np.isfinite(y_proba_arr).all():
        raise ValueError("y_proba must contain only finite values.")

    if np.any(y_proba_arr < 0.0) or np.any(y_proba_arr > 1.0):
        raise ValueError(
            f"y_proba values must be in [0, 1].  "
            f"Got min={y_proba_arr.min():.4f}, max={y_proba_arr.max():.4f}."
        )

    if not np.isfinite(threshold) or not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"threshold must be in [0, 1].  Got: {threshold!r}"
        )


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    """Return numerator / denominator, or None if denominator is zero."""
    if denominator == 0:
        return None
    return numerator / denominator


def _convert_for_json(obj: Any) -> Any:
    """Recursively convert numpy scalar types to native Python types."""
    if isinstance(obj, dict):
        return {k: _convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_for_json(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _fmt(value: Any, precision: int = 4) -> str:
    """Format a metric value for Markdown table display."""
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------
def evaluate_locked_model(
    y_true: pd.Series | np.ndarray,
    y_proba: pd.Series | np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """
    Evaluate a champion model at a fixed, pre-selected threshold.

    Score-based metrics (average precision, ROC-AUC) use ``y_proba`` directly so
    they reflect the full scoring range.  Label-based metrics (precision,
    recall, F1, confusion-matrix values) use ``y_proba >= threshold`` so
    they match exactly what the deployed model would do at the chosen
    operating point.

    Parameters
    ----------
    y_true : pd.Series or np.ndarray
        Ground-truth binary labels.  Must contain only 0 and 1, and must
        include both classes.
    y_proba : pd.Series or np.ndarray
        Predicted probabilities for the positive (fraud) class, in [0, 1].
    threshold : float
        Classification threshold, in [0, 1].  Must be the value chosen during
        Day 6 validation — do NOT tune this parameter here.

    Returns
    -------
    dict[str, Any]
        Flat dictionary of evaluation metrics.  All confusion-matrix counts
        are plain Python ``int``; rates are ``float`` or ``None`` when the
        denominator is zero.

    Raises
    ------
    ValueError
        If any input fails the validation checks.
    """
    _validate_inputs(y_true, y_proba, threshold)

    y_true_arr = _to_array(y_true).astype(int)
    y_proba_arr = _to_array(y_proba).astype(float)
    y_pred = (y_proba_arr >= threshold).astype(int)

    # ── probability-based metrics ──────────────────────────────────────────
    try:
        pr_auc: float | None = float(
            average_precision_score(y_true_arr, y_proba_arr)
        )
    except Exception as exc:
        logger.warning("Could not compute average precision: %s", exc)
        pr_auc = None

    try:
        roc_auc: float | None = float(
            roc_auc_score(y_true_arr, y_proba_arr)
        )
    except Exception as exc:
        logger.warning("Could not compute ROC-AUC: %s", exc)
        roc_auc = None

    # ── label-based metrics ────────────────────────────────────────────────
    precision = float(precision_score(y_true_arr, y_pred, zero_division=0))
    recall    = float(recall_score(y_true_arr, y_pred, zero_division=0))
    f1        = float(f1_score(y_true_arr, y_pred, zero_division=0))

    # ── confusion matrix ───────────────────────────────────────────────────
    tn, fp, fn, tp = confusion_matrix(
        y_true_arr, y_pred, labels=[0, 1]
    ).ravel()
    tn, fp, fn, tp = int(tn), int(fp), int(fn), int(tp)

    # ── derived rates ──────────────────────────────────────────────────────
    specificity         = _safe_ratio(tn, tn + fp)
    false_positive_rate = _safe_ratio(fp, fp + tn)
    false_negative_rate = _safe_ratio(fn, fn + tp)

    total_samples    = int(y_true_arr.size)
    total_fraud      = int(y_true_arr.sum())
    total_legitimate = total_samples - total_fraud

    return {
        "threshold":           threshold,
        "pr_auc":              pr_auc,
        "roc_auc":             roc_auc,
        "precision":           precision,
        "recall":              recall,
        "f1_score":            f1,
        "true_positives":      tp,
        "false_positives":     fp,
        "false_negatives":     fn,
        "true_negatives":      tn,
        "specificity":         specificity,
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "fraud_caught":        tp,
        "fraud_missed":        fn,
        "false_alerts":        fp,
        "total_samples":       total_samples,
        "total_fraud":         total_fraud,
        "total_legitimate":    total_legitimate,
    }


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------
def build_final_evaluation_summary(
    metrics: dict[str, Any],
    model_name: str,
    threshold: float,
    split_name: str = "test",
    threshold_source: str = "validation-selected operating point (policy metadata unavailable)",
) -> dict[str, Any]:
    """
    Wrap raw evaluation metrics into a labelled, JSON-serialisable summary.

    Parameters
    ----------
    metrics : dict[str, Any]
        Output of :func:`evaluate_locked_model`.
    model_name : str
        Canonical name of the champion model, e.g. ``"xgboost_baseline"``.
    threshold : float
        The locked threshold that was applied (for documentation purposes;
        it should already appear inside ``metrics``).
    split_name : str
        Human-readable label for the data split, e.g. ``"test"`` or
        ``"validation"``.

    Returns
    -------
    dict[str, Any]
        Complete evaluation summary.
    """
    return {
        "project": "Credit Card Fraud Detection & Risk Scoring System",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "split_name": split_name,
        "threshold_source": threshold_source,
        "threshold_selection_note": (
            "Historical observation: repository history records model and threshold "
            "selection on validation before this random held-out split was evaluated. The result "
            "has now been observed and must not be reused for tuning. Exact duplicate "
            "rows were reported in the source dataset, but cross-split overlap was "
            "not recorded, so this is not out-of-time or real-world evidence."
        ),
        **metrics,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def save_final_evaluation(
    summary: dict[str, Any],
    output_path: str | Path = DEFAULT_EVALUATION_JSON,
) -> Path:
    """
    Serialise the final evaluation summary to a JSON file.

    Parameters
    ----------
    summary : dict[str, Any]
        Output of :func:`build_final_evaluation_summary`.
    output_path : str or Path
        Destination file.  Parent directories are created automatically.

    Returns
    -------
    Path
        Resolved path to the saved JSON file.
    """
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation evidence: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clean = _convert_for_json(summary)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(clean, fh, indent=2)

    logger.info("Final evaluation JSON saved → %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def write_final_evaluation_report(
    summary: dict[str, Any],
    output_path: str | Path = DEFAULT_EVALUATION_REPORT,
) -> Path:
    """
    Write a human-readable Markdown report for the final evaluation.

    Parameters
    ----------
    summary : dict[str, Any]
        Output of :func:`build_final_evaluation_summary`.
    output_path : str or Path
        Destination ``.md`` file.  Parent directories are created
        automatically.

    Returns
    -------
    Path
        Resolved path to the saved report.

    Notes
    -----
    The report is designed to be GitHub-readable and explains *why* each
    metric was chosen, so it doubles as documentation for recruiters and
    reviewers.
    """
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite evaluation evidence: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model_name   = summary.get("model_name", "unknown")
    split_name   = summary.get("split_name", "test")
    threshold    = summary.get("threshold", "N/A")
    threshold_source = summary.get("threshold_source", "historical validation artifact")
    generated_at = summary.get("generated_at", "N/A")
    note         = summary.get("threshold_selection_note", "")

    total_samples    = summary.get("total_samples", "N/A")
    total_fraud      = summary.get("total_fraud", "N/A")
    total_legitimate = summary.get("total_legitimate", "N/A")
    tp = summary.get("true_positives",  "N/A")
    fp = summary.get("false_positives", "N/A")
    fn = summary.get("false_negatives", "N/A")
    tn = summary.get("true_negatives",  "N/A")

    # format large integers with commas where applicable
    def _ifmt(v: Any) -> str:
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)

    lines: list[str] = [
        "# Final Model Evaluation Report: Credit Card Fraud Detection",
        "",
        "## Report Metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Generated | {generated_at} |",
        f"| Champion model | `{model_name}` |",
        f"| Evaluated split | `{split_name}` |",
        f"| Locked threshold | `{threshold}` |",
        f"| Threshold source | {threshold_source} |",
        "",
        "---",
        "",
        "## Integrity Note — Threshold Selection",
        "",
        note,
        "",
        "This preserves the recorded result as historical evidence; it is not a "
        "claim about deployment or future performance.",
        "",
        "---",
        "",
        "## Dataset Summary",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Split evaluated | `{split_name}` |",
        f"| Total samples | {_ifmt(total_samples)} |",
        f"| Fraud cases | {_ifmt(total_fraud)} |",
        f"| Legitimate cases | {_ifmt(total_legitimate)} |",
        "",
        "---",
        "",
        "## Final Evaluation Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Average precision** | **{_fmt(summary.get('pr_auc'))}** |",
        f"| ROC-AUC | {_fmt(summary.get('roc_auc'))} |",
        f"| Precision | {_fmt(summary.get('precision'))} |",
        f"| Recall | {_fmt(summary.get('recall'))} |",
        f"| F1-score | {_fmt(summary.get('f1_score'))} |",
        f"| Specificity | {_fmt(summary.get('specificity'))} |",
        f"| False Positive Rate | {_fmt(summary.get('false_positive_rate'))} |",
        f"| False Negative Rate | {_fmt(summary.get('false_negative_rate'))} |",
        "",
        "---",
        "",
        "## Confusion Matrix",
        "",
        "| | Predicted Legitimate | Predicted Fraud |",
        "|---|---|---|",
        f"| **Actual Legitimate** | TN = {_ifmt(tn)} | FP = {_ifmt(fp)} |",
        f"| **Actual Fraud**      | FN = {_ifmt(fn)} | TP = {_ifmt(tp)} |",
        "",
        "### Interpretation",
        "",
        f"- **True positives:** {_ifmt(tp)} — labelled fraud rows flagged at this threshold.",
        f"- **False negatives:** {_ifmt(fn)} — labelled fraud rows not flagged.",
        f"- **False positives:** {_ifmt(fp)} — labelled legitimate rows flagged.",
        f"- **True negatives:** {_ifmt(tn)} — labelled legitimate rows not flagged.",
        "",
        "> **Decision context:** The historical threshold was selected on validation "
        "for the point estimate recall constraint recorded in its source artifact. "
        "No fraud-loss, review-cost, recovery, or authorization policy was evaluated.",
        "",
        "---",
        "",
        "## Why Average Precision Is the Primary Metric",
        "",
        f"This evaluation split contains **{(100 * total_fraud / total_samples):.4f} % fraud** "
        "when the recorded counts are available — an extreme class imbalance."
        if isinstance(total_fraud, int) and isinstance(total_samples, int) and total_samples
        else "The evaluation concerns an extremely imbalanced fraud classification problem.",
        "Under these conditions:",
        "",
        "- **Accuracy** is misleading.  A model that always predicts 'legitimate' "
        "achieves ~99.8 % accuracy while catching zero fraud.",
        "- **ROC-AUC** is influenced heavily by the large number of true negatives and "
        "can appear strong even when fraud detection is poor.",
        "- **Average precision** measures the quality of the precision–recall "
        "trade-off for the fraud class only.  It is the most meaningful single-number "
        "summary for this problem.",
        "",
        "---",
        "",
        "## Project Result Summary",
        "",
        "| Stage | Result |",
        "|---|---|",
        f"| Recorded model | `{model_name}` |",
        f"| Recorded threshold | {threshold} |",
        f"| **Final {split_name} average precision** | **{_fmt(summary.get('pr_auc'))}** |",
        f"| Final {split_name} Recall | {_fmt(summary.get('recall'))} |",
        f"| Final {split_name} Precision | {_fmt(summary.get('precision'))} |",
        f"| Final {split_name} F1-score | {_fmt(summary.get('f1_score'))} |",
        "",
        "---",
        "",
        "*Report generated automatically by `src/evaluation/final_evaluation.py`.*",
    ]

    report_text = "\n".join(lines)
    output_path.write_text(report_text, encoding="utf-8")
    logger.info("Final evaluation report saved → %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Main guard
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(
        "This module is not meant to be run directly.\n"
        "Use the orchestration script instead:\n\n"
        "    python3 -m scripts.run_final_evaluation\n"
    )
