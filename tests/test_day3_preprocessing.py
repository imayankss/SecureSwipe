"""Tests for the Day 3 preprocessing and stratified data split pipeline.

These tests use only synthetic, deterministic pandas DataFrames. They do
not require the real Kaggle dataset and do not perform any model
training, evaluation, SMOTE, threshold tuning, SHAP, or API/dashboard
logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer

# Ensure the repo root is importable regardless of where pytest is invoked from.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.preprocessing.feature_config import (
    TARGET_COLUMN,
    get_all_features,
    get_feature_groups,
    get_passthrough_features,
    get_pca_features,
    get_required_columns,
    get_scale_features,
    validate_feature_config,
)
from src.data.split_data import (
    assert_disjoint_split_rows,
    create_train_val_test_split,
    get_class_distribution,
    get_split_summary,
    separate_features_target,
    validate_split_inputs,
)
from src.preprocessing.preprocessors import (
    build_preprocessor,
    fit_preprocessor,
    fit_transform_train_val_test,
    get_preprocessing_summary,
    transform_features,
    validate_features_for_preprocessing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_fraud_df() -> pd.DataFrame:
    """Create a deterministic synthetic fraud dataset for testing.

    Returns:
        A DataFrame with 1000 rows, columns Time, V1-V28, Amount, Class,
        and roughly 5% fraud (Class = 1), with both classes present.
    """
    rng = np.random.default_rng(42)
    n_rows = 1000
    n_fraud = 50  # ~5% fraud

    fraud_indices = rng.choice(n_rows, size=n_fraud, replace=False)
    class_values = np.zeros(n_rows, dtype=int)
    class_values[fraud_indices] = 1

    data = {"Time": rng.uniform(0, 172792, n_rows)}

    for i in range(1, 29):
        data[f"V{i}"] = rng.normal(loc=0.0, scale=1.0, size=n_rows)

    data["Amount"] = rng.uniform(0, 5000, n_rows)
    data["Class"] = class_values

    df = pd.DataFrame(data)

    # Re-order columns to match Time, V1..V28, Amount, Class.
    ordered_columns = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount", "Class"]
    return df[ordered_columns]


@pytest.fixture(scope="module")
def synthetic_splits(synthetic_fraud_df: pd.DataFrame) -> dict[str, object]:
    """Create a stratified train/validation/test split from synthetic data.

    Returns:
        The dictionary returned by ``create_train_val_test_split``.
    """
    X, y = separate_features_target(synthetic_fraud_df)
    return create_train_val_test_split(X, y)


# ---------------------------------------------------------------------------
# feature_config tests
# ---------------------------------------------------------------------------

def test_feature_config_is_valid() -> None:
    """validate_feature_config should not raise for the project configuration."""
    validate_feature_config()


def test_feature_groups_have_expected_columns() -> None:
    """Feature groups should contain the expected PCA, scale, and target setup."""
    pca_features = get_pca_features()
    scale_features = get_scale_features()
    passthrough_features = get_passthrough_features()
    all_features = get_all_features()
    required_columns = get_required_columns()
    feature_groups = get_feature_groups()

    expected_pca_features = [f"V{i}" for i in range(1, 29)]
    assert pca_features == expected_pca_features

    assert "Time" in scale_features
    assert "Amount" in scale_features

    assert passthrough_features == expected_pca_features

    assert TARGET_COLUMN not in all_features
    assert len(required_columns) == 31
    assert TARGET_COLUMN in required_columns

    assert "scale_features" in feature_groups
    assert "passthrough_features" in feature_groups
    assert "all_features" in feature_groups
    assert "required_columns" in feature_groups


# ---------------------------------------------------------------------------
# split_data: feature/target separation tests
# ---------------------------------------------------------------------------

def test_separate_features_target_removes_class_from_features(
    synthetic_fraud_df: pd.DataFrame,
) -> None:
    """separate_features_target should cleanly remove Class from X."""
    X, y = separate_features_target(synthetic_fraud_df)

    assert TARGET_COLUMN not in X.columns
    assert y.name == TARGET_COLUMN
    assert len(X) == len(y)
    assert X.shape[1] == 30


# ---------------------------------------------------------------------------
# split_data: input validation tests
# ---------------------------------------------------------------------------

def test_validate_split_inputs_accepts_valid_dataframe(
    synthetic_fraud_df: pd.DataFrame,
) -> None:
    """validate_split_inputs should not raise for a valid dataframe."""
    validate_split_inputs(synthetic_fraud_df)


def test_validate_split_inputs_rejects_missing_target(
    synthetic_fraud_df: pd.DataFrame,
) -> None:
    """validate_split_inputs should raise if the target column is missing."""
    df_missing_target = synthetic_fraud_df.drop(columns=[TARGET_COLUMN]).copy()

    with pytest.raises(ValueError):
        validate_split_inputs(df_missing_target)


def test_validate_split_inputs_rejects_single_class_target(
    synthetic_fraud_df: pd.DataFrame,
) -> None:
    """validate_split_inputs should raise if only one class is present."""
    df_single_class = synthetic_fraud_df.copy()
    df_single_class[TARGET_COLUMN] = 0

    with pytest.raises(ValueError):
        validate_split_inputs(df_single_class)


# ---------------------------------------------------------------------------
# split_data: train/validation/test split tests
# ---------------------------------------------------------------------------

def test_create_train_val_test_split_returns_expected_keys(
    synthetic_splits: dict[str, object],
) -> None:
    """create_train_val_test_split should return all six expected keys."""
    expected_keys = {"X_train", "X_val", "X_test", "y_train", "y_val", "y_test"}
    assert expected_keys == set(synthetic_splits.keys())


def test_create_train_val_test_split_sizes_are_reasonable(
    synthetic_splits: dict[str, object],
) -> None:
    """Split sizes should be approximately 70/15/15."""
    train_rows = len(synthetic_splits["X_train"])
    val_rows = len(synthetic_splits["X_val"])
    test_rows = len(synthetic_splits["X_test"])
    total_rows = train_rows + val_rows + test_rows

    train_ratio = train_rows / total_rows
    val_ratio = val_rows / total_rows
    test_ratio = test_rows / total_rows

    assert train_ratio == pytest.approx(0.70, abs=0.02)
    assert val_ratio == pytest.approx(0.15, abs=0.02)
    assert test_ratio == pytest.approx(0.15, abs=0.02)


def test_create_train_val_test_split_preserves_both_classes(
    synthetic_splits: dict[str, object],
) -> None:
    """Both classes should be present in every split after stratification."""
    for key in ("y_train", "y_val", "y_test"):
        unique_values = set(synthetic_splits[key].unique().tolist())
        assert unique_values == {0, 1}


def test_no_target_column_in_split_features(
    synthetic_splits: dict[str, object],
) -> None:
    """The target column must never appear in any feature split."""
    for key in ("X_train", "X_val", "X_test"):
        assert TARGET_COLUMN not in synthetic_splits[key].columns


def test_split_row_fingerprints_are_pairwise_disjoint(
    synthetic_splits: dict[str, object],
) -> None:
    fingerprints = assert_disjoint_split_rows(synthetic_splits)
    assert set(fingerprints) == {"train", "validation", "test"}
    assert all(len(value) == 64 for value in fingerprints.values())


def test_split_rejects_exact_duplicate_rows(synthetic_fraud_df: pd.DataFrame) -> None:
    duplicated = pd.concat([synthetic_fraud_df, synthetic_fraud_df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        separate_features_target(duplicated)


# ---------------------------------------------------------------------------
# split_data: summary tests
# ---------------------------------------------------------------------------

def test_get_class_distribution_returns_expected_keys(
    synthetic_splits: dict[str, object],
) -> None:
    """get_class_distribution should return all expected keys."""
    distribution = get_class_distribution(synthetic_splits["y_train"])

    expected_keys = {
        "total",
        "legitimate_count",
        "fraud_count",
        "legitimate_percentage",
        "fraud_percentage",
    }
    assert expected_keys == set(distribution.keys())


def test_get_split_summary_returns_expected_keys(
    synthetic_splits: dict[str, object],
) -> None:
    """get_split_summary should return all expected keys."""
    summary = get_split_summary(synthetic_splits)

    expected_keys = {
        "train_rows",
        "validation_rows",
        "test_rows",
        "total_rows",
        "train_percentage",
        "validation_percentage",
        "test_percentage",
        "train_class_distribution",
        "validation_class_distribution",
        "test_class_distribution",
        "feature_count",
        "target_name",
        "row_fingerprints",
        "duplicate_policy",
    }
    assert expected_keys == set(summary.keys())


# ---------------------------------------------------------------------------
# preprocessors: validation tests
# ---------------------------------------------------------------------------

def test_validate_features_for_preprocessing_accepts_valid_features(
    synthetic_splits: dict[str, object],
) -> None:
    """validate_features_for_preprocessing should accept a clean feature matrix."""
    validate_features_for_preprocessing(synthetic_splits["X_train"])


def test_validate_features_for_preprocessing_rejects_class_column(
    synthetic_splits: dict[str, object],
) -> None:
    """validate_features_for_preprocessing should reject a leaked Class column."""
    X_with_target = synthetic_splits["X_train"].copy()
    X_with_target[TARGET_COLUMN] = synthetic_splits["y_train"].values

    with pytest.raises(ValueError):
        validate_features_for_preprocessing(X_with_target)


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -np.inf])
def test_validate_features_for_preprocessing_rejects_non_finite(
    synthetic_splits: dict[str, object],
    invalid_value: float,
) -> None:
    invalid = synthetic_splits["X_train"].copy()
    invalid.iloc[0, invalid.columns.get_loc("V1")] = invalid_value
    with pytest.raises(ValueError, match="missing|finite"):
        validate_features_for_preprocessing(invalid)


def test_validate_features_for_preprocessing_rejects_reordered_features(
    synthetic_splits: dict[str, object],
) -> None:
    invalid = synthetic_splits["X_train"].copy()
    invalid = invalid[[*invalid.columns[1:], invalid.columns[0]]]
    with pytest.raises(ValueError, match="order"):
        validate_features_for_preprocessing(invalid)


# ---------------------------------------------------------------------------
# preprocessors: build / fit / transform tests
# ---------------------------------------------------------------------------

def test_build_preprocessor_returns_column_transformer() -> None:
    """build_preprocessor should return an unfitted ColumnTransformer."""
    preprocessor = build_preprocessor()
    assert isinstance(preprocessor, ColumnTransformer)


def test_fit_preprocessor_fits_on_train_data(
    synthetic_splits: dict[str, object],
) -> None:
    """fit_preprocessor should return a fitted ColumnTransformer."""
    fitted_preprocessor = fit_preprocessor(synthetic_splits["X_train"])

    assert isinstance(fitted_preprocessor, ColumnTransformer)
    assert hasattr(fitted_preprocessor, "transformers_")


def test_transform_features_returns_dataframe_with_same_rows(
    synthetic_splits: dict[str, object],
) -> None:
    """transform_features should return a clean DataFrame with matching rows."""
    fitted_preprocessor = fit_preprocessor(synthetic_splits["X_train"])
    X_val_processed = transform_features(
        synthetic_splits["X_val"], fitted_preprocessor
    )

    assert isinstance(X_val_processed, pd.DataFrame)
    assert len(X_val_processed) == len(synthetic_splits["X_val"])
    assert TARGET_COLUMN not in X_val_processed.columns
    assert not X_val_processed.isnull().values.any()


# ---------------------------------------------------------------------------
# preprocessors: full fit/transform pipeline tests
# ---------------------------------------------------------------------------

def test_fit_transform_train_val_test_outputs_expected_shapes(
    synthetic_splits: dict[str, object],
) -> None:
    """fit_transform_train_val_test should preserve row counts and return feature names."""
    results = fit_transform_train_val_test(
        synthetic_splits["X_train"],
        synthetic_splits["X_val"],
        synthetic_splits["X_test"],
    )

    assert len(results["X_train_processed"]) == len(synthetic_splits["X_train"])
    assert len(results["X_val_processed"]) == len(synthetic_splits["X_val"])
    assert len(results["X_test_processed"]) == len(synthetic_splits["X_test"])
    assert len(results["feature_names"]) > 0


def test_get_preprocessing_summary_contains_expected_keys(
    synthetic_splits: dict[str, object],
) -> None:
    """get_preprocessing_summary should return all expected keys."""
    results = fit_transform_train_val_test(
        synthetic_splits["X_train"],
        synthetic_splits["X_val"],
        synthetic_splits["X_test"],
    )

    summary = get_preprocessing_summary(
        synthetic_splits["X_train"],
        results["X_train_processed"],
        results["feature_names"],
    )

    expected_keys = {
        "original_feature_count",
        "processed_feature_count",
        "scaled_features",
        "passthrough_features",
        "processed_feature_names",
        "train_rows",
        "leakage_note",
    }
    assert expected_keys == set(summary.keys())
