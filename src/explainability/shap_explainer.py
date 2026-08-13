"""SHAP explainability utilities for the credit card fraud detection project.

This module generates SHAP-based explanations for the Day 5 champion
XGBoost model. It is intentionally narrow in scope:

- Samples a small subset of validation data (never the test set).
- Calculates SHAP values for that sample only.
- Summarizes feature importance using mean absolute SHAP values.
- Saves CSV/JSON feature importance tables, a bar plot, and a
  Markdown report.

Important:
    This module must never be used to tune the model, select features,
    or change preprocessing. SHAP is for explanation only.

    Because V1-V28 are anonymized PCA-transformed features, SHAP
    values explain model behavior in terms of these transformed
    components. They do not map directly to real-world transaction
    attributes such as merchant, location, or card type.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.preprocessing.feature_config import RANDOM_STATE

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_SIZE = 1000
DEFAULT_RANDOM_STATE = RANDOM_STATE
DEFAULT_TOP_N = 20


def sample_explanation_data(
    X: pd.DataFrame,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> pd.DataFrame:
    """Sample a small, deterministic subset of rows for SHAP explanation.

    Args:
        X: Feature DataFrame to sample from (validation features only).
        sample_size: Maximum number of rows to sample. If X has fewer
            rows than sample_size, the full DataFrame is returned.
        random_state: Random seed for reproducible sampling.

    Returns:
        A DataFrame containing at most ``sample_size`` rows from ``X``.

    Raises:
        ValueError: If X is empty.
    """
    if X is None or X.empty:
        raise ValueError("X must not be empty when sampling explanation data.")

    if len(X) <= sample_size:
        logger.info(
            "Requested sample_size=%s is >= available rows=%s; using full data.",
            sample_size,
            len(X),
        )
        return X.copy()

    sample = X.sample(n=sample_size, random_state=random_state)
    logger.info(
        "Sampled %s rows for SHAP explanation (from %s available).",
        len(sample),
        len(X),
    )
    return sample


def calculate_shap_values(model: Any, X_sample: pd.DataFrame) -> np.ndarray:
    """Calculate SHAP values for a fitted tree-based model.

    Args:
        model: A fitted model compatible with shap.TreeExplainer
            (e.g. the Day 5 XGBoost champion model).
        X_sample: A small sample of feature rows to explain. Must not
            include the target column.

    Returns:
        A 2D numpy array of SHAP values with shape
        (n_samples, n_features).

    Raises:
        ImportError: If the shap package is not installed.
        ValueError: If X_sample is empty.
    """
    if X_sample is None or X_sample.empty:
        raise ValueError("X_sample must not be empty when calculating SHAP values.")

    try:
        import shap
    except ImportError as exc:
        raise ImportError(
            "The 'shap' package is required for SHAP explainability. "
            "Install it with: pip install shap"
        ) from exc

    explainer = shap.TreeExplainer(model)
    raw_shap_values = explainer.shap_values(X_sample)

    # Some SHAP/XGBoost combinations return a list (one array per class)
    # for binary classification. Use the positive-class array if so.
    if isinstance(raw_shap_values, list):
        shap_values = raw_shap_values[-1]
    else:
        shap_values = raw_shap_values

    shap_values = np.asarray(shap_values)
    logger.info("Calculated SHAP values with shape %s.", shap_values.shape)
    return shap_values


def build_shap_feature_importance(
    shap_values: np.ndarray,
    feature_names: list[str],
) -> pd.DataFrame:
    """Build a feature importance table from SHAP values.

    Importance is the mean absolute SHAP value per feature, reflecting
    the average magnitude of each feature's contribution to model
    predictions across the explained sample.

    Args:
        shap_values: A 2D array of SHAP values, shape
            (n_samples, n_features).
        feature_names: Feature names matching the columns of
            shap_values, in order.

    Returns:
        A DataFrame with columns ["feature", "mean_abs_shap_value"],
        sorted by mean_abs_shap_value descending.

    Raises:
        ValueError: If shap_values is empty, not 2D, or the feature
            count does not match feature_names.
    """
    shap_array = np.asarray(shap_values)

    if shap_array.size == 0:
        raise ValueError("shap_values must not be empty.")

    if shap_array.ndim != 2:
        raise ValueError(
            "shap_values must be 2D (n_samples, n_features), "
            f"got shape {shap_array.shape}."
        )

    if shap_array.shape[1] != len(feature_names):
        raise ValueError(
            "Number of feature_names must match number of SHAP value "
            f"columns: {len(feature_names)} != {shap_array.shape[1]}."
        )

    mean_abs_shap = np.abs(shap_array).mean(axis=0)

    importance_df = pd.DataFrame(
        {
            "feature": feature_names,
            "mean_abs_shap_value": mean_abs_shap,
        }
    )

    importance_df = importance_df.sort_values(
        "mean_abs_shap_value", ascending=False
    ).reset_index(drop=True)

    return importance_df


def save_shap_outputs(
    feature_importance_df: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Save SHAP feature importance as CSV and JSON.

    Args:
        feature_importance_df: Output of build_shap_feature_importance.
        output_dir: Directory in which to save the outputs. Created if
            it does not already exist.

    Returns:
        A dictionary mapping output name to saved path:
        {"csv": Path, "json": Path}.

    Raises:
        ValueError: If feature_importance_df is empty or missing the
            required columns.
    """
    required_columns = {"feature", "mean_abs_shap_value"}
    if feature_importance_df is None or feature_importance_df.empty:
        raise ValueError("feature_importance_df must not be empty.")
    if not required_columns.issubset(feature_importance_df.columns):
        raise ValueError(
            f"feature_importance_df must contain columns {required_columns}."
        )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "shap_feature_importance.csv"
    json_path = output_dir / "shap_top_features.json"

    feature_importance_df.to_csv(csv_path, index=False)

    top_features = feature_importance_df.to_dict(orient="records")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(top_features, f, indent=2)

    logger.info("Saved SHAP feature importance CSV to %s.", csv_path)
    logger.info("Saved SHAP top features JSON to %s.", json_path)

    return {"csv": csv_path, "json": json_path}


