from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_REPORT_PATH = Path("reports/day2_eda_summary.md")
TARGET_COLUMN = "Class"


def ensure_report_dir(report_path: str | Path = DEFAULT_REPORT_PATH) -> Path:
    """Ensure the parent directory of the report path exists.

    Args:
        report_path: Destination path for the Markdown report.

    Returns:
        The resolved Path to the report file.
    """
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_dataset_overview(df: pd.DataFrame) -> dict[str, object]:
    """Summarize high-level dataset shape and quality information.

    Args:
        df: The DataFrame to summarize.

    Returns:
        A dictionary with rows, columns, column_names, missing_values_total,
        duplicate_rows, memory_usage_mb, numeric_columns_count, and
        non_numeric_columns_count.
    """
    numeric_columns = df.select_dtypes(include="number").columns
    non_numeric_columns = df.select_dtypes(exclude="number").columns

    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": list(df.columns),
        "missing_values_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage_mb": round(df.memory_usage(deep=True).sum() / (1024 ** 2), 4),
        "numeric_columns_count": int(len(numeric_columns)),
        "non_numeric_columns_count": int(len(non_numeric_columns)),
    }


def get_missing_values_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize missing values per column.

    Args:
        df: The DataFrame to inspect.

    Returns:
        A DataFrame with columns 'column', 'missing_count', and
        'missing_percentage', sorted by missing_count descending. Only
        columns with at least one missing value are included. If there
        are no missing values, an empty DataFrame with the same columns
        is returned.
    """
    expected_columns = ["column", "missing_count", "missing_percentage"]
    total_rows = len(df)

    missing_counts = df.isna().sum()
    missing_counts = missing_counts[missing_counts > 0]

    if missing_counts.empty:
        return pd.DataFrame(columns=expected_columns)

    summary = pd.DataFrame(
        {
            "column": missing_counts.index,
            "missing_count": missing_counts.values,
        }
    )
    summary["missing_percentage"] = round((summary["missing_count"] / total_rows) * 100, 4)
    summary = summary.sort_values(by="missing_count", ascending=False).reset_index(drop=True)

    return summary


def get_basic_numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Generate a transposed descriptive statistics summary for numeric columns.

    Args:
        df: The DataFrame to summarize.

    Returns:
        A DataFrame with one row per numeric column and statistics such as
        count, mean, std, min, 25%, 50%, 75%, and max as columns. Returns
        an empty DataFrame if no numeric columns exist.
    """
    numeric_df = df.select_dtypes(include="number")

    if numeric_df.empty:
        return pd.DataFrame()

    return numeric_df.describe().transpose()


