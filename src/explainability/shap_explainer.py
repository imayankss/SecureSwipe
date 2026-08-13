"""SHAP explainability utilities for the credit card fraud detection project.

This module generates SHAP-based explanations for the Day 5 champion
XGBoost model. It is intentionally narrow in scope:

- Builds an explicit fraud/high-score/representative validation cohort.
- Explains the XGBoost raw margin and proves local additivity.
- Summarizes combined and per-cohort mean absolute SHAP values.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.preprocessing.feature_config import RANDOM_STATE

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_SIZE = 1000
DEFAULT_RANDOM_STATE = RANDOM_STATE
DEFAULT_TOP_N = 20


@dataclass(frozen=True)
class VerifiedShapExplanation:
    """SHAP values whose declared model output passed an additivity check."""

    values: np.ndarray
    base_value: float
    model_output: np.ndarray
    reconstructed_output: np.ndarray
    output_name: str
    max_abs_additivity_error: float


@dataclass(frozen=True)
class ExplanationCohort:
    """Disjoint, labelled rows selected for representative/cohort explanation."""

    features: pd.DataFrame
    labels: np.ndarray
    raw_scores: np.ndarray
    cohort_names: np.ndarray


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


def calculate_verified_shap_explanation(
    model: Any,
    X_sample: pd.DataFrame,
    *,
    additivity_atol: float = 1e-5,
) -> VerifiedShapExplanation:
    """Calculate XGBoost raw-margin SHAP values and prove local additivity.

    Args:
        model: A fitted model compatible with shap.TreeExplainer
            (e.g. the Day 5 XGBoost champion model).
        X_sample: A small sample of feature rows to explain. Must not
            include the target column.

    Returns:
        Values, base value, native raw margins, reconstructed raw margins,
        declared output name, and the observed maximum additivity error.

    Raises:
        ImportError: If the shap package is not installed.
        ValueError: If inputs/model output are unsupported, non-finite, or do
            not satisfy additivity within ``additivity_atol``.
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

    if not isinstance(additivity_atol, (int, float)) or not np.isfinite(additivity_atol):
        raise ValueError("additivity_atol must be a finite non-negative number.")
    if additivity_atol < 0:
        raise ValueError("additivity_atol must be a finite non-negative number.")
    if X_sample.columns.has_duplicates:
        raise ValueError("X_sample feature names must be unique.")
    try:
        values = X_sample.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("X_sample must contain only numeric features.") from exc
    if not np.isfinite(values).all():
        raise ValueError("X_sample must contain only finite feature values.")
    if not hasattr(model, "get_booster") or not hasattr(model, "get_xgb_params"):
        raise ValueError("Verified SHAP currently supports fitted XGBoost classifiers only.")
    if model.get_xgb_params().get("objective") != "binary:logistic":
        raise ValueError("Verified SHAP requires XGBoost objective='binary:logistic'.")

    explainer = shap.TreeExplainer(model, model_output="raw")
    raw_shap_values = explainer.shap_values(X_sample)

    # Some SHAP/XGBoost combinations return a list (one array per class)
    # for binary classification. Use the positive-class array if so.
    if isinstance(raw_shap_values, list):
        shap_values = raw_shap_values[-1]
    else:
        shap_values = raw_shap_values

    shap_values = np.asarray(shap_values, dtype=float)
    if shap_values.shape != X_sample.shape or not np.isfinite(shap_values).all():
        raise ValueError(
            "SHAP returned invalid values: expected shape "
            f"{X_sample.shape}, got {shap_values.shape}."
        )

    expected = np.asarray(explainer.expected_value, dtype=float).reshape(-1)
    if expected.size != 1 or not np.isfinite(expected[0]):
        raise ValueError("Binary SHAP expected_value must contain one finite raw margin.")
    base_value = float(expected[0])

    try:
        import xgboost as xgb
    except ImportError as exc:  # pragma: no cover - installed with the training profile
        raise ImportError("xgboost is required to verify SHAP additivity.") from exc
    matrix = xgb.DMatrix(X_sample, feature_names=[str(column) for column in X_sample.columns])
    model_output = np.asarray(
        model.get_booster().predict(matrix, output_margin=True), dtype=float
    ).reshape(-1)
    reconstructed = base_value + shap_values.sum(axis=1)
    if model_output.shape != reconstructed.shape or not np.isfinite(model_output).all():
        raise ValueError("XGBoost returned an invalid raw-margin output for SHAP verification.")
    error = float(np.max(np.abs(model_output - reconstructed)))
    if not np.allclose(model_output, reconstructed, rtol=1e-6, atol=additivity_atol):
        raise ValueError(
            "SHAP additivity failed for raw-margin output: "
            f"max_abs_error={error:.9g}, tolerance={additivity_atol:.9g}."
        )

    logger.info(
        "Verified SHAP raw-margin additivity for %s rows (max_abs_error=%s).",
        len(X_sample),
        error,
    )
    return VerifiedShapExplanation(
        values=shap_values,
        base_value=base_value,
        model_output=model_output,
        reconstructed_output=reconstructed,
        output_name="raw_margin_log_odds",
        max_abs_additivity_error=error,
    )


