"""Synthetic tests for Day 7 SHAP explainability helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from src.explainability.shap_explainer import (
    ExplanationCohort,
    VerifiedShapExplanation,
    build_cohort_feature_importance,
    build_explanation_cohort,
    build_shap_feature_importance,
    calculate_verified_shap_explanation,
    plot_shap_summary_bar,
    sample_explanation_data,
    save_shap_cohort_evidence,
    save_shap_outputs,
    summarize_explanation_cohort,
    write_shap_markdown_report,
)


def test_sample_explanation_data_caps_sample_size() -> None:
    X = pd.DataFrame({"a": range(20), "b": range(20, 40)})
    sample = sample_explanation_data(X, sample_size=5, random_state=42)

    assert len(sample) == 5
    assert list(sample.columns) == ["a", "b"]


def test_sample_explanation_data_rejects_empty_dataframe() -> None:
    with pytest.raises(ValueError):
        sample_explanation_data(pd.DataFrame())


def test_build_shap_feature_importance_sorts_mean_abs_values() -> None:
    shap_values = np.array([[1.0, -3.0, 0.5], [-1.0, 1.0, -0.5]])
    df = build_shap_feature_importance(shap_values, ["f1", "f2", "f3"])

    assert list(df["feature"]) == ["f2", "f1", "f3"]
    assert df.iloc[0]["mean_abs_shap_value"] == pytest.approx(2.0)


def test_build_shap_feature_importance_rejects_feature_mismatch() -> None:
    with pytest.raises(ValueError):
        build_shap_feature_importance(np.ones((3, 2)), ["only_one"])


def _verified_explanation(values: np.ndarray) -> VerifiedShapExplanation:
    reconstructed = 0.1 + values.sum(axis=1)
    return VerifiedShapExplanation(
        values=values,
        base_value=0.1,
        model_output=reconstructed.copy(),
        reconstructed_output=reconstructed,
        output_name="raw_margin_log_odds",
        max_abs_additivity_error=0.0,
    )


def test_xgboost_shap_reconstructs_declared_raw_margin() -> None:
    features = pd.DataFrame(
        {
            "a": np.tile(np.array([-2, -1, 0, 1, 2, 3], dtype=float), 6),
            "b": np.tile(np.array([0, 1, 0, 1, 0, 1], dtype=float), 6),
        }
    )
    labels = np.tile(np.array([0, 0, 0, 1, 1, 1]), 6)
    model = XGBClassifier(
        n_estimators=12,
        max_depth=2,
        learning_rate=0.2,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=1,
    ).fit(features, labels)

    explanation = calculate_verified_shap_explanation(model, features.iloc[:8])

    assert explanation.output_name == "raw_margin_log_odds"
    assert explanation.values.shape == (8, 2)
    assert explanation.max_abs_additivity_error < 1e-5
    np.testing.assert_allclose(
        explanation.reconstructed_output,
        explanation.model_output,
        atol=1e-5,
        rtol=1e-6,
    )


def test_verified_shap_rejects_an_estimator_without_verifiable_raw_margin() -> None:
    features = pd.DataFrame({"a": [-1.0, 0.0, 1.0, 2.0], "b": [0.0, 1.0, 0.0, 1.0]})
    model = LogisticRegression().fit(features, np.array([0, 0, 1, 1]))
    with pytest.raises(ValueError, match="XGBoost classifiers only"):
        calculate_verified_shap_explanation(model, features)


def test_explanation_cohort_is_disjoint_deterministic_and_reports_composition() -> None:
    features = pd.DataFrame({"a": np.arange(20), "b": np.arange(20) * -1.0})
    labels = np.array([1, 1, 0, 0, 1] + [0] * 15)
    scores = np.linspace(0.01, 0.99, 20)

    first = build_explanation_cohort(
        features, labels, scores, sample_size=12, random_state=7
    )
    second = build_explanation_cohort(
        features, labels, scores, sample_size=12, random_state=7
    )
    assert first.features.index.is_unique
    assert list(first.features.index) == list(second.features.index)
    assert set(first.cohort_names) == {
        "labelled_fraud",
        "high_raw_score",
        "representative_random",
    }

    summary = summarize_explanation_cohort(first)
    assert summary["rows"] == 12
    assert summary["labelled_fraud_rows"] >= 3
    assert summary["is_prevalence_representative"] is False
    assert sum(item["rows"] for item in summary["cohorts"].values()) == 12


def test_save_shap_outputs_plot_and_report(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "feature": ["V1", "V2"],
            "mean_abs_shap_value": [0.25, 0.10],
        }
    )

    explanation = _verified_explanation(np.array([[0.2, -0.1], [0.3, 0.2]]))
    cohort = ExplanationCohort(
        features=pd.DataFrame({"V1": [1.0, 2.0], "V2": [3.0, 4.0]}),
        labels=np.array([1, 0]),
        raw_scores=np.array([0.9, 0.2]),
        cohort_names=np.array(["labelled_fraud", "representative_random"]),
    )
    cohort_summary = summarize_explanation_cohort(cohort)
    cohort_importance = build_cohort_feature_importance(
        explanation, ["V1", "V2"], cohort.cohort_names
    )

    outputs = save_shap_outputs(df, tmp_path / "explainability")
    evidence_path = save_shap_cohort_evidence(
        explanation,
        cohort_summary,
        cohort_importance,
        tmp_path / "explainability",
    )
    second_evidence_path = save_shap_cohort_evidence(
        explanation,
        cohort_summary,
        cohort_importance,
        tmp_path / "second",
    )
    plot_path = plot_shap_summary_bar(df, tmp_path / "figures" / "shap.png")
    report_path = write_shap_markdown_report(
        df,
        tmp_path / "report.md",
        explanation=explanation,
        cohort_summary=cohort_summary,
        cohort_importance=cohort_importance,
    )

    assert outputs["csv"].exists()
    assert outputs["json"].exists()
    assert evidence_path.exists()
    assert evidence_path.read_bytes() == second_evidence_path.read_bytes()
    assert evidence_path.read_text(encoding="utf-8").endswith("\n")
    assert plot_path.exists()
    assert plot_path.stat().st_size > 0
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "raw margin (log-odds)" in report
    assert "Additivity status" in report
    assert "not prevalence-representative" in report
    assert "predicted fraud probability" not in report