def dataframe_to_markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Convert a DataFrame into a simple Markdown table string.

    Args:
        df: The DataFrame to convert.
        max_rows: Maximum number of rows to include in the table.

    Returns:
        A Markdown-formatted table as a string, or a fallback message if
        the DataFrame is empty.
    """
    if df is None or df.empty:
        return "_No data available for this section._"

    limited_df = df.head(max_rows).copy()

    if not isinstance(limited_df.index, pd.RangeIndex):
        limited_df = limited_df.reset_index()

    headers = [str(column) for column in limited_df.columns]
    table_lines = ["| " + " | ".join(headers) + " |"]
    table_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for _, row in limited_df.iterrows():
        formatted_values = []
        for value in row.tolist():
            try:
                if isinstance(value, float):
                    formatted_values.append(f"{value:.4f}")
                else:
                    formatted_values.append(str(value))
            except Exception:
                formatted_values.append("N/A")
        table_lines.append("| " + " | ".join(formatted_values) + " |")

    return "\n".join(table_lines)


def build_class_imbalance_section(imbalance_summary: dict[str, object]) -> str:
    """Build the Markdown section explaining class imbalance and metric choice.

    Args:
        imbalance_summary: Dictionary produced by
            src.eda.imbalance_analysis.generate_imbalance_summary().

    Returns:
        A Markdown-formatted section as a string.
    """
    recommended_metrics = imbalance_summary.get("recommended_metrics", [])
    metrics_list = "\n".join(f"- {metric}" for metric in recommended_metrics)

    section_lines = [
        "## Class Imbalance Analysis",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total transactions | {imbalance_summary.get('total_transactions')} |",
        f"| Legitimate transactions | {imbalance_summary.get('legitimate_count')} "
        f"({imbalance_summary.get('legitimate_percentage')}%) |",
        f"| Fraudulent transactions | {imbalance_summary.get('fraud_count')} "
        f"({imbalance_summary.get('fraud_percentage')}%) |",
        f"| Imbalance ratio (legitimate:fraud) | {imbalance_summary.get('imbalance_ratio')}:1 |",
        f"| Majority-class accuracy baseline | "
        f"{imbalance_summary.get('majority_class_accuracy_baseline')}% |",
        "",
        "### Why Accuracy Is Misleading",
        "",
        str(imbalance_summary.get("accuracy_warning", "Accuracy warning not available.")),
        "",
        "Because legitimate transactions dominate this dataset, a model can achieve a very "
        "high accuracy score while still failing to detect any fraud at all. Accuracy treats "
        "every correct prediction equally, but in fraud detection the rare positive class "
        "(fraud) is exactly what matters most to the business.",
        "",
        "### Recommended Evaluation Metrics",
        "",
        metrics_list if metrics_list else "_No recommended metrics were provided._",
        "",
        "Precision and recall are especially important for fraud detection: recall measures "
        "how many actual fraudulent transactions are correctly identified, while precision "
        "measures how trustworthy a fraud alert is. F1-score balances the two, and PR-AUC and "
        "ROC-AUC summarize performance across all classification thresholds. The confusion "
        "matrix makes the tradeoff between false positives and false negatives explicit.",
    ]

    return "\n".join(section_lines)


def build_figures_section(figure_paths: dict[str, str | Path] | None = None) -> str:
    """Build the Markdown section listing generated EDA figures.

    Args:
        figure_paths: Dictionary mapping figure names to their saved file
            paths. Expected keys include class_distribution,
            amount_distribution_by_class, time_distribution_by_class, and
            correlation_heatmap.

    Returns:
        A Markdown-formatted section as a string.
    """
    expected_figures = [
        ("class_distribution", "Class Distribution"),
        ("amount_distribution_by_class", "Amount Distribution by Class"),
        ("time_distribution_by_class", "Time Distribution by Class"),
        ("correlation_heatmap", "Correlation Heatmap"),
    ]

    if not figure_paths:
        return "## Generated Figures\n\nNo figures were generated for this report."

    section_lines = ["## Generated Figures", ""]

    for key, label in expected_figures:
        if key in figure_paths:
            section_lines.append(f"- **{label}:** `{str(figure_paths[key])}`")

    extra_keys = [key for key in figure_paths if key not in dict(expected_figures)]
    for key in extra_keys:
        section_lines.append(f"- **{key}:** `{str(figure_paths[key])}`")

    if len(section_lines) == 2:
        section_lines.append("No matching figures were found in the provided figure paths.")

    return "\n".join(section_lines)


def build_day2_eda_report(
    df: pd.DataFrame,
    imbalance_summary: dict[str, object],
    figure_paths: dict[str, str | Path] | None = None,
) -> str:
    """Build the complete Day 2 EDA Markdown report as a single string.

    Args:
        df: The full credit card transaction DataFrame.
        imbalance_summary: Dictionary produced by
            src.eda.imbalance_analysis.generate_imbalance_summary().
        figure_paths: Optional dictionary mapping figure names to saved
            file paths.

    Returns:
        The complete Markdown report content as a string.
    """
    overview = get_dataset_overview(df)
    missing_summary = get_missing_values_summary(df)
    numeric_summary = get_basic_numeric_summary(df)
    timestamp = "omitted for deterministic evidence; see run manifest"

    column_overview = ", ".join(f"`{column}`" for column in overview["column_names"])

    missing_section = (
        dataframe_to_markdown_table(missing_summary)
        if not missing_summary.empty
        else "No missing values were found in the dataset."
    )

    numeric_section = (
        dataframe_to_markdown_table(numeric_summary, max_rows=35)
        if not numeric_summary.empty
        else "No numeric columns were available to summarize."
    )

    report_sections = [
        "# Day 2 EDA Summary: Credit Card Fraud Detection",
        "",
        f"_Report generated: {timestamp}_",
        "",
        "## Project Context",
        "",
        "This report covers Day 2 of the Credit Card Fraud Detection & Risk Scoring "
        "System project. Day 2 focuses exclusively on exploratory data analysis, dataset "
        "validation, and class imbalance explanation. No preprocessing, scaling, model "
        "training, or threshold tuning has been performed at this stage.",
        "",
        "## Dataset Overview",
        "",
        f"- Rows: {overview['rows']}",
        f"- Columns: {overview['columns']}",
        f"- Numeric columns: {overview['numeric_columns_count']}",
        f"- Non-numeric columns: {overview['non_numeric_columns_count']}",
        f"- Missing values (total): {overview['missing_values_total']}",
        f"- Duplicate rows: {overview['duplicate_rows']}",
        f"- Memory usage: {overview['memory_usage_mb']} MB",
        "",
        "## Column Overview",
        "",
        column_overview,
        "",
        "## Missing Values Summary",
        "",
        missing_section,
        "",
        "## Duplicate Rows",
        "",
        f"The dataset contains {overview['duplicate_rows']} duplicate row(s).",
        "",
        "## Basic Numeric Summary",
        "",
        numeric_section,
        "",
        build_class_imbalance_section(imbalance_summary),
        "",
        build_figures_section(figure_paths),
        "",
        "## Why Accuracy Is Misleading",
        "",
        str(imbalance_summary.get("accuracy_warning", "Accuracy warning not available.")),
        "",
        "## Day 2 Conclusions",
        "",
        "- The dataset was loaded and validated successfully.",
        "- The target distribution (`Class`) is highly imbalanced.",
        "- Fraudulent transactions are extremely rare compared to legitimate transactions.",
        "- Accuracy alone is not a reliable metric for evaluating fraud detection performance.",
        "- Future evaluation must rely on precision, recall, F1-score, PR-AUC, ROC-AUC, and "
        "the confusion matrix instead of accuracy.",
        "",
        "## Day 3 Next Steps",
        "",
        "- Build a leakage-safe preprocessing pipeline.",
        "- Create a stratified train/validation/test split.",
        "- Apply scaling where appropriate, such as for the `Amount` and `Time` columns.",
        "- Prepare the dataset for baseline model training.",
        "",
    ]

    return "\n".join(report_sections)


def save_day2_eda_report(
    df: pd.DataFrame,
    imbalance_summary: dict[str, object],
    figure_paths: dict[str, str | Path] | None = None,
    report_path: str | Path = DEFAULT_REPORT_PATH,
) -> Path:
    """Build and save the Day 2 EDA Markdown report to disk.

    Args:
        df: The full credit card transaction DataFrame.
        imbalance_summary: Dictionary produced by
            src.eda.imbalance_analysis.generate_imbalance_summary().
        figure_paths: Optional dictionary mapping figure names to saved
            file paths.
        report_path: Destination path for the saved Markdown report.

    Returns:
        The Path where the report was saved.
    """
    report_content = build_day2_eda_report(df, imbalance_summary, figure_paths)
    path = ensure_report_dir(report_path)
    path.write_text(report_content, encoding="utf-8")
    return path


if __name__ == "__main__":
    print(
        "This module provides report-building functions for the Day 2 EDA summary. "
        "It does not load data or generate figures on its own. "
        "Use scripts/run_day2_eda.py to orchestrate data loading, figure generation, "
        "and report saving."
    )
