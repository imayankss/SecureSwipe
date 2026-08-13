"""Leakage-safe feature/target separation and stratified data splitting.

This module is responsible for:
    1. Separating the raw dataset into features (X) and target (y).
    2. Creating a stratified train/validation/test split that preserves
       the rare fraud class ratio across all three splits.
    3. Summarizing and persisting the resulting splits and their metadata.

No preprocessing transformations (scaling, encoding, SMOTE, etc.) and no
model training happen in this file. Those concerns belong to
``src/preprocessing/preprocessors.py`` and the Day 4 model training modules.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.preprocessing.feature_config import (
    ALL_FEATURES,
    RANDOM_STATE,
    TARGET_COLUMN,
    TEST_SIZE,
    TRAIN_SIZE,
    VALIDATION_SIZE,
)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_INTERIM_DIR = Path("data/interim")
DEFAULT_METADATA_PATH = Path("artifacts/preprocessing/split_metadata.json")

# Tolerance used when checking that split ratios sum to 1.0.
_SPLIT_SIZE_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_split_inputs(
    df: pd.DataFrame,
    target_col: str = TARGET_COLUMN,
    feature_cols: Optional[list[str]] = None,
) -> None:
    """Validate a raw dataframe before separating features and target.

    Args:
        df: The raw (or validated) dataset containing both features and
            the target column.
        target_col: Name of the target column. Defaults to ``TARGET_COLUMN``.
        feature_cols: Names of the feature columns to expect. Defaults to
            ``ALL_FEATURES`` when not provided.

    Raises:
        ValueError: If the dataframe is empty, the target column is
            missing, the target contains missing or invalid values, only
            one class is present, feature columns are missing, duplicate
            columns exist, or the target column is also listed as a
            feature column.
    """
    if feature_cols is None:
        feature_cols = ALL_FEATURES

    if df is None or df.empty:
        raise ValueError(
            "Cannot validate split inputs: the provided DataFrame is empty."
        )

    duplicate_columns = df.columns[df.columns.duplicated()].tolist()
    if duplicate_columns:
        raise ValueError(
            f"Duplicate columns found in DataFrame: {duplicate_columns}. "
            "Each column name must be unique."
        )

    if target_col not in df.columns:
        raise ValueError(
            f"Target column '{target_col}' was not found in the DataFrame. "
            f"Available columns: {list(df.columns)}"
        )

    if target_col in feature_cols:
        raise ValueError(
            f"Target column '{target_col}' must not be included in the "
            "feature column list. This would cause target leakage."
        )

    missing_features = [col for col in feature_cols if col not in df.columns]
    if missing_features:
        raise ValueError(
            f"The following expected feature columns are missing from the "
            f"DataFrame: {missing_features}"
        )

    target_series = df[target_col]

    if target_series.isnull().any():
        missing_count = int(target_series.isnull().sum())
        raise ValueError(
            f"Target column '{target_col}' contains {missing_count} missing "
            "value(s). The target must be fully populated."
        )

    unique_values = set(target_series.unique().tolist())
    allowed_values = {0, 1}
    if not unique_values.issubset(allowed_values):
        raise ValueError(
            f"Target column '{target_col}' must only contain 0 and 1. "
            f"Found unexpected values: {unique_values - allowed_values}"
        )

    if len(unique_values) < 2:
        raise ValueError(
            f"Target column '{target_col}' only contains a single class "
            f"({unique_values}). Both legitimate (0) and fraud (1) classes "
            "must be present to perform a stratified split."
        )

    expected_columns = list(feature_cols) + [target_col]
    if list(df.columns) != expected_columns:
        raise ValueError(
            "Split input columns must exactly match the canonical ordered "
            f"schema. Expected {expected_columns}; found {list(df.columns)}."
        )

    missing_counts = df[expected_columns].isna().sum()
    if int(missing_counts.sum()) > 0:
        raise ValueError("Split inputs contain missing feature or target values.")

    numeric_values = df[expected_columns].to_numpy(dtype=float, copy=False)
    if not np.isfinite(numeric_values).all():
        raise ValueError("Split inputs contain non-finite values.")

    duplicate_count = int(df.duplicated(subset=expected_columns, keep=False).sum())
    if duplicate_count:
        raise ValueError(
            "Split inputs contain exact duplicate rows; resolve duplicates "
            f"before splitting ({duplicate_count} duplicated row occurrences)."
        )


def fingerprint_rows(X: pd.DataFrame, y: Optional[pd.Series] = None) -> pd.Series:
    """Return stable SHA-256 row identifiers without exposing transaction values."""
    if y is not None:
        if len(X) != len(y):
            raise ValueError("Cannot fingerprint rows with mismatched X/y lengths.")
        frame = X.copy()
        frame[TARGET_COLUMN] = y.to_numpy()
    else:
        frame = X

    def _digest(raw_hash: int) -> str:
        return hashlib.sha256(str(int(raw_hash)).encode("ascii")).hexdigest()

    raw_hashes = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    return raw_hashes.map(_digest)


def assert_disjoint_split_rows(
    splits: dict[str, Union[pd.DataFrame, pd.Series]],
) -> dict[str, str]:
    """Fail if any exact feature+target row appears in more than one split."""
    row_hashes = {
        "train": set(fingerprint_rows(splits["X_train"], splits["y_train"])),
        "validation": set(fingerprint_rows(splits["X_val"], splits["y_val"])),
        "test": set(fingerprint_rows(splits["X_test"], splits["y_test"])),
    }
    pairs = (("train", "validation"), ("train", "test"), ("validation", "test"))
    for left, right in pairs:
        overlap = row_hashes[left] & row_hashes[right]
        if overlap:
            raise ValueError(
                f"Exact-row leakage detected between {left} and {right}: "
                f"{len(overlap)} overlapping row fingerprint(s)."
            )
    return {
        name: hashlib.sha256("".join(sorted(values)).encode("ascii")).hexdigest()
        for name, values in row_hashes.items()
    }


# ---------------------------------------------------------------------------
# Feature / target separation
# ---------------------------------------------------------------------------

def separate_features_target(
    df: pd.DataFrame,
    target_col: str = TARGET_COLUMN,
    feature_cols: Optional[list[str]] = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Separate a dataframe into a feature matrix ``X`` and target ``y``.

    Args:
        df: The raw (or validated) dataset containing both features and
            the target column.
        target_col: Name of the target column. Defaults to ``TARGET_COLUMN``.
        feature_cols: Names of the feature columns to extract. Defaults to
            ``ALL_FEATURES`` when not provided.

    Returns:
        A tuple ``(X, y)`` where ``X`` is a DataFrame containing only the
        requested feature columns and ``y`` is a Series containing the
        target column. The original ``df`` is never mutated.
    """
    if feature_cols is None:
        feature_cols = ALL_FEATURES

    validate_split_inputs(df, target_col=target_col, feature_cols=feature_cols)

    # Use .copy() so downstream mutations never affect the original df.
    X = df.loc[:, list(feature_cols)].copy()
    y = df.loc[:, target_col].copy()

    if target_col in X.columns:
        raise ValueError(
            f"Target column '{target_col}' unexpectedly remained in the "
            "feature matrix after separation. This indicates a bug in "
            "feature_cols configuration."
        )

    return X, y


