"""Day 7 runner: SHAP explainability for the champion XGBoost model.

This script generates SHAP-based explanations for the Day 5 champion
model using a small sample of validation data. It does not retrain
the model, tune hyperparameters, or touch the test set.

Run from the repo root:

    python3 -m scripts.run_day7_explainability
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

from src.artifacts.bundle import load_verified_joblib
from src.preprocessing.feature_config import RANDOM_STATE
from src.utils.config import load_project_config

from src.explainability.shap_explainer import (
    build_cohort_feature_importance,
    build_explanation_cohort,
    build_shap_feature_importance,
    calculate_verified_shap_explanation,
    plot_shap_summary_bar,
    save_shap_cohort_evidence,
    save_shap_outputs,
    summarize_explanation_cohort,
    write_shap_markdown_report,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

PROJECT_CONFIG = load_project_config()
DEFAULT_MODEL_PATH = PROJECT_CONFIG.artifacts.legacy_model_dir / "xgboost_baseline.joblib"
DEFAULT_PROCESSED_DIR = PROJECT_CONFIG.data.processed_dir
DEFAULT_EXPLAINABILITY_DIR = Path("reports/explainability")
DEFAULT_FIGURES_DIR = PROJECT_CONFIG.reports.figures_dir
DEFAULT_SAMPLE_SIZE = 1000
DEFAULT_RANDOM_STATE = RANDOM_STATE
DEFAULT_SUMMARY_TOP_N = 20
DEFAULT_TOP_FEATURES_TOP_N = 10


def load_champion_model(model_path: str | Path = DEFAULT_MODEL_PATH) -> Any:
    """Load the Day 5 champion XGBoost model.

    Args:
        model_path: Path to the saved model artifact.

    Returns:
        The loaded model object.

    Raises:
        FileNotFoundError: If the model artifact does not exist.
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Champion model not found at {model_path}. "
            "Run Day 5 (scripts/run_day5_advanced_models.py) first to "
            "train and save the XGBoost model."
        )

    model = load_verified_joblib(
        model_path,
        trusted_root=Path(__file__).resolve().parents[1] / "artifacts",
        required_attributes=("predict_proba",),
    )
    logger.info("Loaded champion model from %s.", model_path)
    return model


def load_validation_features(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
) -> pd.DataFrame:
    """Load the Day 3 processed validation feature matrix only.

    This intentionally loads validation features only. It never reads
    test-set files, since SHAP explanation must not touch the test
    set reserved for Day 7's final locked evaluation.

    Args:
        processed_dir: Directory containing Day 3 processed parquet
            files.

    Returns:
        The validation feature DataFrame (X_val_processed).

    Raises:
        FileNotFoundError: If the validation features file is missing.
        ValueError: If the target column is present in the features.
    """
    processed_dir = Path(processed_dir)
    x_val_path = processed_dir / "X_val_processed.parquet"

    if not x_val_path.exists():
        raise FileNotFoundError(
            f"Validation features not found at {x_val_path}. "
            "Run Day 3 (scripts/run_day3_preprocessing.py) first to "
            "generate processed data splits."
        )

    X_val = pd.read_parquet(x_val_path)

    if "Class" in X_val.columns:
        raise ValueError(
            "Class column must not be present in validation features. "
            "Check the Day 3 preprocessing output for leakage."
        )

    logger.info("Loaded validation features with shape %s.", X_val.shape)
    return X_val


def load_validation_labels(processed_dir: str | Path = DEFAULT_PROCESSED_DIR) -> pd.Series:
    """Load finite binary validation labels for explicit cohort composition."""
    path = Path(processed_dir) / "y_val.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"Validation labels not found at {path}.")
    frame = pd.read_parquet(path)
    if list(frame.columns) != ["Class"]:
        raise ValueError("y_val.parquet must contain exactly the Class column.")
    labels = frame["Class"]
    numeric = pd.to_numeric(labels, errors="raise").to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or not set(np.unique(numeric)).issubset({0.0, 1.0}):
        raise ValueError("Validation labels must contain only finite binary values.")
    return pd.Series(numeric.astype(int), index=labels.index, name="Class")


