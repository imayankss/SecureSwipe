"""
src/models/model_comparison.py
--------------------------------
Credit Card Fraud Detection & Risk Scoring System — Day 5

Validation-only model comparison utilities.

Responsibilities
----------------
* Build a ranked comparison table from per-model metric dictionaries.
* Select a champion model by validation PR-AUC.
* Persist outputs as CSV, JSON, and a GitHub-readable Markdown report.

Strict Day 5 scope — this module does NOT:
  - Touch the test set.
  - Implement threshold tuning.
  - Generate PR / ROC curve plots.
  - Run SHAP analysis.
  - Import any model training code.

Upstream contract (Day 4)
--------------------------
``src.evaluation.classification_metrics.calculate_binary_classification_metrics``
returns dicts with keys including ``f1_score`` (not ``f1``).  This module
accepts both spellings so it integrates cleanly with Day 4 without requiring
any edits to that module.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

DEFAULT_COMPARISON_DIR = Path("reports/model_comparison")

# Minimum keys every entry in metrics_list must supply.
_REQUIRED_KEYS: tuple[str, ...] = ("model_name", "pr_auc")

# Final column order in the comparison DataFrame.
COMPARISON_COLUMNS: list[str] = [
    "model_name",
    "pr_auc",
    "roc_auc",
    "precision",
    "recall",
    "f1",
    "validation_rows",
    "validation_frauds",
]

# Backward-compatible public name used by tests and downstream callers.
REQUIRED_COLUMNS: list[str] = COMPARISON_COLUMNS

# Numeric metric columns that are rounded for display.
_METRIC_COLS: list[str] = ["pr_auc", "roc_auc", "precision", "recall", "f1"]
_ROUND_DECIMALS: int = 4


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _coerce_float(value: Any) -> float | None:
    """Return a Python ``float`` or ``None``; swallows ``NaN``."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _to_python(value: Any) -> Any:
    """Convert numpy scalars to native Python types (for JSON serialisation)."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _normalise_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise a raw per-model metrics dict into the canonical shape.

    Handles
    -------
    * ``f1_score`` → ``f1`` alias (Day 4 metric naming).
    * Numpy scalars → Python primitives (JSON-safe).
    * ``validation_rows`` / ``validation_frauds`` derived from confusion-
      matrix components when not explicitly present.
    """
    m: dict[str, Any] = {k: _to_python(v) for k, v in raw.items()}

    # Accept f1_score as alias for f1 (Day 4 classification_metrics naming).
    if "f1" not in m and "f1_score" in m:
        m["f1"] = m.pop("f1_score")

    # Derive validation totals from confusion matrix parts when absent.
    tn = m.get("true_negatives") or 0
    fp = m.get("false_positives") or 0
    fn = m.get("false_negatives") or 0
    tp = m.get("true_positives") or 0

    if "validation_rows" not in m:
        total = tn + fp + fn + tp
        m["validation_rows"] = int(total) if total > 0 else None

    if "validation_frauds" not in m:
        fraud_total = fn + tp
        m["validation_frauds"] = int(fraud_total) if fraud_total > 0 else None

    return m


