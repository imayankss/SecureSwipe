"""
Day 5 runner: train the XGBoost advanced model and build a validation-only
model comparison report.

This script:
    1. Loads Day 3 processed train and validation data (never test data).
    2. Trains an XGBoost classifier on training data only.
    3. Evaluates the trained model on the validation set only, using
       probability scores for PR-AUC / ROC-AUC and the default 0.5
       threshold for precision, recall, and F1.
    4. Saves the trained model artifact.
    5. Saves XGBoost validation metrics.
    6. Loads existing Day 4 baseline metrics (dummy, logistic regression,
       random forest) if available and combines them with the Day 5
       XGBoost metrics into a single validation-only comparison table.
    7. Selects a champion model by highest validation PR-AUC.
    8. Saves the comparison table as CSV, JSON, and a Markdown report.

Run from the project root with:

    python -m scripts.run_day5_advanced_models

This script intentionally never loads or evaluates on the test set, does
not implement threshold tuning, plotting, or SHAP, and does not perform
risk scoring. Those are reserved for later days.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src.utils.config import load_project_config

# ---------------------------------------------------------------------------
# Project imports
#
# We try to reuse existing Day 3 / Day 4 / Day 5 utilities wherever they are
# available so this script does not duplicate logic that already lives
# elsewhere in the project. Each import is wrapped so the script still gives
# a clear, actionable error message if a dependency module is missing,
# rather than a deep traceback.
# ---------------------------------------------------------------------------

try:
    from src.models.advanced_models import (
        calculate_scale_pos_weight,
        save_model,
        train_xgboost_model,
    )
except ImportError as exc:  # pragma: no cover - exercised via integration run
    raise ImportError(
        "Could not import src.models.advanced_models. "
        "Make sure Day 5's advanced_models.py has been added to the project "
        "before running this script."
    ) from exc

try:
    from src.evaluation.classification_metrics import (
        evaluate_model,
        save_metrics_json,
    )
except ImportError as exc:  # pragma: no cover - exercised via integration run
    raise ImportError(
        "Could not import src.evaluation.classification_metrics. "
        "This module is expected to already exist from Day 4."
    ) from exc

try:
    from src.models.model_comparison import (
        build_model_comparison_table,
        load_existing_metrics,
        save_model_comparison_outputs,
        select_champion_model,
        write_markdown_comparison_report,
    )
except ImportError as exc:  # pragma: no cover - exercised via integration run
    raise ImportError(
        "Could not import src.models.model_comparison. "
        "Make sure Day 5's model_comparison.py has been added to the "
        "project before running this script."
    ) from exc

# Optional reuse of the Day 4 processed-data loader. Day 4's loader only
# ever reads train/val parquet files, so reusing it keeps this script from
# duplicating that logic while still guaranteeing the test set is never
# touched.
try:
    from scripts.run_day4_baseline_models import (
        load_processed_training_data as _load_day4_processed_data,
    )
except ImportError:
    _load_day4_processed_data = None


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

PROJECT_CONFIG = load_project_config()
DEFAULT_PROCESSED_DIR = PROJECT_CONFIG.data.processed_dir
DEFAULT_MODELS_DIR = PROJECT_CONFIG.artifacts.legacy_model_dir
DEFAULT_XGBOOST_MODEL_PATH = DEFAULT_MODELS_DIR / "xgboost_baseline.joblib"

CONFIGURED_METRICS_DIR = PROJECT_CONFIG.reports.metrics_dir
DEFAULT_DAY4_METRICS_PATH = CONFIGURED_METRICS_DIR / "day4_baseline_metrics.json"
DEFAULT_DAY5_METRICS_PATH = CONFIGURED_METRICS_DIR / "day5_xgboost_metrics.json"

DEFAULT_COMPARISON_DIR = Path("reports/model_comparison")
DEFAULT_COMPARISON_CSV_PATH = DEFAULT_COMPARISON_DIR / "validation_model_comparison.csv"
DEFAULT_COMPARISON_JSON_PATH = DEFAULT_COMPARISON_DIR / "validation_model_comparison.json"
DEFAULT_COMPARISON_REPORT_PATH = DEFAULT_COMPARISON_DIR / "day5_model_comparison.md"

XGBOOST_MODEL_NAME = "xgboost_baseline"

# Day 4 baseline model names, used to look up their metrics inside the Day 4
# metrics JSON file. These must match the keys produced by
# src.models.baseline_models.get_baseline_models().
DAY4_BASELINE_MODEL_NAMES = ("dummy_baseline", "logistic_regression", "random_forest")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the Day 5 advanced modeling runner.

    Returns:
        Parsed CLI arguments with sensible project-relative defaults.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Train the Day 5 XGBoost advanced model on training data, "
            "evaluate it on the validation set, and build a validation-only "
            "model comparison report."
        )
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory containing Day 3 processed train/validation parquet files.",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=DEFAULT_MODELS_DIR,
        help="Directory where the trained XGBoost model artifact will be saved.",
    )
    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=CONFIGURED_METRICS_DIR,
        help="Directory containing Day 4 metrics and where Day 5 metrics will be saved.",
    )
    parser.add_argument(
        "--comparison-dir",
        type=Path,
        default=DEFAULT_COMPARISON_DIR,
        help="Directory where model comparison outputs (CSV/JSON/Markdown) will be saved.",
    )
    parser.add_argument(
        "--day4-metrics-path",
        type=Path,
        default=None,
        help=(
            "Explicit path to the Day 4 baseline metrics JSON file. "
            "Defaults to <metrics-dir>/day4_baseline_metrics.json."
        ),
    )
    return parser.parse_args()


def load_train_val_data(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """
    Load Day 3 processed training and validation data only.

    This function deliberately never loads test data. If the Day 4
    processed-data loader is importable, it is reused directly since it
    already implements the same train/validation-only loading contract.
    Otherwise, a local fallback loader is used.

    Args:
        processed_dir: Directory containing the processed parquet files.

    Returns:
        Tuple of (X_train, y_train, X_val, y_val).

    Raises:
        FileNotFoundError: If any required parquet file is missing.
        ValueError: If the loaded data fails basic consistency checks.
    """
    if _load_day4_processed_data is not None:
        logger.info("Reusing Day 4 processed-data loader for train/validation data.")
        return _load_day4_processed_data(processed_dir)

    logger.info("Day 4 processed-data loader unavailable. Using local fallback loader.")
    processed_dir = Path(processed_dir)

    required_files = {
        "X_train": processed_dir / "X_train_processed.parquet",
        "X_val": processed_dir / "X_val_processed.parquet",
        "y_train": processed_dir / "y_train.parquet",
        "y_val": processed_dir / "y_val.parquet",
    }

    missing = [str(path) for path in required_files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing Day 3 processed data file(s): "
            + ", ".join(missing)
            + ". Run scripts/run_day3_preprocessing.py first."
        )

    x_train = pd.read_parquet(required_files["X_train"])
    x_val = pd.read_parquet(required_files["X_val"])
    y_train = pd.read_parquet(required_files["y_train"])["Class"]
    y_val = pd.read_parquet(required_files["y_val"])["Class"]

    if len(x_train) != len(y_train):
        raise ValueError("X_train and y_train row counts do not match.")
    if len(x_val) != len(y_val):
        raise ValueError("X_val and y_val row counts do not match.")
    if "Class" in x_train.columns or "Class" in x_val.columns:
        raise ValueError("Target column 'Class' must not be present in feature data.")

    return x_train, y_train, x_val, y_val


def _build_comparison_row(
    model_name: str,
    metrics: Dict[str, Any],
    validation_rows: int,
    validation_frauds: int,
) -> Dict[str, Any]:
    """
    Convert a single model's raw classification metrics dictionary into the
    standardized row format expected by the model comparison table.

    Args:
        model_name: Name of the model the metrics belong to.
        metrics: Output of calculate_binary_classification_metrics /
            evaluate_model, containing keys such as precision, recall,
            f1_score, roc_auc, and pr_auc.
        validation_rows: Total number of rows in the validation set used.
        validation_frauds: Total number of fraud rows in the validation set.

    Returns:
        Dictionary with the standardized comparison columns: model_name,
        pr_auc, roc_auc, precision, recall, f1, validation_rows,
        validation_frauds.
    """
    return {
        "model_name": model_name,
        "pr_auc": metrics.get("pr_auc"),
        "roc_auc": metrics.get("roc_auc"),
        "precision": metrics.get("precision"),
        "recall": metrics.get("recall"),
        "f1": metrics.get("f1_score", metrics.get("f1")),
        "validation_rows": validation_rows,
        "validation_frauds": validation_frauds,
    }


def build_day5_comparison_rows(
    xgboost_metrics: Dict[str, Any],
    day4_metrics_path: str | Path,
    validation_rows: int,
    validation_frauds: int,
) -> list[Dict[str, Any]]:
    """
    Build the list of standardized comparison rows for Day 5.

    Combines the Day 5 XGBoost validation metrics with any Day 4 baseline
    metrics (dummy, logistic regression, random forest) that can be found
    on disk. Missing Day 4 metrics are skipped with a warning rather than
    causing the script to fail, since Day 5 should still be able to run
    even if the Day 4 metrics file is unavailable.

    Args:
        xgboost_metrics: Validation metrics for the Day 5 XGBoost model.
        day4_metrics_path: Path to the Day 4 baseline metrics JSON file.
        validation_rows: Total number of rows in the validation set.
        validation_frauds: Total number of fraud rows in the validation set.

    Returns:
        List of standardized comparison row dictionaries.
    """
    rows: list[Dict[str, Any]] = []

    day4_metrics = load_existing_metrics(day4_metrics_path)
    if not day4_metrics:
        logger.warning(
            "No Day 4 baseline metrics found at %s. "
            "The comparison report will only include the Day 5 XGBoost model.",
            day4_metrics_path,
        )

    for baseline_name in DAY4_BASELINE_MODEL_NAMES:
        baseline_metrics = day4_metrics.get(baseline_name)
        if baseline_metrics is None:
            logger.warning("Day 4 metrics for '%s' were not found. Skipping.", baseline_name)
            continue
        rows.append(
            _build_comparison_row(
                baseline_name, baseline_metrics, validation_rows, validation_frauds
            )
        )

    rows.append(
        _build_comparison_row(
            XGBOOST_MODEL_NAME, xgboost_metrics, validation_rows, validation_frauds
        )
    )

    return rows


def run_day5_advanced_models(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    models_dir: str | Path = DEFAULT_MODELS_DIR,
    metrics_dir: str | Path = CONFIGURED_METRICS_DIR,
    comparison_dir: str | Path = DEFAULT_COMPARISON_DIR,
    day4_metrics_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Run the full Day 5 advanced modeling workflow.

    Steps:
        1. Load Day 3 processed train/validation data (no test data).
        2. Calculate scale_pos_weight from y_train only.
        3. Train XGBoost on training data only.
        4. Evaluate XGBoost on the validation set only.
        5. Save the trained XGBoost model artifact.
        6. Save XGBoost validation metrics.
        7. Build a validation-only comparison table against Day 4 baselines.
        8. Select the champion model by highest validation PR-AUC.
        9. Save comparison outputs as CSV, JSON, and Markdown.

    Args:
        processed_dir: Directory containing Day 3 processed parquet files.
        models_dir: Directory where the XGBoost model artifact is saved.
        metrics_dir: Directory containing Day 4 metrics and where Day 5
            metrics are saved.
        comparison_dir: Directory where comparison outputs are saved.
        day4_metrics_path: Optional explicit path to the Day 4 metrics
            JSON file. Defaults to <metrics_dir>/day4_baseline_metrics.json.

    Returns:
        Dictionary summarizing the run, including dataset shapes, the
        trained model path, validation metrics, the comparison table, the
        champion model name, and all output paths.
    """
    metrics_dir = Path(metrics_dir)
    if day4_metrics_path is None:
        day4_metrics_path = metrics_dir / "day4_baseline_metrics.json"

    print("Day 5 Advanced Modeling Started")

    # Step 1: load train/validation data only.
    x_train, y_train, x_val, y_val = load_train_val_data(processed_dir)
    print(f"Loaded train rows: {len(x_train)}")
    print(f"Loaded validation rows: {len(x_val)}")

    # Step 2 + 3: calculate scale_pos_weight and train XGBoost on train only.
    scale_pos_weight = calculate_scale_pos_weight(y_train)
    print(f"Calculated scale_pos_weight: {scale_pos_weight:.4f}")

    print("Training XGBoost...")
    xgboost_model = train_xgboost_model(x_train, y_train)

    # Step 4: evaluate on validation data only.
    print("Evaluating on validation set...")
    xgboost_metrics = evaluate_model(xgboost_model, x_val, y_val)

    # Step 5: save the trained model artifact.
    model_path = Path(models_dir) / f"{XGBOOST_MODEL_NAME}.joblib"
    save_model(xgboost_model, model_path)
    print(f"Saved model: {model_path}")

    # Step 6: save XGBoost validation metrics.
    day5_metrics_path = metrics_dir / "day5_xgboost_metrics.json"
    save_metrics_json({XGBOOST_MODEL_NAME: xgboost_metrics}, day5_metrics_path)

    # Step 7: build the validation-only comparison table.
    validation_rows = int(len(y_val))
    validation_frauds = int(y_val.sum())
    comparison_rows = build_day5_comparison_rows(
        xgboost_metrics, day4_metrics_path, validation_rows, validation_frauds
    )
    comparison_df = build_model_comparison_table(comparison_rows)

    # Step 8: select the champion model by highest validation PR-AUC.
    champion_model = select_champion_model(comparison_df, primary_metric="pr_auc")

    # Step 9: save comparison outputs as CSV, JSON, and Markdown.
    comparison_paths = save_model_comparison_outputs(comparison_df, comparison_dir)
    report_path = write_markdown_comparison_report(
        comparison_df,
        champion_model,
        Path(comparison_dir) / "day5_model_comparison.md",
    )
    print(f"Saved comparison report: {report_path}")

    print("Day 5 Advanced Modeling Completed")

    return {
        "dataset_shapes": {
            "X_train": tuple(x_train.shape),
            "X_val": tuple(x_val.shape),
        },
        "scale_pos_weight": scale_pos_weight,
        "xgboost_metrics": xgboost_metrics,
        "model_path": model_path,
        "day5_metrics_path": day5_metrics_path,
        "comparison_df": comparison_df,
        "champion_model": champion_model,
        "comparison_paths": comparison_paths,
        "report_path": report_path,
    }