def generate_validation_raw_scores(model: Any, features: pd.DataFrame) -> np.ndarray:
    """Return bounded class scores without describing them as probabilities."""
    scores = np.asarray(model.predict_proba(features), dtype=float)
    if scores.ndim != 2 or scores.shape != (len(features), 2):
        raise ValueError("Champion model predict_proba must return two columns.")
    positive_scores = scores[:, 1]
    if not np.isfinite(positive_scores).all() or np.logical_or(
        positive_scores < 0, positive_scores > 1
    ).any():
        raise ValueError("Champion model returned an invalid bounded raw score.")
    return positive_scores


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Day 7 SHAP runner."""
    parser = argparse.ArgumentParser(
        description="Run Day 7 SHAP explainability for the champion model."
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=str(DEFAULT_MODEL_PATH),
        help="Path to the champion model artifact.",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default=str(DEFAULT_PROCESSED_DIR),
        help="Directory containing Day 3 processed validation features.",
    )
    parser.add_argument(
        "--explainability-dir",
        type=str,
        default=str(DEFAULT_EXPLAINABILITY_DIR),
        help="Directory to save SHAP CSV/JSON/Markdown outputs.",
    )
    parser.add_argument(
        "--figures-dir",
        type=str,
        default=str(DEFAULT_FIGURES_DIR),
        help="Directory to save SHAP plot PNG outputs.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="Maximum number of validation rows to sample for SHAP.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=DEFAULT_RANDOM_STATE,
        help="Random seed used for sampling validation rows.",
    )
    return parser.parse_args()


def run_day7_explainability(
    model_path: str | Path = DEFAULT_MODEL_PATH,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    explainability_dir: str | Path = DEFAULT_EXPLAINABILITY_DIR,
    figures_dir: str | Path = DEFAULT_FIGURES_DIR,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> dict[str, Any]:
    """Run the full Day 7 SHAP explainability workflow.

    Workflow:
        1. Load the champion XGBoost model.
        2. Load validation features (validation data only).
        3. Load aligned validation labels and compute uncalibrated raw scores.
        4. Select disjoint fraud/high-score/representative explanation cohorts.
        5. Calculate raw-margin SHAP values and prove additivity.
        6. Build combined and per-cohort mean absolute SHAP importance.
        7. Save aggregate evidence, importance tables, plots, and a report.

    Args:
        model_path: Path to the champion model artifact.
        processed_dir: Directory containing Day 3 processed data.
        explainability_dir: Directory for CSV/JSON/Markdown outputs.
        figures_dir: Directory for PNG plot outputs.
        sample_size: Maximum validation rows to sample for SHAP.
        random_state: Random seed for sampling.

    Returns:
        A dictionary summarizing the run, including paths to all
        generated outputs.
    """
    explainability_dir = Path(explainability_dir)
    figures_dir = Path(figures_dir)

    print("Day 7 SHAP Explainability Started")

    model = load_champion_model(model_path)
    print(f"Loaded model: {model_path}")

    X_val = load_validation_features(processed_dir)
    print(f"Loaded validation rows: {len(X_val)}")
    y_val = load_validation_labels(processed_dir)
    if len(X_val) != len(y_val) or not X_val.index.equals(y_val.index):
        raise ValueError("Validation features and labels must have identical aligned row indexes.")
    validation_scores = generate_validation_raw_scores(model, X_val)

    cohort = build_explanation_cohort(
        X_val,
        y_val,
        validation_scores,
        sample_size=sample_size,
        random_state=random_state,
    )
    print(f"Selected validation rows for SHAP: {len(cohort.features)}")

    explanation = calculate_verified_shap_explanation(model, cohort.features)
    print(
        "Verified SHAP raw-margin additivity: "
        f"max_abs_error={explanation.max_abs_additivity_error:.9g}"
    )

    feature_importance_df = build_shap_feature_importance(
        explanation.values, feature_names=list(cohort.features.columns)
    )
    cohort_summary = summarize_explanation_cohort(cohort)
    cohort_importance = build_cohort_feature_importance(
        explanation,
        list(cohort.features.columns),
        cohort.cohort_names,
    )

    shap_paths = save_shap_outputs(feature_importance_df, explainability_dir)
    print(f"Saved SHAP feature importance: {shap_paths['csv']}")
    print(f"Saved SHAP top features: {shap_paths['json']}")
    cohort_evidence_path = save_shap_cohort_evidence(
        explanation,
        cohort_summary,
        cohort_importance,
        explainability_dir,
    )
    print(f"Saved SHAP cohort evidence: {cohort_evidence_path}")

    summary_bar_path = figures_dir / "shap_summary_bar.png"
    plot_shap_summary_bar(
        feature_importance_df,
        summary_bar_path,
        top_n=DEFAULT_SUMMARY_TOP_N,
    )
    print(f"Saved SHAP summary bar plot: {summary_bar_path}")

    top_features_plot_path = figures_dir / "shap_top_features.png"
    plot_shap_summary_bar(
        feature_importance_df,
        top_features_plot_path,
        top_n=DEFAULT_TOP_FEATURES_TOP_N,
    )
    print(f"Saved SHAP top features plot: {top_features_plot_path}")

    report_path = explainability_dir / "shap_summary_report.md"
    write_shap_markdown_report(
        feature_importance_df,
        report_path,
        explanation=explanation,
        cohort_summary=cohort_summary,
        cohort_importance=cohort_importance,
        top_n=DEFAULT_SUMMARY_TOP_N,
    )
    print(f"Saved SHAP markdown report: {report_path}")

    return {
        "model_path": Path(model_path),
        "validation_rows": len(X_val),
        "sampled_rows": len(cohort.features),
        "shap_output": explanation.output_name,
        "max_abs_additivity_error": explanation.max_abs_additivity_error,
        "cohort_summary": cohort_summary,
        "cohort_evidence_json": cohort_evidence_path,
        "feature_importance_csv": shap_paths["csv"],
        "feature_importance_json": shap_paths["json"],
        "summary_bar_plot": summary_bar_path,
        "top_features_plot": top_features_plot_path,
        "report_path": report_path,
        "top_features": feature_importance_df.head(DEFAULT_SUMMARY_TOP_N),
    }


def print_success_message(results: dict[str, Any]) -> None:
    """Print a clean success summary after the Day 7 SHAP run.

    Args:
        results: The dictionary returned by run_day7_explainability.
    """
    print("\nDay 7 SHAP Explainability Completed")
    print(f"Model used: {results['model_path']}")
    print(f"Validation rows available: {results['validation_rows']}")
    print(f"Validation rows sampled for SHAP: {results['sampled_rows']}")
    print(f"SHAP model output: {results['shap_output']}")
    print(f"Maximum additivity error: {results['max_abs_additivity_error']:.9g}")
    print(f"Cohort evidence JSON: {results['cohort_evidence_json']}")
    print(f"Feature importance CSV: {results['feature_importance_csv']}")
    print(f"Feature importance JSON: {results['feature_importance_json']}")
    print(f"Summary bar plot: {results['summary_bar_plot']}")
    print(f"Top features plot: {results['top_features_plot']}")
    print(f"Markdown report: {results['report_path']}")
    print(
        "Note: SHAP was used for explanation only. The model was not "
        "retuned, retrained, or modified. The test set was not used."
    )


def main() -> None:
    """Parse arguments, run the Day 7 SHAP pipeline, and report results."""
    print(
        "Direct unmanifested execution is disabled. Use "
        "`python scripts/run_reference_stage.py --stage day7 --output-dir <new-dir>`. ",
        file=sys.stderr,
    )
    raise SystemExit(2)

    args = parse_args()

    try:
        results = run_day7_explainability(
            model_path=args.model_path,
            processed_dir=args.processed_dir,
            explainability_dir=args.explainability_dir,
            figures_dir=args.figures_dir,
            sample_size=args.sample_size,
            random_state=args.random_state,
        )
        print_success_message(results)
    except FileNotFoundError as exc:
        logger.error("Required file not found: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logger.error("Invalid data encountered: %s", exc)
        sys.exit(1)
    except ImportError as exc:
        logger.error("Missing dependency: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error during Day 7 SHAP run: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
