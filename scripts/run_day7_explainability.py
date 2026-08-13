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

from src.artifacts.bundle import load_verified_joblib
from src.preprocessing.feature_config import RANDOM_STATE
from src.utils.config import load_project_config

from src.explainability.shap_explainer import (
    build_shap_feature_importance,
    calculate_shap_values,
    plot_shap_summary_bar,
    sample_explanation_data,
    save_shap_outputs,
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
        3. Sample up to ``sample_size`` validation rows.
        4. Calculate SHAP values for the sample.
        5. Build mean absolute SHAP feature importance.
        6. Save feature importance as CSV and JSON.
        7. Save SHAP summary bar plots as PNG.
        8. Save a Markdown report explaining the top features.

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

    X_sample = sample_explanation_data(
        X_val, sample_size=sample_size, random_state=random_state
    )
    print(f"Sampled validation rows for SHAP: {len(X_sample)}")

    shap_values = calculate_shap_values(model, X_sample)
    print("Calculated SHAP values")

    feature_importance_df = build_shap_feature_importance(
        shap_values, feature_names=list(X_sample.columns)
    )

    shap_paths = save_shap_outputs(feature_importance_df, explainability_dir)
    print(f"Saved SHAP feature importance: {shap_paths['csv']}")
    print(f"Saved SHAP top features: {shap_paths['json']}")

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
        top_n=DEFAULT_SUMMARY_TOP_N,
    )
    print(f"Saved SHAP markdown report: {report_path}")

    return {
        "model_path": Path(model_path),
        "validation_rows": len(X_val),
        "sampled_rows": len(X_sample),
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