def plot_shap_summary_bar(
    feature_importance_df: pd.DataFrame,
    output_path: str | Path,
    top_n: int = DEFAULT_TOP_N,
) -> Path:
    """Plot a horizontal bar chart of the top SHAP feature importances.

    Args:
        feature_importance_df: Output of build_shap_feature_importance,
            sorted descending by mean_abs_shap_value.
        output_path: File path (PNG) to save the plot to.
        top_n: Number of top features to display.

    Returns:
        The path the plot was saved to.

    Raises:
        ValueError: If feature_importance_df is empty.
    """
    if feature_importance_df is None or feature_importance_df.empty:
        raise ValueError("feature_importance_df must not be empty.")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plot_df = feature_importance_df.head(top_n).iloc[::-1]

    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(plot_df))))
    ax.barh(plot_df["feature"], plot_df["mean_abs_shap_value"], color="#4C72B0")
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title(f"Top {len(plot_df)} Features by SHAP Importance")
    fig.tight_layout()

    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    logger.info("Saved SHAP summary bar plot to %s.", output_path)
    return output_path


def write_shap_markdown_report(
    feature_importance_df: pd.DataFrame,
    output_path: str | Path,
    top_n: int = DEFAULT_TOP_N,
) -> Path:
    """Write a Markdown report explaining the top SHAP features.

    Args:
        feature_importance_df: Output of build_shap_feature_importance.
        output_path: File path (.md) to save the report to.
        top_n: Number of top features to include in the report table.

    Returns:
        The path the report was saved to.

    Raises:
        ValueError: If feature_importance_df is empty.
    """
    if feature_importance_df is None or feature_importance_df.empty:
        raise ValueError("feature_importance_df must not be empty.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    top_features_df = feature_importance_df.head(top_n)

    table_lines = [
        "| Rank | Feature | Mean Absolute SHAP Value |",
        "|---:|---|---:|",
    ]
    for rank, row in enumerate(top_features_df.itertuples(index=False), start=1):
        table_lines.append(
            f"| {rank} | {row.feature} | {row.mean_abs_shap_value:.6f} |"
        )
    table_markdown = "\n".join(table_lines)

    report_lines = [
        "# SHAP Feature Importance Summary",
        "",
        "## Purpose",
        "",
        "This report explains which features most influenced the "
        "champion XGBoost model's fraud predictions, based on mean "
        "absolute SHAP values calculated on a sample of validation "
        "data.",
        "",
        "## Important Limitation",
        "",
        "Because `V1` to `V28` are anonymized PCA-transformed features, "
        "SHAP values explain model behavior in terms of these "
        "transformed components. They do not map directly to "
        "real-world transaction attributes such as merchant, "
        "location, or card type.",
        "",
        f"## Top {len(top_features_df)} Features by SHAP Importance",
        "",
        table_markdown,
        "",
        "## How to Read This Report",
        "",
        "- A higher mean absolute SHAP value means the feature has, "
        "on average, a larger impact on the model's predicted fraud "
        "probability across the explained sample.",
        "- This ranking reflects model behavior only. It does not "
        "imply causation or a verified real-world explanation.",
        "",
        "## Scope Notes",
        "",
        "- SHAP values were calculated on a sample of validation data "
        "only, never on the test set used for final evaluation.",
        "- SHAP was used strictly for explanation. It was not used to "
        "tune the model, select features, or change preprocessing.",
        "",
    ]
    report_markdown = "\n".join(report_lines)

    output_path.write_text(report_markdown, encoding="utf-8")
    logger.info("Saved SHAP markdown report to %s.", output_path)
    return output_path


if __name__ == "__main__":
    print(
        "This module is intended to be used by "
        "scripts/run_day7_explainability.py, not run directly."
    )
