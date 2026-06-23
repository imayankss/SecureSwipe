"""Day 4 tests for the Credit Card Fraud Detection & Risk Scoring System.

These tests validate baseline model creation/training/saving and
fraud-aware classification metrics calculation. All tests use
synthetic, deterministic pandas DataFrames -- the real Kaggle dataset
is never required.

Run from the repository root:

    pytest tests/test_day4_baseline_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

# Ensure the project root is importable when tests are run directly or
# from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.baseline_models import (  # noqa: E402
    create_dummy_baseline,
    create_logistic_regression_baseline,
    create_random_forest_baseline,
    get_baseline_models,
    get_model_summary,
    load_model,
    save_model,
    save_models,
    train_baseline_models,
    train_model,
    validate_training_data,
)
from src.evaluation.classification_metrics import (  # noqa: E402
    calculate_binary_classification_metrics,
    evaluate_model,
    evaluate_models,
    find_best_model_by_pr_auc,
    get_positive_class_scores,
    metrics_to_dataframe,
    validate_evaluation_inputs,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

RANDOM_SEED = 42
N_FEATURES = 30
FRAUD_RATIO = 0.10


def _make_synthetic_dataset(
    n_rows: int, n_features: int, fraud_ratio: float, seed: int
) -> tuple[pd.DataFrame, pd.Series]:
    """Build a deterministic synthetic feature/target dataset.

    Fraud rows are shifted away from the legitimate rows so that the
    classes are mildly separable, which keeps metrics such as PR-AUC
    well-defined and stable across test runs.
    """
    rng = np.random.RandomState(seed)
    X = rng.normal(loc=0.0, scale=1.0, size=(n_rows, n_features))

    n_fraud = max(2, int(round(n_rows * fraud_ratio)))
    y = np.zeros(n_rows, dtype=int)
    fraud_idx = rng.choice(n_rows, size=n_fraud, replace=False)
    y[fraud_idx] = 1

    # Shift fraud rows so the classes are mildly separable.
    X[fraud_idx] += 1.5

    columns = [f"V{i}" for i in range(1, n_features + 1)]
    X_df = pd.DataFrame(X, columns=columns)
    y_series = pd.Series(y, name="Class")
    return X_df, y_series


@pytest.fixture
def synthetic_processed_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Return deterministic synthetic (X_train, y_train, X_val, y_val).

    - 300 training rows, 120 validation rows.
    - 30 numeric features.
    - Binary target with both classes present.
    - Roughly 10% fraud in each split for stable metrics.
    """
    X_train, y_train = _make_synthetic_dataset(
        n_rows=300, n_features=N_FEATURES, fraud_ratio=FRAUD_RATIO, seed=RANDOM_SEED
    )
    X_val, y_val = _make_synthetic_dataset(
        n_rows=120, n_features=N_FEATURES, fraud_ratio=FRAUD_RATIO, seed=RANDOM_SEED + 1
    )
    return X_train, y_train, X_val, y_val


# ---------------------------------------------------------------------------
# Model factory tests
# ---------------------------------------------------------------------------


def test_create_dummy_baseline_returns_dummy_classifier() -> None:
    model = create_dummy_baseline()
    assert isinstance(model, DummyClassifier)
    assert model.strategy == "most_frequent"


def test_create_logistic_regression_baseline_uses_balanced_class_weight() -> None:
    model = create_logistic_regression_baseline()
    assert isinstance(model, LogisticRegression)
    assert model.class_weight == "balanced"


def test_create_random_forest_baseline_uses_balanced_class_weight() -> None:
    model = create_random_forest_baseline()
    assert isinstance(model, RandomForestClassifier)
    assert model.class_weight == "balanced"


