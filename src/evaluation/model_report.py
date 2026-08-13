"""Markdown report generation for Day 4 baseline model training and evaluation.

This module builds and saves a human-readable Markdown summary of the
baseline models trained for the Credit Card Fraud Detection & Risk
Scoring System, including validation metrics, confusion matrix
interpretation, and the best model selected by PR-AUC.

No model training, threshold tuning, plotting, or test-set evaluation is
performed in this module.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd

DEFAULT_REPORT_PATH: Path = Path("reports/day4_baseline_model_summary.md")


def ensure_report_dir(report_path: Union[str, Path] = DEFAULT_REPORT_PATH) -> Path:
    """Ensure the parent directory of the report path exists.

    Args:
        report_path: Destination path for the Markdown report.

    Returns:
        The report path with its parent directory created if needed.
    """
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return report_path


def dataframe_to_markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Convert a pandas DataFrame into a Markdown table without extra dependencies.

    Args:
        df: The DataFrame to convert.
        max_rows: Maximum number of rows to include in the table.

    Returns:
        A Markdown-formatted table as a string, or a fallback message if
        the DataFrame is empty.
    """
    if df is None or df.empty:
        return "_No data available._"

    display_df = df.head(max_rows)
    columns = [str(column) for column in display_df.columns]

    header_row = "| " + " | ".join(columns) + " |"
    separator_row = "| " + " | ".join(["---"] * len(columns)) + " |"

    body_rows = []
    for _, row in display_df.iterrows():
        formatted_values = [str(value) for value in row.tolist()]
        body_rows.append("| " + " | ".join(formatted_values) + " |")

    table_lines = [header_row, separator_row] + body_rows
    return "\n".join(table_lines)


def format_model_list(model_summary: Dict[str, Any]) -> str:
    """Format the trained model names and types as a Markdown bullet list.

    Args:
        model_summary: Dictionary produced by the baseline model training
            step, expected to contain "model_names" and "model_types".

    Returns:
        A Markdown bullet list describing each trained model.
    """
    model_names = model_summary.get("model_names", [])
    model_types = model_summary.get("model_types", {})

    if not model_names:
        return "_No models were trained._"

    lines = []
    for model_name in model_names:
        model_type = model_types.get(model_name, "Unknown")
        lines.append(f"- **{model_name}** ({model_type})")

    return "\n".join(lines)


def format_metrics_table(metrics_df: pd.DataFrame) -> str:
    """Format validation metrics as a focused Markdown table.

    Args:
        metrics_df: DataFrame containing model comparison metrics.

    Returns:
        A Markdown-formatted table string containing the key validation
        metrics columns.
    """
    expected_columns = [
        "model_name",
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
        "pr_auc",
        "false_positives",
        "false_negatives",
        "true_positives",
    ]

    if metrics_df is None or metrics_df.empty:
        return "_No validation metrics available._"

    available_columns = [column for column in expected_columns if column in metrics_df.columns]
    table_df = metrics_df[available_columns]
    return dataframe_to_markdown_table(table_df)


def _format_artifact_paths(paths: Optional[Dict[str, Union[str, Path]]]) -> str:
    """Format a dictionary of artifact paths as a Markdown bullet list.

    Args:
        paths: Dictionary mapping artifact names to file paths.

    Returns:
        A Markdown bullet list of artifact paths, or a fallback message
        if no paths were provided.
    """
    if not paths:
        return "_No artifact paths were provided._"

    lines = [f"- **{name}**: `{path}`" for name, path in paths.items()]
    return "\n".join(lines)