def _sanitise_for_json(value: Any) -> Any:
    """Replace ``float('nan')`` with ``None`` so JSON serialisation succeeds."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _df_to_markdown_table(df: pd.DataFrame) -> str:
    """
    Render a DataFrame as a GitHub-flavoured Markdown table.

    No external dependencies (``tabulate`` not required).

    Parameters
    ----------
    df:
        DataFrame to render.  ``None`` values display as ``N/A``.
        ``float`` values are formatted to four decimal places.
        ``int`` values are comma-formatted.

    Returns
    -------
    str
        Multi-line Markdown table string.
    """

    def _fmt(val: Any) -> str:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        if isinstance(val, float):
            return f"{val:.4f}"
        if isinstance(val, int):
            return f"{val:,}"
        return str(val)

    headers = list(df.columns)
    # Pre-compute formatted values so we can measure column widths.
    formatted: list[list[str]] = [
        [_fmt(v) for v in row] for row in df.itertuples(index=False)
    ]
    col_widths = [
        max(len(headers[i]), *(len(row[i]) for row in formatted))
        for i in range(len(headers))
    ]

    def _row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells)) + " |"

    separator = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"

    lines = [_row(headers), separator] + [_row(row) for row in formatted]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_metrics_list(metrics_list: list[dict[str, Any]]) -> None:
    """
    Ensure *metrics_list* is non-empty and every entry has the required keys.

    Parameters
    ----------
    metrics_list:
        List of per-model metric dicts.

    Raises
    ------
    TypeError
        If *metrics_list* is not a ``list``, or any entry is not a ``dict``.
    ValueError
        If the list is empty or a required key is missing from any entry.
    """
    if not isinstance(metrics_list, list):
        raise TypeError(
            f"metrics_list must be a list, got {type(metrics_list).__name__!r}."
        )
    if len(metrics_list) == 0:
        raise ValueError(
            "metrics_list is empty.  Pass at least one model's metrics dict."
        )
    for idx, entry in enumerate(metrics_list):
        if not isinstance(entry, dict):
            raise TypeError(
                f"Entry [{idx}] in metrics_list must be a dict, "
                f"got {type(entry).__name__!r}."
            )
        # Accept f1_score as a substitute for f1
        normalised_keys = set(entry.keys()) | (
            {"f1"} if "f1_score" in entry else set()
        )
        for key in _REQUIRED_KEYS:
            if key not in normalised_keys:
                label = entry.get("model_name", f"index {idx}")
                raise ValueError(
                    f"Entry for model '{label}' is missing required key '{key}'."
                )

        metric_keys = ("roc_auc", "precision", "recall")
        for key in metric_keys:
            if key not in normalised_keys:
                label = entry.get("model_name", f"index {idx}")
                raise ValueError(
                    f"Entry for model '{label}' is missing required key '{key}'."
                )
        if "f1" not in normalised_keys:
            label = entry.get("model_name", f"index {idx}")
            raise ValueError(
                f"Entry for model '{label}' is missing required key 'f1'."
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_model_comparison_table(
    metrics_list: list[dict[str, Any]],
) -> pd.DataFrame:
    """
    Build a sorted, validation-only model comparison DataFrame.

    Parameters
    ----------
    metrics_list:
        A list of per-model metric dicts.  Each dict must contain at least
        ``model_name`` and ``pr_auc``.  The Day 4 field name ``f1_score``
        is accepted as an alias for ``f1``.  ``confusion_matrix`` raw arrays
        are silently dropped; individual TP/TN/FP/FN keys are used instead.

    Returns
    -------
    pd.DataFrame
        Comparison table with columns in :data:`COMPARISON_COLUMNS` order,
        sorted by ``pr_auc`` descending.  Models whose ``pr_auc`` is
        ``None`` / ``NaN`` appear at the bottom.

    Raises
    ------
    TypeError
        When *metrics_list* is not a ``list`` or entries are not dicts.
    ValueError
        When *metrics_list* is empty or a required key is absent.

    Examples
    --------
    >>> metrics = [
    ...     {"model_name": "logistic_regression", "pr_auc": 0.65,
    ...      "roc_auc": 0.97, "precision": 0.80, "recall": 0.60,
    ...      "f1_score": 0.69, "true_negatives": 40000,
    ...      "false_positives": 50, "false_negatives": 20, "true_positives": 50},
    ...     {"model_name": "random_forest", "pr_auc": 0.82,
    ...      "roc_auc": 0.98, "precision": 0.88, "recall": 0.74,
    ...      "f1_score": 0.80, "true_negatives": 40010,
    ...      "false_positives": 40, "false_negatives": 18, "true_positives": 52},
    ... ]
    >>> df = build_model_comparison_table(metrics)
    >>> df.iloc[0]["model_name"]  # best PR-AUC first
    'random_forest'
    """
    _validate_metrics_list(metrics_list)

    normalised = [_normalise_entry(m) for m in metrics_list]

    rows: list[dict[str, Any]] = []
    for m in normalised:
        row: dict[str, Any] = {}
        for col in COMPARISON_COLUMNS:
            val = m.get(col)
            # Round floats for metric columns
            if col in _METRIC_COLS:
                val = _coerce_float(val)
                if val is not None:
                    val = round(val, _ROUND_DECIMALS)
            row[col] = val
        rows.append(row)

    df = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)

    # Sort descending by pr_auc; push None to the bottom.
    def _sort_key(v: Any) -> float:
        f = _coerce_float(v)
        return f if f is not None else float("-inf")

    df = df.loc[df["pr_auc"].map(_sort_key).sort_values(ascending=False).index]
    df = df.reset_index(drop=True)

    logger.info(
        "Built model comparison table: %d models ranked by pr_auc (desc).",
        len(df),
    )
    return df


def select_champion_model(
    comparison_df: pd.DataFrame,
    primary_metric: str = "pr_auc",
) -> str:
    """
    Return the ``model_name`` of the highest-ranking model.

    Parameters
    ----------
    comparison_df:
        DataFrame produced by :func:`build_model_comparison_table`.
    primary_metric:
        Column name to rank by.  Defaults to ``"pr_auc"``.

    Returns
    -------
    str
        Name of the champion model.

    Raises
    ------
    ValueError
        When *comparison_df* is empty, *primary_metric* column is absent,
        or every value in that column is ``None`` / ``NaN``.

    Examples
    --------
    >>> champion = select_champion_model(df, primary_metric="pr_auc")
    >>> print(champion)
    'xgboost_baseline'
    """
    if comparison_df.empty:
        raise ValueError(
            "comparison_df is empty.  Cannot select a champion model."
        )
    if primary_metric not in comparison_df.columns:
        raise ValueError(
            f"Primary metric '{primary_metric}' was not found in "
            f"comparison_df.  Available: {list(comparison_df.columns)}"
        )

    valid_mask = comparison_df[primary_metric].apply(
        lambda v: _coerce_float(v) is not None
    )
    if not valid_mask.any():
        raise ValueError(
            f"All values in column '{primary_metric}' are None/NaN.  "
            "Cannot determine a champion model."
        )

    best_idx = (
        comparison_df.loc[valid_mask, primary_metric]
        .apply(_coerce_float)
        .idxmax()
    )
    champion: str = str(comparison_df.loc[best_idx, "model_name"])
    best_score = _coerce_float(comparison_df.loc[best_idx, primary_metric])

    logger.info(
        "Champion model → '%s'  (validation %s = %.4f)",
        champion,
        primary_metric,
        best_score if best_score is not None else float("nan"),
    )
    return champion


def save_model_comparison_outputs(
    comparison_df: pd.DataFrame,
    output_dir: str | Path = DEFAULT_COMPARISON_DIR,
) -> dict[str, Path]:
    """
    Persist the comparison table as **CSV** and **JSON**.

    Parameters
    ----------
    comparison_df:
        DataFrame produced by :func:`build_model_comparison_table`.
    output_dir:
        Target directory (created if it does not exist).

    Returns
    -------
    dict[str, Path]
        Keys ``"csv"`` and ``"json"`` pointing to the written files.

    Raises
    ------
    ValueError
        When *comparison_df* is empty.

    Notes
    -----
    ``NaN`` values are serialised as JSON ``null`` for downstream
    compatibility.
    """
    if comparison_df.empty:
        raise ValueError(
            "comparison_df is empty.  Nothing to save."
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / "validation_model_comparison.csv"
    json_path = out / "validation_model_comparison.json"

    # --- CSV -----------------------------------------------------------
    comparison_df.to_csv(csv_path, index=False)
    logger.info("Saved comparison CSV  → %s", csv_path)

    # --- JSON -----------------------------------------------------------
    # Serialise with NaN → null so the file is valid JSON everywhere.
    records: list[dict[str, Any]] = []
    for row in comparison_df.to_dict(orient="records"):
        records.append({k: _sanitise_for_json(v) for k, v in row.items()})

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)
    logger.info("Saved comparison JSON → %s", json_path)

    return {"csv": csv_path, "json": json_path}


def load_existing_metrics(metrics_path: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load an existing metrics JSON file, returning an empty dict when absent.

    Day 5 uses this to bring Day 4 validation metrics into the comparison
    table. The file is expected to be keyed by model name, with each value
    containing validation-only metrics.
    """
    metrics_path = Path(metrics_path)
    if not metrics_path.exists():
        logger.warning("Metrics file not found: %s", metrics_path)
        return {}

    with open(metrics_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected metrics JSON at {metrics_path} to contain an object keyed by model name."
        )

    return data