def test_get_baseline_models_returns_expected_models() -> None:
    models = get_baseline_models()
    expected_keys = {"dummy_baseline", "logistic_regression", "random_forest"}
    assert set(models.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Training data validation tests
# ---------------------------------------------------------------------------


def test_validate_training_data_accepts_valid_data(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    # Should not raise for valid, well-formed training data.
    validate_training_data(X_train, y_train)


def test_validate_training_data_rejects_empty_X() -> None:
    empty_X = pd.DataFrame(columns=[f"V{i}" for i in range(1, N_FEATURES + 1)])
    empty_y = pd.Series([], dtype=int, name="Class")
    with pytest.raises(ValueError):
        validate_training_data(empty_X, empty_y)


def test_validate_training_data_rejects_mismatched_lengths(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    mismatched_y = y_train.iloc[:-1]
    with pytest.raises(ValueError):
        validate_training_data(X_train, mismatched_y)


def test_validate_training_data_rejects_class_column_leakage(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    leaked_X = X_train.copy()
    leaked_X["Class"] = y_train.values
    with pytest.raises(ValueError):
        validate_training_data(leaked_X, y_train)


def test_validate_training_data_rejects_single_class_target(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    single_class_y = pd.Series(np.zeros(len(y_train), dtype=int), name="Class")
    with pytest.raises(ValueError):
        validate_training_data(X_train, single_class_y)


def test_validate_training_data_rejects_missing_values_in_X(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    X_with_nan = X_train.copy()
    X_with_nan.iloc[0, 0] = np.nan
    with pytest.raises(ValueError):
        validate_training_data(X_with_nan, y_train)


# ---------------------------------------------------------------------------
# Model training tests
# ---------------------------------------------------------------------------


def test_train_model_returns_fitted_model(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    model = create_logistic_regression_baseline()

    fitted_model = train_model(model, X_train, y_train)

    assert hasattr(fitted_model, "predict")
    predictions = fitted_model.predict(X_train)
    assert len(predictions) == len(X_train)


def test_train_baseline_models_trains_all_models(synthetic_processed_data) -> None:
    X_train, y_train, X_val, _ = synthetic_processed_data

    models = train_baseline_models(X_train, y_train)

    expected_keys = {"dummy_baseline", "logistic_regression", "random_forest"}
    assert set(models.keys()) == expected_keys

    for model in models.values():
        predictions = model.predict(X_val)
        assert len(predictions) == len(X_val)


# ---------------------------------------------------------------------------
# Save / load tests
# ---------------------------------------------------------------------------


def test_save_and_load_model_roundtrip(tmp_path, synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    model = train_model(create_logistic_regression_baseline(), X_train, y_train)

    saved_path = save_model(model, "logistic_regression", output_dir=tmp_path)
    assert Path(saved_path).exists()

    loaded_model = load_model(saved_path)

    original_predictions = model.predict(X_train)
    loaded_predictions = loaded_model.predict(X_train)
    np.testing.assert_array_equal(original_predictions, loaded_predictions)


def test_save_models_returns_paths_for_all_models(tmp_path, synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    models = train_baseline_models(X_train, y_train)

    saved_paths = save_models(models, output_dir=tmp_path)

    assert set(saved_paths.keys()) == set(models.keys())
    for path in saved_paths.values():
        assert Path(path).exists()


def test_load_model_raises_for_missing_file(tmp_path) -> None:
    missing_path = tmp_path / "does_not_exist.joblib"
    with pytest.raises(FileNotFoundError):
        load_model(missing_path)


# ---------------------------------------------------------------------------
# Model summary tests
# ---------------------------------------------------------------------------


def test_get_model_summary_contains_expected_keys(synthetic_processed_data) -> None:
    X_train, y_train, _, _ = synthetic_processed_data
    models = train_baseline_models(X_train, y_train)

    summary = get_model_summary(models)

    expected_keys = {"model_names", "model_count", "model_types", "baseline_note"}
    assert expected_keys.issubset(summary.keys())
    assert summary["model_count"] == len(models)
    assert set(summary["model_names"]) == set(models.keys())


# ---------------------------------------------------------------------------
# Evaluation input validation tests
# ---------------------------------------------------------------------------


def test_validate_evaluation_inputs_accepts_valid_inputs(synthetic_processed_data) -> None:
    _, _, _, y_val = synthetic_processed_data
    y_pred = y_val.copy()
    y_proba = np.where(y_val.values == 1, 0.9, 0.1)

    # Should not raise for valid, well-formed evaluation inputs.
    validate_evaluation_inputs(y_val, y_pred, y_proba)


# ---------------------------------------------------------------------------
# Positive class score extraction tests
# ---------------------------------------------------------------------------


def test_get_positive_class_scores_returns_1d_array(synthetic_processed_data) -> None:
    X_train, y_train, X_val, _ = synthetic_processed_data
    model = train_model(create_logistic_regression_baseline(), X_train, y_train)

    scores = get_positive_class_scores(model, X_val)

    assert isinstance(scores, np.ndarray)
    assert scores.ndim == 1
    assert len(scores) == len(X_val)


# ---------------------------------------------------------------------------
# Metric calculation tests
# ---------------------------------------------------------------------------


def test_calculate_binary_classification_metrics_contains_expected_keys(
    synthetic_processed_data,
) -> None:
    _, _, _, y_val = synthetic_processed_data
    y_pred = y_val.copy()
    y_proba = np.where(y_val.values == 1, 0.9, 0.1)

    metrics = calculate_binary_classification_metrics(y_val, y_pred, y_proba)

    expected_keys = {
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
        "pr_auc",
        "confusion_matrix",
        "true_negatives",
        "false_positives",
        "false_negatives",
        "true_positives",
        "fraud_detection_note",
    }
    assert expected_keys.issubset(metrics.keys())


def test_calculate_binary_classification_metrics_perfect_predictions(
    synthetic_processed_data,
) -> None:
    _, _, _, y_val = synthetic_processed_data
    y_pred = y_val.copy()
    y_proba = np.where(y_val.values == 1, 1.0, 0.0)

    metrics = calculate_binary_classification_metrics(y_val, y_pred, y_proba)

    assert metrics["accuracy"] == pytest.approx(1.0)
    assert metrics["precision"] == pytest.approx(1.0)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0


# ---------------------------------------------------------------------------
# Single and multi-model evaluation tests
# ---------------------------------------------------------------------------


def test_evaluate_model_returns_metrics(synthetic_processed_data) -> None:
    X_train, y_train, X_val, y_val = synthetic_processed_data
    model = train_model(create_random_forest_baseline(), X_train, y_train)

    metrics = evaluate_model(model, X_val, y_val)

    assert "accuracy" in metrics
    assert "pr_auc" in metrics
    assert "confusion_matrix" in metrics


def test_evaluate_models_returns_metrics_for_all_models(synthetic_processed_data) -> None:
    X_train, y_train, X_val, y_val = synthetic_processed_data
    models = train_baseline_models(X_train, y_train)

    all_metrics = evaluate_models(models, X_val, y_val)

    assert set(all_metrics.keys()) == set(models.keys())
    for metrics in all_metrics.values():
        assert "pr_auc" in metrics
        assert "f1_score" in metrics


# ---------------------------------------------------------------------------
# Metrics-to-dataframe tests
# ---------------------------------------------------------------------------


def test_metrics_to_dataframe_has_model_rows(synthetic_processed_data) -> None:
    X_train, y_train, X_val, y_val = synthetic_processed_data
    models = train_baseline_models(X_train, y_train)
    all_metrics = evaluate_models(models, X_val, y_val)

    metrics_df = metrics_to_dataframe(all_metrics)

    assert len(metrics_df) == len(models)
    assert "model_name" in metrics_df.columns
    assert set(metrics_df["model_name"]) == set(models.keys())


# ---------------------------------------------------------------------------
# Best-model selection tests
# ---------------------------------------------------------------------------


def test_find_best_model_by_pr_auc_returns_model_name(synthetic_processed_data) -> None:
    X_train, y_train, X_val, y_val = synthetic_processed_data
    models = train_baseline_models(X_train, y_train)
    all_metrics = evaluate_models(models, X_val, y_val)

    best_model_name = find_best_model_by_pr_auc(all_metrics)

    assert best_model_name in models.keys()


def test_find_best_model_by_pr_auc_ignores_missing_scores() -> None:
    fake_metrics = {
        "model_a": {"pr_auc": None},
        "model_b": {"pr_auc": 0.5},
    }
    best_model_name = find_best_model_by_pr_auc(fake_metrics)
    assert best_model_name == "model_b"


def test_find_best_model_by_pr_auc_returns_none_when_no_valid_scores() -> None:
    fake_metrics = {
        "model_a": {"pr_auc": None},
        "model_b": {"pr_auc": None},
    }
    assert find_best_model_by_pr_auc(fake_metrics) is None