def build_day4_baseline_model_report(
    model_summary: Dict[str, Any],
    metrics_df: pd.DataFrame,
    best_model_name: Optional[str],
    model_paths: Optional[Dict[str, Union[str, Path]]] = None,
    metrics_paths: Optional[Dict[str, Union[str, Path]]] = None,
) -> str:
    """Build the complete Day 4 baseline model Markdown report.

    Args:
        model_summary: Summary dictionary describing trained baseline models.
        metrics_df: DataFrame of validation metrics across all models.
        best_model_name: Name of the model with the highest PR-AUC, or
            None if no valid PR-AUC was available.
        model_paths: Optional dictionary of saved model artifact paths.
        metrics_paths: Optional dictionary of saved metrics file paths.

    Returns:
        The complete Markdown report as a string.
    """
    generated_at = "omitted for deterministic evidence; see run manifest"

    if best_model_name:
        best_model_section = (
            f"The best baseline model by PR-AUC is **{best_model_name}**. "
            "PR-AUC was used to select this model because it focuses on "
            "the rare positive (fraud) class rather than overall accuracy."
        )
    else:
        best_model_section = (
            "No valid PR-AUC value was available across the trained "
            "models, so a best baseline model could not be selected. "
            "This can happen if a model only predicts a single class."
        )

    report_sections = [
        "# Day 4 Baseline Model Summary: Credit Card Fraud Detection",
        "",
        "## Report Metadata",
        f"- Generated: {generated_at}",
        "",
        "## Project Context",
        (
            "This project detects fraudulent credit card transactions in a "
            "highly imbalanced dataset. Day 2 confirmed that fraud cases "
            "are extremely rare compared to legitimate transactions. Day 3 "
            "produced leakage-safe processed training, validation, and "
            "test data. Day 4 trains baseline models on the training data "
            "and evaluates them on the validation data only."
        ),
        "",
        "## Day 4 Scope",
        (
            "Day 4 covers the following baseline models and evaluation "
            "steps:\n"
            "- Dummy baseline (naive majority-class predictor)\n"
            "- Logistic Regression baseline\n"
            "- Random Forest baseline\n"
            "- Validation set metrics for each model\n"
            "- No threshold tuning was performed\n"
            "- No final test-set evaluation was performed"
        ),
        "",
        "## Models Trained",
        format_model_list(model_summary),
        "",
        "## Validation Metrics",
        format_metrics_table(metrics_df),
        "",
        "## Best Baseline Model",
        best_model_section,
        "",
        "## Why Accuracy Is Not Enough",
        (
            "Fraud is a rare event in this dataset, so a model can predict "
            "almost every transaction as legitimate and still achieve a "
            "very high accuracy score while catching no fraud at all. "
            "Precision, recall, F1-score, PR-AUC, ROC-AUC, and the "
            "confusion matrix give a much more honest picture of how well "
            "a model actually detects fraud. PR-AUC is especially "
            "important here because it summarizes the precision-recall "
            "tradeoff for the rare positive class under heavy imbalance."
        ),
        "",
        "## Confusion Matrix Interpretation",
        (
            "- **True negatives**: legitimate transactions correctly "
            "classified as legitimate.\n"
            "- **False positives**: legitimate transactions incorrectly "
            "flagged as fraud.\n"
            "- **False negatives**: fraudulent transactions that were "
            "missed by the model.\n"
            "- **True positives**: fraudulent transactions correctly "
            "caught by the model.\n\n"
            "False negatives are especially costly in fraud detection "
            "because each one represents a fraudulent transaction that "
            "went undetected."
        ),
        "",
        "## Generated Model Artifacts",
        _format_artifact_paths(model_paths),
        "",
        "## Generated Metrics Files",
        _format_artifact_paths(metrics_paths),
        "",
        "## Day 4 Conclusions",
        (
            "- Baseline models (Dummy, Logistic Regression, Random Forest) "
            "were trained on the training data.\n"
            "- Validation metrics were generated for every baseline model.\n"
            "- These results establish a benchmark that advanced models "
            "must beat.\n"
            "- The test set remains untouched and reserved for final "
            "evaluation."
        ),
        "",
        "## Day 5 Next Steps",
        (
            "- Train an XGBoost or LightGBM model.\n"
            "- Compare the advanced model against the Day 4 baselines.\n"
            "- Continue prioritizing PR-AUC, recall, precision, and "
            "F1-score over accuracy.\n"
            "- Avoid selecting a final model based on accuracy alone."
        ),
        "",
    ]

    return "\n".join(report_sections)


def save_day4_baseline_model_report(
    model_summary: Dict[str, Any],
    metrics_df: pd.DataFrame,
    best_model_name: Optional[str],
    model_paths: Optional[Dict[str, Union[str, Path]]] = None,
    metrics_paths: Optional[Dict[str, Union[str, Path]]] = None,
    report_path: Union[str, Path] = DEFAULT_REPORT_PATH,
) -> Path:
    """Build and save the Day 4 baseline model Markdown report.

    Args:
        model_summary: Summary dictionary describing trained baseline models.
        metrics_df: DataFrame of validation metrics across all models.
        best_model_name: Name of the model with the highest PR-AUC, or
            None if no valid PR-AUC was available.
        model_paths: Optional dictionary of saved model artifact paths.
        metrics_paths: Optional dictionary of saved metrics file paths.
        report_path: Destination path for the Markdown report.

    Returns:
        The path where the report was saved.
    """
    report_path = ensure_report_dir(report_path)

    report_content = build_day4_baseline_model_report(
        model_summary=model_summary,
        metrics_df=metrics_df,
        best_model_name=best_model_name,
        model_paths=model_paths,
        metrics_paths=metrics_paths,
    )

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(report_content)

    return report_path


if __name__ == "__main__":
    print(
        "This module builds the Day 4 baseline model Markdown report for "
        "the Credit Card Fraud Detection & Risk Scoring System.\n"
        "It is intended to be used by scripts/run_day4_baseline_models.py, "
        "not run directly."
    )
