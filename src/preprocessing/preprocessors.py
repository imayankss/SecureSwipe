"""
Leakage-safe preprocessing pipeline for the
Credit Card Fraud Detection & Risk Scoring System.

This module builds a ColumnTransformer that scales the Time and Amount
columns with StandardScaler and passes through the already PCA-transformed
V1-V28 columns. The preprocessor is always fit on training data only, and
validation/test data is transformed using that fitted preprocessor. No model
training or evaluation happens in this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler

from src.artifacts.bundle import load_verified_joblib, write_checksum_sidecar

from src.preprocessing.feature_config import (
    ALL_FEATURES,
    PASSTHROUGH_FEATURES,
    SCALE_FEATURES,
    TARGET_COLUMN,
)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_PREPROCESSOR_PATH: Path = Path("artifacts/preprocessing/preprocessor.joblib")
DEFAULT_PROCESSED_DIR: Path = Path("data/processed")


def validate_features_for_preprocessing(
    X: pd.DataFrame,
    expected_features: Optional[List[str]] = None,
) -> None:
    """
    Validate that a feature DataFrame is safe to use for preprocessing.

    Args:
        X: Feature DataFrame to validate.
        expected_features: Columns that must be present in X. Defaults to
            ALL_FEATURES from feature_config.

    Raises:
        ValueError: If X is empty, missing expected columns, contains the
            target column, has duplicate columns, has non-numeric expected
            columns, or has fully empty expected columns.
    """
    if expected_features is None:
        expected_features = ALL_FEATURES

    if X.empty:
        raise ValueError("Input feature DataFrame X is empty.")

    missing_columns = [col for col in expected_features if col not in X.columns]
    if missing_columns:
        raise ValueError(
            f"Input feature DataFrame is missing expected columns: {missing_columns}"
        )

    extra_columns = [col for col in X.columns if col not in expected_features]
    if extra_columns:
        raise ValueError(
            f"Input feature DataFrame contains unexpected columns: {extra_columns}"
        )

    if list(X.columns) != list(expected_features):
        raise ValueError(
            "Input features are not in canonical order. "
            f"Expected {list(expected_features)}; found {list(X.columns)}."
        )

    if TARGET_COLUMN in X.columns:
        raise ValueError(
            f"Target column '{TARGET_COLUMN}' must not be present in the "
            "feature DataFrame used for preprocessing."
        )

    if len(X.columns) != len(set(X.columns)):
        raise ValueError("Input feature DataFrame contains duplicate column names.")

    non_numeric_columns = [
        col for col in expected_features if not pd.api.types.is_numeric_dtype(X[col])
    ]
    if non_numeric_columns:
        raise ValueError(
            f"Expected columns must be numeric. Non-numeric columns found: "
            f"{non_numeric_columns}"
        )

    missing_counts = X[expected_features].isna().sum()
    if int(missing_counts.sum()) > 0:
        raise ValueError(
            "Expected columns must contain no missing values. Found: "
            f"{missing_counts[missing_counts > 0].to_dict()}"
        )

    numeric_values = X[expected_features].to_numpy(dtype=float, copy=False)
    if not np.isfinite(numeric_values).all():
        raise ValueError("Expected columns must contain only finite numeric values.")

    if (X["Time"] < 0).any():
        raise ValueError("Time values must be non-negative.")
    if (X["Amount"] < 0).any():
        raise ValueError("Amount values must be non-negative.")


def build_preprocessor(
    scale_features: Optional[List[str]] = None,
    passthrough_features: Optional[List[str]] = None,
) -> ColumnTransformer:
    """
    Build an unfitted leakage-safe ColumnTransformer.

    Args:
        scale_features: Columns to scale with StandardScaler. Defaults to
            SCALE_FEATURES (Time, Amount).
        passthrough_features: Columns to pass through unchanged. Defaults to
            PASSTHROUGH_FEATURES (V1-V28).

    Returns:
        An unfitted ColumnTransformer.
    """
    if scale_features is None:
        scale_features = SCALE_FEATURES
    if passthrough_features is None:
        passthrough_features = PASSTHROUGH_FEATURES

    transformers = [
        ("scaler", StandardScaler(), list(scale_features)),
        ("passthrough", "passthrough", list(passthrough_features)),
    ]

    try:
        preprocessor = ColumnTransformer(
            transformers=transformers,
            verbose_feature_names_out=False,
        )
    except TypeError:
        # Older scikit-learn versions do not support verbose_feature_names_out.
        preprocessor = ColumnTransformer(transformers=transformers)

    return preprocessor


def fit_preprocessor(
    X_train: pd.DataFrame,
    preprocessor: Optional[ColumnTransformer] = None,
) -> ColumnTransformer:
    """
    Fit a preprocessor on training data only.

    Args:
        X_train: Training feature DataFrame.
        preprocessor: An unfitted ColumnTransformer. If None, one is built
            with default feature groups.

    Returns:
        The fitted ColumnTransformer.
    """
    validate_features_for_preprocessing(X_train)

    if preprocessor is None:
        preprocessor = build_preprocessor()

    preprocessor.fit(X_train)
    return preprocessor


def get_transformed_feature_names(preprocessor: ColumnTransformer) -> List[str]:
    """
    Get clean output feature names from a fitted ColumnTransformer.

    Args:
        preprocessor: A fitted ColumnTransformer.

    Returns:
        A list of output feature names as strings.
    """
    try:
        names = preprocessor.get_feature_names_out()
        return [str(name) for name in names]
    except Exception:
        # Fallback for environments where get_feature_names_out is unavailable.
        names = []
        for transformer_name, _transformer, columns in preprocessor.transformers_:
            if transformer_name == "remainder":
                continue
            names.extend([str(col) for col in columns])
        return names


def transform_features(
    X: pd.DataFrame,
    fitted_preprocessor: ColumnTransformer,
) -> pd.DataFrame:
    """
    Transform a feature DataFrame using an already-fitted preprocessor.

    Args:
        X: Feature DataFrame to transform (e.g. validation or test split).
        fitted_preprocessor: A preprocessor previously fit on training data.

    Returns:
        A new pandas DataFrame with transformed feature values, preserving
        the original row index. The input DataFrame is not mutated.
    """
    validate_features_for_preprocessing(X)

    transformed_array = fitted_preprocessor.transform(X)
    feature_names = get_transformed_feature_names(fitted_preprocessor)

    transformed_df = pd.DataFrame(
        transformed_array,
        columns=feature_names,
        index=X.index,
    )
    return transformed_df


def fit_transform_train_val_test(
    X_train: pd.DataFrame,
    X_val: pd.DataFrame,
    X_test: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Fit a preprocessor on training data and transform all three splits.

    Args:
        X_train: Training feature DataFrame.
        X_val: Validation feature DataFrame.
        X_test: Test feature DataFrame.

    Returns:
        A dictionary with keys: "preprocessor", "X_train_processed",
        "X_val_processed", "X_test_processed", and "feature_names".
    """
    fitted_preprocessor = fit_preprocessor(X_train)
    feature_names = get_transformed_feature_names(fitted_preprocessor)

    X_train_processed = transform_features(X_train, fitted_preprocessor)
    X_val_processed = transform_features(X_val, fitted_preprocessor)
    X_test_processed = transform_features(X_test, fitted_preprocessor)

    return {
        "preprocessor": fitted_preprocessor,
        "X_train_processed": X_train_processed,
        "X_val_processed": X_val_processed,
        "X_test_processed": X_test_processed,
        "feature_names": feature_names,
    }