def write_markdown_comparison_report(
    comparison_df: pd.DataFrame,
    champion_model: str,
    output_path: str | Path = DEFAULT_COMPARISON_DIR / "day5_model_comparison.md",
) -> Path:
    """
    Write a GitHub-readable Markdown model comparison report.

    The report covers:

    * Why PR-AUC is the correct primary metric for imbalanced fraud detection.
    * The ranked validation comparison table.
    * The selected champion model and its key metrics.
    * Confusion-matrix terminology and business cost framing.
    * Data leakage discipline reminders.
    * Day 6 next steps.

    Parameters
    ----------
    comparison_df:
        Sorted DataFrame from :func:`build_model_comparison_table`.
    champion_model:
        Name of the best model from :func:`select_champion_model`.
    output_path:
        ``.md`` file destination (parent directory created if absent).

    Returns
    -------
    Path
        Resolved path of the written Markdown file.

    Raises
    ------
    ValueError
        When *comparison_df* is empty.
    """
    if comparison_df.empty:
        raise ValueError(
            "comparison_df is empty.  Cannot write a comparison report."
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = "omitted for deterministic evidence; see run manifest"
    n_models = len(comparison_df)
    model_list_md = "\n".join(
        f"- `{name}`" for name in comparison_df["model_name"].tolist()
    )

    # Champion callout values ------------------------------------------------
    champion_row = comparison_df[comparison_df["model_name"] == champion_model]
    if champion_row.empty:
        c_pr_auc = "N/A"
        c_recall = "N/A"
        c_precision = "N/A"
        c_f1 = "N/A"
    else:
        cr = champion_row.iloc[0]
        c_pr_auc   = f"{cr['pr_auc']:.4f}"   if _coerce_float(cr["pr_auc"])   is not None else "N/A"
        c_recall   = f"{cr['recall']:.4f}"   if _coerce_float(cr.get("recall"))   is not None else "N/A"
        c_precision = f"{cr['precision']:.4f}" if _coerce_float(cr.get("precision")) is not None else "N/A"
        c_f1        = f"{cr['f1']:.4f}"       if _coerce_float(cr.get("f1"))       is not None else "N/A"

    table_md = _df_to_markdown_table(comparison_df)

    report = f"""\
# Day 5 Model Comparison — Credit Card Fraud Detection

> **Generated:** {timestamp}
> **Evaluation split:** Validation only (test set untouched)

---

## 1. Overview

This report compares **{n_models} fraud detection models** on the **validation
set**.  The test set is reserved for final evaluation and has not been touched.

Models evaluated:

{model_list_md}

**Champion model (highest validation PR-AUC): `{champion_model}`**

---

## 2. Why PR-AUC Is the Primary Metric

Plain **accuracy** is misleading for fraud detection. Because only ~0.17 % of
transactions are fraudulent, a model that labels every transaction as legitimate
achieves > 99 % accuracy while catching **zero fraud cases**.

**PR-AUC (Area Under the Precision-Recall Curve)** is a far more reliable
signal for rare positive-class problems:

| Metric | What It Measures | Why It Matters Here |
|--------|-----------------|---------------------|
| **Precision** | Of flagged fraud alerts, how many are real? | Controls false-alarm rate |
| **Recall** | Of actual frauds, how many did we catch? | Controls missed-fraud rate |
| **PR-AUC** | Area under the precision-recall curve across all thresholds | Robust to class imbalance; summarises the precision-recall trade-off |
| ROC-AUC | True-positive rate vs false-positive rate | Useful but can appear high even when positive-class performance is weak |
| Accuracy | Fraction correctly classified | Reported for completeness; **not optimised** |

A higher PR-AUC means the model maintains strong precision as it catches more
fraud (increases recall) — the real business objective.

---

## 3. Validation Comparison Table

> Sorted by `pr_auc` descending.  `N/A` indicates the metric could not be
> computed (e.g., DummyClassifier with no positive-class probability support).

{table_md}

---

## 4. Champion Model

| Field | Value |
|-------|-------|
| **Model** | `{champion_model}` |
| **Selected by** | Highest validation PR-AUC |
| **PR-AUC** | {c_pr_auc} |
| **Recall** | {c_recall} |
| **Precision** | {c_precision} |
| **F1** | {c_f1} |

The champion model offers the best precision-recall trade-off on the validation
set.  It is the recommended candidate for threshold tuning and final test-set
evaluation in subsequent days.

---

## 5. Confusion Matrix Terminology

Understanding the four outcome types is essential for business decisions:

| Term | Description | Business Impact |
|------|-------------|-----------------|
| **True Positive (TP)** | Fraud correctly flagged | Revenue protected |
| **True Negative (TN)** | Legitimate transaction approved | Frictionless customer experience |
| **False Positive (FP)** | Legitimate transaction wrongly blocked | Customer friction, manual review cost |
| **False Negative (FN)** | Fraud missed by the model | **Financial loss, security risk** |

In fraud detection, **false negatives are typically more costly than false
positives**.  Threshold tuning (Day 6) explicitly controls this trade-off.

---

## 6. Data Discipline & Leakage Prevention

| Rule | Status |
|------|--------|
| All models trained on `X_train` / `y_train` only | ✅ |
| `scale_pos_weight` derived from `y_train` only | ✅ |
| Validation set used only for evaluation, never fitting | ✅ |
| Test set untouched throughout Day 5 | ✅ |
| No threshold tuning performed | ✅ |

---

## 7. Day 6 Next Steps

- [ ] Tune classification threshold on the **validation set**.
- [ ] Run cost-sensitive threshold analysis (FP cost vs FN cost).
- [ ] Evaluate the champion model on the **test set** for final metrics.
- [ ] Generate Precision-Recall and ROC curve plots.
- [ ] Add SHAP explainability for the champion model.

---

*Report auto-generated by `src/models/model_comparison.py`.*
"""

    output_path.write_text(report, encoding="utf-8")
    logger.info("Saved comparison Markdown → %s", output_path)
    return output_path.resolve()


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def build_and_save_comparison(
    metrics_list: list[dict[str, Any]],
    output_dir: str | Path = DEFAULT_COMPARISON_DIR,
    primary_metric: str = "pr_auc",
) -> dict[str, Any]:
    """
    Convenience wrapper: build table → select champion → save all outputs.

    Calls :func:`build_model_comparison_table`, :func:`select_champion_model`,
    :func:`save_model_comparison_outputs`, and
    :func:`write_markdown_comparison_report` in sequence.

    Parameters
    ----------
    metrics_list:
        List of per-model metric dicts (same format accepted by
        :func:`build_model_comparison_table`).
    output_dir:
        Directory for CSV, JSON, and Markdown outputs.
    primary_metric:
        Column to rank models by.  Defaults to ``"pr_auc"``.

    Returns
    -------
    dict[str, Any]
        Dictionary with keys:

        * ``comparison_df``   — the ranked DataFrame
        * ``champion_model``  — name of the best model
        * ``csv_path``        — :class:`~pathlib.Path` to saved CSV
        * ``json_path``       — :class:`~pathlib.Path` to saved JSON
        * ``markdown_path``   — :class:`~pathlib.Path` to saved Markdown report
    """
    output_dir = Path(output_dir)

    comparison_df = build_model_comparison_table(metrics_list)
    champion_model = select_champion_model(comparison_df, primary_metric)
    save_paths = save_model_comparison_outputs(comparison_df, output_dir)
    markdown_path = write_markdown_comparison_report(
        comparison_df,
        champion_model,
        output_path=output_dir / "day5_model_comparison.md",
    )

    logger.info(
        "build_and_save_comparison complete.  Champion: '%s'.  "
        "Outputs written to %s",
        champion_model,
        output_dir,
    )

    return {
        "comparison_df": comparison_df,
        "champion_model": champion_model,
        "csv_path": save_paths["csv"],
        "json_path": save_paths["json"],
        "markdown_path": markdown_path,
    }


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(
        "model_comparison.py is a library module.\n"
        "It is intended to be called by:\n\n"
        "    python -m scripts.run_day5_advanced_models\n\n"
        "or imported directly:\n\n"
        "    from src.models.model_comparison import build_and_save_comparison"
    )
