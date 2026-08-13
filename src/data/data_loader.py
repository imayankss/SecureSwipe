from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.feature_config import REQUIRED_COLUMNS

DEFAULT_DATA_PATH = Path("data/raw/creditcard.csv")


def get_required_columns() -> list[str]:
    """Return the expected dataset columns in their canonical order."""
    return list(REQUIRED_COLUMNS)


def validate_dataset_schema(
    df: pd.DataFrame,
    allow_extra_columns: bool = False,
    strict_order: bool = True,
    reject_duplicate_rows: bool = True,
) -> None:
    """Validate that a DataFrame matches the expected credit card fraud schema.

    Args:
        df: The DataFrame to validate.
        allow_extra_columns: If False, raise an error when columns outside
            the required schema are present.
        strict_order: If True (the safe default), required columns must use
            the exact canonical order.
        reject_duplicate_rows: Reject exact duplicate transactions before any
            split so identical rows cannot cross evaluation boundaries.

    Raises:
        ValueError: If any schema or data quality check fails.
    """
    if df.empty:
        raise ValueError("Dataset is empty. Expected at least one row of data.")

    if len(df.columns) != len(set(df.columns)):
        raise ValueError("Dataset contains duplicate column names.")

    required = get_required_columns()

    missing_columns = [column for column in required if column not in df.columns]
    if missing_columns:
        raise ValueError(
            f"Dataset is missing required columns: {missing_columns}. "
            f"Expected columns: {required}."
        )

    if not allow_extra_columns:
        extra_columns = [column for column in df.columns if column not in required]
        if extra_columns:
            raise ValueError(
                f"Dataset contains unexpected extra columns: {extra_columns}. "
                "Set allow_extra_columns=True if this is intentional."
            )

    if strict_order:
        ordered_required_in_df = [column for column in df.columns if column in required]
        if ordered_required_in_df != required:
            raise ValueError(
                "Dataset columns are not in the expected order. "
                f"Expected order: {required}. "
                f"Found order: {ordered_required_in_df}."
            )

    target_column = "Class"
    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' is missing from the dataset.")

    if df[target_column].isna().any():
        raise ValueError(f"Target column '{target_column}' contains missing values.")

    unique_classes = set(df[target_column].dropna().unique().tolist())
    if not unique_classes.issubset({0, 1}):
        raise ValueError(
            f"Target column '{target_column}' must only contain 0 and 1. "
            f"Found values: {sorted(unique_classes)}."
        )

    numeric_columns = ["Time", "Amount", "Class"] + [f"V{i}" for i in range(1, 29)]
    non_numeric_columns = [
        column for column in numeric_columns if not pd.api.types.is_numeric_dtype(df[column])
    ]
    if non_numeric_columns:
        raise ValueError(f"Expected numeric columns are not numeric: {non_numeric_columns}.")

    missing_counts = df[required].isna().sum()
    missing_value_counts = {
        str(column): int(count) for column, count in missing_counts.items() if count
    }
    if missing_value_counts:
        raise ValueError(
            "Dataset contains missing values in required columns: "
            f"{missing_value_counts}."
        )

    feature_values = df[required].to_numpy(dtype=float, copy=False)
    if not np.isfinite(feature_values).all():
        invalid_count = int((~np.isfinite(feature_values)).sum())
        raise ValueError(
            "Dataset contains non-finite values (NaN or infinity) in required "
            f"columns: {invalid_count} value(s)."
        )

    if (df["Time"] < 0).any():
        raise ValueError("Dataset contains negative Time values.")
    if (df["Amount"] < 0).any():
        raise ValueError("Dataset contains negative Amount values.")

    if reject_duplicate_rows:
        duplicate_count = int(df.duplicated(subset=required, keep=False).sum())
        if duplicate_count:
            raise ValueError(
                "Dataset contains exact duplicate rows. Remove or explicitly "
                f"resolve {duplicate_count} duplicated row occurrences before splitting."
            )


def fingerprint_dataframe(df: pd.DataFrame) -> str:
    """Return a deterministic SHA-256 fingerprint of schema, dtypes, and rows.

    The digest contains no raw values and can be recorded in a manifest. Row
    order is significant because the dataset's ``Time`` ordering matters for
    future blocked evaluation.
    """
    validate_dataset_schema(df)
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, df.columns)).encode("utf-8"))
    digest.update(b"\x00")
    digest.update("\x1f".join(map(str, df.dtypes)).encode("utf-8"))
    digest.update(b"\x00")
    row_hashes = pd.util.hash_pandas_object(df, index=False, categorize=True)
    digest.update(row_hashes.to_numpy(dtype="uint64", copy=False).tobytes())
    return digest.hexdigest()


def load_credit_card_data(
    data_path: str | Path = DEFAULT_DATA_PATH,
    validate: bool = True,
) -> pd.DataFrame:
    """Load the raw credit card transactions dataset from disk.

    Args:
        data_path: Path to the creditcard.csv file. Defaults to
            data/raw/creditcard.csv relative to the project root.
        validate: If True, run schema validation after loading.

    Returns:
        A pandas DataFrame containing the raw transaction data.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
        ValueError: If the file is not a CSV, or if validation fails.
    """
    path = Path(data_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. "
            "Please download creditcard.csv from Kaggle and place it in data/raw/."
        )

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a .csv file, but got: {path.suffix}")

    df = pd.read_csv(path)

    if validate:
        validate_dataset_schema(df)

    return df


def summarize_dataset(df: pd.DataFrame) -> dict[str, object]:
    """Generate a summary of dataset shape, quality, and class balance.

    Args:
        df: The DataFrame to summarize.

    Returns:
        A dictionary with row/column counts, missing value and duplicate
        counts, memory usage, and class balance statistics if a 'Class'
        column is present.
    """
    summary: dict[str, object] = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "missing_values_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / (1024 ** 2), 4),
    }

    if "Class" in df.columns:
        class_counts = df["Class"].value_counts().to_dict()
        fraud_count = int(class_counts.get(1, 0))
        legitimate_count = int(class_counts.get(0, 0))
        total_count = fraud_count + legitimate_count
        fraud_percentage = round((fraud_count / total_count) * 100, 4) if total_count > 0 else 0.0

        summary["class_counts"] = {int(key): int(value) for key, value in class_counts.items()}
        summary["fraud_count"] = fraud_count
        summary["legitimate_count"] = legitimate_count
        summary["fraud_percentage"] = fraud_percentage

    return summary


if __name__ == "__main__":
    try:
        dataset = load_credit_card_data()
        summary = summarize_dataset(dataset)

        print("Dataset loaded successfully.")
        print(f"Rows: {summary['rows']}")
        print(f"Columns: {summary['columns']}")
        print(f"Missing values total: {summary['missing_values_total']}")
        print(f"Duplicate rows: {summary['duplicate_rows']}")
        print(f"Memory usage (MB): {summary['memory_usage_mb']}")

        if "fraud_count" in summary:
            print(f"Legitimate transactions: {summary['legitimate_count']}")
            print(f"Fraudulent transactions: {summary['fraud_count']}")
            print(f"Fraud percentage: {summary['fraud_percentage']}%")

    except FileNotFoundError as error:
        print(f"File not found: {error}")
    except ValueError as error:
        print(f"Validation error: {error}")
