"""Synthetic tests for locked final evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.evaluation.final_evaluation import (
    build_final_evaluation_summary,
    evaluate_locked_model,
    save_final_evaluation,
    write_final_evaluation_report,
)


def test_evaluate_locked_model_uses_fixed_threshold() -> None:
    y_true = np.array([0, 0, 1, 1])
    y_proba = np.array([0.10, 0.60, 0.40, 0.90])

    metrics = evaluate_locked_model(y_true, y_proba, threshold=0.50)

    assert metrics["true_negatives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["true_positives"] == 1
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["f1_score"] == pytest.approx(0.5)
    assert metrics["pr_auc"] is not None
    assert metrics["roc_auc"] is not None


def test_evaluate_locked_model_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        evaluate_locked_model([0, 1], [0.1, 0.9], threshold=1.5)


@pytest.mark.parametrize("invalid_score", [np.nan, np.inf, -np.inf])
def test_evaluate_locked_model_rejects_non_finite_scores(invalid_score: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        evaluate_locked_model([0, 1], [0.1, invalid_score], threshold=0.5)


def test_historical_report_avoids_unsupported_claims(tmp_path: Path) -> None:
    metrics = evaluate_locked_model([0, 0, 1, 1], [0.05, 0.2, 0.8, 0.95], 0.53)
    summary = build_final_evaluation_summary(metrics, "xgboost_baseline", 0.53)
    report = write_final_evaluation_report(summary, tmp_path / "historical.md")
    combined = (summary["threshold_selection_note"] + report.read_text(encoding="utf-8")).lower()
    forbidden = ("unbiased", "production performance", "real-world performance", "blocked", "approved", "acceptable level")
    assert not any(term in combined for term in forbidden)
    assert "historical" in combined


def test_build_summary_and_save_outputs(tmp_path: Path) -> None:
    metrics = evaluate_locked_model([0, 0, 1, 1], [0.05, 0.2, 0.8, 0.95], 0.53)
    summary = build_final_evaluation_summary(
        metrics,
        model_name="xgboost_baseline",
        threshold=0.53,
        split_name="test",
    )

    json_path = save_final_evaluation(summary, tmp_path / "final.json")
    report_path = write_final_evaluation_report(summary, tmp_path / "final.md")

    assert json_path.exists()
    assert report_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["model_name"] == "xgboost_baseline"
    assert saved["threshold"] == pytest.approx(0.53)
    assert "validation" in saved["threshold_selection_note"].lower()
    assert "Final Model Evaluation" in report_path.read_text(encoding="utf-8")
