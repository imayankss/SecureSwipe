from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_loader import (  # noqa: E402
    get_required_columns,
    fingerprint_dataframe,
    summarize_dataset,
    validate_dataset_schema,
)
from src.eda.imbalance_analysis import (  # noqa: E402
    calculate_class_counts,
    calculate_class_percentages,
    calculate_imbalance_ratio,
    explain_accuracy_problem,
    format_imbalance_summary_for_console,
    generate_imbalance_summary,
    get_majority_class_accuracy_baseline,
    validate_target_column,
)

N_LEGITIMATE_ROWS = 8
N_FRAUD_ROWS = 2
N_TOTAL_ROWS = N_LEGITIMATE_ROWS + N_FRAUD_ROWS


@pytest.fixture
def synthetic_credit_card_df() -> pd.DataFrame:
    """Build a small synthetic DataFrame matching the expected dataset schema.

    Contains both legitimate (Class = 0) and fraudulent (Class = 1) rows
    so it can be used to test schema validation and imbalance analysis
    without requiring the real Kaggle dataset.
    """
    data: dict[str, list[float] | list[int]] = {
        "Time": [float(i) for i in range(N_TOTAL_ROWS)],
    }

    for i in range(1, 29):
        data[f"V{i}"] = [round(i * 0.1 + j, 2) for j in range(N_TOTAL_ROWS)]

    data["Amount"] = [round(10.0 + j, 2) for j in range(N_TOTAL_ROWS)]
    data["Class"] = [0] * N_LEGITIMATE_ROWS + [1] * N_FRAUD_ROWS

    df = pd.DataFrame(data)
    df = df[get_required_columns()]

    return df


@pytest.fixture
def required_columns() -> list[str]:
    """Return the expected dataset columns using get_required_columns()."""
    return get_required_columns()


def test_get_required_columns_returns_expected_schema(required_columns: list[str]) -> None:
    assert required_columns[0] == "Time"
    assert required_columns[-1] == "Class"
    assert "Amount" in required_columns
    for i in range(1, 29):
        assert f"V{i}" in required_columns
    assert len(required_columns) == 31