# ---------------------------------------------------------------------------
# Train / validation / test split
# ---------------------------------------------------------------------------

def create_train_val_test_split(
    X: pd.DataFrame,
    y: pd.Series,
    train_size: float = TRAIN_SIZE,
    validation_size: float = VALIDATION_SIZE,
    test_size: float = TEST_SIZE,
    random_state: int = RANDOM_STATE,
) -> dict[str, Union[pd.DataFrame, pd.Series]]:
    """Create a stratified train/validation/test split.

    The split is performed in two stages so that the rare fraud class
    ratio is preserved in every resulting subset:

    1. Split ``X``/``y`` into ``train`` and a temporary ``temp`` set using
       ``train_size``, stratified on ``y``.
    2. Split ``temp`` into ``validation`` and ``test`` using the relative
       proportion of ``test_size`` within ``validation_size + test_size``,
       stratified on the temporary target.

    Args:
        X: Feature matrix.
        y: Target series aligned with ``X``.
        train_size: Proportion of data allocated to the training split.
        validation_size: Proportion of data allocated to the validation
            split.
        test_size: Proportion of data allocated to the test split.
        random_state: Random seed used for reproducibility.

    Returns:
        A dictionary with keys ``X_train``, ``X_val``, ``X_test``,
        ``y_train``, ``y_val``, ``y_test``.

    Raises:
        ValueError: If ``train_size + validation_size + test_size`` does
            not sum to 1.0, or if ``X`` and ``y`` have mismatched lengths.
    """
    total_size = train_size + validation_size + test_size
    if abs(total_size - 1.0) > _SPLIT_SIZE_TOLERANCE:
        raise ValueError(
            "train_size, validation_size, and test_size must sum to 1.0. "
            f"Got train_size={train_size}, validation_size={validation_size}, "
            f"test_size={test_size} (sum={total_size})."
        )

    if len(X) != len(y):
        raise ValueError(
            f"X and y must have the same number of rows. Got len(X)={len(X)} "
            f"and len(y)={len(y)}."
        )

    combined = X.copy()
    combined[TARGET_COLUMN] = y.to_numpy()
    validate_split_inputs(combined)

    # Stage 1: split into train vs. temp (validation + test combined).
    X_train, X_temp, y_train, y_temp = train_test_split(
        X,
        y,
        train_size=train_size,
        random_state=random_state,
        stratify=y,
    )

    # Stage 2: split temp into validation and test, preserving the
    # relative proportion of test_size within (validation_size + test_size).
    remaining_size = validation_size + test_size
    relative_test_size = test_size / remaining_size

    X_val, X_test, y_val, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=relative_test_size,
        random_state=random_state,
        stratify=y_temp,
    )

    target_splits = {
        "training": y_train,
        "validation": y_val,
        "test": y_test,
    }
    for split_name, split_target in target_splits.items():
        if set(split_target.unique().tolist()) != {0, 1}:
            raise ValueError(
                f"The {split_name} split does not contain both target classes. "
                "Use a larger dataset or adjust the split sizes."
            )
    splits = {
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
        "y_train": y_train,
        "y_val": y_val,
        "y_test": y_test,
    }
    assert_disjoint_split_rows(splits)
    return splits


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------

