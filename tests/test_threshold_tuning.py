"""Tests for src/evaluation/threshold_tuning.py.

These tests use small, deterministic synthetic arrays only. They do not
require the real Kaggle dataset, the real trained model artifact, or any
test-set data.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.evaluation.threshold_tuning import (  # noqa: E402
    build_threshold_metrics_table,
    calculate_threshold_metrics,
    save_threshold_outputs,
    select_best_f1_threshold,
    select_false_positive_rate_target_threshold,
    select_recall_target_threshold,
    validate_binary_inputs,
)


# ---------------------------------------------------------------------------
# validate_binary_inputs
# ---------------------------------------------------------------------------


def test_validate_binary_inputs_accepts_valid_inputs() -> None:
    """Valid binary labels and probabilities should not raise."""
    y_true = [0, 1, 0, 1]
    y_proba = [0.1, 0.9, 0.2, 0.8]

    validate_binary_inputs(y_true, y_proba)


def test_validate_binary_inputs_rejects_empty_input() -> None:
    """Empty y_true/y_proba arrays should raise a clear ValueError."""
    with pytest.raises(ValueError):
        validate_binary_inputs([], [])


def test_validate_binary_inputs_rejects_length_mismatch() -> None:
    """Mismatched lengths between y_true and y_proba should raise."""
    y_true = [0, 1, 0]
    y_proba = [0.1, 0.9]

    with pytest.raises(ValueError):
        validate_binary_inputs(y_true, y_proba)


def test_validate_binary_inputs_rejects_invalid_labels() -> None:
    """Labels outside {0, 1} should raise a clear ValueError."""
    y_true = [0, 1, 2]
    y_proba = [0.1, 0.5, 0.9]

    with pytest.raises(ValueError):
        validate_binary_inputs(y_true, y_proba)


def test_validate_binary_inputs_rejects_probability_below_zero() -> None:
    """Probabilities below 0 should raise a clear ValueError."""
    y_true = [0, 1]
    y_proba = [-0.1, 0.9]

    with pytest.raises(ValueError):
        validate_binary_inputs(y_true, y_proba)


def test_validate_binary_inputs_rejects_probability_above_one() -> None:
    """Probabilities above 1 should raise a clear ValueError."""
    y_true = [0, 1]
    y_proba = [0.1, 1.2]

    with pytest.raises(ValueError):
        validate_binary_inputs(y_true, y_proba)


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_validate_binary_inputs_rejects_non_finite_scores(invalid: float) -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        validate_binary_inputs([0, 1], [0.1, invalid])


# ---------------------------------------------------------------------------
# calculate_threshold_metrics
# ---------------------------------------------------------------------------


def test_calculate_threshold_metrics_confusion_values_are_correct() -> None:
    """TP, FP, FN, TN should be calculated correctly at a fixed threshold."""
    y_true = [0, 0, 1, 1]
    y_proba = [0.1, 0.6, 0.4, 0.9]
    threshold = 0.5

    # Predictions at threshold 0.5: [0, 1, 0, 1]
    # Sample 1 (true=0, pred=0) -> TN
    # Sample 2 (true=0, pred=1) -> FP
    # Sample 3 (true=1, pred=0) -> FN
    # Sample 4 (true=1, pred=1) -> TP
    metrics = calculate_threshold_metrics(y_true, y_proba, threshold)

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["tn"] == 1
    assert metrics["fraud_caught"] == 1
    assert metrics["fraud_missed"] == 1
    assert metrics["false_alerts"] == 1
    assert metrics["predicted_frauds"] == 2
    assert metrics["predicted_legitimate"] == 2


def test_calculate_threshold_metrics_precision_recall_f1_are_correct() -> None:
    """Precision, recall, and F1 should match the expected values."""
    y_true = [0, 0, 1, 1]
    y_proba = [0.1, 0.6, 0.4, 0.9]
    threshold = 0.5

    metrics = calculate_threshold_metrics(y_true, y_proba, threshold)

    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)
    assert metrics["false_positive_rate"] == pytest.approx(0.5)
    assert metrics["threshold"] == pytest.approx(0.5)


def test_calculate_threshold_metrics_perfect_predictions() -> None:
    """A perfectly separated dataset should yield full precision and recall."""
    y_true = [0, 0, 1, 1]
    y_proba = [0.05, 0.10, 0.90, 0.95]
    threshold = 0.5

    metrics = calculate_threshold_metrics(y_true, y_proba, threshold)

    assert metrics["tp"] == 2
    assert metrics["fp"] == 0
    assert metrics["fn"] == 0
    assert metrics["tn"] == 2
    assert metrics["precision"] == pytest.approx(1.0)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["f1"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# build_threshold_metrics_table
# ---------------------------------------------------------------------------


def test_build_threshold_metrics_table_creates_one_row_per_threshold() -> None:
    """The table should contain exactly one row per provided threshold."""
    y_true = [0, 0, 1, 1, 0, 1]
    y_proba = [0.05, 0.30, 0.60, 0.90, 0.40, 0.55]
    thresholds = [0.2, 0.5, 0.8]

    table = build_threshold_metrics_table(y_true, y_proba, thresholds=thresholds)

    assert len(table) == len(thresholds)
    assert sorted(table["threshold"].round(2).tolist()) == sorted(thresholds)


def test_build_threshold_metrics_table_uses_default_thresholds() -> None:
    """With no thresholds provided, defaults from 0.01 to 0.99 should be used."""
    y_true = [0, 0, 1, 1, 0, 1]
    y_proba = [0.05, 0.30, 0.60, 0.90, 0.40, 0.55]

    table = build_threshold_metrics_table(y_true, y_proba)

    assert len(table) == 99
    assert table["threshold"].min() == pytest.approx(0.01)
    assert table["threshold"].max() == pytest.approx(0.99)
    # The table should be sorted ascending by threshold.
    assert table["threshold"].is_monotonic_increasing


# ---------------------------------------------------------------------------
# select_best_f1_threshold
# ---------------------------------------------------------------------------


def test_select_best_f1_threshold_returns_max_f1_row() -> None:
    """The row with the highest F1-score should be returned."""
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.1, 0.2, 0.3],
            "precision": [0.5, 0.6, 0.4],
            "recall": [0.5, 0.8, 0.9],
            "f1": [0.5, 0.7, 0.3],
        }
    )

    best = select_best_f1_threshold(threshold_table)

    assert best["threshold"] == pytest.approx(0.2)
    assert best["f1"] == pytest.approx(0.7)


def test_select_best_f1_threshold_breaks_ties_with_smallest_threshold() -> None:
    """When multiple thresholds tie on F1, the smallest threshold wins."""
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.3, 0.1, 0.2],
            "precision": [0.5, 0.5, 0.5],
            "recall": [0.5, 0.5, 0.5],
            "f1": [0.6, 0.6, 0.4],
        }
    )

    best = select_best_f1_threshold(threshold_table)

    assert best["threshold"] == pytest.approx(0.1)
    assert best["f1"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# select_recall_target_threshold
# ---------------------------------------------------------------------------


def test_select_recall_target_threshold_returns_highest_precision_meeting_recall() -> None:
    """The eligible threshold with the highest precision should be returned."""
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.1, 0.2, 0.3, 0.4],
            "precision": [0.90, 0.80, 0.95, 0.99],
            "recall": [0.95, 0.85, 0.81, 0.50],
            "f1": [0.92, 0.82, 0.87, 0.66],
        }
    )

    result = select_recall_target_threshold(threshold_table, min_recall=0.80)

    # Eligible rows (recall >= 0.80): thresholds 0.1, 0.2, 0.3
    # Highest precision among those is 0.95 at threshold 0.3.
    assert result["threshold"] == pytest.approx(0.3)
    assert result["precision"] == pytest.approx(0.95)
    assert result["recall"] >= 0.80


def test_select_recall_target_threshold_raises_error_when_unmet() -> None:
    """A clear ValueError should be raised if no threshold meets min_recall."""
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.5, 0.6, 0.7],
            "precision": [0.9, 0.95, 0.99],
            "recall": [0.30, 0.20, 0.10],
            "f1": [0.45, 0.33, 0.18],
        }
    )

    with pytest.raises(ValueError):
        select_recall_target_threshold(threshold_table, min_recall=0.80)


def test_select_fpr_target_returns_highest_recall_under_cap() -> None:
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.2, 0.4, 0.6],
            "precision": [0.2, 0.6, 0.9],
            "recall": [1.0, 0.8, 0.5],
            "f1": [0.3, 0.7, 0.6],
            "false_positive_rate": [0.2, 0.01, 0.001],
        }
    )
    selected = select_false_positive_rate_target_threshold(
        threshold_table, max_false_positive_rate=0.02
    )
    assert selected["threshold"] == pytest.approx(0.4)
    assert selected["recall"] == pytest.approx(0.8)


def test_threshold_selection_rejects_non_finite_metrics() -> None:
    threshold_table = pd.DataFrame(
        {"threshold": [0.5], "precision": [0.5], "recall": [math.nan], "f1": [0.5]}
    )
    with pytest.raises(ValueError, match="finite"):
        select_best_f1_threshold(threshold_table)


# ---------------------------------------------------------------------------
# save_threshold_outputs
# ---------------------------------------------------------------------------


def test_save_threshold_outputs_writes_csv_and_json(tmp_path: Path) -> None:
    """save_threshold_outputs should write both expected output files."""
    threshold_table = pd.DataFrame(
        {
            "threshold": [0.1, 0.5, 0.9],
            "precision": [0.4, 0.7, 0.95],
            "recall": [0.9, 0.6, 0.2],
            "f1": [0.55, 0.65, 0.33],
        }
    )
    selected_thresholds = {
        "default": {"threshold": 0.5, "precision": 0.7, "recall": 0.6, "f1": 0.65},
        "best_f1": {"threshold": 0.5, "precision": 0.7, "recall": 0.6, "f1": 0.65},
    }

    output_paths = save_threshold_outputs(threshold_table, selected_thresholds, tmp_path)

    csv_path = output_paths["threshold_metrics_csv"]
    json_path = output_paths["selected_thresholds_json"]

    assert csv_path.exists()
    assert json_path.exists()

    saved_table = pd.read_csv(csv_path)
    assert len(saved_table) == len(threshold_table)

    with open(json_path, "r", encoding="utf-8") as json_file:
        saved_selected = json.load(json_file)

    assert "default" in saved_selected
    assert "best_f1" in saved_selected
    assert saved_selected["default"]["threshold"] == pytest.approx(0.5)
