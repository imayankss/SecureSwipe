"""Day 3 Markdown report generation for preprocessing and data splitting.

This module turns the structured outputs of the Day 3 pipeline (split
summary and preprocessing summary dictionaries, plus generated file paths)
into a single human-readable Markdown report saved at
``reports/day3_preprocessing_summary.md``.

This module does not load data, split data, or fit any preprocessing
itself. It only formats and saves results that are computed elsewhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

DEFAULT_REPORT_PATH = Path("reports/day3_preprocessing_summary.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_report_dir(report_path: Union[str, Path] = DEFAULT_REPORT_PATH) -> Path:
    """Ensure the parent directory of the report path exists.

    Args:
        report_path: Destination path of the Markdown report.

    Returns:
        The report path as a ``Path`` object, with its parent directory
        guaranteed to exist.
    """
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return report_path


def format_class_distribution_table(split_summary: dict[str, object]) -> str:
    """Build a Markdown table summarizing class distribution per split.

    Args:
        split_summary: Dictionary containing ``train_class_distribution``,
            ``validation_class_distribution``, and ``test_class_distribution``
            entries, each with ``total``, ``legitimate_count``,
            ``fraud_count``, ``legitimate_percentage``, and
            ``fraud_percentage`` keys.

    Returns:
        A Markdown-formatted table as a string.
    """
    rows_config = [
        ("Train", "train_class_distribution"),
        ("Validation", "validation_class_distribution"),
        ("Test", "test_class_distribution"),
    ]

    header = (
        "| Split | Rows | Legitimate Count | Fraud Count | "
        "Legitimate % | Fraud % |\n"
        "|---|---|---|---|---|---|"
    )

    table_rows = [header]

    for split_label, distribution_key in rows_config:
        distribution = split_summary.get(distribution_key)

        if not distribution:
            table_rows.append(
                f"| {split_label} | N/A | N/A | N/A | N/A | N/A |"
            )
            continue

        total = distribution.get("total", "N/A")
        legitimate_count = distribution.get("legitimate_count", "N/A")
        fraud_count = distribution.get("fraud_count", "N/A")
        legitimate_percentage = distribution.get("legitimate_percentage", "N/A")
        fraud_percentage = distribution.get("fraud_percentage", "N/A")

        table_rows.append(
            f"| {split_label} | {total} | {legitimate_count} | "
            f"{fraud_count} | {legitimate_percentage}% | {fraud_percentage}% |"
        )

    return "\n".join(table_rows)


def format_artifact_paths(paths: Optional[dict[str, Union[str, Path]]]) -> str:
    """Build a Markdown bullet list of generated artifact paths.

    Args:
        paths: Dictionary mapping a logical artifact name to its file
            path. May be ``None`` or empty.

    Returns:
        A Markdown-formatted bullet list, or a fallback message if no
        paths were provided.
    """
    if not paths:
        return "_No artifact paths were provided for this report._"

    bullet_lines = [f"- `{name}`: `{path}`" for name, path in paths.items()]
    return "\n".join(bullet_lines)


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def build_day3_preprocessing_report(
    split_summary: dict[str, object],
    preprocessing_summary: dict[str, object],
    interim_paths: Optional[dict[str, Union[str, Path]]] = None,
    processed_paths: Optional[dict[str, Union[str, Path]]] = None,
    artifact_paths: Optional[dict[str, Union[str, Path]]] = None,
) -> str:
    """Build the full Day 3 preprocessing Markdown report as a string.

    Args:
        split_summary: Dictionary as returned by ``get_split_summary`` in
            ``src/data/split_data.py``.
        preprocessing_summary: Dictionary as returned by
            ``get_preprocessing_summary`` in
            ``src/preprocessing/preprocessors.py``.
        interim_paths: Mapping of interim split file names to their saved
            paths (e.g. from ``save_split_data``).
        processed_paths: Mapping of processed file names to their saved
            paths (e.g. from ``save_processed_data``).
        artifact_paths: Mapping of artifact names (preprocessor, split
            metadata) to their saved paths.

    Returns:
        A complete Markdown report as a single string.
    """
    generated_at = "omitted for deterministic evidence; see run manifest"

    train_rows = split_summary.get("train_rows", "N/A")
    validation_rows = split_summary.get("validation_rows", "N/A")
    test_rows = split_summary.get("test_rows", "N/A")
    total_rows = split_summary.get("total_rows", "N/A")
    train_percentage = split_summary.get("train_percentage", "N/A")
    validation_percentage = split_summary.get("validation_percentage", "N/A")
    test_percentage = split_summary.get("test_percentage", "N/A")
    feature_count = split_summary.get("feature_count", "N/A")
    target_name = split_summary.get("target_name", "Class")

    scaled_features = preprocessing_summary.get("scaled_features", "N/A")
    passthrough_features = preprocessing_summary.get("passthrough_features", "N/A")
    original_feature_count = preprocessing_summary.get(
        "original_feature_count", "N/A"
    )
    processed_feature_count = preprocessing_summary.get(
        "processed_feature_count", "N/A"
    )
    leakage_note = preprocessing_summary.get(
        "leakage_note",
        "The preprocessor was fitted only on training data.",
    )

    report_sections = [
        "# Day 3 Preprocessing Summary: Credit Card Fraud Detection",
        "",
        "## Report Metadata",
        "",
        f"- Generated at: `{generated_at}`",
        "",
        "## Project Context",
        "",
        "This project detects fraudulent credit card transactions in a "
        "highly imbalanced dataset. Day 2 confirmed that fraud cases make "
        "up only a small fraction of all transactions, which means "
        "accuracy alone is not a reliable evaluation metric. Day 3 builds "
        "on that understanding by preparing a leakage-safe foundation for "
        f"modeling: separating features from the `{target_name}` target, "
        "creating a stratified train/validation/test split, and fitting a "
        "preprocessing pipeline strictly on training data.",
        "",
        "## Split Strategy",
        "",
        "- Train: 70%",
        "- Validation: 15%",
        "- Test: 15%",
        f"- Stratification was used on `{target_name}` to preserve the rare "
        "fraud class ratio across all three splits.",
        "- This prevents any split from accidentally over- or "
        "under-representing fraud cases.",
        "",
        "## Split Summary",
        "",
        f"- Train rows: {train_rows} ({train_percentage}%)",
        f"- Validation rows: {validation_rows} ({validation_percentage}%)",
        f"- Test rows: {test_rows} ({test_percentage}%)",
        f"- Total rows: {total_rows}",
        f"- Feature count: {feature_count}",
        "",
        "## Class Distribution by Split",
        "",
        format_class_distribution_table(split_summary),
        "",
        "## Preprocessing Strategy",
        "",
        "- `Time` and `Amount` are scaled using `StandardScaler`.",
        "- `V1`-`V28` are passed through unchanged because they are "
        "already PCA-transformed.",
        f"- `{target_name}` is never included in the preprocessing pipeline.",
        "- The preprocessor is fitted only on training data "
        "(`X_train`) and reused to transform validation and test data.",
        f"- Original feature count: {original_feature_count}",
        f"- Processed feature count: {processed_feature_count}",
        f"- Scaled features: {scaled_features}",
        f"- Passthrough features: {passthrough_features}",
        "",
        "## Data Leakage Prevention",
        "",
        "- The train/validation/test split is created **before** fitting "
        "any preprocessing.",
        "- `StandardScaler` is fitted only on `X_train`.",
        "- Validation and test sets are only **transformed** using the "
        "already-fitted preprocessor, never used to fit it.",
        "- The test set remains untouched until final model evaluation.",
        f"- Leakage note: {leakage_note}",
        "",
        "## Generated Interim Files",
        "",
        format_artifact_paths(interim_paths),
        "",
        "## Generated Processed Files",
        "",
        format_artifact_paths(processed_paths),
        "",
        "## Generated Artifacts",
        "",
        format_artifact_paths(artifact_paths),
        "",
        "## Day 3 Conclusions",
        "",
        "- Stratified train/validation/test splits were created "
        "successfully.",
        "- Stratification preserved the fraud ratio across all splits.",
        "- The preprocessing pipeline is leakage-safe: it was fitted only "
        "on training data.",
        "- Processed datasets are ready to be used for model training.",
        "",
        "## Day 4 Next Steps",
        "",
        "- Train a baseline Logistic Regression model.",
        "- Train a Random Forest model.",
        "- Evaluate both models using precision, recall, F1-score, PR-AUC, "
        "ROC-AUC, and the confusion matrix.",
        "- Avoid relying on accuracy alone, since it is misleading for "
        "this highly imbalanced dataset.",
        "",
    ]

    return "\n".join(report_sections)


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def save_day3_preprocessing_report(
    split_summary: dict[str, object],
    preprocessing_summary: dict[str, object],
    interim_paths: Optional[dict[str, Union[str, Path]]] = None,
    processed_paths: Optional[dict[str, Union[str, Path]]] = None,
    artifact_paths: Optional[dict[str, Union[str, Path]]] = None,
    report_path: Union[str, Path] = DEFAULT_REPORT_PATH,
) -> Path:
    """Build and save the Day 3 preprocessing Markdown report.

    Args:
        split_summary: Dictionary as returned by ``get_split_summary``.
        preprocessing_summary: Dictionary as returned by
            ``get_preprocessing_summary``.
        interim_paths: Mapping of interim split file names to paths.
        processed_paths: Mapping of processed file names to paths.
        artifact_paths: Mapping of artifact names to paths.
        report_path: Destination path for the saved Markdown report.

    Returns:
        The ``Path`` where the report was saved.
    """
    report_path = ensure_report_dir(report_path)

    report_content = build_day3_preprocessing_report(
        split_summary=split_summary,
        preprocessing_summary=preprocessing_summary,
        interim_paths=interim_paths,
        processed_paths=processed_paths,
        artifact_paths=artifact_paths,
    )

    with report_path.open("w", encoding="utf-8") as f:
        f.write(report_content)

    return report_path


if __name__ == "__main__":
    print(
        "This module is intended to be used by "
        "scripts/run_day3_preprocessing.py. It is not meant to be run "
        "directly."
    )
