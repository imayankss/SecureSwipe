"""Day 6 runner: validation-only threshold tuning and curve analysis.

This script loads the Day 5 champion XGBoost model, generates fraud
probabilities on the validation set only, builds a threshold metrics
table, selects business-relevant operating thresholds, and produces
precision-recall/ROC curves, confusion matrix plots, and a Markdown
report.

The test set is never loaded or referenced in this script.

Run from the repository root with:

    python3 -m scripts.run_day6_threshold_tuning
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

# Ensure the repository root is importable when this script is executed
# directly (e.g. python3 scripts/run_day6_threshold_tuning.py) as well as
# via -m (e.g. python3 -m scripts.run_day6_threshold_tuning).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.evaluation.threshold_tuning import (  # noqa: E402
    build_threshold_metrics_table,
    calculate_threshold_metrics,
    select_best_f1_threshold,
    select_recall_target_threshold,
    save_threshold_outputs,
)
from src.evaluation.curves import (  # noqa: E402
    plot_precision_recall_curve,
    plot_roc_curve,
)
from src.evaluation.confusion_analysis import (  # noqa: E402
    plot_confusion_matrix,
)
from src.artifacts.bundle import load_verified_joblib  # noqa: E402
from src.utils.config import load_project_config  # noqa: E402

PROJECT_CONFIG = load_project_config()
DEFAULT_MODEL_PATH = PROJECT_CONFIG.artifacts.legacy_model_dir / "xgboost_baseline.joblib"
DEFAULT_PROCESSED_DIR = PROJECT_CONFIG.data.processed_dir
DEFAULT_THRESHOLD_DIR = PROJECT_CONFIG.reports.threshold_dir
DEFAULT_FIGURES_DIR = PROJECT_CONFIG.reports.figures_dir
DEFAULT_REPORT_PATH = Path("reports/threshold_tuning/day6_threshold_tuning_report.md")
DEFAULT_MIN_RECALL = PROJECT_CONFIG.evaluation.recall_target
DEFAULT_THRESHOLD = PROJECT_CONFIG.evaluation.default_threshold


def load_champion_model(model_path: Path) -> Any:
    """Load the Day 5 champion model artifact.

    Args:
        model_path: Path to the saved joblib model artifact.

    Returns:
        The loaded model object.

    Raises:
        FileNotFoundError: If the model artifact does not exist.
    """
    if not model_path.exists():
        raise FileNotFoundError(
            f"Champion model not found at {model_path}. "
            "Please run Day 5 (scripts/run_day5_advanced_models.py) first."
        )
    return load_verified_joblib(
        model_path,
        trusted_root=_REPO_ROOT / "artifacts",
        required_attributes=("predict_proba",),
    )


def load_validation_data(processed_dir: Path) -> tuple[pd.DataFrame, pd.Series]:
    """Load validation features and labels produced on Day 3.

    Args:
        processed_dir: Directory containing the Day 3 processed parquet
            files.

    Returns:
        Tuple of (X_val, y_val) where y_val is a Series named "Class".

    Raises:
        FileNotFoundError: If either required parquet file is missing.
        ValueError: If row counts mismatch, the target leaks into the
            features, or only one class is present in y_val.
    """
    x_val_path = processed_dir / "X_val_processed.parquet"
    y_val_path = processed_dir / "y_val.parquet"

    if not x_val_path.exists():
        raise FileNotFoundError(
            f"Validation features not found at {x_val_path}. "
            "Please run Day 3 (scripts/run_day3_preprocessing.py) first."
        )
    if not y_val_path.exists():
        raise FileNotFoundError(
            f"Validation labels not found at {y_val_path}. "
            "Please run Day 3 (scripts/run_day3_preprocessing.py) first."
        )

    x_val = pd.read_parquet(x_val_path)
    y_val_df = pd.read_parquet(y_val_path)

    if "Class" not in y_val_df.columns:
        raise ValueError(f"Expected a 'Class' column in {y_val_path}.")
    y_val = y_val_df["Class"]

    if len(x_val) != len(y_val):
        raise ValueError(
            "Validation feature and label row counts do not match. "
            f"X_val rows={len(x_val)}, y_val rows={len(y_val)}."
        )

    if "Class" in x_val.columns:
        raise ValueError("Target column 'Class' must not be present in validation features.")

    unique_labels = set(y_val.unique().tolist())
    if not unique_labels.issubset({0, 1}) or len(unique_labels) < 2:
        raise ValueError(
            "Validation labels must contain both classes (0 and 1). "
            f"Found: {sorted(unique_labels)}."
        )

    return x_val, y_val


def generate_validation_probabilities(model: Any, x_val: pd.DataFrame) -> np.ndarray:
    """Generate fraud probabilities for the validation set.

    Args:
        model: A fitted classifier exposing predict_proba.
        x_val: Validation feature matrix.

    Returns:
        1D numpy array of probabilities for the positive (fraud) class.

    Raises:
        AttributeError: If the model does not expose predict_proba.
    """
    if not hasattr(model, "predict_proba"):
        raise AttributeError(
            "The loaded champion model does not implement predict_proba, "
            "which is required to generate fraud probabilities."
        )
    return model.predict_proba(x_val)[:, 1]


def select_operating_thresholds(
    y_val: pd.Series,
    y_val_proba: np.ndarray,
    threshold_table: pd.DataFrame,
    min_recall: float = DEFAULT_MIN_RECALL,
) -> Dict[str, Dict[str, Any]]:
    """Select default, best-F1, and recall-target operating thresholds.

    Args:
        y_val: Validation ground-truth labels.
        y_val_proba: Validation fraud probabilities.
        threshold_table: Metrics table produced by
            build_threshold_metrics_table.
        min_recall: Minimum recall required for the recall-target
            threshold. Defaults to the configured development recall target.

    Returns:
        Dictionary with keys "default", "best_f1", and "recall_target",
        each mapping to a metrics dictionary.
    """
    default_metrics = calculate_threshold_metrics(
        y_val, y_val_proba, threshold=DEFAULT_THRESHOLD
    )
    best_f1_metrics = select_best_f1_threshold(threshold_table)
    recall_target_metrics = select_recall_target_threshold(
        threshold_table, min_recall=min_recall
    )

    return {
        "default": default_metrics,
        "best_f1": best_f1_metrics,
        "recall_target": {
            **recall_target_metrics,
            "evaluation_scope": PROJECT_CONFIG.evaluation.development_scope,
            "minimum_recall": float(min_recall),
            "selection_method": "highest_precision_meeting_recall_target",
        },
    }


def generate_curve_outputs(
    y_val: pd.Series,
    y_val_proba: np.ndarray,
    figures_dir: Path,
) -> Dict[str, Path]:
    """Generate and save the precision-recall and ROC curves.

    Args:
        y_val: Validation ground-truth labels.
        y_val_proba: Validation fraud probabilities.
        figures_dir: Directory in which to save curve PNG files.

    Returns:
        Dictionary mapping "precision_recall_curve" and "roc_curve" to
        their saved Path objects.
    """
    pr_curve_path = plot_precision_recall_curve(
        y_val, y_val_proba, figures_dir / "precision_recall_curve.png"
    )
    roc_curve_path = plot_roc_curve(
        y_val, y_val_proba, figures_dir / "roc_curve.png"
    )

    return {
        "precision_recall_curve": Path(pr_curve_path),
        "roc_curve": Path(roc_curve_path),
    }


def generate_confusion_matrix_outputs(
    y_val: pd.Series,
    y_val_proba: np.ndarray,
    selected_thresholds: Dict[str, Dict[str, Any]],
    figures_dir: Path,
) -> Dict[str, Path]:
    """Generate and save confusion matrix plots for the selected thresholds.

    Args:
        y_val: Validation ground-truth labels.
        y_val_proba: Validation fraud probabilities.
        selected_thresholds: Output of select_operating_thresholds.
        figures_dir: Directory in which to save confusion matrix PNGs.

    Returns:
        Dictionary mapping each threshold name to its saved Path object.
    """
    filename_map = {
        "default": "confusion_matrix_default_threshold.png",
        "best_f1": "confusion_matrix_best_f1_threshold.png",
        "recall_target": "confusion_matrix_recall_target_threshold.png",
    }
    title_map = {
        "default": "Confusion Matrix (Default Threshold = 0.50)",
        "best_f1": "Confusion Matrix (Best F1 Threshold)",
        "recall_target": "Confusion Matrix (Recall-Target Threshold)",
    }

    saved_paths: Dict[str, Path] = {}
    for name, metrics in selected_thresholds.items():
        output_path = figures_dir / filename_map[name]
        saved_path = plot_confusion_matrix(
            y_val,
            y_val_proba,
            threshold=metrics["threshold"],
            output_path=output_path,
            title=title_map.get(name),
        )
        saved_paths[name] = Path(saved_path)

    return saved_paths


def _format_metrics_block(title: str, metrics: Dict[str, Any]) -> str:
    """Format a single threshold's metrics as a Markdown sub-section.

    Args:
        title: Sub-section title.
        metrics: Metrics dictionary for a single threshold.

    Returns:
        Markdown-formatted string describing the threshold metrics.
    """
    lines = [
        f"### {title}",
        "",
        f"- Threshold: {metrics['threshold']:.2f}",
        f"- Precision: {metrics['precision']:.4f}",
        f"- Recall: {metrics['recall']:.4f}",
        f"- F1-score: {metrics['f1']:.4f}",
        f"- True Positives (fraud caught): {metrics['tp']}",
        f"- False Positives (false alerts): {metrics['fp']}",
        f"- False Negatives (fraud missed): {metrics['fn']}",
        f"- True Negatives: {metrics['tn']}",
        "",
    ]
    return "\n".join(lines)


def build_day6_threshold_tuning_report(
    model_name: str,
    validation_rows: int,
    validation_frauds: int,
    selected_thresholds: Dict[str, Dict[str, Any]],
    min_recall: float,
    generated_at: str | None = None,
) -> str:
    """Build the Day 6 Markdown threshold tuning report.

    Args:
        model_name: Name of the champion model being analyzed.
        validation_rows: Number of rows in the validation set.
        validation_frauds: Number of fraud cases in the validation set.
        selected_thresholds: Output of select_operating_thresholds.

    Returns:
        Complete Markdown report content as a string.
    """
    generated_at = generated_at or "omitted for deterministic evidence; see run manifest"
    recall_target = selected_thresholds["recall_target"]

    sections = [
        "# Day 6 Threshold Tuning Report: Credit Card Fraud Detection",
        "",
        f"**Generated:** {generated_at}",
        f"**Model:** {model_name}",
        "",
        "## Validation Dataset",
        "",
        f"- Validation rows: {validation_rows}",
        f"- Validation fraud cases: {validation_frauds}",
        "",
        "## Why Threshold Tuning Matters",
        "",
        f"The configured default classification threshold of {DEFAULT_THRESHOLD:.2f} "
        "is rarely optimal for "
        "highly imbalanced fraud detection problems. Lowering the threshold "
        "tends to catch more fraud (higher recall) at the cost of more false "
        "alerts (lower precision). Raising the threshold reduces false alerts "
        "but risks missing more fraud. Accuracy is not used to choose a "
        "threshold here because the fraud class is rare; precision, recall, "
        "F1-score, and the confusion matrix are far more informative.",
        "",
        f"## Default Threshold ({DEFAULT_THRESHOLD:.2f})",
        "",
        _format_metrics_block("Default Threshold Performance", selected_thresholds["default"]),
        "## Best F1 Threshold",
        "",
        _format_metrics_block("Best F1 Threshold Performance", selected_thresholds["best_f1"]),
        f"## Recall-Target Threshold (recall >= {min_recall:.2f})",
        "",
        _format_metrics_block(
            "Recall-Target Threshold Performance", selected_thresholds["recall_target"]
        ),
        "## Development Operating Point",
        "",
        f"The development recall-target operating point is **{recall_target['threshold']:.2f}**. "
        f"It has the highest observed precision among sweep points with recall >= {min_recall:.2f}. "
        "This point estimate is not a business policy: false-positive, review, loss, "
        "recovery, capacity, and uncertainty assumptions must be reviewed before use.",
        "",
        "## Generated Artifacts",
        "",
        "- reports/threshold_tuning/threshold_metrics.csv",
        "- reports/threshold_tuning/selected_thresholds.json",
        "- reports/figures/precision_recall_curve.png",
        "- reports/figures/roc_curve.png",
        "- reports/figures/confusion_matrix_default_threshold.png",
        "- reports/figures/confusion_matrix_best_f1_threshold.png",
        "- reports/figures/confusion_matrix_recall_target_threshold.png",
        "",
        "## Note on Data Usage",
        "",
        "Only the validation set was used for this analysis. The repository's "
        "historical random holdout has already been observed and is not loaded "
        "or reused by this development command.",
        "",
    ]
    return "\n".join(sections)


def save_day6_threshold_tuning_report(report_content: str, report_path: Path) -> Path:
    """Save the Day 6 Markdown report to disk.

    Args:
        report_content: Markdown report content.
        report_path: Destination file path. Parent directories are
            created if missing.

    Returns:
        Path to the saved report file.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content, encoding="utf-8")
    return report_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Day 6 runner.

    Returns:
        Parsed argparse.Namespace with configurable paths and options.
    """
    parser = argparse.ArgumentParser(
        description="Day 6: validation-only threshold tuning and curve analysis."
    )
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--threshold-dir", type=Path, default=DEFAULT_THRESHOLD_DIR)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--min-recall", type=float, default=DEFAULT_MIN_RECALL)
    return parser.parse_args()


def run_day6_threshold_tuning(
    model_path: Path = DEFAULT_MODEL_PATH,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    threshold_dir: Path = DEFAULT_THRESHOLD_DIR,
    figures_dir: Path = DEFAULT_FIGURES_DIR,
    report_path: Path = DEFAULT_REPORT_PATH,
    min_recall: float = DEFAULT_MIN_RECALL,
) -> Dict[str, Any]:
    """Run the complete Day 6 threshold tuning and curve analysis pipeline.

    Args:
        model_path: Path to the Day 5 champion model artifact.
        processed_dir: Directory containing Day 3 processed parquet files.
        threshold_dir: Directory in which to save threshold tuning outputs.
        figures_dir: Directory in which to save curve and confusion matrix
            figures.
        report_path: Destination path for the Markdown report.
        min_recall: Minimum recall required for the recall-target threshold.

    Returns:
        Dictionary summarizing the pipeline results and output paths.
    """
    print("Day 6 Threshold Tuning Started")

    model = load_champion_model(model_path)
    model_name = model_path.stem
    print(f"Loaded model: {model_path}")

    x_val, y_val = load_validation_data(processed_dir)
    print(f"Loaded validation rows: {len(x_val)}")

    y_val_proba = generate_validation_probabilities(model, x_val)
    print("Generated validation probabilities")

    threshold_table = build_threshold_metrics_table(y_val, y_val_proba)

    selected_thresholds = select_operating_thresholds(
        y_val, y_val_proba, threshold_table, min_recall=min_recall
    )

    threshold_output_paths = save_threshold_outputs(
        threshold_table, selected_thresholds, threshold_dir
    )
    print("Saved threshold metrics")

    curve_paths = generate_curve_outputs(y_val, y_val_proba, figures_dir)
    print("Saved PR curve")
    print("Saved ROC curve")

    confusion_matrix_paths = generate_confusion_matrix_outputs(
        y_val, y_val_proba, selected_thresholds, figures_dir
    )
    print("Saved confusion matrices")

    report_content = build_day6_threshold_tuning_report(
        model_name=model_name,
        validation_rows=len(y_val),
        validation_frauds=int(y_val.sum()),
        selected_thresholds=selected_thresholds,
        min_recall=min_recall,
    )
    saved_report_path = save_day6_threshold_tuning_report(report_content, report_path)
    print("Saved Day 6 threshold report")

    print("Day 6 Threshold Tuning Completed")

    return {
        "model_name": model_name,
        "validation_rows": len(y_val),
        "validation_frauds": int(y_val.sum()),
        "selected_thresholds": selected_thresholds,
        "threshold_output_paths": threshold_output_paths,
        "curve_paths": curve_paths,
        "confusion_matrix_paths": confusion_matrix_paths,
        "report_path": saved_report_path,
    }


def print_success_message(results: Dict[str, Any]) -> None:
    """Print a clean summary of the Day 6 pipeline results.

    Args:
        results: Dictionary returned by run_day6_threshold_tuning.
    """
    print("\nDay 6 threshold tuning completed successfully.")
    print(f"Model: {results['model_name']}")
    print(f"Validation rows: {results['validation_rows']}")
    print(f"Validation fraud cases: {results['validation_frauds']}")
    print(f"Report saved to: {results['report_path']}")
    print("Note: the test set was not loaded or used at any point.")


def main() -> None:
    """Parse arguments, run the Day 6 pipeline, and handle errors."""
    print(
        "Direct unmanifested execution is disabled. Use "
        "`python scripts/run_reference_stage.py --stage day6 --output-dir <new-dir>`. ",
        file=sys.stderr,
    )
    raise SystemExit(2)

    args = parse_args()
    try:
        results = run_day6_threshold_tuning(
            model_path=args.model_path,
            processed_dir=args.processed_dir,
            threshold_dir=args.threshold_dir,
            figures_dir=args.figures_dir,
            report_path=args.report_path,
            min_recall=args.min_recall,
        )
        print_success_message(results)
    except FileNotFoundError as error:
        print(f"File not found error: {error}")
        sys.exit(1)
    except ValueError as error:
        print(f"Value error: {error}")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001
        print(f"Unexpected error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