def calculate_shap_values(model: Any, X_sample: pd.DataFrame) -> np.ndarray:
    """Compatibility wrapper returning only verified raw-margin SHAP values."""
    return calculate_verified_shap_explanation(model, X_sample).values


def build_explanation_cohort(
    X: pd.DataFrame,
    y_true: pd.Series | np.ndarray,
    raw_scores: pd.Series | np.ndarray,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> ExplanationCohort:
    """Select disjoint labelled-fraud, high-score, and representative rows.

    This purposeful cohort is not prevalence-representative. Up to one quarter
    is reserved for labelled fraud, one quarter for the highest remaining raw
    scores, and the rest is a deterministic random sample of remaining rows.
    """
    if X is None or X.empty:
        raise ValueError("X must not be empty when building an explanation cohort.")
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
        raise ValueError("sample_size must be a positive integer.")
    labels = np.asarray(y_true)
    scores = np.asarray(raw_scores, dtype=float)
    if labels.ndim != 1 or scores.ndim != 1 or len(X) != len(labels) or len(X) != len(scores):
        raise ValueError("X, y_true, and raw_scores must have equal one-dimensional rows.")
    if not np.isfinite(labels.astype(float)).all() or not set(np.unique(labels)).issubset({0, 1}):
        raise ValueError("y_true must contain only finite binary labels.")
    if not np.isfinite(scores).all() or np.logical_or(scores < 0, scores > 1).any():
        raise ValueError("raw_scores must be finite and in [0, 1].")

    size = min(sample_size, len(X))
    positions = np.arange(len(X))
    quarter = max(1, size // 4) if size >= 3 else 0
    fraud_candidates = positions[labels == 1]
    fraud_order = fraud_candidates[np.lexsort((fraud_candidates, -scores[fraud_candidates]))]
    fraud_selected = fraud_order[: min(quarter, len(fraud_order))]

    available = np.setdiff1d(positions, fraud_selected, assume_unique=True)
    high_order = available[np.lexsort((available, -scores[available]))]
    high_selected = high_order[: min(quarter, len(high_order), size - len(fraud_selected))]

    remaining = np.setdiff1d(available, high_selected, assume_unique=True)
    representative_count = size - len(fraud_selected) - len(high_selected)
    rng = np.random.default_rng(random_state)
    representative_selected = (
        np.sort(rng.choice(remaining, size=representative_count, replace=False))
        if representative_count
        else np.asarray([], dtype=int)
    )
    selected = np.concatenate((fraud_selected, high_selected, representative_selected))
    cohort_names = np.concatenate(
        (
            np.repeat("labelled_fraud", len(fraud_selected)),
            np.repeat("high_raw_score", len(high_selected)),
            np.repeat("representative_random", len(representative_selected)),
        )
    )
    if len(np.unique(selected)) != size:
        raise RuntimeError("Explanation cohort selection produced duplicate rows.")
    return ExplanationCohort(
        features=X.iloc[selected].copy(),
        labels=labels[selected].astype(int),
        raw_scores=scores[selected],
        cohort_names=cohort_names,
    )


def _score_summary(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "max": float(np.max(values)),
    }


def summarize_explanation_cohort(cohort: ExplanationCohort) -> dict[str, Any]:
    """Return strict aggregate label/score composition for an explanation cohort."""
    if len(cohort.features) == 0:
        raise ValueError("Explanation cohort must not be empty.")
    cohorts: dict[str, Any] = {}
    for name in ("labelled_fraud", "high_raw_score", "representative_random"):
        mask = cohort.cohort_names == name
        if mask.any():
            cohorts[name] = {
                "rows": int(mask.sum()),
                "labelled_fraud_rows": int(cohort.labels[mask].sum()),
                "raw_score": _score_summary(cohort.raw_scores[mask]),
            }
    return {
        "selection": "purposeful_disjoint_fraud_high_score_and_representative_cohort",
        "is_prevalence_representative": False,
        "rows": len(cohort.features),
        "labelled_fraud_rows": int(cohort.labels.sum()),
        "labelled_legitimate_rows": int(len(cohort.labels) - cohort.labels.sum()),
        "raw_score": _score_summary(cohort.raw_scores),
        "cohorts": cohorts,
    }


def build_cohort_feature_importance(
    explanation: VerifiedShapExplanation,
    feature_names: list[str],
    cohort_names: np.ndarray,
) -> dict[str, pd.DataFrame]:
    """Build separate mean-absolute raw-margin importance for every cohort."""
    names = np.asarray(cohort_names)
    if names.ndim != 1 or len(names) != len(explanation.values):
        raise ValueError("cohort_names must align one-to-one with SHAP rows.")
    return {
        str(name): build_shap_feature_importance(explanation.values[names == name], feature_names)
        for name in sorted(np.unique(names))
    }


def save_shap_cohort_evidence(
    explanation: VerifiedShapExplanation,
    cohort_summary: Mapping[str, Any],
    cohort_importance: Mapping[str, pd.DataFrame],
    output_dir: str | Path,
) -> Path:
    """Persist strict aggregate output/additivity/cohort evidence; never row data."""
    payload = {
        "schema_version": 1,
        "output_name": explanation.output_name,
        "base_value": explanation.base_value,
        "max_abs_additivity_error": explanation.max_abs_additivity_error,
        "additivity_verified": True,
        "cohort_summary": dict(cohort_summary),
        "cohort_top_features": {
            name: frame.head(10).to_dict(orient="records")
            for name, frame in sorted(cohort_importance.items())
        },
    }
    path = Path(output_dir) / "shap_cohort_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


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
    ax.set_xlabel("Mean |SHAP value| (raw margin / log-odds)")
    ax.set_title(f"Top {len(plot_df)} Features by SHAP Importance")
    fig.tight_layout()

    fig.savefig(output_path, dpi=150)
    plt.close(fig)

    logger.info("Saved SHAP summary bar plot to %s.", output_path)
    return output_path


def write_shap_markdown_report(
    feature_importance_df: pd.DataFrame,
    output_path: str | Path,
    *,
    explanation: VerifiedShapExplanation,
    cohort_summary: Mapping[str, Any],
    cohort_importance: Mapping[str, pd.DataFrame],
    top_n: int = DEFAULT_TOP_N,
) -> Path:
    """Write a Markdown report explaining the top SHAP features.

    Args:
        feature_importance_df: Output of build_shap_feature_importance.
        output_path: File path (.md) to save the report to.
        explanation: Verified raw-margin SHAP evidence.
        cohort_summary: Aggregate label/score composition, with no row vectors.
        cohort_importance: Separate feature-importance tables per cohort.
        top_n: Number of top features to include in the combined report table.

    Returns:
        The path the report was saved to.

    Raises:
        ValueError: If feature_importance_df is empty.
    """
    if feature_importance_df is None or feature_importance_df.empty:
        raise ValueError("feature_importance_df must not be empty.")
    if explanation.output_name != "raw_margin_log_odds":
        raise ValueError("SHAP report requires verified raw-margin/log-odds output.")
    if not cohort_summary or not cohort_importance:
        raise ValueError("SHAP report requires cohort composition and cohort importance.")

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

    cohort_lines = [
        "| Cohort | Rows | Labelled fraud | Raw score min | Median | Mean | Max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    cohorts = cohort_summary.get("cohorts")
    if not isinstance(cohorts, Mapping):
        raise ValueError("cohort_summary must contain a cohorts mapping.")
    for name, details in sorted(cohorts.items()):
        if not isinstance(details, Mapping) or not isinstance(details.get("raw_score"), Mapping):
            raise ValueError("Every cohort summary must contain aggregate raw-score evidence.")
        scores = details["raw_score"]
        cohort_lines.append(
            f"| `{name}` | {details['rows']} | {details['labelled_fraud_rows']} | "
            f"{float(scores['min']):.6f} | {float(scores['median']):.6f} | "
            f"{float(scores['mean']):.6f} | {float(scores['max']):.6f} |"
        )

    per_cohort_lines: list[str] = []
    for name, frame in sorted(cohort_importance.items()):
        per_cohort_lines.extend(
            (
                f"### `{name}`",
                "",
                "| Rank | Feature | Mean absolute SHAP value |",
                "|---:|---|---:|",
            )
        )
        for rank, row in enumerate(frame.head(5).itertuples(index=False), start=1):
            per_cohort_lines.append(
                f"| {rank} | {row.feature} | {row.mean_abs_shap_value:.6f} |"
            )
        per_cohort_lines.append("")

    report_lines = [
        "# SHAP Feature Importance Summary",
        "",
        "## Purpose",
        "",
        "This report describes which transformed features contributed most to "
        "the champion XGBoost model's **raw margin (log-odds)** on an explicit "
        "validation explanation cohort. It does not describe calibrated fraud "
        "probability or causal effects.",
        "",
        "## Important Limitation",
        "",
        "Because `V1` to `V28` are anonymized PCA-transformed features, "
        "SHAP values explain model behavior in terms of these "
        "transformed components. They do not map directly to "
        "real-world transaction attributes such as merchant, "
        "location, or card type.",
        "",
        "## Output and Additivity Evidence",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Model output explained | `{explanation.output_name}` |",
        f"| SHAP base value | {explanation.base_value:.9g} |",
        f"| Rows checked | {len(explanation.values)} |",
        f"| Maximum absolute additivity error | {explanation.max_abs_additivity_error:.9g} |",
        "| Additivity status | verified against native XGBoost `output_margin=True` |",
        "",
        "## Explanation Cohort Composition",
        "",
        "The cohort deliberately includes labelled-fraud and high-raw-score rows "
        "alongside a random remainder. It is **not prevalence-representative** and "
        "must not be used to estimate alert prevalence or performance.",
        "",
        *cohort_lines,
        "",
        f"## Top {len(top_features_df)} Features by SHAP Importance",
        "",
        table_markdown,
        "",
        "## How to Read This Report",
        "",
        "- A higher mean absolute SHAP value means a larger average contribution "
        "to the raw margin/log-odds across this purposeful cohort. The direction "
        "for an individual row can differ.",
        "- This ranking reflects model behavior only. It does not "
        "imply causation or a verified real-world explanation.",
        "",
        "## Cohort-Specific Top Features",
        "",
        *per_cohort_lines,
        "## Scope Notes",
        "",
        "- SHAP values were calculated on a sample of validation data "
        "only. The already-observed historical test split was not loaded.",
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