def print_success_message(results: Dict[str, Any]) -> None:
    """
    Print a clean, human-readable summary of a successful Day 5 run.

    Args:
        results: The dictionary returned by run_day5_advanced_models.
    """
    print()
    print("Day 5 advanced modeling completed successfully.")
    print(f"Train shape: {results['dataset_shapes']['X_train']}")
    print(f"Validation shape: {results['dataset_shapes']['X_val']}")
    print(f"scale_pos_weight (train-only): {results['scale_pos_weight']:.4f}")
    print(f"XGBoost model saved to: {results['model_path']}")
    print(f"XGBoost validation metrics saved to: {results['day5_metrics_path']}")
    print(f"Champion model (highest validation PR-AUC): {results['champion_model']}")
    print(f"Comparison CSV: {results['comparison_paths'].get('csv')}")
    print(f"Comparison JSON: {results['comparison_paths'].get('json')}")
    print(f"Comparison report: {results['report_path']}")
    print("Note: the test set was not loaded or evaluated during this run.")


def main() -> None:
    """
    Command-line entry point for the Day 5 advanced modeling runner.

    Parses arguments, runs the full pipeline, prints a success summary,
    and exits with a non-zero status code on failure.
    """
    print(
        "Direct unmanifested execution is disabled. Use "
        "`python scripts/run_reference_stage.py --stage day5 --output-dir <new-dir>`. ",
        file=sys.stderr,
    )
    raise SystemExit(2)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        results = run_day5_advanced_models(
            processed_dir=args.processed_dir,
            models_dir=args.models_dir,
            metrics_dir=args.metrics_dir,
            comparison_dir=args.comparison_dir,
            day4_metrics_path=args.day4_metrics_path,
        )
        print_success_message(results)
    except FileNotFoundError as exc:
        logger.error("Required file was not found: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logger.error("Invalid data or configuration: %s", exc)
        sys.exit(1)
    except ImportError as exc:
        logger.error("A required module could not be imported: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - top-level CLI safety net
        logger.error("Unexpected error during Day 5 advanced modeling: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