def get_class_distribution(y: pd.Series) -> dict[str, object]:
    """Summarize the class distribution of a target series.

    Args:
        y: Target series containing only 0 (legitimate) and 1 (fraud).

    Returns:
        A dictionary with ``total``, ``legitimate_count``, ``fraud_count``,
        ``legitimate_percentage``, and ``fraud_percentage``.

    Raises:
        ValueError: If ``y`` is empty.
    """
    total = int(len(y))
    if total == 0:
        raise ValueError("Cannot compute class distribution for an empty series.")

    legitimate_count = int((y == 0).sum())
    fraud_count = int((y == 1).sum())

    return {
        "total": total,
        "legitimate_count": legitimate_count,
        "fraud_count": fraud_count,
        "legitimate_percentage": round(legitimate_count / total * 100, 4),
        "fraud_percentage": round(fraud_count / total * 100, 4),
    }


def get_split_summary(
    splits: dict[str, Union[pd.DataFrame, pd.Series]]
) -> dict[str, object]:
    """Summarize row counts, percentages, and class distributions per split.

    Args:
        splits: Dictionary as returned by ``create_train_val_test_split``,
            containing ``X_train``, ``X_val``, ``X_test``, ``y_train``,
            ``y_val``, and ``y_test``.

    Returns:
        A dictionary describing the split sizes, percentages, per-split
        class distributions, feature count, and target column name.
    """
    required_keys = {"X_train", "X_val", "X_test", "y_train", "y_val", "y_test"}
    missing_keys = required_keys - set(splits.keys())
    if missing_keys:
        raise ValueError(
            f"splits dictionary is missing required keys: {sorted(missing_keys)}"
        )

    X_train = splits["X_train"]
    X_val = splits["X_val"]
    X_test = splits["X_test"]
    y_train = splits["y_train"]
    y_val = splits["y_val"]
    y_test = splits["y_test"]

    train_rows = int(len(X_train))
    validation_rows = int(len(X_val))
    test_rows = int(len(X_test))
    total_rows = train_rows + validation_rows + test_rows

    if total_rows == 0:
        raise ValueError("Cannot build split summary: all splits are empty.")

    target_name = getattr(y_train, "name", None) or TARGET_COLUMN

    fingerprints = assert_disjoint_split_rows(splits)
    return {
        "train_rows": train_rows,
        "validation_rows": validation_rows,
        "test_rows": test_rows,
        "total_rows": total_rows,
        "train_percentage": round(train_rows / total_rows * 100, 4),
        "validation_percentage": round(validation_rows / total_rows * 100, 4),
        "test_percentage": round(test_rows / total_rows * 100, 4),
        "train_class_distribution": get_class_distribution(y_train),
        "validation_class_distribution": get_class_distribution(y_val),
        "test_class_distribution": get_class_distribution(y_test),
        "feature_count": int(X_train.shape[1]),
        "target_name": target_name,
        "row_fingerprints": fingerprints,
        "duplicate_policy": "reject_exact_rows_before_split",
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_split_data(
    splits: dict[str, Union[pd.DataFrame, pd.Series]],
    output_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
) -> dict[str, Path]:
    """Save train/validation/test splits to parquet files.

    Args:
        splits: Dictionary as returned by ``create_train_val_test_split``,
            containing ``X_train``, ``X_val``, ``X_test``, ``y_train``,
            ``y_val``, and ``y_test``.
        output_dir: Directory where the parquet files will be written.
            Created automatically if it does not exist.

    Returns:
        A dictionary mapping each split name (e.g. ``"X_train"``) to the
        ``Path`` of the saved parquet file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: dict[str, Path] = {}

    for split_name, split_data in splits.items():
        file_path = output_dir / f"{split_name}.parquet"

        if split_name.startswith("y_"):
            # Convert the target Series to a single-column DataFrame so it
            # can be saved as parquet, using the canonical target column
            # name regardless of the Series' own name attribute.
            data_to_save = split_data.to_frame(name=TARGET_COLUMN)
        else:
            data_to_save = split_data

        data_to_save.to_parquet(file_path, index=True)
        saved_paths[split_name] = file_path

    return saved_paths


def save_split_metadata(
    split_summary: dict[str, object],
    metadata_path: Union[str, Path] = DEFAULT_METADATA_PATH,
) -> Path:
    """Save split summary metadata to a JSON file.

    Args:
        split_summary: Dictionary as returned by ``get_split_summary``.
        metadata_path: Destination path for the JSON metadata file.
            Parent directories are created automatically if missing.

    Returns:
        The ``Path`` where the metadata file was saved.
    """
    metadata_path = Path(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = dict(split_summary)
    metadata["generated_at"] = datetime.now(timezone.utc).isoformat()

    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)

    return metadata_path


def load_split_data(
    input_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
) -> dict[str, Union[pd.DataFrame, pd.Series]]:
    """Load previously saved train/validation/test parquet splits.

    Args:
        input_dir: Directory containing the saved split parquet files.

    Returns:
        A dictionary with keys ``X_train``, ``X_val``, ``X_test``,
        ``y_train``, ``y_val``, ``y_test``. Feature splits are returned as
        DataFrames; target splits are returned as Series.

    Raises:
        FileNotFoundError: If any of the expected parquet files are
            missing from ``input_dir``.
    """
    input_dir = Path(input_dir)
    split_names = ["X_train", "X_val", "X_test", "y_train", "y_val", "y_test"]

    loaded: dict[str, Union[pd.DataFrame, pd.Series]] = {}

    for split_name in split_names:
        file_path = input_dir / f"{split_name}.parquet"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Expected split file not found at '{file_path}'. "
                "Run the Day 3 preprocessing script to generate split data "
                "before attempting to load it."
            )

        data = pd.read_parquet(file_path)

        if split_name.startswith("y_"):
            loaded[split_name] = data[TARGET_COLUMN]
        else:
            loaded[split_name] = data

    return loaded