def test_validate_dataset_schema_accepts_valid_dataframe(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    validate_dataset_schema(synthetic_credit_card_df)


def test_validate_dataset_schema_rejects_missing_required_column(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    df_missing_column = synthetic_credit_card_df.drop(columns=["V10"])

    with pytest.raises(ValueError) as exc_info:
        validate_dataset_schema(df_missing_column)

    assert "V10" in str(exc_info.value)


def test_validate_dataset_schema_rejects_invalid_class_values(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    df_invalid_class = synthetic_credit_card_df.copy()
    df_invalid_class.loc[0, "Class"] = 2

    with pytest.raises(ValueError) as exc_info:
        validate_dataset_schema(df_invalid_class)

    error_message = str(exc_info.value)
    assert "Class" in error_message or "0 and 1" in error_message


def test_validate_dataset_schema_rejects_duplicate_columns() -> None:
    df_duplicate_columns = pd.DataFrame([[1, 2]], columns=["Time", "Time"])

    with pytest.raises(ValueError):
        validate_dataset_schema(df_duplicate_columns)


def test_validate_dataset_schema_rejects_non_numeric_amount(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    df_non_numeric_amount = synthetic_credit_card_df.copy()
    df_non_numeric_amount["Amount"] = df_non_numeric_amount["Amount"].astype(object)
    df_non_numeric_amount.loc[0, "Amount"] = "not_a_number"

    with pytest.raises(ValueError) as exc_info:
        validate_dataset_schema(df_non_numeric_amount)

    assert "Amount" in str(exc_info.value)


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -np.inf])
def test_validate_dataset_schema_rejects_non_finite_features(
    synthetic_credit_card_df: pd.DataFrame,
    invalid_value: float,
) -> None:
    invalid = synthetic_credit_card_df.copy()
    invalid.loc[0, "V10"] = invalid_value
    with pytest.raises(ValueError, match="missing|non-finite"):
        validate_dataset_schema(invalid)


def test_validate_dataset_schema_rejects_exact_duplicate_rows(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    duplicated = pd.concat(
        [synthetic_credit_card_df, synthetic_credit_card_df.iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_dataset_schema(duplicated)


def test_validate_dataset_schema_rejects_wrong_order(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    reordered = synthetic_credit_card_df[["Amount", *synthetic_credit_card_df.columns[:-2], "Class"]]
    with pytest.raises(ValueError, match="order"):
        validate_dataset_schema(reordered)


def test_dataset_fingerprint_is_deterministic_and_order_sensitive(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    first = fingerprint_dataframe(synthetic_credit_card_df)
    second = fingerprint_dataframe(synthetic_credit_card_df.copy())
    reordered = synthetic_credit_card_df.iloc[::-1].reset_index(drop=True)
    assert first == second
    assert len(first) == 64
    assert first != fingerprint_dataframe(reordered)


def test_summarize_dataset_returns_expected_keys(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    summary = summarize_dataset(synthetic_credit_card_df)

    expected_keys = {
        "rows",
        "columns",
        "missing_values_total",
        "duplicate_rows",
        "memory_usage_mb",
        "class_counts",
        "fraud_count",
        "legitimate_count",
        "fraud_percentage",
    }

    for key in expected_keys:
        assert key in summary


def test_validate_target_column_accepts_valid_binary_target(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    validate_target_column(synthetic_credit_card_df)


def test_validate_target_column_rejects_missing_target_column(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    df_missing_target = synthetic_credit_card_df.drop(columns=["Class"])

    with pytest.raises(ValueError):
        validate_target_column(df_missing_target)


def test_validate_target_column_rejects_missing_target_values(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    df_missing_value = synthetic_credit_card_df.copy()
    df_missing_value.loc[0, "Class"] = None

    with pytest.raises(ValueError):
        validate_target_column(df_missing_value)


def test_calculate_class_counts_returns_correct_counts(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    counts = calculate_class_counts(synthetic_credit_card_df)

    assert counts["total_transactions"] == len(synthetic_credit_card_df)
    assert counts["legitimate_count"] == N_LEGITIMATE_ROWS
    assert counts["fraud_count"] == N_FRAUD_ROWS


def test_calculate_class_percentages_returns_percentages(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    percentages = calculate_class_percentages(synthetic_credit_card_df)

    legitimate_percentage = percentages["legitimate_percentage"]
    fraud_percentage = percentages["fraud_percentage"]

    assert isinstance(legitimate_percentage, float)
    assert isinstance(fraud_percentage, float)
    assert pytest.approx(legitimate_percentage + fraud_percentage, abs=0.01) == 100.0


def test_calculate_imbalance_ratio_returns_legit_to_fraud_ratio(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    ratio = calculate_imbalance_ratio(synthetic_credit_card_df)
    expected_ratio = round(N_LEGITIMATE_ROWS / N_FRAUD_ROWS, 2)

    assert ratio == expected_ratio


def test_majority_class_accuracy_baseline(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    baseline_accuracy = get_majority_class_accuracy_baseline(synthetic_credit_card_df)

    assert isinstance(baseline_accuracy, float)
    assert baseline_accuracy > 0
    assert baseline_accuracy <= 100


def test_explain_accuracy_problem_returns_meaningful_text(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    explanation = explain_accuracy_problem(synthetic_credit_card_df).lower()

    for expected_word in ["accuracy", "imbalanced", "fraud", "precision", "recall"]:
        assert expected_word in explanation


def test_generate_imbalance_summary_contains_expected_keys(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    summary = generate_imbalance_summary(synthetic_credit_card_df)

    expected_keys = {
        "total_transactions",
        "legitimate_count",
        "fraud_count",
        "legitimate_percentage",
        "fraud_percentage",
        "imbalance_ratio",
        "majority_class_accuracy_baseline",
        "accuracy_warning",
        "recommended_metrics",
    }

    for key in expected_keys:
        assert key in summary


def test_format_imbalance_summary_for_console_returns_string(
    synthetic_credit_card_df: pd.DataFrame,
) -> None:
    summary = generate_imbalance_summary(synthetic_credit_card_df)
    formatted_output = format_imbalance_summary_for_console(summary)

    assert isinstance(formatted_output, str)

    lowercase_output = formatted_output.lower()
    for expected_label in ["fraud", "legitimate", "accuracy", "recommended", "metrics"]:
        assert expected_label in lowercase_output