def save_processed_data(
    X_train_processed: pd.DataFrame,
    X_val_processed: pd.DataFrame,
    X_test_processed: pd.DataFrame,
    y_train: pd.Series,
    y_val: pd.Series,
    y_test: pd.Series,
    output_dir: Union[str, Path] = DEFAULT_PROCESSED_DIR,
) -> Dict[str, Path]:
    """
    Save processed feature and target splits to parquet files.

    Args:
        X_train_processed: Processed training features.
        X_val_processed: Processed validation features.
        X_test_processed: Processed test features.
        y_train: Training target values.
        y_val: Validation target values.
        y_test: Test target values.
        output_dir: Directory where processed files will be saved. Created
            if it does not already exist.

    Returns:
        A dictionary mapping each split name to its saved file path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: Dict[str, Path] = {}

    feature_splits = {
        "X_train_processed": X_train_processed,
        "X_val_processed": X_val_processed,
        "X_test_processed": X_test_processed,
    }
    for name, df in feature_splits.items():
        path = output_dir / f"{name}.parquet"
        df.to_parquet(path)
        saved_paths[name] = path

    target_splits = {
        "y_train": y_train,
        "y_val": y_val,
        "y_test": y_test,
    }
    for name, series in target_splits.items():
        target_df = series.to_frame(name=TARGET_COLUMN)
        path = output_dir / f"{name}.parquet"
        target_df.to_parquet(path)
        saved_paths[name] = path

    return saved_paths


def save_preprocessor(
    fitted_preprocessor: ColumnTransformer,
    output_path: Union[str, Path] = DEFAULT_PREPROCESSOR_PATH,
) -> Path:
    """
    Save a fitted preprocessor to disk using joblib.

    Args:
        fitted_preprocessor: A preprocessor that has already been fit.
        output_path: File path to save the preprocessor to. Parent
            directories are created if missing.

    Returns:
        The path the preprocessor was saved to.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(fitted_preprocessor, output_path)
    write_checksum_sidecar(output_path)
    return output_path


def load_preprocessor(
    preprocessor_path: Union[str, Path] = DEFAULT_PREPROCESSOR_PATH,
) -> ColumnTransformer:
    """
    Load a previously saved preprocessor from disk.

    Args:
        preprocessor_path: File path of the saved preprocessor.

    Returns:
        The loaded ColumnTransformer.

    Raises:
        FileNotFoundError: If no file exists at preprocessor_path.
    """
    preprocessor_path = Path(preprocessor_path)
    if not preprocessor_path.exists():
        raise FileNotFoundError(
            f"Preprocessor not found at {preprocessor_path}. "
            "Run the Day 3 preprocessing script to generate it: "
            "python3 scripts/run_day3_preprocessing.py"
        )
    trusted_root = (
        preprocessor_path.parent.parent
        if preprocessor_path.parent.name == "preprocessing"
        else preprocessor_path.parent
    )
    return load_verified_joblib(
        preprocessor_path,
        trusted_root=trusted_root,
        required_attributes=("transform",),
    )


def get_preprocessing_summary(
    X_train: pd.DataFrame,
    X_train_processed: pd.DataFrame,
    feature_names: List[str],
) -> Dict[str, Any]:
    """
    Build a summary dictionary describing the preprocessing step.

    Args:
        X_train: The original (unprocessed) training feature DataFrame.
        X_train_processed: The processed training feature DataFrame.
        feature_names: Output feature names from the fitted preprocessor.

    Returns:
        A dictionary describing original/processed feature counts, scaled
        and passthrough feature groups, processed feature names, the number
        of training rows, and a note on how data leakage was prevented.
    """
    return {
        "original_feature_count": X_train.shape[1],
        "processed_feature_count": X_train_processed.shape[1],
        "scaled_features": list(SCALE_FEATURES),
        "passthrough_features": list(PASSTHROUGH_FEATURES),
        "processed_feature_names": list(feature_names),
        "train_rows": X_train.shape[0],
        "leakage_note": (
            "The preprocessor (StandardScaler on Time and Amount, "
            "passthrough on V1-V28) was fit only on X_train. Validation "
            "and test features were transformed using this already-fitted "
            "preprocessor and were never used to fit any scaling statistics."
        ),
    }
